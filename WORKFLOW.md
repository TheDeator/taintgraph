# White-box Sink↔Source Workflow

Reusable workflow for white-box pentest across Java/Spring, .NET, PHP, Python.
Goal: trace sink↔source efficiently, trustworthily, reproducibly, with low token
cost — via a deterministic graph plus a model that fills only the residual.

---
## 0. Principles (invariant)
1. **Static enumerates** (complete, exact, cheap, reproducible); the **model fills
   only the residual** (judgement). Never let a model build the structural graph.
2. **Every edge carries provenance**: `static-exact | static-candidate |
   model-inferred`. Never mix proven edges with inferred ones.
3. **Boundaries are flagged, not swallowed.** "Path stops here
   (reflection/gRPC/unmodeled dispatch)" beats a false "no path".
4. **Bidirectional graph**, anchored on both sinks and sources, meeting in the
   middle.

**Golden rule:** *"not reachable" is NOT proof of safety* — only "no static path
found". Never use it to dismiss a bug. See §6.

---
## 1. Tools to install
Portable core (no project build required):
- `ripgrep` (rg), `sqlite3`, `python3`
- `semgrep` — multi-language taint, **supports PHP**, no build. `pipx install semgrep`

High-fidelity tier (only when source BUILDS; Java/C#/Python — **no PHP**):
- CodeQL CLI; .NET SDK (`dotnet`) for C#; JDK + Maven/Gradle for Java

Dependency / SCA tier (for CVE triage, §5.6):
- `.NET`: `dotnet list package --vulnerable`
- cross-ecosystem: Trivy or Grype (lockfile → known-vuln versions)
- optional: OWASP Dependency-Check

Optional: `universal-ctags` for quick symbol triage.

CodeQL note: "build" = **compile** source (no live DB / running app / secrets
needed). The real blocker on client code is a working compile chain
(NuGet/SDK/all projects present). If it won't build: `--build-mode none`
(lower type fidelity — weakens exactly the generic/interface resolution you
care about) OR stay on the portable core.

---
## 2. Reusable assets (toolkit/ — carried between engagements)
> In the public repo, `graphquery` + the importers ship; the `*_<lang>` extractors,
> sink catalogs and taint rules are build-it-yourself (docs/EXTRACTORS.md,
> examples/). Paths below name the files you create, following the convention.

```
toolkit/
  extractors/      one script per mechanism — THE core asset
      routes_cs.py   [Http*]/[Route] -> source set
      routes_java.py   @*Mapping       -> source set
      calls_direct_cs.py    caller->callee direct, INCLUDING calls to library APIs
                         (recorded as kind=external nodes)        <-- addition #1
      mediatr_cs.py         Send(T) -> IRequestHandler<T,>
      di_cs.py       AddX<IFoo,Foo> -> interface->impl
      spring_impl_java.py     @Service/@Component impl + @Autowired
      grpc_cs.py            .proto -> service base (FLAG boundary)
      reflection_cs.py      Activator/GetType/invoke (FLAG boundary)
      deps_cs.py            manifests + lockfiles -> dependency table  <-- addition #2
  sinks/           dangerous-API catalog per language (csharp/java/php/python)
  sources/         input/source patterns per framework
  semgrep-rules/   custom taint rules (incl. PHP)
  codeql-models/   custom Models-as-Data (MediatR, MyBatis, in-house)
```
Asset rule: what travels between projects is `extractors/ sinks/ sources/
semgrep-rules/ codeql-models/` (amortised). The per-project DB is NOT an asset.

---
## 3. Graph schema
See [`docs/SCHEMA.sql`](docs/SCHEMA.sql). Tables: `node` (incl. `kind=external`
for library symbols), `edge` (with provenance + mechanism), `source` (incl.
`stored` for second-order), `sink`, `boundary`, and `dependency` (SCA layer).

---
## 4. Agent architecture
Deterministic substrate: SQLite + `graphquery` CLI. Queries are SQL — never
proxied through a model.
```
[hunter] --Bash--> graphquery (CLI) --> SQLite          exact facts, 0 interpretation
    |
    +--bulk, isolate context--> [graph-agent (Haiku)] --> graphquery --> VERBATIM + summary
    |                            (context isolation only; never invents edges)
    +--judgement--------------> [model Phase 2/5] (disambiguate impl / label sink)
```
- Deterministic queries (callers, trace-back, why-unreachable, cve-check): hunter
  calls the CLI directly.
- Bulk jobs whose large output must stay out of the hunter's context: delegate to
  the graph-agent, which returns CLI output verbatim.
- Only Phase 2 (pick impl from candidates) and Phase 5 (semantic labels) use a
  model to "think".

---
## 5. Per-project process

### 5.0 Recon (~5 min)
Count files/languages. Inventory the dispatch mechanisms actually present
(mediatr? grpc? assembly-scan DI? reflection? event bus?) → enable only the
needed extractors. **BUILD GATE:** try `dotnet build` / `mvn compile`.
Pass → CodeQL enabled in 5.3. Fail → portable core.

### 5.1 Static facts (Phase 1 — no model, reproducible)
```
sqlite3 graph.db < docs/SCHEMA.sql
python toolkit/extractors/calls_direct_cs.py SRC | sqlite3 graph.db   # internal + external calls
python toolkit/extractors/routes_*.py     SRC | sqlite3 graph.db   # -> source
python toolkit/extractors/mediatr_cs.py      SRC | sqlite3 graph.db   # -> edge static-exact
python toolkit/extractors/di_cs.py    SRC | sqlite3 graph.db
python toolkit/extractors/spring_impl_java.py  SRC | sqlite3 graph.db
python toolkit/extractors/grpc_cs.py         SRC | sqlite3 graph.db   # -> boundary
python toolkit/extractors/reflection_cs.py   SRC | sqlite3 graph.db   # -> boundary
python toolkit/extractors/deps_cs.py         SRC | sqlite3 graph.db   # -> dependency (SCA)
python toolkit/load_sinks_cs.py sinks/cs.txt SRC | sqlite3 graph.db
```

### 5.2 Resolve edges (Phase 2)
- 1 candidate → auto-link `static-exact` (no model call).
- ≥2 candidates / unknown dispatcher → give the model ONLY that candidate list +
  annotations (`@Primary`/`@Qualifier`/config) → pick → record `model-inferred`.
  (answer space bounded to real candidates → no out-of-set hallucination)

### 5.3 Taint layer (Phase 3 — optional high-fidelity tier, degrades gracefully)
Engine results import into the same graph (`finding` table) and OUTRANK the regex
tier (precedence §6.5). If an engine is not installed, skip the step — you stay on
the regex tier (see docs/LIMITATIONS.md; treat "not reachable" with more care).
- semgrep (any stack, incl. PHP): `toolkit/build-semgrep.sh SRC graph.db [lang]`
- CodeQL (C#/Java/Python, needs build): `toolkit/build-codeql-cs.sh SRC graph.db`
- then: `graphquery findings all` — lists findings and CROSS-CHECKS them against the
  regex graph (an engine-confirmed sink the graph calls "not reachable" = a regex
  false-negative, L1).
- Always: grep sink-inventory as a triage baseline.

### 5.4 Hunt — bidirectional (Phase 4). `graphquery` verbs:
```
graphquery callers <node>          one step backward (works for external nodes too)
graphquery callees <node>          one step forward
graphquery trace-back <sink>       sink -> source (backward BFS)
graphquery trace-fwd  <source>     source -> sink (forward BFS)
graphquery meet <sink> <source>    meet-in-the-middle (fewest nodes explored)
graphquery why-unreachable <sink>  LIST the boundaries/leaves where BFS stopped   <-- core of §6
graphquery cve-check <lib.func>    SCA version + callers + call sites (see §5.6)   <-- addition #2
```
The taint engine covers the forward direction; `graphquery` covers backward + meet.

### 5.5 Label & prioritise (Phase 5)
Model labels sinks (unsanitised input?) and ranks paths. `agy-tracer` traces a
specific flow on demand — it does NOT build the index.

### 5.6 CVE / library triage (addition #2)
"CVE in function X of library L — are we vulnerable?" needs **three** ingredients;
the graph supplies only the middle one:
1. **Vulnerable version present?** → `dependency` table (from `deps_cs.py` + SCA tool).
2. **Is the vulnerable path called?** → `graphquery callers <L.func>` (fast filter).
3. **Are trigger preconditions met?** → read CVE detail + call site → model/manual.
`graphquery cve-check <lib.func>` combines (1)+(2) and lists call sites for (3).

**DATA-DRIVEN CVE TRAP** — apply §6 doubly. Many CVEs are triggered by *data*,
not by an explicit call to the vulnerable function:
- **Log4Shell**: you only call `log.info(userInput)`; `callers(jndiLookup)` in your
  code = 0, yet you ARE vulnerable.
- **Deserialization gadgets** (Json.NET `TypeNameHandling`, `BinaryFormatter`,
  SnakeYAML, Jackson default typing): the "call" is data.
For these, query usage of the library's **public entry API + config**
(`log.*`, `DeserializeObject` + `TypeNameHandling`), NOT the internal vuln
function. `0 callers` is NEVER "not vulnerable" here.

---
## 6. Verifying "not reachable" (sink→source) — MANDATORY
A "not reachable" from the database is NOT safe. Always verify; grep must TARGET
where the graph is blind (do not re-grep direct calls by function name — that just
repeats the blind spot):
1. **Read why BFS stopped** (`graphquery why-unreachable`):
   - dead-end at a leaf → more trustworthy, but still do step 2;
   - stopped at a BOUNDARY (reflection/gRPC/unmodeled dispatch/cross-service) →
     NOT concluded, verification mandatory.
2. **Targeted grep:**
   a. function/class name **as a string**     → reflection, bean-by-name, config key
   b. the **type** name (not the method)       → type-based dispatch (mediator/event/DI)
   c. in `*.xml *.yaml *.proto *.json *.config` → wiring outside code (Spring XML, MyBatis)
   d. same field/property/cache-key WRITTEN at A, READ at B → container flow + second-order/stored
   e. does the sink's method appear in any registration/handler-map/generic binding
3. **Run the other direction** (cheap): try source→sink forward from suspect entries.
4. **Label, never write "safe":**
   - "no static path, dead-end leaf, grep a–e clean" → unreachable (manual-verified)
   - "stopped at boundary" / any grep a–e hit        → NEEDS MANUAL TRACE (not dismissed)
   The database alone may only say "no static path found".
5. High-value endpoints (auth/payment/admin/file/cross-tenant) → ALWAYS reviewed
   manually regardless of result.

**Miss taxonomy (why false-negatives happen):** unmodeled dispatch;
reflection/string-key; wrong multi-impl pick; flow through libraries/containers;
async/delegate/event; cross-service gRPC; XML/YAML wiring; code-gen under
build-mode none; over-aggressive sanitizer models; missing source catalog
(especially STORED/second-order); missing sink catalog (in-house wrappers);
non-deterministic model disambiguation.

---
## 6.5 Source precedence, conflicts & corrections
When sources disagree, resolve by this ladder (highest trust first). The rule is
**tools propose, source code disposes** — a tool result is a lead, verification
against the actual code is truth.

1. **Hand verification of the source code** at the site — ground truth.
2. **High-fidelity static** (CodeQL / Roslyn, build tier) — type-resolved.
3. **Semgrep taint** (configured rules).
4. **The graph (regex tier)**, internally ordered by provenance:
   `static-exact > static-candidate > model-inferred` (and `manual-verified`
   from the overlay ranks with hand verification).
5. **Catalogs / heuristics** (sink lists) — candidates only.

A higher tier does **not** silently override a lower one — CodeQL has
false-negatives too. A disagreement is a flag to verify, never an auto-resolve.

**Conflict rules**
- Graph says *reachable*, code review shows a real guard/sanitizer/dead code →
  **code wins**; refute the edge/path (prune false-positive), record the reason.
- Graph says *not reachable*, but verification (grep / other direction / CodeQL)
  finds a path → the graph **missed an edge**; add it (manual-verified) and note
  the mechanism — also a signal to extend an extractor.
- Two tools disagree → **UNRESOLVED**; escalate to hand verification, never
  auto-pick.
- **Safety bias** (ties to the golden rule): while unresolved, treat as
  *potentially reachable / needs review*, never as *safe*.

**Corrections — the self-correcting overlay (never mutate extracted facts)**
Agents/humans correct the graph through a separate `override` layer, so machine
facts and human corrections never mix and survive re-extraction:
```
graphquery annotate-add    <src> <dst> --reason R [--evidence f:line] [--mech reflection] [--author id]
graphquery annotate-refute <src> <dst> --reason R [--evidence f:line] [--author id]
graphquery overrides        # audit trail
```
- `add`    — an edge confirmed by hand that extraction missed (e.g. a resolved
  reflection/gRPC boundary). Traversal includes it, tagged `manual-verified`, and
  any path using it is flagged "uses a manual override".
- `refute` — a (src,dst) edge proven wrong (e.g. regex-tier over-merge). Excluded
  from traversal, **kept** for audit (not deleted).
Every override carries reason + evidence + author + timestamp. Re-running the
extractors regenerates the fact layer; the overlay persists and is re-applied.
**Recurring overrides of the same shape are the harvest signal** → upgrade the
extractor (§8), don't keep patching by hand.

---
## 7. Benchmark (projects with known answers — measure yourself)
With ground truth (e.g. a prior findings list): map each known bug → expected
sink/source, run the workflow, and for each bug ask "did it report reachable?".
- correctly reachable → good recall.
- "not reachable" but real → a BLIND SPOT: patch the extractor/sink/source and
  re-run. This quantifies the workflow's trustworthiness before client use.

---
## 8. Cleanup & handover (engagement close)
**DISCARD** (per-project, contains client code = client data; follow the
data-handling policy): `graph.db`, semgrep/CodeQL output, CodeQL database, temp
trace files, client source.
**KEEP** into `toolkit/` (harvest reusable improvements): new extractors for new
dispatch mechanisms; new `sinks/`/`sources/` entries; new semgrep rules / CodeQL
models; newly discovered boundary types.
**Checklist:** stop all graph-agent/hunter processes; delete DB + outputs; commit
only the `toolkit/` diff (shared assets, NO client data); confirm no client source
remains outside the permitted area.

---
## Roadmap
- [ ] `docs/SCHEMA.sql` — done
- [ ] `toolkit/sinks/*.txt` — done (csharp/java/php/python)
- [ ] `toolkit/graphquery` CLI (callers/callees/trace/meet/why-unreachable/cve-check)
- [ ] `toolkit/extractors/` — start with mediatr_cs.py, routes_cs.py, calls_direct_cs.py, deps_cs.py
- [x] `toolkit/semgrep-rules/` — starter taint rules (cs + php) + importer + `findings`
- [x] CodeQL wrapper + SARIF importer; [ ] MediatR QL additional-step (open, see toolkit/codeql/README.md)
- [ ] Benchmark harness against a ground-truth project
