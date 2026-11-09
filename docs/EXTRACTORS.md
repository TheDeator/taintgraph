# Extractor plug-in contract

An extractor reads a source tree and emits SQL on **stdout**, piped into the
graph: `python toolkit/extractors/<name>.py SRC | sqlite3 graph.db`. Any
extractor in any language is interchangeable as long as it obeys this contract —
`graphquery` and the schema never change. This is what lets a new stack be
supported by *writing a new extractor*, nothing else.

## Output
- Plain SQL `INSERT` statements, UTF-8, on stdout.
- Wrap the batch in `BEGIN;` ... `COMMIT;` for speed.
- Reference nodes by their **natural key** (see below). Never allocate ids.
- Emit `INSERT OR IGNORE INTO node(...)` for every endpoint you reference, so an
  extractor is self-sufficient regardless of run order.

## Node key convention
- Internal symbol: `Namespace.Class.Method` (fully qualified where resolvable).
- External/library symbol: `Type.Method` (or bare name), `kind='external'`,
  `file=NULL`.
- Over-merging (e.g. two overloads sharing a key) is acceptable: it over-connects
  the graph, which errs toward NOT missing a path — the safe direction. Never
  under-connect to look precise.

## What each extractor type emits
| Type | Tables | mechanism / provenance |
|------|--------|------------------------|
| Direct-call   | `node`, `edge` | `direct` / `static-exact` |
| Virtual-edge  | `node`, `edge` | `mediatr\|di\|spring\|event` / `static-exact` (1 target) or `static-candidate` (≥2) |
| Source anchor | `node`, `source` | — (marks an entry point) |
| Sink loader   | `node`, `sink` | — (marks a dangerous method) |
| Boundary      | `node`, `boundary` | — (records WHERE the graph goes blind) |
| Dependency    | `dependency` | — (SCA layer for CVE triage) |

## Rules
1. **Resolve statically or flag — never guess.** If dispatch resolves to exactly
   one target by type → emit a `static-exact` edge. If it resolves to several →
   emit each as `static-candidate` (a model picks later, recorded `model-inferred`).
   If it cannot be resolved statically (reflection, string key, cross-service) →
   emit a `boundary` row, not a fabricated edge.
2. **Provenance is mandatory** on every edge.
3. **Idempotent.** Re-running on the same tree must not corrupt the graph
   (`INSERT OR IGNORE` on nodes; edges may duplicate — queries use DISTINCT).
4. **Language-specific, contract-generic.** Parsing C# vs Java vs Python differs
   (even for direct calls), but the emitted rows are identical in shape.

