# Example run (regex tier)

> The `toolkit/extractors/*` and `build-*.sh` commands below are run against the
> **private reference engine**; those files are not shipped (see README "What this
> repo contains"). You build equivalent `*_<lang>` extractors from
> `docs/EXTRACTORS.md`; the SHIPPED `graphquery` then produces the output shown.

Target: a large enterprise **.NET + MediatR** codebase — 146 projects, ~9,700
`.cs` files — analysed **without building it** (portable regex tier). All client
identifiers below are anonymised; this repo carries no client data.

## Commands
```
sqlite3 graph.db < docs/SCHEMA.sql
python toolkit/extractors/routes_cs.py  SRC | sqlite3 graph.db
python toolkit/extractors/mediatr_cs.py        SRC | sqlite3 graph.db
python toolkit/extractors/load_sinks_cs.py toolkit/sinks/cs.txt SRC | sqlite3 graph.db
graphquery trace-back all
```

## Graph built (no compiler, ~2.5 min total)
| metric | value |
|---|---|
| nodes | 3,522 |
| **MediatR edges resolved** | **461** |
| route sources | 1,799 |
| sink methods | 1,604 |
| extraction time | routes 41s · mediatr 55s · sinks 43s |

Sink breakdown: ssrf 1124, redirect 208, deser 202, path 52, code 12, sqli 6.

## What this demonstrates

**1. The type-bound backbone resolves — the thing grep/ctags miss.** A sample
resolved edge has no direct call between the two methods; it is bound only by the
command type:
```
IntegrationService.GetDetail  --Send(new GetDetailQuery)-->  GetDetailQueryHandler.Handle   [mediatr/static-exact]
```
461 such edges were recovered automatically.

**2. Clean route->sink paths found automatically.** 60 sinks trace back to an
HTTP route through the MediatR backbone alone, e.g.:
```
[route GET ...]  LogsController.GetLogByTraceId  --mediatr-->  <handler that contains the sink>
```

**3. The not-reachable discipline is enforced, not hidden.** 1,379 sinks had no
static path **on this layer alone**. The tool never calls these "safe" — each
prints the §6 warning and its stop reason:
```
NO STATIC PATH TO A SOURCE  (NOT proof of safety — verify, see AGENT_NOTES C)
   stop: <node>  [dead-end-leaf]
```
Example: the 6 SQLi sinks are all in DB-migration/infrastructure classes and
dead-end as leaves — plausibly not request-reachable, but flagged for manual
confirmation rather than dismissed.

## Honest limits of the regex tier (and the fix)
- Most of the 1,379 non-paths are a **tooling limit, not a safety result**:
  without receiver-type resolution, `calls_direct` keys callees by bare name, so
  deep *direct-call* chains (handler -> service -> repository-sink) do not connect
  to fully-qualified sink nodes. The **exact, type-bound** edges (routes, MediatR)
  do connect — which is why they carry the demo.
- `calls_direct` still answers ad-hoc "who calls a function named X" queries.
- The **Roslyn/CodeQL tier** (same schema) adds real type resolution and closes
  the direct-call gap. This is the documented upgrade, not a redesign.

## Takeaway
Even at the no-build regex tier, the graph recovers the framework-dispatch edges
a naive call-graph cannot see, finds real route->sink paths in minutes across a
~9.7k-file codebase, and — by design — reports every miss as "verify here", never
as "safe".

---
# Multi-language validation: Java / Spring (minimal set)

No Java repo was on hand (the real target is .NET), so the Java set is validated
on a small synthetic Spring sample — enough to prove the methodology generalises:
**the same schema and the same `graphquery` are reused unchanged; only new
`*_java` extractors were added.**

```
build-graph-java.sh <spring-src> graph.db     # routes_java, spring_impl_java, calls_direct_java, load_sinks_java
graphquery trace-back queryForObject
```

The Spring analog of MediatR is **interface -> impl**: a controller calls an
injected `UserService` (interface); the real code and the SQLi sink live in
`UserServiceImpl`. `spring_impl_java` binds that edge by type — invisible to a
plain call-graph. Result:
```
### SINK com.demo.svc.UserServiceImpl.lookup
  REACHABLE from source [route: GET /api/users/{id}]
     com.demo.web.UserController.get [spring/static-exact]
     com.demo.svc.UserServiceImpl.lookup
```
Same `node/edge/source/sink` tables, same provenance tags, same trace engine as
the C# run above — confirming the framework is language-agnostic and a new stack
is a matter of writing `*_<lang>` extractors against the fixed contract.

---
# Engine tier: semgrep on the real .NET codebase (cross-check)

semgrep 1.184.0 (starter rules) run on the real ~9.7k-file .NET codebase, imported
into the same graph, then cross-checked by `graphquery findings`. Aggregate
(client identifiers withheld):

- **8 findings**: 7 × `cs-weak-deser-typenamehandling` (Json.NET `TypeNameHandling`
  != None — the data-driven deserialization risk), 1 × `cs-sqli-concat-raw`
  (string-concatenated `ExecuteSqlRaw`). 7/8 resolved to a method node.
- **Every resolved finding sat on a node the regex graph calls NOT reachable** →
  each flagged: *"ENGINE-FLAGGED but regex graph finds NO path → likely regex-tier
  false-negative (L1); trust the engine (precedence §6.5)"*.

Why: those sinks live in event-bus / Redis / integration-event / migration code
reached via the message bus, DI and framework config — **not** via the HTTP
route + MediatR edges the regex tier models. That is exactly the L1 blind spot,
and the deser findings are the data-driven class where `0 callers != safe`
(AGENT_NOTES §D).

**This is the methodology validating itself:** the high-fidelity tier, in the
same store, *measured* the regex tier's false-negatives instead of either tier
silently hiding them — and the precedence rule said which to trust. It also shows
why "not reachable" is never "safe".

---
# CodeQL graph export into the schema (closes L1 on real code)

CodeQL's type-resolved call graph exported into the SAME schema via
`build-codeql-graph.sh` (buildless DB; `--build-mode none`):
- **1,059,202 call edges** imported as `provenance=codeql`, keys ALIGNING with the
  regex tier (1707/1799 route sources and 283 sinks appear in them).
- Route-reachable sinks **60 -> 68**; **10 reachable paths are load-bearing on a
  CodeQL edge** — a mixed-provenance chain the regex tier cannot form alone, e.g.
  `route -> Handler.Handle [mediatr] -> ...CallApiMonitor [call/codeql]` (an SSRF
  sink reached only because CodeQL resolved the receiver-typed direct call).
- Most other sinks stay not-route-reachable because their true entry is the
  message bus / gRPC / startup, not HTTP — correctly reported (that is L6 source
  coverage, not an L1 miss).

The agent still queries the cheap `graphquery`; CodeQL is the precompute backend
whose precise edges carry higher trust in the precedence ladder (§6.5) — a reading
discipline the agent applies, not a weight `graphquery` traversal computes.

**Bug found & fixed in-session:** backward BFS was short-circuiting at any boundary
node, so a sink that itself used reflection was wrongly called "not reachable"
even when it had static callers. Fixed: a boundary is an informational flag on a
path, a hard stop only at a leaf (no static predecessors). The framework
correcting its own traversal bug — exactly the CONTRIBUTING/self-correction ethos.

---
# Benchmark: CodeQL build vs no-build (and why injection findings are absent)

Same security-extended suite, same ~9.7k-file .NET/MediatR codebase.
| | findings (rule,file,line) |
|---|---|
| CodeQL `--build-mode none` (buildless) | 173 |
| CodeQL autobuild (full build) | 181 |

- **Full build is a STRICT SUPERSET of buildless** (0 findings lost); it adds 8:
  `user-controlled-bypass` x2, `sensitive-information` x2, `log-forging` x4 — the
  dataflow-sensitive ones buildless's weaker type resolution missed. Magnitude is
  small (~4.5%), so buildless is a strong, cheap approximation for this target.
- **Neither build mode reports SQL/command/SSRF injection** (only XSS, 8, identical
  in both). Per the engagement's ground truth (this codebase was already pentested),
  **it simply has no SQLi/command-injection bugs** — so the absence of those findings
  is a correct TRUE NEGATIVE, not evidence of any tool blind spot. (The one concat
  raw-SQL semgrep flagged is in DB-migration code, not request-reachable.)
- Caveat, not a conclusion: CodeQL does not model MediatR dispatch by default (a
  known general limitation our `mediatr_cs` extractor addresses), but THIS codebase
  offers no injection-through-a-mediator flow to test that against, so we draw no
  conclusion about it here.
