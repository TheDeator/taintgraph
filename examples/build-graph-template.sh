#!/usr/bin/env bash
# TEMPLATE orchestrator — adapt per language. The real build-*.sh are not shipped;
# this shows the pipeline shape. Extractors are YOURS to build (docs/EXTRACTORS.md);
# graphquery + the importers ARE shipped (toolkit/).
#
# Usage: build-graph-template.sh SRC [graph.db]
set -euo pipefail
SRC="${1:?usage: build-graph-template.sh SRC [DB]}"; DB="${2:-graph.db}"
HERE="$(cd "$(dirname "$0")" && pwd)"            # adjust paths to your layout
EXTR="$HERE/../toolkit/extractors"               # where your _<lang> extractors live
SINKS="$HERE/../toolkit/sinks/<lang>.txt"        # your sink catalog

# 1) bootstrap the schema (REQUIRED first step)
rm -f "$DB"
sqlite3 "$DB" < "$HERE/../docs/SCHEMA.sql"

# 2) run each extractor you built — each emits SQL on stdout, piped into the DB.
#    Order is free (idempotent via INSERT OR IGNORE). Typical set:
for e in routes_<lang> <virtual_edge>_<lang> calls_direct_<lang>; do
  echo "[*] $e" >&2
  python3 "$EXTR/$e.py" "$SRC" | sqlite3 "$DB"
done

# 3) load the sink catalog (marks methods that call a dangerous API as sinks)
python3 "$EXTR/load_sinks_<lang>.py" "$SINKS" "$SRC" | sqlite3 "$DB"

# 4) (optional) high-fidelity tiers — import engine results into the same DB:
#    semgrep: semgrep --config ... --json SRC | python3 toolkit/import_findings.py semgrep - ...
#    CodeQL : codeql ... ; python3 toolkit/import_codeql_graph.py callgraph.csv | sqlite3 "$DB"

sqlite3 "$DB" "SELECT 'nodes',COUNT(*) FROM node UNION ALL SELECT 'edges',COUNT(*) FROM edge \
UNION ALL SELECT 'sources',COUNT(*) FROM source UNION ALL SELECT 'sinks',COUNT(*) FROM sink;"
# then query:  toolkit/graphquery --db "$DB" trace-back <sink>
