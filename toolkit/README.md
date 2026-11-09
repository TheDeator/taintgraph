# toolkit/ — engine + your assets

What is PUBLIC and runnable here:
- `graphquery` — the query CLI (callers/callees/trace-back/trace-fwd/meet/
  why-unreachable/cve-check/findings/explore/annotate-add/annotate-refute/overrides).
- `import_findings.py` — semgrep JSON / CodeQL SARIF -> the `finding` table.
- `import_codeql_graph.py` — CodeQL call-graph CSV -> high-fidelity `codeql` edges.
- `codeql/README.md` — how the CodeQL tier plugs in.

What is BUILD-IT-YOURSELF and NOT in this repo (operational / offensive / tunable):
- `extractors/*_<lang>.py` — one per dispatch mechanism; emit SQL on stdout. Build
  from `../docs/EXTRACTORS.md`, starting at `../examples/extractor_skeleton.py`.
  (So `toolkit/extractors/` is empty on a fresh clone — expected.)
- `sinks/<lang>.txt` — dangerous-API catalogs (`category:api` per line). Format
  sample: `../examples/sinks_sample.txt`.
- `semgrep-rules/` — your taint rules (semgrep covers PHP, which CodeQL cannot).
- `build-graph-*.sh` — orchestration; pattern in `../examples/build-graph-template.sh`.

Carry your built extractors/catalogs/rules between engagements; harvest
improvements (new extractor, new sink, new rule, new boundary type) as you go.