## Shared helper
`toolkit/extractors/parse_cs.py` provides comment/string scrubbing, brace
matching and a method iterator for the C# extractors. A new language brings its
own parser (Python's stdlib `ast`, tree-sitter/JavaParser for Java) but emits the
same rows.

## Fidelity tiers
- **Regex tier** (these scripts): no build required, runs on broken/partial
  source. Direct-call receiver *types* are not resolved, so deep direct-call
  chains are approximate; the strong, type-bound edges (routes, MediatR) are
  exact. Good for triage and for the MediatR-backbone trace.
- **Roslyn/CodeQL tier**: full type resolution; upgrade path when the project
  builds. Same schema, higher-fidelity edges.

## Naming convention (one file per language — decided up front)
Every extractor and its language-specific resource carries a **language suffix**;
language-agnostic components carry **none**. Adding a stack means writing new
`_<lang>` files, never editing a C# file to also handle Java.

`lang` tokens: `cs` (C#/.NET), `java`, `php`, `py` (Python).

| component | C# (done) | Java (future) | PHP (future) |
|-----------|-----------|---------------|--------------|
| parser helper | `parse_cs.py` | `parse_java.py` | `parse_php.py` |
| direct calls | `calls_direct_cs.py` | `calls_direct_java.py` | `calls_direct_php.py` |
| virtual edge | `mediatr_cs.py`, `di_cs.py` | `spring_impl_java.py` | — |
| source anchor | `routes_cs.py` | `routes_java.py` | `routes_php.py` |
| boundary | `grpc_cs.py`, `reflection_cs.py` | `reflection_java.py` | — |
| sink loader | `load_sinks_cs.py` | `load_sinks_java.py` | `load_sinks_php.py` |
| dependencies | `deps_cs.py` | `deps_java.py` (pom/gradle) | `deps_php.py` (composer) |
| sink catalog | `sinks/cs.txt` | `sinks/java.txt` | `sinks/php.txt` |
| build script | `build-graph-cs.sh` | `build-graph-java.sh` | `build-graph-php.sh` |

**No suffix (shared across all languages):** `graphquery`, `docs/SCHEMA.sql`.
These never change when a language is added — only new `_<lang>` extractors plug
into the same schema and the same query CLI.

## Virtual-edge specs (the type-bound edges that beat grep)
These are statically resolvable but invisible to a naive call-graph — the highest-
value extractors. Build them from these specs (do not rely on a shipped reference;
none is public). Each binds by TYPE, not by a named call.

### .NET — MediatR (`mediatr_cs`)
Call site: `_mediator.Send(new FooCommand(...))` / `Publish(new FooEvent(...))`.
Bind to the handler by the command/event TYPE: a class
`FooHandler : IRequestHandler<FooCommand, TResult>` (or `INotificationHandler<FooEvent>`).
Edge: enclosing method of the Send -> `FooHandler.Handle`. One handler = static-exact;
several = static-candidate. (A plain call-graph only sees a call to `IMediator.Send`.)

### .NET — DI interface->impl (`di_cs`)
A class consumes a dependency typed as an INTERFACE, injected by constructor/field
(`private readonly IFoo _foo;`). A call `_foo.Bar(...)` has receiver declared type
`IFoo`; the real target is the registered impl's `Bar`. Resolve the interface->impl
map from (a) `class Foo : IFoo` declarations and/or (b) DI registrations
`services.AddScoped/AddTransient/AddSingleton<IFoo, Foo>()`. Edge: caller -> `Foo.Bar`.
One impl = static-exact; several = static-candidate (disambiguate later via a model /
`[FromKeyedServices]` / config). NOTE: this needs per-class field/param TYPE
resolution — exactly the receiver-typing the pure bare-name `calls_direct` tier
lacks (that is L1 in docs/LIMITATIONS.md). Expect to resolve receiver types here or
your deep direct-call chains will under-connect and produce false "not reachable".

### Spring — interface->impl (`spring_impl_java`)
Same shape in Java: an `@Autowired`/constructor-injected interface field resolves to
its `@Service`/`implements` impl. Edge: caller -> `Impl.method`. One impl =
static-exact; several = static-candidate.

### Not statically resolvable -> flag a boundary, never fabricate
Reflection (`Activator.CreateInstance`, `Type.GetType(...).Invoke`), string-keyed
lookups, cross-service gRPC, config/XML wiring: emit a `boundary` row (reason), not
an edge. A verified-by-hand edge is added later via `graphquery annotate-add`.

## Entry-point (source) mechanisms — inventory per project
Edges are only half the model; SOURCES are the other half, and a reduction's
completeness depends on them. The `routes_*` extractor ships modelling only
MVC/attribute routes. Inventory the project's entry-point types and extend the
source extraction to cover each one it uses (symmetric to the dispatch inventory):

| entry type | how to detect | source to emit |
|------------|---------------|----------------|
| MVC route | `[HttpGet/Post...]`, `@*Mapping` | `routes_<lang>` (shipped pattern) |
| Razor Page | `.cshtml.cs` with `OnGet/OnPostAsync` | `sources_razor_<lang>` — key the handler, detail = page path |
| gRPC method | class `: *.XxxBase` service impl | source kind='grpc' (its request carries remote input) |
| hosted/bg service | `IHostedService` / `BackgroundService.ExecuteAsync` | source kind='background' |
| message/event consumer | `@EventListener`, `INotificationHandler`, consumer base | source kind='message' |
| webhook | a route marked `[AllowAnonymous]` taking external callbacks | route, flag unauthenticated |

A sink reachable only from an un-modelled entry shows "not reachable" (false
negative). See docs/LIMITATIONS.md L6 and docs/AGENT_NOTES.md §H.
