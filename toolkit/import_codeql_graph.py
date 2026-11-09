#!/usr/bin/env python3
"""Import a CodeQL call-graph CSV (from `codeql bqrs decode --format=csv`) into
the graph as high-fidelity edges (provenance=codeql). This is the L1 fix: precise,
type-resolved call edges the regex tier cannot produce, in the SAME schema, queried
by the SAME cheap graphquery. Consumes tool output -> language-agnostic.
Usage: import_codeql_graph.py callgraph.csv | sqlite3 graph.db
"""
import sys, csv

def q(x):
    if x is None: return 'NULL'
    return "'" + str(x).replace("'", "''") + "'"

def main(path):
    r = csv.reader(open(path, encoding='utf-8', errors='ignore'))
    rows = list(r)
    if rows and rows[0] and rows[0][0].lower() in ('src', '"src"', 'col0'):
        rows = rows[1:]  # drop header
    print("BEGIN;")
    for row in rows:
        if len(row) < 2: continue
        src, dst = row[0].strip(), row[1].strip()
        file = row[2].strip() if len(row) > 2 else None
        line = row[3].strip() if len(row) > 3 else None
        if not src or not dst: continue
        for k in (src, dst):
            print(f"INSERT OR IGNORE INTO node(key,kind,name) VALUES({q(k)},'method',{q(k.rsplit('.',1)[-1])});")
        lv = line if (line and line.isdigit()) else 'NULL'
        print("INSERT INTO edge(src,dst,mechanism,provenance,file,line) "
              f"VALUES({q(src)},{q(dst)},'call','codeql',{q(file)},{lv});")
    print("COMMIT;")

if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit("usage: import_codeql_graph.py callgraph.csv")
    main(sys.argv[1])
