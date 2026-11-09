# Start here

**What this is.** A methodology + tooling to trace **sink ↔ source** across a
codebase *faster, more accurately, and with less token cost over time* than
repeated grep. Not a demo — the three goals are the whole point:

- **Faster / more accurate:** it recovers framework-dispatch edges a plain
  call-graph misses (MediatR, Spring interface→impl, gRPC, DI) and queries from
  both ends.
- **Token-cheaper long-term:** the graph is built **once**, deterministically,
  and its large output **never enters the AI's context**. After that, each
  question is a bounded query returning a few rows — not a grep that dumps
  hundreds of noisy lines into context every single time.

**When it pays (and when NOT).** Use it on a **large and/or framework-heavy**
project you will query repeatedly. For a **small project or a single one-off
lookup, just grep** — building a graph you won't query enough is the exact
"make-work that costs more tokens" this framework exists to avoid. The build
cost must be amortised by the queries that follow.

## Apply to a new project — 3 steps
1. **Prerequisites:** `python3` + `sqlite3` (details in [`INSTALL.md`](INSTALL.md)).
   The core needs no target build and no Python packages.
2. **Install the skill** so your agent knows the purpose and procedure:
   ```
   cp -r skill/taintgraph  <your-project>/.claude/skills/
   ```
> Note: `graphquery` + the importers ship and run as-is; the extractors do not —
> your agent builds them first (that is what the skill directs). Nothing under
> `toolkit/extractors/` exists on a fresh clone; that is by design, not a bug.

3. **Tell your agent one line:**
   > Use the `taintgraph` skill to build the code graph for this project
   > and trace sinks to sources.

   No skill mechanism in your tool? Point the agent at the doc directly:
   > Read `<path>/taintgraph/skill/taintgraph/SKILL.md` and follow
   > it for this project.

## The extractors are build-it-yourself (by design)
The query engine (`toolkit/graphquery`) and the importers ARE shipped. The
language **extractors, sink catalogs and taint rules are NOT** — they are
operational/offensive/tunable tooling kept private. So on a fresh clone there is
nothing to "run" under `toolkit/extractors/` yet; that is expected.

The designed first step (what the skill makes your agent do) is to **write the
`*_<lang>` extractor(s)** following [`docs/EXTRACTORS.md`](docs/EXTRACTORS.md),
starting from [`examples/extractor_skeleton.py`](examples/extractor_skeleton.py)
and [`examples/build-graph-template.sh`](examples/build-graph-template.sh). The
methodology is proven on C#/.NET and Java/Spring; the code to reproduce it is
yours to build (that is also what keeps the trace accurate and tuned to your
target).

## Map of the docs
- [`START_HERE.md`](START_HERE.md) — this file.
- [`INSTALL.md`](INSTALL.md) — setup + quickstart commands.
- [`WORKFLOW.md`](WORKFLOW.md) — the full process, principles, cleanup.
- [`docs/AGENT_NOTES.md`](docs/AGENT_NOTES.md) — the discipline the agent must follow.
- [`docs/EXTRACTORS.md`](docs/EXTRACTORS.md) — how to add a language/framework.
- [`skill/taintgraph/SKILL.md`](skill/taintgraph/SKILL.md) — what the agent reads.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — report a flaw / contribute (AI included).
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — known weaknesses & open questions.
