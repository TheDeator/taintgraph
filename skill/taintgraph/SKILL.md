---
name: taintgraph
description: >-
  Build and query a deterministic code graph for white-box vulnerability tracing
  on a source tree (C#/.NET+MediatR, Java/Spring, PHP, Python). Use when starting
  a white-box/source-code security review, when asked to trace a sink to its
  source (or a source to its sinks), to find who calls a function across an
  enterprise codebase without repeated grep, to check reachability of a CVE-prone
  library call, or to map attack surface. Prefer this over ad-hoc grep loops
  whenever the target has more source than is worth reading by hand.
---

# taintgraph

A static code graph (SQLite) + `graphquery` CLI that recovers framework-dispatch
edges a plain call-graph misses (MediatR, Spring interface→impl, DI), queried
from both ends. The repo root is this skill's parent project (`WORKFLOW.md`,
`docs/`, `toolkit/`); resolve paths relative to it.

## Purpose (why this exists)
Make tracing FASTER, MORE ACCURATE, and CHEAPER in tokens than repeated grep.
The graph is built once (deterministically; its large output stays OUT of your
context) and each later question is a bounded query returning a few rows — not a
grep dumping hundreds of lines into context every time. If a task would not
recoup the build cost, do not use this — say so and grep instead.

## When to use / when NOT
USE: white-box review, source in hand, a LARGE and/or framework-heavy codebase
(MediatR, Spring DI, gRPC, reflection) you will query repeatedly.
DO NOT: small targets (a few dozen files) or a single one-off lookup — plain grep
is cheaper; never build a graph "for completeness" you won't query enough to
amortise. Not for black-box or binary-only targets.

GIGO — the graph is only as good as the extractors/catalogs behind it. A wrong or
missing edge yields a false "not reachable" (missed bug) AND costs MORE tokens
downstream (you grep-verify, re-trace, distrust it). So invest upfront: build
extractors carefully, validate against a few known chains before relying on the
graph, and when the build is wrong for this project, FIX THE EXTRACTOR rather than
working around it query-by-query — the fix amortises across every later query and
across future similar-stack projects. Never quote a "not reachable" from a graph
you have not sanity-checked (see §C in AGENT_NOTES).

## Customize for this project (first run)
The query engine (`toolkit/graphquery`) and importers SHIP; the **extractors, sink
catalogs and taint rules do NOT** (operational/offensive, kept private). So on a
fresh clone there is nothing under `toolkit/extractors/` to run yet — that is by
design. Your first job is to build them:
1. Recon TWO kinds of mechanism:
   - **dispatch mechanisms** (for edges): MediatR? Spring DI? gRPC? reflection?
   - **entry-point mechanisms** (for sources): MVC routes? Razor Pages
     (`OnGet/OnPost`)? gRPC service methods? hosted/background services
     (`ExecuteAsync`)? message/event consumers? webhooks?
   The default `routes_*` extractor models ONLY MVC/attribute routes. Any other
   entry type is a `source` gap that SILENTLY drops reachability (a sink reached
   only from a Razor Page or a background service shows as "not reachable").
   Extend the source extractor to cover every entry type the project uses BEFORE
   trusting any reachability reduction.
2. WRITE the `*_<lang>` extractor(s) per docs/EXTRACTORS.md, starting from
   `examples/extractor_skeleton.py` (there is no reference extractor to copy — it
   is not shipped). Prioritise the source anchor + the framework's type-bound
   "virtual edge" (MediatR / .NET DI interface->impl / Spring impl — specified in
   docs/EXTRACTORS.md) — that is what beats grep.
3. Build the sink catalog `sinks/<lang>.txt` and tune sources for this project's
   in-house dangerous APIs / entry points.

## Procedure

1. **Recon (WORKFLOW.md §5.0).** Identify language/stack and which dispatch
   mechanisms are present (MediatR? gRPC? Spring impls? reflection?). Decide the
   build gate: does the target compile? (CodeQL tier) or not (regex tier).

2. **Build the graph.** Bootstrap the schema (`sqlite3 graph.db <
   docs/SCHEMA.sql`), then run the extractors you wrote, piping SQL into the DB
   (see `examples/build-graph-template.sh`). The extractors are not shipped; write
   them FIRST following `docs/EXTRACTORS.md` (emit SQL to stdout, node natural
   keys, provenance tags, resolve-or-flag), using `examples/extractor_skeleton.py`
   as the template and the virtual-edge specs in docs/EXTRACTORS.md.

3. **Query — bidirectional (WORKFLOW.md §5.4).**
   `toolkit/graphquery --db graph.db {callers|callees|trace-back|trace-fwd|why-unreachable|cve-check} <arg>`
   Run the deterministic CLI directly; never re-derive its answers from memory.
   For bulk tracing whose large output should stay out of context, delegate to a
   separate graph-agent that returns CLI output verbatim (WORKFLOW.md §4).

4. **Apply the discipline (docs/AGENT_NOTES.md — MANDATORY).**
   - A "NO STATIC PATH" / "not reachable" result is **never** proof of safety.
     Follow AGENT_NOTES §C: read `why-unreachable`, then targeted grep at the
     blind spot (string/type/config/container, NOT a re-grep of direct calls),
     then the other direction. Label "NEEDS MANUAL TRACE", not "safe".
   - Every edge has a provenance tag; never trust `model-inferred` like
     `static-exact` (§A).
   - CVE triage needs version + reachability + preconditions; `0 callers` is not
     "not vulnerable" for data-driven CVEs like Log4Shell / deser gadgets (§D).
   - Always manually review high-value endpoints (auth/payment/admin/file/
     cross-tenant) regardless of the graph result.
   - **Exploration (§G):** a deterministic backbone fails the SAME way every
     session. Spend a small, HARD-CAPPED budget on `graphquery explore --seed S
     --explore-budget K` (the uncertainty frontier); use a new seed per session
     and LOG it; capture confirmed off-graph edges via `annotate-add`.
   - **Precedence & conflicts (§E):** tools propose, source code disposes. Trust
     order: hand-read code > CodeQL/Roslyn > semgrep > graph (by provenance) >
     catalogs. Disagreement = verify, never auto-resolve; while unresolved treat
     as reachable, never safe.
   - **Self-correct the graph via the overlay** (never edit facts): when you
     verify an edge extraction missed, `graphquery annotate-add <src> <dst>
     --reason .. --evidence f:line`; when you prove an edge wrong,
     `annotate-refute ..`. Overlay persists across re-extraction and is audited
     (`graphquery overrides`). Repeated same-shape corrections -> extend the
     extractor instead.

5. **Cleanup (WORKFLOW.md §8).** `graph.db` and scanner output are client data —
   delete at engagement close; harvest only reusable assets back to `toolkit/`.

## Challenge it
This methodology is a hypothesis and may be wrong. If a result, an extractor, or
a principle is unsound, do not work around it silently — route it per
docs/AGENT_NOTES.md §F (overlay / fix extractor / record a counterexample in
docs/LIMITATIONS.md). Finding a real flaw is a valid, valued outcome.

## Key references
- `WORKFLOW.md` — full process, principles, build gate, cleanup.
- `docs/AGENT_NOTES.md` — the ready-to-apply discipline blocks (read §C before
  acting on any trace).
- `docs/EXTRACTORS.md` — contract for adding a new language/framework.
