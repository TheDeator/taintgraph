#!/usr/bin/env python3
"""Import CodeQL (SARIF) or semgrep (JSON) results into the `finding` table, so
engine output lives in the same store and outranks the regex graph (precedence
WORKFLOW.md §6.5). Consumes TOOL OUTPUT, not source -> language-agnostic (no _lang).
Usage:
  import_findings.py semgrep results.json [--src SRC --lang cs|java] | sqlite3 graph.db
  import_findings.py sarif   results.sarif [--src SRC --lang cs|java] | sqlite3 graph.db
--src/--lang (optional): resolve each finding to its enclosing method node.
Reads tool output as data (run with -I).
"""
import sys, os, json

def q(x):
    if x is None: return 'NULL'
    return "'" + str(x).replace("'", "''") + "'"

def load_parser(lang):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extractors'))
    return __import__('parse_' + lang)

def resolve(parser, src, path, line):
    if not (parser and src and line): return None
    fp = path if os.path.isabs(path) else os.path.join(src, path)
    if not os.path.exists(fp):
        for dp, _, fs in os.walk(src):
            if os.path.basename(path) in fs: fp = os.path.join(dp, os.path.basename(path)); break
    try: s = open(fp, encoding='utf-8', errors='ignore').read()
    except OSError: return None
    sc = parser.scrub(s)
    for m in parser.iter_methods(sc):
        if m['line'] <= line <= m.get('end_line', m['line']): return m['key']
    return None

def rows_semgrep(data):
    for r in data.get('results', []):
        loc = r.get('end') or r.get('start') or {}
        yield ('semgrep', r.get('check_id', '').split('.')[-1],
               (r.get('extra') or {}).get('severity', ''),
               r.get('path', ''), (r.get('start') or {}).get('line'),
               (r.get('extra') or {}).get('message', ''))

def rows_sarif(data):
    for run in data.get('runs', []):
        tool = (((run.get('tool') or {}).get('driver') or {}).get('name') or 'codeql')
        for r in run.get('results', []):
            msg = (r.get('message') or {}).get('text', '')
            rule = r.get('ruleId', '')
            sev = r.get('level', '')
            locs = r.get('locations') or []
            if not locs: 
                yield (tool.lower(), rule, sev, '', None, msg); continue
            pl = (locs[0].get('physicalLocation') or {})
            uri = ((pl.get('artifactLocation') or {}).get('uri') or '')
            line = (pl.get('region') or {}).get('startLine')
            yield (tool.lower(), rule, sev, uri, line, msg)

def main(argv):
    if len(argv) < 2: sys.exit(__doc__)
    kind, path = argv[0], argv[1]
    src = lang = None
    for i, a in enumerate(argv):
        if a == '--src': src = argv[i+1]
        if a == '--lang': lang = argv[i+1]
    parser = load_parser(lang) if lang else None
    data = json.load(open(path, encoding='utf-8', errors='ignore'))
    rows = rows_semgrep(data) if kind == 'semgrep' else rows_sarif(data)
    print("BEGIN;")
    print("CREATE TABLE IF NOT EXISTS finding(tool TEXT,rule TEXT,severity TEXT,"
          "file TEXT,line INTEGER,message TEXT,node TEXT,provenance TEXT);")
    for tool, rule, sev, f, line, msg in rows:
        node = resolve(parser, src, f, line)
        if node:
            print(f"INSERT OR IGNORE INTO node(key,kind,name) VALUES({q(node)},'method',{q(node.rsplit('.',1)[-1])});")
        print("INSERT INTO finding(tool,rule,severity,file,line,message,node,provenance) "
              f"VALUES({q(tool)},{q(rule)},{q(sev)},{q(f)},{'NULL' if line is None else line},{q(msg)},{q(node)},{q(tool)});")
    print("COMMIT;")

if __name__ == '__main__':
    main(sys.argv[1:])
