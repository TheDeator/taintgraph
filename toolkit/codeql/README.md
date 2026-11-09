# CodeQL tier

> `build-codeql-cs.sh` / `build-codeql-graph.sh` and `callgraph.ql` are
> build-it-yourself (not shipped); `examples/build-graph-template.sh` shows the
> pattern. The SARIF/CSV importers (`../import_findings.py`, `../import_codeql_graph.py`)
> ARE shipped.

`build-codeql-cs.sh` runs CodeQL's standard C# security suite and imports the
SARIF into the graph's `finding` table (same store, higher trust — precedence
§6.5). Needs the project to compile (or `CODEQL_BUILD_MODE=none`, lower fidelity).
CodeQL supports C#/Java/Python — **not PHP** (semgrep carries PHP).

## Known gap to contribute: MediatR (and CQRS mediators)
Out of the box CodeQL does NOT connect `_mediator.Send(cmd)` to the matching
`IRequestHandler<cmd,>.Handle` — the same type-bound edge our `mediatr_cs`
extractor models. The high-value reusable asset here is an **additional taint
step** (QL) or a Models-as-Data summary that propagates taint from the command
object's properties into the handler's request parameter. This is documented as
an open contribution in `docs/LIMITATIONS.md`; implement + test it with the
CodeQL CLI before claiming it works (do not ship untested QL).

## Call-graph export (closes L1)
Beyond findings, CodeQL's type-resolved call graph can be exported into the SAME
schema as high-fidelity edges — the fix for L1 (the regex tier cannot resolve
receiver types, so deep direct-call chains under-connect).
```
# after a CodeQL DB exists (build-codeql-cs.sh leaves one, or create your own):
toolkit/build-codeql-graph.sh <CODEQL_DB> graph.db
# -> runs codeql/callgraph.ql, imports edges with provenance=codeql,
#    queryable by the cheap graphquery (callers/callees/trace-back) as usual.
```
The agent still queries the fast graph; CodeQL is the precompute backend. Edges
are tagged `provenance=codeql` so they rank above regex-tier edges (§6.5).
