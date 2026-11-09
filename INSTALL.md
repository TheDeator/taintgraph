# Install & Quickstart

## Requirements

**Core (required) — no build of the target needed, zero Python packages:**
| tool | why | install |
|------|-----|---------|
| Python 3.8+ | extractors + `graphquery` (stdlib only) | system package |
| sqlite3     | the graph database | system package |

**Optional tiers — what each adds, and what you LOSE without it.**
The framework degrades gracefully: with only the core you still get the full
graph, bidirectional tracing, boundaries, overlay and SCA parsing. The optional
tools raise fidelity; their absence never breaks a run, it just narrows coverage.

| tool | install | you GAIN | WITHOUT it you lose |
|------|---------|----------|---------------------|
| ripgrep (`rg`) | system package | targeted manual verification (AGENT_NOTES §C) | fall back to grep/Read; §C verification is slower |
| **semgrep** | `pipx install semgrep` (or `python3 -m pip install --user semgrep`) | real taint findings, **incl. PHP** (CodeQL can't do PHP); run semgrep, then `import_findings.py` (shipped) → `graphquery findings` | **no high-fidelity taint, no PHP engine**; you stay on the regex tier, so L1/L2 (under-connection, over-merge — see docs/LIMITATIONS.md) apply in full and "not reachable" is weaker |
| CodeQL CLI | `gh extensions install github/gh-codeql`, or the release bundle | interprocedural, field-sensitive taint for **C#/Java/Python** (not PHP); CodeQL → SARIF → `import_findings.py` (shipped) → `graphquery findings` | **no engine-grade cross-check** to catch regex-tier false-negatives; relies on build-ability of the target |
| .NET SDK / JDK+Maven | system package | lets CodeQL compile & extract the target | CodeQL must use `--build-mode none` (lower type fidelity) or is unavailable |
| Trivy / Grype / `dotnet list --vulnerable` | per tool | populate the `vulnerable` flag for `cve-check` | `deps_*` still lists versions, but `cve-check` cannot confirm *which* are vulnerable |

If none of the optional tools are present, you run the **regex tier only** — fast,
no build, but with the documented limits in [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).
Treat "not reachable" with extra caution (AGENT_NOTES §C) in that mode.

> The core extractors parse source text — they do **not** compile the target and
> need no NuGet/SDK. This is deliberate: client source is often partial or won't
> build.

## Installing CodeQL (optional, high-fidelity tier)
Use the **bundle** (ships the standard query packs; the bare CLI would need extra
`codeql pack download`). Linux:
```
mkdir -p ~/tools && cd ~/tools
curl -L -o codeql-bundle.tar.gz \
  https://github.com/github/codeql-action/releases/latest/download/codeql-bundle-linux64.tar.gz
tar xzf codeql-bundle.tar.gz          # creates ./codeql
export PATH="$HOME/tools/codeql:$PATH" # add this line to ~/.zshrc to persist
codeql --version
```
C# extraction needs the project to compile. If it won't build (common on client
source), skip the build:
```
codeql database create ... --build-mode=none ; codeql database analyze ... --output=out.sarif
python3 toolkit/import_findings.py sarif out.sarif --src <SRC> --lang cs | sqlite3 graph.db
```
`--build-mode none` is faster and needs no .NET SDK, at lower type fidelity
(weaker generic/interface resolution). With a working `dotnet build`, omit it for
full fidelity. CodeQL covers C#/Java/Python — **not PHP** (use semgrep there).

## Clone
```
git clone <repo-url> taintgraph
cd taintgraph
```

## Quickstart
The **query engine ships** (`toolkit/graphquery`, importers). The **extractors do
not** — build them once from [`docs/EXTRACTORS.md`](docs/EXTRACTORS.md), starting
from `examples/extractor_skeleton.py`. Then (see `examples/build-graph-template.sh`):
```
# 0. bootstrap the schema (REQUIRED first)
sqlite3 graph.db < docs/SCHEMA.sql

# 1. run YOUR extractors to populate the graph (names follow the _<lang> convention)
python3 toolkit/extractors/routes_<lang>.py          SRC | sqlite3 graph.db
python3 toolkit/extractors/<virtual_edge>_<lang>.py  SRC | sqlite3 graph.db   # e.g. di_cs / mediatr_cs / spring_impl_java
python3 toolkit/extractors/calls_direct_<lang>.py    SRC | sqlite3 graph.db
python3 toolkit/extractors/load_sinks_<lang>.py  toolkit/sinks/<lang>.txt SRC | sqlite3 graph.db

# 2. query with the SHIPPED engine (never grep the same thing twice)
toolkit/graphquery --db graph.db trace-back all          # every sink -> source
toolkit/graphquery --db graph.db trace-back ExecuteSqlRaw # one sink category/api
toolkit/graphquery --db graph.db callers  GetUserById     # who calls a function
toolkit/graphquery --db graph.db why-unreachable <name>   # WHY a trace stopped
toolkit/graphquery --db graph.db explore --seed 7 --explore-budget 12  # seeded frontier (AGENT_NOTES §G)
toolkit/graphquery --db graph.db annotate-add <src> <dst> --reason ".." --evidence f:line  # overlay (never edits facts)
toolkit/graphquery --db graph.db overrides                # audit trail

# 3. (optional) high-fidelity tier — the IMPORTERS ship; run your engine, then import:
semgrep --config <your-rules-dir> --json SRC > sg.json
python3 toolkit/import_findings.py semgrep sg.json --src SRC --lang <lang> | sqlite3 graph.db
# CodeQL: codeql database create/analyze ... --format=sarifv2.1.0 --output=out.sarif
python3 toolkit/import_findings.py sarif out.sarif --src SRC --lang <lang> | sqlite3 graph.db
toolkit/graphquery --db graph.db findings all            # list + cross-check vs your graph
```
> A reference `build-graph-*.sh` that chains the above is NOT shipped (it is yours
> to write); `examples/build-graph-template.sh` is the annotated pattern to copy.

## Other stacks
Spring / PHP / Python need their own extractors (same schema). See
[`docs/EXTRACTORS.md`](docs/EXTRACTORS.md) for the plug-in contract and
[`WORKFLOW.md`](WORKFLOW.md) §2 for the per-stack extractor list. The `.NET` set
(`routes_cs`, `mediatr`, `calls_direct`, `load_sinks`) is the reference
implementation to copy from.

## Read before trusting results
- [`WORKFLOW.md`](WORKFLOW.md) — the full process, build gate, cleanup.
- [`docs/AGENT_NOTES.md`](docs/AGENT_NOTES.md) — **§C: "not reachable" is never
  "safe"**. Mandatory reading before acting on any trace result.

## Cleanup (engagement close)
`graph.db` and scanner output contain client code = client data. They are
git-ignored; delete them at close and harvest only reusable assets back into
`toolkit/` (WORKFLOW.md §8).
