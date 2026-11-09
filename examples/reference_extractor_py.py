#!/usr/bin/env python3
"""reference_extractor_py.py — a REAL, runnable reference extractor (stdlib only).

Purpose: kill the cold-start / GIGO-from-zero problem. A fresh clone ships NO tuned
extractors (they are operational/private), so this is the public, working baseline you
can run on any Python source tree on day one, and the concrete pattern to copy when you
write a tuned `_<lang>` extractor. It parses with the stdlib `ast` (real resolution, not
regex), and emits the full node/edge/source/sink/boundary contract as SQL.

    python3 reference_extractor_py.py SRC [sinks.txt] | sqlite3 graph.db

What it does (honestly, within a single-file reference):
  - nodes: every def / async def, keyed  module.Class.func  (natural key, no ids)
  - edges: intra-project calls resolved by name -> static-exact (1 target) or
           static-candidate (name collision / cross-module). Over-connects rather than
           under-connects (the safe direction). Library/builtin calls are NOT faked.
  - sources: Flask/FastAPI-style route decorators (@app.route/get/post/…, @router.post)
  - sinks: any def whose body calls an api in the catalog (category:api lines)
  - boundary: dynamic dispatch it cannot resolve (getattr()(), eval/exec,
              importlib/__import__) — FLAGGED, never silently dropped

Limits (same honesty as docs/LIMITATIONS.md): name-based cross-module resolution (no
full type inference) -> L1/L2 apply; decorator-only routes (no urls.py); Django/async
frameworks partial. Good enough to run, triage, and demonstrate the contract.
"""
import ast, os, sys

DEFAULT_SINKS = [  # illustrative, python-oriented; tune/replace via the sinks.txt arg
    ('cmdi', 'os.system'), ('cmdi', 'subprocess.run'), ('cmdi', 'subprocess.Popen'),
    ('cmdi', 'subprocess.call'), ('code', 'eval'), ('code', 'exec'),
    ('deser', 'pickle.loads'), ('deser', 'yaml.load'), ('sqli', 'execute'),
    ('sqli', 'executescript'), ('ssrf', 'requests.get'), ('ssrf', 'requests.post'),
    ('ssrf', 'urlopen'), ('path', 'open'), ('ssti', 'render_template_string'),
]
ROUTE_ATTRS = {'route', 'get', 'post', 'put', 'delete', 'patch'}


def q(x):
    if x is None: return 'NULL'
    return "'" + str(x).replace("'", "''") + "'"


def module_key(rel):
    k = rel[:-3].replace(os.sep, '.')          # strip .py, path -> dotted
    if k.endswith('.__init__'): k = k[:-9]
    return k


def dotted(node):
    """Flatten an ast expression used as a call target into a dotted string, or None."""
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def direct_calls(fn):
    """Yield Call nodes lexically inside fn but NOT inside a nested def (those are
    their own nodes). Explicit bounded walk so we can prune at nested-def boundaries."""
    out, stack = [], list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue                            # don't descend into nested defs
        if isinstance(n, ast.Call):
            out.append(n)
        stack.extend(ast.iter_child_nodes(n))
    return out


