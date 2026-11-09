# examples/

The working engine (extractors, `graphquery`, sink catalogs, taint rules) is **not
shipped** in this repo by design — it is operational, tunable, offensive tooling.
What IS public is the **methodology** (see `../docs/`) and the illustrative files
here, so you can build your own engine against the plug-in contract.

- `extractor_skeleton.py` — a commented template following `../docs/EXTRACTORS.md`.
  Copy it, fill the language-specific parsing, and it emits rows the shared schema
  and query layer consume.
- `sinks_sample.txt` — the sink-catalog FORMAT (a few entries). Build your own
  full catalog per language and per engagement.
- `session_example.md` — what an end-to-end session looks like (anonymised).

Start at `../START_HERE.md`, read `../docs/EXTRACTORS.md` for the contract, then
implement the extractors you need.
