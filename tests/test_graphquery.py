#!/usr/bin/env python3
"""Unit tests for toolkit/graphquery — the deterministic query engine.

These guard the properties the methodology leans on:
  - backward reachability enumerates sources; a disconnected sink reports NO path
    WITH the "not proof of safety" disclaimer (golden rule);
  - the overlay is ENFORCED in traversal (refute prunes, add injects manual-verified);
  - boundaries are reported as a flag, never silently swallowed;
  - meet-in-the-middle returns junction nodes iff a static path exists;
  - trace-fwd 'all' never SILENTLY truncates (the §G regression: old code did
    starts[:50] / hit[:5] with no seed and no announcement).

Pure stdlib (unittest + subprocess); no third-party deps. Run: python3 -m unittest
discover -s tests   (or: python3 tests/test_graphquery.py)
"""
import os, sys, sqlite3, subprocess, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GRAPHQUERY = os.path.join(ROOT, 'toolkit', 'graphquery')
SCHEMA = os.path.join(ROOT, 'docs', 'SCHEMA.sql')


def build_db(path, nodes=(), edges=(), sources=(), sinks=(), boundaries=()):
    con = sqlite3.connect(path); cur = con.cursor()
    with open(SCHEMA) as f:
        cur.executescript(f.read())
    for key, kind, name in nodes:
        cur.execute("INSERT INTO node(key,kind,name) VALUES(?,?,?)", (key, kind, name))
    for src, dst, mech, prov in edges:
        cur.execute("INSERT INTO edge(src,dst,mechanism,provenance) VALUES(?,?,?,?)",
                    (src, dst, mech, prov))
    for node, kind, detail in sources:
        cur.execute("INSERT INTO source(node,kind,detail) VALUES(?,?,?)", (node, kind, detail))
    for node, cat, api in sinks:
        cur.execute("INSERT INTO sink(node,category,api) VALUES(?,?,?)", (node, cat, api))
    for node, reason in boundaries:
        cur.execute("INSERT INTO boundary(node,reason) VALUES(?,?)", (node, reason))
    con.commit(); con.close()


def run(db, *args):
    r = subprocess.run([sys.executable, GRAPHQUERY, '--db', db, *args],
                       capture_output=True, text=True)
    return r.stdout + r.stderr


class GraphQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, 'g.db')

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    # --- a simple source -> mid -> sink chain, reused by several tests ---
    def _chain(self):
        build_db(self.db,
            nodes=[('Web.Ctrl.Act', 'controller', 'Act'),
                   ('App.Svc.Do', 'method', 'Do'),
                   ('Data.Repo.Run', 'method', 'Run')],
            edges=[('Web.Ctrl.Act', 'App.Svc.Do', 'direct', 'static-exact'),
                   ('App.Svc.Do', 'Data.Repo.Run', 'direct', 'static-exact')],
            sources=[('Web.Ctrl.Act', 'route', 'POST /act')],
            sinks=[('Data.Repo.Run', 'sqli', 'ExecuteSqlRaw')])

    def test_trace_back_reaches_source(self):
        self._chain()
        out = run(self.db, 'trace-back', 'Run')
        self.assertIn('REACHABLE from 1 source(s)', out)
        self.assertIn('POST /act', out)
        self.assertIn('App.Svc.Do', out)      # the chain is printed

    def test_trace_back_no_path_keeps_safety_disclaimer(self):
        # sink with no incoming edge at all -> no source, but MUST NOT imply "safe"
        build_db(self.db,
            nodes=[('Lonely.Repo.Run', 'method', 'Run')],
            sinks=[('Lonely.Repo.Run', 'sqli', 'ExecuteSqlRaw')])
        out = run(self.db, 'trace-back', 'Run')
        self.assertIn('NO STATIC PATH', out)
        self.assertIn('NOT proof of safety', out)   # golden rule stays visible

    def test_trace_fwd_finds_sink(self):
        self._chain()
        out = run(self.db, 'trace-fwd', 'Act')
        self.assertIn('-> SINK Data.Repo.Run', out)

    def test_trace_fwd_all_does_not_silently_truncate(self):
        # 60 independent source->sink pairs (> old hidden cap of 50, > default budget 12).
        # REGRESSION: old code did starts[:50] with no announcement -> sinks 51..60 vanished.
        nodes, edges, sources, sinks = [], [], [], []
        for i in range(60):
            s, k = f'S{i}.Ctrl.Act', f'S{i}.Repo.Sink'
            nodes += [(s, 'controller', 'Act'), (k, 'method', 'Sink')]
            edges += [(s, k, 'direct', 'static-exact')]
            sources += [(s, 'route', f'GET /s{i}')]
            sinks += [(k, 'ssrf', 'HttpClient')]
        build_db(self.db, nodes=nodes, edges=edges, sources=sources, sinks=sinks)
        out = run(self.db, 'trace-fwd', 'all')
        # every one of the 60 reachable sinks must appear ...
        self.assertEqual(out.count('-> SINK'), 60)
        # ... and the fact that it analysed ALL of them is announced, not silent
        self.assertIn('no silent cap', out)

    def test_trace_fwd_all_seeded_caps_and_announces(self):
        nodes, edges, sources, sinks = [], [], [], []
        for i in range(60):
            s, k = f'S{i}.Ctrl.Act', f'S{i}.Repo.Sink'
            nodes += [(s, 'controller', 'Act'), (k, 'method', 'Sink')]
            edges += [(s, k, 'direct', 'static-exact')]
            sources += [(s, 'route', f'GET /s{i}')]
            sinks += [(k, 'ssrf', 'HttpClient')]
        build_db(self.db, nodes=nodes, edges=edges, sources=sources, sinks=sinks)
        out = run(self.db, 'trace-fwd', 'all', '--seed', '7', '--explore-budget', '5')
        self.assertIn('seeded sample: seed=7', out)     # §G: announced + reproducible
        self.assertLessEqual(out.count('-> SINK'), 5)   # capped to the budget

    def test_overlay_refute_prunes_edge(self):
        self._chain()
        # refute the mid->sink edge: trace-back must now find NO path
        run(self.db, 'annotate-refute', 'App.Svc.Do', 'Data.Repo.Run',
            '--reason', 'guarded by allowlist', '--author', 'test')
        out = run(self.db, 'trace-back', 'Run')
        self.assertIn('NO STATIC PATH', out)
        self.assertNotIn('POST /act', out)

    def test_overlay_add_injects_manual_verified_edge(self):
        # two disconnected halves; add the bridging edge via the overlay
        build_db(self.db,
            nodes=[('Web.Ctrl.Act', 'controller', 'Act'), ('Data.Repo.Run', 'method', 'Run')],
            sources=[('Web.Ctrl.Act', 'route', 'POST /act')],
            sinks=[('Data.Repo.Run', 'sqli', 'ExecuteSqlRaw')])
        before = run(self.db, 'trace-back', 'Run')
        self.assertIn('NO STATIC PATH', before)
        run(self.db, 'annotate-add', 'Web.Ctrl.Act', 'Data.Repo.Run',
            '--reason', 'reflection dispatch confirmed by hand', '--author', 'test')
        after = run(self.db, 'trace-back', 'Run')
        self.assertIn('REACHABLE from 1 source(s)', after)
        self.assertIn('manual-verified', after)   # provenance of injected edge

    def test_boundary_reported_as_flag_not_swallowed(self):
        # sink's only predecessor is a boundary node (unmodelled dispatch) with no preds
        build_db(self.db,
            nodes=[('Edge.Dispatcher', 'external', 'Dispatcher'),
                   ('Data.Repo.Run', 'method', 'Run')],
            edges=[('Edge.Dispatcher', 'Data.Repo.Run', 'reflection', 'static-candidate')],
            sinks=[('Data.Repo.Run', 'sqli', 'ExecuteSqlRaw')],
            boundaries=[('Edge.Dispatcher', 'reflection')])
        out = run(self.db, 'why-unreachable', 'Run')
        self.assertIn('boundary', out)        # the stop is surfaced, with its reason
        self.assertIn('reflection', out)

    def test_meet_nonempty_when_path_exists(self):
        self._chain()
        out = run(self.db, 'meet', 'Run', 'Act')
        self.assertIn('a static path EXISTS', out)
        for n in ('Web.Ctrl.Act', 'App.Svc.Do', 'Data.Repo.Run'):
            self.assertIn(n, out)

    def test_meet_empty_when_disconnected(self):
        build_db(self.db,
            nodes=[('Web.Ctrl.Act', 'controller', 'Act'), ('Data.Repo.Run', 'method', 'Run')],
            sources=[('Web.Ctrl.Act', 'route', 'POST /act')],
            sinks=[('Data.Repo.Run', 'sqli', 'ExecuteSqlRaw')])
        out = run(self.db, 'meet', 'Run', 'Act')
        self.assertIn('NO STATIC MEET', out)
        self.assertIn('NOT proof of safety', out)   # same discipline as trace-back


if __name__ == '__main__':
    unittest.main(verbosity=2)
