# Agent instruction blocks

Ready-to-paste notes for the agents that drive this workflow. They encode the
four principles and the discipline that keeps model error from becoming a missed
vulnerability.

---
## 0. Build quality bounds everything (GIGO — all agents)
```
The graph's accuracy is capped by the extractors, sink catalogs and taint rules
behind it. A wrong/missing edge is not a neutral gap: it yields a false
"not reachable" (a MISSED BUG) and it costs you MORE tokens, because you then
grep-verify, re-trace and distrust the graph. Two consequences:
  - Validate before you rely. Confirm a few KNOWN chains resolve in the graph
    before trusting a negative on an unknown one.
  - When the build is wrong for THIS project (missing a dispatch mechanism, a
    sink the catalog lacks, a mis-keyed node), fix the EXTRACTOR, not the one
    query. A per-query workaround is paid every query; an extractor fix
    amortises across all later queries and across future similar-stack projects.
This is why the upfront build deserves a capable model and real token budget:
it is the cheapest place to spend, and the most expensive place to be sloppy.
```

## A. Provenance discipline (all agents)
```
Every edge you add to or read from the graph has a provenance tag:
  static-exact     proven by syntax (direct call, single-candidate dispatch)
  static-candidate enumerated possibility, not yet resolved
  model-inferred   chosen by a model from a bounded candidate set
Never treat model-inferred like static-exact. When a trace relies on a
model-inferred edge, say so and flag it for manual confirmation.
```

## B. Graph service / hunter protocol
```
The graph is SQLite + the graphquery CLI. It is the single source of truth.
- Deterministic questions (callers, callees, trace-back, trace-fwd, meet,
  why-unreachable, cve-check) are answered by running graphquery directly.
- A graph-agent exists ONLY to isolate context for bulk jobs (e.g. tracing many
  sinks). It returns graphquery output VERBATIM plus a short summary. It must
  NEVER invent, guess, or "remember" an edge that graphquery did not return.
- A model is used to THINK only for: Phase-2 disambiguation (pick the real impl
  from a listed candidate set) and Phase-5 labelling (is input unsanitised?).
```

## C. "Not reachable" verification (MANDATORY, sink->source)
```
A "not reachable" result is NOT proof of safety — only "no static path found".
Never use it to dismiss a bug. When trace-back returns no source:

1. Run `graphquery why-unreachable <sink>` and read WHY BFS stopped:
   - dead-end at a leaf  -> more trustworthy, still do step 2.
   - stopped at BOUNDARY  (reflection / gRPC / unmodeled dispatch / cross-service)
     -> NOT concluded; verification mandatory.
2. Targeted grep AT THE BLIND SPOT (do NOT re-grep direct calls by name):
   a. the function/class name AS A STRING   -> reflection, bean-by-name, config key
   b. the TYPE name (not the method)         -> type-based dispatch (mediator/event/DI)
   c. in *.xml *.yaml *.proto *.json *.config -> wiring outside code (Spring XML, MyBatis)
   d. same field/property/cache-key WRITTEN at A and READ at B
                                             -> container flow + second-order/stored
   e. does the sink's method appear in any registration / handler-map / generic binding
3. Try the OTHER direction (source->sink forward) from suspect entries.
4. Label the result; never write "safe":
   "no static path, dead-end leaf, grep a-e clean" -> unreachable (manual-verified)
   "stopped at boundary" / any grep a-e hit        -> NEEDS MANUAL TRACE (not dismissed)
5. High-value endpoints (auth/payment/admin/file/cross-tenant) are reviewed
   manually regardless of result.
```

## D. CVE / library triage
```
Being vulnerable to a CVE needs THREE facts; the graph gives only the second:
1. vulnerable version present?   -> dependency table (graphquery cve-check)
2. is the vulnerable path called? -> callers of the library symbol
3. trigger preconditions met?    -> read the CVE + the call site (manual/model)

DATA-DRIVEN CVE TRAP: for Log4Shell, deserialization gadgets (Json.NET
TypeNameHandling, BinaryFormatter, SnakeYAML, Jackson default typing) and similar,
the dangerous function is invoked by DATA, not by an explicit call in the code.
`callers(internalVulnFunc)` can be 0 while the code is fully vulnerable. For these,
check usage of the library's PUBLIC ENTRY API plus its configuration, and treat
0 callers as inconclusive, never as "not vulnerable".
```

---
## E. Source precedence, conflicts & self-correction
```
TRUST LADDER (highest first) — tools propose, source code disposes:
  1. hand verification of the code at the site   (ground truth)
  2. high-fidelity static (CodeQL/Roslyn, build) (type-resolved)
  3. semgrep taint (configured rules)
  4. the graph (regex tier): static-exact > static-candidate > model-inferred
     (manual-verified from the overlay ranks with hand verification)
  5. catalogs/heuristics (sink lists)            (candidates only)
A higher tier does NOT auto-override a lower one; a disagreement is a flag to
verify, never an auto-resolve.

CONFLICTS:
  graph reachable  + code shows guard/dead code -> code wins; REFUTE the edge.
  graph not-reach. + verification finds a path  -> graph missed it; ADD the edge.
  two tools disagree                            -> UNRESOLVED -> verify by hand.
  while unresolved                              -> treat as reachable/needs review,
                                                   NEVER as safe (golden rule).

CORRECTIONS (you MAY fix the graph, via the overlay only — never edit facts):
  graphquery annotate-add    <src> <dst> --reason R --evidence f:line --mech m
  graphquery annotate-refute <src> <dst> --reason R --evidence f:line
  - add    = an edge you confirmed by hand that extraction missed.
  - refute = an edge you proved wrong (kept for audit, excluded from traversal).
  Always include a reason + evidence. The fact layer is untouched; your overlay
  survives re-extraction. If you find yourself making the same correction
  repeatedly, that is a signal to extend the extractor, not to keep annotating.
```