def route_of(fn):
    """Return (VERB, path) list for Flask/FastAPI-style decorators, else []."""
    hits = []
    for d in fn.decorator_list:
        if not isinstance(d, ast.Call): continue
        attr = d.func.attr if isinstance(d.func, ast.Attribute) else None
        if attr not in ROUTE_ATTRS: continue
        path = None
        if d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str):
            path = d.args[0].value
        verbs = []
        if attr == 'route':
            for kw in d.keywords:
                if kw.arg == 'methods' and isinstance(kw.value, (ast.List, ast.Tuple)):
                    verbs = [e.value for e in kw.value.elts
                             if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            verbs = verbs or ['GET']
        else:
            verbs = [attr.upper()]
        for v in verbs: hits.append((v, path or '/'))
    return hits


class Collector(ast.NodeVisitor):
    """First pass: record every def's key; also index simple-name -> [keys]."""
    def __init__(self, modkey):
        self.modkey, self.cls, self.defs = modkey, [], []

    def visit_ClassDef(self, node):
        self.cls.append(node.name); self.generic_visit(node); self.cls.pop()

    def _def(self, node):
        key = '.'.join([self.modkey] + self.cls + [node.name])
        self.defs.append((key, node, list(self.cls)))
        self.cls.append('')               # mark: nested defs get a flat key, no false nesting
        self.generic_visit(node); self.cls.pop()

    visit_FunctionDef = _def
    visit_AsyncFunctionDef = _def


def main(root, sinks_file=None):
    sinks = list(DEFAULT_SINKS)
    if sinks_file and os.path.exists(sinks_file):
        sinks = []
        for ln in open(sinks_file, encoding='utf-8', errors='ignore'):
            ln = ln.split('#', 1)[0].strip()
            if ':' in ln: c, a = ln.split(':', 1); sinks.append((c.strip(), a.strip()))
    sink_by_suffix = {}                   # last segment -> [(cat, full)]
    for c, a in sinks: sink_by_suffix.setdefault(a.rsplit('.', 1)[-1], []).append((c, a))

    # pass 1: collect all defs across the tree (for cross-file name resolution)
    alldefs = []                           # (key, fn_node, classlist, rel)
    byname = {}                            # simple name -> [keys]
    for dp, _, fs in os.walk(root):
        for f in fs:
            if not f.endswith('.py'): continue
            p = os.path.join(dp, f); rel = os.path.relpath(p, root)
            try: tree = ast.parse(open(p, encoding='utf-8', errors='ignore').read(), filename=rel)
            except (OSError, SyntaxError): continue
            c = Collector(module_key(rel)); c.visit(tree)
            for key, node, cls in c.defs:
                alldefs.append((key, node, cls, rel))
                byname.setdefault(node.name, []).append(key)

    # pass 2: emit SQL
    print("BEGIN;")
    for key, fn, cls, rel in alldefs:
        is_route = route_of(fn)
        kind = 'controller' if is_route else 'method'
        print(f"INSERT OR IGNORE INTO node(key,kind,name,type,file,line) "
              f"VALUES({q(key)},{q(kind)},{q(fn.name)},{q('.'.join([module_key(rel)]+cls) or None)},"
              f"{q(rel)},{fn.lineno});")
        for verb, path in is_route:
            print(f"INSERT INTO source(node,kind,detail) VALUES({q(key)},'route',{q(verb+' '+path)});")

        seen_sink = set()
        for call in direct_calls(fn):
            chain = dotted(call.func)
            if not chain: continue
            leaf = chain.rsplit('.', 1)[-1]
            # --- sink? (api suffix match against the catalog) ---
            for cat, full in sink_by_suffix.get(leaf, []):
                if (chain == full or chain.endswith('.' + full) or full == leaf) and (cat, full) not in seen_sink:
                    print(f"INSERT INTO sink(node,category,api) VALUES({q(key)},{q(cat)},{q(full)});")
                    seen_sink.add((cat, full))
            # --- boundary: dynamic dispatch to an unknown target (NOT eval/exec: those
            #     are code-injection SINKS above, not an unresolved call edge) ---
            if leaf == '__import__' or chain in ('importlib.import_module', 'getattr'):
                print(f"INSERT INTO boundary(node,reason,file,line) "
                      f"VALUES({q(key)},'reflection:dynamic-dispatch',{q(rel)},{call.lineno});")
                continue
            # --- intra-project call edge, resolved by name ---
            targets = byname.get(leaf)
            if not targets: continue          # library/builtin/unresolved -> do NOT fabricate
            prov = 'static-exact' if len(targets) == 1 else 'static-candidate'
            for t in targets:
                if t == key: continue         # ignore trivial self-recursion edge
                print(f"INSERT INTO edge(src,dst,mechanism,provenance,file,line) "
                      f"VALUES({q(key)},{q(t)},'direct',{q(prov)},{q(rel)},{call.lineno});")
    print("COMMIT;")


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: reference_extractor_py.py SRC [sinks.txt]")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
