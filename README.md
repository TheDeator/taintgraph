# taintgraph

A reusable, AI-assisted methodology for **white-box vulnerability tracing** across
framework-heavy codebases (Java/Spring, .NET, PHP, Python).

It replaces repetitive, token-hungry grep-and-read loops with a **deterministic
code graph** that you query from both ends (sink→source and source→sink), and a
**disciplined use of LLMs** that fills only the gaps a static tool cannot resolve.

> This is primarily a **methodology** for white-box tracing that generalises
> across languages and projects. The code here is a **reference implementation**
> whose job is, in order: (1) to validate the methodology on real code, and
> (2) to be reused across engagements. It contains no client code, findings or
> engagement data — only the reusable workflow and assets.

## Why it exists (read this first)

Three goals, in order — anything that does not serve them is out of scope:
1. **Faster, more accurate tracing** — recover framework-dispatch edges a plain
   call-graph misses (MediatR, Spring interface→impl, gRPC, DI); query both ends.
2. **Lower token cost over time** — build the graph **once** (its large output
   never enters the AI's context); then each question is a **bounded query**
   (a few rows), not a grep that dumps hundreds of lines into context repeatedly.

**When it pays, and when not:** use it on a large / framework-heavy codebase you
will query repeatedly. For a tiny project or a one-off lookup, **just grep** —
a graph you won't query enough costs more than it saves, which is the exact
anti-pattern this avoids.

**Output is only as good as the extractors (GIGO).** The graph is not magic: its
accuracy is bounded by the quality of the extractors, sink catalogs and taint
rules you feed it. A sloppy build is *worse than nothing* — a wrong or missing
edge produces a **false "not reachable"** (missed bug) **and costs MORE tokens**,
because the agent then grep-verifies, re-traces and second-guesses the graph it
cannot trust. So budget an **upfront investment**: build the extractors with a
**capable model**, validate them against ground truth, and treat that one-time
cost as real. It pays back two ways — (1) **amortised across many queries** on
this codebase, and (2) **reused on future similar projects** (same stack /
frameworks). That is why the sweet spot is **medium-to-large projects, run over
many sessions, with deep or wide source→sink distance and colliding function
names** — exactly where naive grep is most expensive and the upfront build earns
out. On a small, shallow, uniquely-named target the upfront cost never amortises;
grep wins. See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for the honest ledger
of what the current extractors do and don't recover.

New here? See **[`START_HERE.md`](START_HERE.md)** for the 3-step apply-to-a-project.

---

## The problem

During white-box review you locate a dangerous sink (`ExecuteSqlRaw`,
`Runtime.exec`, `unserialize`, `pickle.loads`…) and need to know whether
attacker-controlled input can reach it. The naive approach is to grep for the
enclosing function, then grep for *its* callers, and repeat. This:

- **doesn't scale** — large codebases have thousands of files;
- **wastes context/tokens** — every grep dumps hundreds of noisy lines;
- **silently misses edges** — modern frameworks dispatch through *types*, not
  named calls: MediatR (`Send(cmd)`→`IRequestHandler<cmd,>`), Spring
  interface→impl, gRPC, DI, events, reflection. A plain call-graph tool is blind
  to these and reports a false *"not reachable"*.

## The approach — four principles

1. **Static enumerates; the model fills only the residual.** The deterministic
   layer extracts every fact it can (symbols, direct calls, typed dispatch,
   routes, DI). The LLM is invoked *only* on genuine ambiguity, and its answer
   space is constrained to a verified candidate set — so it cannot hallucinate
   an edge that does not exist.
2. **Every edge carries provenance** — `static-exact | static-candidate |
   model-inferred` — so an inferred link is never trusted like a proven one.
3. **Boundaries are flagged, never swallowed.** Where the graph goes blind
   (reflection, gRPC, unmodeled dispatch) it records *why* a trace stopped,
   turning a silent false-negative into an actionable "verify here".
4. **Bidirectional graph, meeting in the middle.** Backward from sinks and
   forward from sources cover each other's blind spots and minimise exploration.

**Golden rule:** *"not reachable" is never proof of safety* — only "no static
path found yet". It is used to deprioritise, never to dismiss. See
[`docs/AGENT_NOTES.md`](docs/AGENT_NOTES.md).

## How AI is used (the point of this repo)

The LLM is treated as a **bounded reasoner, not an oracle**:

- **Deterministic substrate, model on top.** A SQLite graph + a query CLI answer
  all exact questions (`callers`, `callees`, `trace-back`, `cve-check`). Models
  never proxy deterministic queries — that would break reproducibility.
- **Cheap models for bounded judgement.** Haiku/Sonnet-class models resolve only
  multi-candidate dispatch (pick the real impl from a listed set) and label sinks
  — small, parallelisable, low-hallucination tasks.
- **Agent separation.** A deterministic *graph service* owns the database; a
  *hunter* agent asks it bounded questions, keeping large tool output out of its
  own context. (See [`docs/AGENT_NOTES.md`](docs/AGENT_NOTES.md).)
- **Skepticism as a first-class control.** Provenance tags, boundary flags and
  the not-reachable discipline exist specifically to keep model error from
  becoming a missed vulnerability.

## Getting started

```
git clone <repo-url> taintgraph && cd taintgraph
# graphquery ships; build your *_<lang> extractors from docs/EXTRACTORS.md first
sqlite3 graph.db < docs/SCHEMA.sql
python3 toolkit/extractors/<your-extractors>.py SRC | sqlite3 graph.db   # see examples/build-graph-template.sh
toolkit/graphquery --db graph.db trace-back all
```

Full setup and prerequisites: [`INSTALL.md`](INSTALL.md). A worked run with real
numbers: [`docs/EXAMPLE_RUN.md`](docs/EXAMPLE_RUN.md).

## Use it with an AI agent

Copy the skill so your agent knows when and how to drive the workflow:

```
cp -r skill/taintgraph  <your-project>/.claude/skills/
```

The agent then builds the graph, queries it from both ends, and — critically —
applies the "not reachable is never safe" discipline from
[`docs/AGENT_NOTES.md`](docs/AGENT_NOTES.md). To add a new language/framework it
follows [`docs/EXTRACTORS.md`](docs/EXTRACTORS.md).

## What this repo contains

**Shipped and runnable:** the query engine `toolkit/graphquery`, the result
importers (`toolkit/import_findings.py`, `toolkit/import_codeql_graph.py`), the
graph schema `docs/SCHEMA.sql`, and `examples/` (a skeleton extractor, a build
template, a sink-catalog sample, an example session).

**Build-it-yourself — NOT shipped by design (operational / offensive / tunable):**
the language **extractors** (`*_<lang>.py`), the **sink catalogs**, the **taint
rules**, and the orchestration `build-*.sh`. You build the extractors once against
the plug-in contract in [`docs/EXTRACTORS.md`](docs/EXTRACTORS.md), starting from
[`examples/extractor_skeleton.py`](examples/extractor_skeleton.py) and
[`examples/build-graph-template.sh`](examples/build-graph-template.sh). Once your
extractors produce the graph, the shipped `graphquery` queries it. So: nothing
under `toolkit/extractors/`, `toolkit/sinks/` or `toolkit/semgrep-rules/` is in
this repo — that is expected, not a missing file.

## Repository layout

```
INSTALL.md               Setup + quickstart (clone -> install -> run)
WORKFLOW.md              Full operational playbook (per-project run + cleanup)
docs/
  SCHEMA.sql             SQLite graph schema (key-based)
  EXTRACTORS.md          Plug-in contract for adding a language/framework
  AGENT_NOTES.md         Ready-to-paste agent instruction blocks (discipline)
  EXAMPLE_RUN.md         Real run on a ~9.7k-file .NET codebase (anonymised)
skill/taintgraph/ Claude Code skill — copy into .claude/skills/
toolkit/                 Engine (shipped) + your assets (build-it-yourself)
  graphquery             Deterministic query CLI                 [shipped]
  import_findings.py     semgrep/CodeQL results -> finding table [shipped]
  import_codeql_graph.py CodeQL call graph -> codeql edges       [shipped]
  codeql/README.md       CodeQL tier notes                       [shipped]
  extractors/            *_<lang>.py you build (EXTRACTORS.md)    [NOT shipped]
  sinks/ semgrep-rules/  your catalogs / taint rules             [NOT shipped]
examples/                skeleton extractor, build template, sinks sample, session
```

## Status

The methodology, schema and the shipped `graphquery` + importers are validated on
a large real .NET/MediatR codebase ([`docs/EXAMPLE_RUN.md`](docs/EXAMPLE_RUN.md)),
with a minimal Java/Spring set confirming the multi-language claim on the same
schema and CLI. The language extractors are build-it-yourself by design (see
"What this repo contains"). Next: FQ direct-call resolution, PHP/Python extractors, CodeQL
tier, and a ground-truth benchmark (see [`WORKFLOW.md`](WORKFLOW.md) roadmap).

## Hygiene

Per-project artifacts (the graph DB, scanner output, client source) are
disposable and contain client data — they are git-ignored and deleted at
engagement close. Only reusable assets are committed.