---
## F. Challenge the methodology (you are invited to find its bugs)
```
This framework is a HYPOTHESIS. The architecture may be wrong, an extractor may
be unsound, the schema may not model something, a principle may be false. When
you notice this while working, do NOT silently work around it — route it:

  1. wrong FACT in this project's graph  -> overlay (annotate-add/refute, §E).
  2. extractor systematically wrong      -> fix the *_<lang> extractor (toolkit)
     per docs/EXTRACTORS.md. Signal: you keep making the same overlay fix.
  3. methodology/architecture flawed      -> the most valuable report. Add an
     entry to docs/LIMITATIONS.md with a MINIMAL COUNTEREXAMPLE (inputs -> wrong
     output) + impact, then propose a change to WORKFLOW.md / the principles.

Actively look for counterexamples to the framework's own claims — especially:
  - a trace it calls "not reachable" that you can show IS reachable (false-neg);
  - over-connection that floods a query with noise (would make it COST tokens,
    falsifying goal #2);
  - a provenance/precedence call that led you to the wrong conclusion.
Prefer a failing example over prose. Honesty about a flaw outranks a clean demo.
See CONTRIBUTING.md.
```

---
## G. Exploration budget & seeded diversity (avoid systematic blind spots)
```
WHY: a deterministic backbone turns independent errors into CORRELATED ones — if
the path is wrong, every session fails the SAME way (silent, repeatable misses).
The cure is not random noise everywhere (that burns tokens); it is BOUNDED,
TARGETED exploration at the frontier the graph already admits it is unsure about.

BUDGET (preserve the token goal):
  ~90% effort: exploit the deterministic backbone (static-exact edges) — cheap.
  <=10%, HARD-CAPPED: explore. Never let exploration uncap the token budget.

WHERE to explore (not uniform — the graph hands you the map):
  graphquery explore --seed S --explore-budget K
  -> a seeded, budgeted sample of {boundaries, static-candidate / model-inferred
     edges, isolated/not-reachable sinks}. Items also flagged by an engine are
     marked — prioritise those. This is where breakthroughs AND bugs both live
     (dynamic dispatch = attacker-interesting).

SEEDED DIVERSITY (large sample space without per-run cost):
  Pick a DIFFERENT --seed each session and LOG it. Each run is cheap and
  reproducible; the UNION of sessions explores broadly (ensemble over time).
  Same seed reproduces the run exactly -> stochasticity stays auditable.
  `trace-back all --seed S --explore-budget K` traces a seeded subset of sinks.

PRIOR, NOT PRISON:
  The backbone is a prior, not truth. You MAY go off-graph when you have a reason.
  When an off-graph hop proves real, capture it: `annotate-add` (provenance
  manual-verified). Exploration that pays off becomes backbone -> cost amortises,
  never re-paid. Repeated same-shape finds -> extend an extractor (CONTRIBUTING).

ATTACK THE BACKBONE (decorrelate failures):
  Each session, spend a small budget to try to FALSIFY one high-traffic assumption
  on the path (AGENT_NOTES §F). Different seeds challenge different assumptions ->
  a wrong path gets caught across sessions instead of failing silently forever.

DECORRELATE WITH INDEPENDENT TIERS:
  An engine with different biases (semgrep/CodeQL `findings`) breaks the graph's
  systematic errors better than random re-runs — different bias, not just noise.
  Cross-check (§C/§6.5) is part of exploration, not separate from it.
```

---
## H. Source coverage (reachability is only as complete as the source model)
```
A "reachable-from-N-sources" reduction is only as complete as the SOURCE table.
The default source extractor models MVC/attribute routes ONLY. If the project uses
other entry points — Razor Pages (OnGet/OnPost), gRPC service methods, hosted/
background services (ExecuteAsync), message/event consumers, webhooks, minimal-API —
a sink reached only from those will show "not reachable" and be SILENTLY dropped.

Before trusting any sink-pruning ("1000 sinks -> 12 route-reachable"):
  1. Inventory the project's entry-point mechanisms (SKILL customize step).
  2. Confirm the source extractor covers each; if not, extend it first.
  3. Cross-check with a SOURCE-AGNOSTIC pass (grep attacker-controlled values into
     sinks, i.e. the inverted direction) — it catches sinks behind unmodelled
     entries. (In benchmark this inverted pass found SSRF candidates the route-only
     reduction missed: a Razor Page and a background-service path.)
Treat the reduction as a PRIORITISATION, not a proof that the excluded sinks are safe.
```
