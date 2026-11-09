#!/usr/bin/env python3
"""Guards the cold-start promise: a fresh clone can run examples/reference_extractor_py.py
on a Python target and get a REAL reachability graph — including the cross-file,
cross-function direct-call chain the regex tier under-connects (L1).

Pure stdlib. Run: python3 -m unittest discover -s tests
"""
import os, sys, sqlite3, subprocess, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXTRACTOR = os.path.join(ROOT, 'examples', 'reference_extractor_py.py')
GRAPHQUERY = os.path.join(ROOT, 'toolkit', 'graphquery')
SCHEMA = os.path.join(ROOT, 'docs', 'SCHEMA.sql')

WEB = '''\
from flask import Flask, request
from svc import handle
app = Flask(__name__)

@app.route("/run", methods=["POST"])
def run_endpoint():
    return handle(request.form["cmd"])
'''
SVC = '''\
import os, importlib
def handle(cmd):
    return do_exec(cmd)
def do_exec(cmd):
    os.system(cmd)
def dyn(name):
    importlib.import_module(name)
    return eval(name)
'''


class ReferenceExtractorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, 'app'); os.makedirs(self.src)
        with open(os.path.join(self.src, 'web.py'), 'w') as f: f.write(WEB)
        with open(os.path.join(self.src, 'svc.py'), 'w') as f: f.write(SVC)
        self.db = os.path.join(self.tmp, 'g.db')
        con = sqlite3.connect(self.db)
        with open(SCHEMA) as f:
            con.executescript(f.read())
        con.commit(); con.close()
        sql = subprocess.run([sys.executable, EXTRACTOR, self.src],
                             capture_output=True, text=True).stdout
        con = sqlite3.connect(self.db); con.executescript(sql); con.commit(); con.close()

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def _count(self, table):
        con = sqlite3.connect(self.db); n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        con.close(); return n

    def _gq(self, *args):
        return subprocess.run([sys.executable, GRAPHQUERY, '--db', self.db, *args],
                              capture_output=True, text=True).stdout

    def test_graph_populated(self):
        self.assertGreaterEqual(self._count('source'), 1)   # the Flask route
        self.assertGreaterEqual(self._count('sink'), 2)     # os.system + eval
        self.assertGreaterEqual(self._count('boundary'), 1) # importlib dynamic dispatch

    def test_route_detected_as_source(self):
        con = sqlite3.connect(self.db)
        detail = con.execute("SELECT detail FROM source").fetchone()[0]; con.close()
        self.assertEqual(detail, 'POST /run')

    def test_cross_file_chain_resolves_static_exact(self):
        # the L1-hard part: route -> handle (imported) -> do_exec (same module) -> os.system
        out = self._gq('trace-back', 'cmdi')
        self.assertIn('REACHABLE from 1 source(s)', out)
        self.assertIn('POST /run', out)
        for step in ('web.run_endpoint', 'svc.handle', 'svc.do_exec'):
            self.assertIn(step, out)
        self.assertIn('static-exact', out)

    def test_eval_is_sink_not_boundary(self):
        con = sqlite3.connect(self.db)
        cats = {r[0] for r in con.execute("SELECT category FROM sink")}
        breasons = {r[0] for r in con.execute("SELECT reason FROM boundary")}; con.close()
        self.assertIn('code', cats)                      # eval -> code sink
        self.assertTrue(all('import' in r or 'dispatch' in r for r in breasons))


if __name__ == '__main__':
    unittest.main(verbosity=2)
