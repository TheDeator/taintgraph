# Limitations & open questions (falsifiability ledger)

Honest, known weaknesses of the current framework. Each is a standing invitation
to disprove or fix (see CONTRIBUTING.md). "Not reachable" is never "safe"; this
page is why. Entries: what · impact · how to detect · status.

## Regex-tier extractors
- **L1 — no receiver-type resolution.** `calls_direct_*` keys callees by bare
  name, so deep *direct-call* chains do not connect to fully-qualified sink
  nodes → `trace-back` can report a **false "not reachable"**.
  Detect: `why-unreachable` dead-ends at a method you can see is called.
  Status: MITIGATED when CodeQL is available — `build-codeql-graph.sh` exports
  CodeQL's type-resolved call graph as provenance=codeql edges (same schema,
  same graphquery), recovering receiver-typed chains the regex tier misses.
  Still open for the no-CodeQL case. Other fix paths: Roslyn/tree-sitter tier; OR run the engine tier
  (semgrep/CodeQL) whose `findings` cross-check flags exactly these false-negatives.
  Without any engine installed you run regex-only and L1 applies in full.
  DEVELOPMENT DIRECTION (planned) — tree-sitter extractor tier: replace/augment the
  regex `parse_*`/`calls_*` with a tree-sitter AST pass. Prior art: CodeGraph
  (colbymchenry/codegraph, MIT) ships a tree-sitter kernel across 20+ languages into
  a SQLite graph — evidence the AST route is tractable and portable, and it would
  give us Java/PHP/Python/Go node+edge extraction at far lower per-language cost than
  hand-written regex (the GIGO-reducing, upfront-amortised investment per README
  "Output is only as good as the extractors"). HONEST CAVEAT: tree-sitter alone still
  does NOT do receiver-type resolution — CodeGraph's own call edges are name/import
  heuristics and it lists DI/reflection as a known gap, so L1 is only *fully* closed
  by a type/symbol pass (Roslyn/CodeQL) on top. tree-sitter fixes the parsing half
  (fewer mis-keyed/missed nodes, L4) and is the better substrate for `static-exact`
  facts; it does not by itself make bare-name callees type-resolved.
- **L2 — bare-name over-merge.** Two methods sharing a name collapse to one key →
  `callers/callees` **over-connect** (false positives, noise).
  Impact: could inflate traces and *cost tokens* — in tension with goal #2.
  Status: open; quantify via benchmark. This over-connection bias is on trial.
- **L4 — heuristic parsing.** Comment/string scrubbing and the method regex are
  approximate (Java text blocks, exotic generics, modifier-less methods,
  constructors). Some methods missed, some false matches.
  Status: open; acceptable for triage, fixed by the compiler-backed tier.

## Virtual-edge extractors
- **L5 — incomplete dispatch modelling.** `mediatr_cs` only resolves
  `Send(new X())`, not `Send(variable)`. `spring_impl_java` links to *all* impls
  of an interface and does not disambiguate `@Primary`/`@Qualifier`/profiles →
  may over-connect (static-candidate) or miss variable-typed dispatch.
  Status: open.

## Sources / sinks / deps
- **L6 — source / entry-point coverage (a CUSTOMIZE responsibility).** The default
  `routes_*` extractor models ONLY attribute/MVC routing (ASP.NET `[Http*]`, Spring
  `@*Mapping`). It does NOT model: Razor Pages (`OnGet/OnPost`), minimal-API,
  conventional routing, gRPC service methods, hosted/background services
  (`ExecuteAsync`), message/event consumers, webhooks, Django `urls.py`. Each
  unmodelled entry type is a SILENT source gap: a sink reachable only from it shows
  "not reachable", so a reachability reduction drops it. Observed in benchmark: two
  SSRF candidates (an `ip-api.com` call in a Razor Page; a variable-host call behind
  a hosted service) were excluded by a route-only reduction and only a
  source-agnostic grep strategy found them. Fix per project: inventory entry-point
  mechanisms (SKILL customize step) and extend the source extractor — never treat
  "reachable from N routes" as complete.
  DEVELOPMENT DIRECTION (planned) — multi-framework route-convention catalog: build a
  reusable table of entry-point patterns per framework so `sources_*` is not written
  from scratch each project. Prior art to mine: CodeGraph's route modelling covers
  ~16 frameworks (ASP.NET `[HttpGet("/x")]`, Spring `@*Mapping`, Django
  `path()/re_path()/url()`, Flask, FastAPI, Express, NestJS `@Controller`+verb +
  `@MessagePattern`/`@SubscribeMessage`, Laravel, Rails, Gin/chi/mux, Axum/actix/
  Rocket, Play, Drupal, CodeIgniter, Vapor, Astro) — a ready inventory of the
  attribute/decorator conventions to port into our per-language source extractors.
  We need only the convention list (data), not their tool. Still our responsibility:
  the non-route entry types CodeGraph also does NOT model (Razor Pages, hosted/
  background services, gRPC, reflection, DI-wired consumers) — those stay manual per
  project, see §H in AGENT_NOTES.
- **L7 — cve-check naivety.** The `vulnerable` flag needs an external advisories
  feed; version matching is substring, not semver-range. Status: open.

## Second-order / stored flows
- **L8 — second-order (stored) data flow is NOT modelled (structural weakness).**
  The graph is a CALL graph, not a store-mediated DATA-flow graph. For a stored /
  second-order bug (attacker data written to a DB / config / cache / file by one
  flow, read back and used dangerously by another), the framework finds the WRITE
  half (source → … → write-site) and the READ half (read-site → … → sink) as two
  SEPARATE call chains but does NOT connect them — there is no edge joining
  "write store X" to "read store X". The store is the gap, so a second-order flow
  shows up as two disconnected traces.
  Impact: stored XSS / stored SQLi / stored SSRF, config-write→SSRF, poisoned-cache
  flows, etc. are missed by automated reachability. `source.kind='stored'` exists in
  the schema as a placeholder but no extractor populates it.
  Current mitigation: MANUAL only — AGENT_NOTES §C(d): grep the same table/column /
  cache-key / config-key written at A and read at B, plus the bidirectional
  discipline. Not automated.
  Not unique to this framework: CodeQL / semgrep taint also does NOT cross the
  persistence boundary without custom modelling — second-order through a datastore
  is a hard, industry-wide problem.
  DEVELOPMENT DIRECTION (planned, to solve later): a "store-mediated virtual edge"
  extractor — emit write-site and read-site nodes KEYED BY STORAGE LOCATION
  (table.column, cache key, config key), then connect matching keys as
  `mechanism='stored'` edges. This is analogous to the type-bound MediatR edge, but
  keyed on a DATA location instead of a type. Hard because keys are often
  dynamic/computed → resolve the static ones, flag the rest as boundaries (never
  fabricate). Would let trace-back cross the store and surface second-order chains.

## Validation gaps
- **L3 — Java validated on a SYNTHETIC sample only.** No real Spring repo has
  been run. The multi-language *mechanics* are proven; real-world recall is not.
  Status: open.

## Methodology-level open questions (the architecture might be wrong)
- **Q1 — is the provenance trust order right?** `static-exact > candidate >
  model-inferred` and the source precedence ladder are asserted, not measured.
- **Q2 — does the token-saving claim hold end-to-end?** Build-once + bounded
  queries *should* beat repeated grep, but this has not been measured against a
  real grep-based session. If over-connection (L2) makes queries noisy, the
  framework could cost MORE tokens — which would falsify its reason to exist.
  Status: open; the benchmark is meant to answer this.
