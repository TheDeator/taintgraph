# examples/

The **tuned** engine (the per-language `_<lang>` extractors, sink catalogs and taint
rules) is **not shipped** by design — it is operational, tunable, offensive tooling.
What IS public is the **methodology** (see `../docs/`), the shared query layer
(`../toolkit/graphquery`), and the files here — including ONE real, runnable reference
extractor so a fresh clone starts from a working pipeline, not a blank page.

- `reference_extractor_py.py` — a **real, runnable** reference extractor (stdlib
  `ast`, no deps). Run it on any Python tree and it emits the full contract
  (nodes, direct-call edges, Flask/FastAPI routes as sources, catalogued sinks,
  dynamic-dispatch boundaries) straight into the graph:
  `python3 reference_extractor_py.py SRC [sinks.txt] | sqlite3 graph.db`.
  It exists so a fresh clone is **not GIGO-from-zero** — you see the whole pipeline
  work (including cross-file direct-call chains the regex tier under-connects, L1)
  and have a concrete, honest pattern to copy for a tuned `_<lang>` extractor. Its
  limits mirror `../docs/LIMITATIONS.md` (name-based resolution, decorator-only routes).
- `extractor_skeleton.py` — a barer commented template following `../docs/EXTRACTORS.md`,
  for starting from an empty frame rather than the Python reference.
- `sinks_sample.txt` — the sink-catalog FORMAT (a few entries). Build your own
  full catalog per language and per engagement.
- `session_example.md` — what an end-to-end session looks like (anonymised).

Start at `../START_HERE.md`, read `../docs/EXTRACTORS.md` for the contract, then
implement the extractors you need.
