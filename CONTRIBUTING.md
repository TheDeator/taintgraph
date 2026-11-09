# Contributing — including by AI agents

**This methodology is a hypothesis, not gospel.** Nothing guarantees the
architecture is correct; there may be bugs in the extractors, unsound principles,
or things the schema cannot express. Finding and fixing those is a first-class
contribution — and an AI agent using this framework is **explicitly invited** to
do it, not to silently work around a flaw.

## Three levels of "something is wrong" — route each correctly
1. **A fact in THIS project's graph is wrong** (a missed or false edge).
   → fix in the **overlay**: `graphquery annotate-add/annotate-refute` with reason
   + evidence. Per-project, audited, never touches shared code. (AGENT_NOTES §E)
2. **An extractor systematically produces wrong rows** (misses a dispatch
   pattern, over-merges, mis-parses). Signal: you keep making the same overlay
   correction. → fix the `*_<lang>` extractor (toolkit) per `docs/EXTRACTORS.md`.
   This is a **contribution**, not a per-project patch.
3. **The methodology/architecture itself is flawed** (a principle is unsound, the
   schema can't model something, the precedence/provenance rule gives wrong
   calls, a stated claim is false). → this is the most valuable report. Record it
   (below) with a concrete **counterexample**, then propose a change to
   `WORKFLOW.md` / the principles.

## How to report / contribute
- Add an entry to [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) with: **what** is
  wrong, a **minimal counterexample** (inputs → wrong output), **impact**
  (false-negative? token cost? wrong trust call?), and **status** (open/fixed).
- For a fix: change the extractor/doc, add or update the counterexample, and note
  it in LIMITATIONS. Keep per-project data out of the repo.
- Prefer a failing example over prose. "Here is code the graph traces wrong" beats
  "I think X might be off".

## The bar: does the change serve the three goals?
Every change must make tracing **faster, more accurate, or cheaper in tokens**
(see START_HERE). A change that adds machinery without serving those — or that
makes the graph so noisy it costs more tokens than grep — is a regression, even
if it is "more complete". Over-connection (the deliberate safe-direction bias) is
itself on trial: if it explodes traces and wastes tokens, that is a bug to report.
