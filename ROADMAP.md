# HKOS Roadmap

## Current release

**v1.2.0** (released 2026-09-08) provides a deterministic JSON Repository
as the single source of truth, MCP and CLI interfaces, typed relations, a
SQLite index/query backend, cross-project graph traversal, and more than
1,000 automated tests.

## Released

### v1.0 — Foundation

- JSON Repository as the canonical source of truth.
- Projects, campaigns, knowledge lifecycle, deterministic retrieval, context,
  snapshots, migrations, backup/rollback, and performance instrumentation.
- Crash-safe writes and system-level qualification.

### v1.1 — Adoption and graph authoring

- MCP server and `hkos` CLI.
- Typed relation authoring with cross-project targets.
- Deterministic classification transparency and Failure-Priority ranking.
- Cursor/Windsurf presets and LangChain/AutoGen integration examples.

### v1.2 — SQLite index and cross-project traversal

- Optional SQLite **index/query backend** with WAL and per-entity delta writes.
- Explicit JSON-to-SQLite index migration while the JSON Repository remains
  the SSOT.
- Query Contract Q1–Q5 parity across JSON and SQLite indexes.
- Deterministic cross-project relationship traversal.

## Next: v1.3 — Knowledge Integrity

The next release implements the contract defined by
[ADR-001](docs/design/adr-001-knowledge-integrity-contract.md):

- one lifecycle-status vocabulary;
- CANONICAL-only default retrieval eligibility;
- the same eligibility rules for graph-expanded candidates;
- agent observations remain NEW by default;
- separate verification and canonicalization actions;
- ranking correctness and retrieval observability.

These items are target behavior, not claims about v1.2.0.

## Later

- Entity revisions and optimistic concurrency.
- Evidence-rich provenance and temporal knowledge.
- Retrieval-quality benchmarks and regression gates.
- A candidate-provider extension point with optional semantic retrieval.
- Diversity-aware selection and shared multi-agent governance.

## Principles that will not change

- The JSON Repository is the SSOT; indexes, snapshots, manifests, and caches
  are rebuildable projections.
- The Librarian remains the knowledge write-policy boundary.
- Canonicalization and retrieval eligibility contain no LLM calls.
- Query Contract Q1–Q5 remains frozen.
- Optional semantic retrieval may propose candidates but cannot define truth.
- Evolution within 1.x remains additive and backward compatible.
