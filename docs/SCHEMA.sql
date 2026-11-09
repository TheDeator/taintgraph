-- taintgraph : SQLite schema (key-based)
-- Load: sqlite3 graph.db < docs/SCHEMA.sql
--
-- Design note: nodes are identified by a NATURAL TEXT KEY (not an autoincrement
-- id). This lets every extractor run independently and emit INSERTs that
-- reference other nodes by key, with no id coordination — the plug-in contract
-- in docs/EXTRACTORS.md. Keys are fully-qualified where possible
-- (Namespace.Class.Method); library symbols are kind=external.

CREATE TABLE node(
  key   TEXT PRIMARY KEY,   -- Namespace.Class.Method  (or bare name / Type.Method for external)
  kind  TEXT,               -- method | controller | handler | type | external
  name  TEXT,               -- simple name
  type  TEXT,               -- declaring type / namespace
  file  TEXT,               -- NULL for external / unresolved
  line  INTEGER
);

CREATE TABLE edge(
  src        TEXT,          -- node.key of caller
  dst        TEXT,          -- node.key of callee (may be external / bare)
  mechanism  TEXT,          -- direct | mediatr | di | spring | event | grpc | reflection
  provenance TEXT,          -- static-exact | static-candidate | model-inferred
  file       TEXT,
  line       INTEGER
);

CREATE TABLE source(
  node   TEXT,              -- node.key of the entry method
  kind   TEXT,              -- route | header | body | query | stored
  detail TEXT               -- e.g. "POST /api/vpc/create"
);

CREATE TABLE sink(
  node     TEXT,            -- node.key of the method that calls the dangerous API
  category TEXT,            -- sqli | cmdi | path | deser | ssrf | xxe | ssti | ldap | redirect | code
  api      TEXT
);

CREATE TABLE boundary(
  node   TEXT,
  reason TEXT,              -- reflection | grpc-cross-service | unmodeled-dispatch | assembly-scan-di | config-wiring
  file   TEXT,
  line   INTEGER
);

CREATE TABLE dependency(
  name       TEXT,
  version    TEXT,
  ecosystem  TEXT,          -- nuget | maven | composer | pypi
  file       TEXT,
  vulnerable INTEGER DEFAULT 0,
  advisory   TEXT
);

CREATE INDEX i_edge_src    ON edge(src);
CREATE INDEX i_edge_dst    ON edge(dst);
CREATE INDEX i_node_name   ON node(name);
CREATE INDEX i_sink_node   ON sink(node);
CREATE INDEX i_source_node ON source(node);
CREATE INDEX i_dep_name    ON dependency(name);

-- Self-correcting overlay (never mutates extracted facts; see WORKFLOW.md §6.5).
-- action='add'    : an edge an agent/human confirmed by hand that extraction missed.
-- action='refute' : a (src,dst) edge proven wrong; excluded from traversal, kept for audit.
-- Survives re-running extractors, so machine facts and human corrections never mix.
CREATE TABLE IF NOT EXISTS override(
  src TEXT, dst TEXT,
  action    TEXT,   -- add | refute
  mechanism TEXT,   -- for add: how it was resolved (reflection, manual, ...)
  reason    TEXT,
  evidence  TEXT,   -- file:line or note
  author    TEXT,
  ts        TEXT
);
CREATE INDEX IF NOT EXISTS i_ovr_src ON override(src);
CREATE INDEX IF NOT EXISTS i_ovr_dst ON override(dst);

-- High-fidelity engine results (CodeQL/semgrep), imported by toolkit/import_findings.py.
-- They carry higher trust in the precedence ladder (WORKFLOW.md §6.5) — a READING
-- discipline, not a weight graphquery computes (traversal is unweighted). `node` links
-- a finding to the enclosing method when resolvable, enabling cross-check vs the graph.
CREATE TABLE IF NOT EXISTS finding(
  tool       TEXT,   -- codeql | semgrep
  rule       TEXT,
  severity   TEXT,
  file       TEXT,
  line       INTEGER,
  message    TEXT,
  node       TEXT,   -- resolved enclosing method key (may be NULL)
  provenance TEXT    -- codeql | semgrep  (high trust)
);
CREATE INDEX IF NOT EXISTS i_finding_node ON finding(node);
