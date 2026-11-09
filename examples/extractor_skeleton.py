#!/usr/bin/env python3
"""TEMPLATE extractor — see docs/EXTRACTORS.md for the full contract.

Name real ones <function>_<lang>.py (lang in cs|java|php|py). Emit SQL on stdout,
piped into the graph:  python <this> SRC | sqlite3 graph.db

Contract (summary):
  - reference nodes by NATURAL KEY (e.g. Namespace.Class.Method); never allocate ids
  - INSERT OR IGNORE every node you reference (self-sufficient, any run order)
  - every edge carries provenance: static-exact | static-candidate | model-inferred
  - resolve statically OR flag a boundary — never fabricate an edge
  - over-connect rather than under-connect (safe direction for not-missing)
"""
import os, sys

def q(x):
    if x is None: return 'NULL'
    return "'" + str(x).replace("'", "''") + "'"

def iter_methods(source_text):
    """TODO: language-specific. Yield dicts with at least:
       {'key': 'Ns.Class.Method', 'name': 'Method', 'line': 10, 'body': '...'}
    Use the language's parser (C#: a regex/Roslyn pass; Python: stdlib `ast`;
    Java: tree-sitter/JavaParser). Strip comments/strings first so you don't match
    inside them."""
    return []  # placeholder

def main(root):
    print("BEGIN;")
    for dp, _, fs in os.walk(root):
        for f in fs:
            # if not f.endswith('.<ext>'): continue
            try: s = open(os.path.join(dp, f), encoding='utf-8', errors='ignore').read()
            except OSError: continue
            rel = os.path.relpath(os.path.join(dp, f), root)
            for m in iter_methods(s):
                ck = m['key']
                print(f"INSERT OR IGNORE INTO node(key,kind,name,file,line) "
                      f"VALUES({q(ck)},'method',{q(m['name'])},{q(rel)},{m['line']});")
                # --- EDGE example (a direct call) ---
                # print("INSERT INTO edge(src,dst,mechanism,provenance,file,line) "
                #       f"VALUES({q(ck)},{q(callee_key)},'direct','static-exact',{q(rel)},{m['line']});")
                # --- SOURCE example (an HTTP entry point) ---
                # print(f"INSERT INTO source(node,kind,detail) VALUES({q(ck)},'route',{q('POST /x')});")
                # --- SINK example (method calls a dangerous API) ---
                # print(f"INSERT INTO sink(node,category,api) VALUES({q(ck)},'sqli','ExecuteSqlRaw');")
                # --- BOUNDARY example (dynamic dispatch the graph can't resolve) ---
                # print(f"INSERT INTO boundary(node,reason,file,line) "
                #       f"VALUES({q(ck)},'reflection:Activator',{q(rel)},{m['line']});")
    print("COMMIT;")

if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit("usage: extractor_skeleton.py SRC")
    main(sys.argv[1])
