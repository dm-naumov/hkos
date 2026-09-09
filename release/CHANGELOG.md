# HKOS Changelog

## [1.2.0] — 2026-09-08 (feature release, DS-017 v1.2)

### Maintenance — release consistency

- Synchronized active release metadata and roadmap with v1.2.0.
- Clarified that SQLite is a derived index/query backend while the JSON
  Repository remains the SSOT.
- Added a CI architecture gate for version and active-document consistency.

### Added — SQLite index backend (IP-017-v1.2, ЭТАПЫ 1–3)

- `SqliteIndexStore`: second official Index Layer backend — one
  `indexes/index_store.db` per project (stdlib sqlite3, zero new deps,
  WAL). Full IndexStore contract: read/write/exists/delete/list_names/
  fingerprint; the five JSON index docs are mirrored 1:1 (order-preserving).
- Delta write path: `update_entity`/`remove_entity` replace one entity's
  rows in a single transaction — O(entity size), not O(corpus); index
  update through `IndexEngine` is routed to the delta automatically.
  Measured on an equal stand: ~73× faster than the full `.idx` rewrite
  over 2000 sequential updates.
- SQL query layer: `SqliteIndexSnapshot` executes Q1–Q5 as SQL (B-tree
  seek) behind the frozen IndexSnapshot interface; no parse, no cache.
- Selection by config: `hkos.index.backend: json|sqlite` (json default);
  honored by the MCP context and the CLI. SSOT stays plain JSON.
- `hkos migrate [--project] [--check] [--force]` — explicit JSON→SQLite
  index migration (no automatic trigger, per DS-017); `--check` dry run,
  re-runs skip migrated projects unless `--force`.
- Fix: empty `entity_words`/`entity_tags` markers (`id: []`) were lost in
  SQLite — seq=-1 marker rows restore exact JSON parity.

### Added — cross-project graph traversal (IP-017-v1.2, ЭТАП 4)

- `RelationshipTraverser` is project-aware: BFS carries each node's
  project; edges are read from the node's own project snapshot and
  cross-project targets (`target_project_id`) are resolved through the
  target project's snapshot (`snapshot_provider`); retrieval wires it in.
- Relations index records now carry `target_project_id` (additive; `""`
  = intra-project); SQLite `rel` gained the column with a safe upgrade of
  existing databases (ALTER TABLE ... DEFAULT '').
- Authoring fix: edges without `source_id` were dead for traversal
  (`out[""]`) — `Librarian.validate_relations` now normalizes source to
  the owner and generates a missing `relation_id`.

### Fixed

- Relations authoring produced unreachable edges when `source_id` was
  omitted (previous release gap) — see above.

## [1.1.0] — 2026-09-08 (feature release, DS-017 v1.1)

### Added — graph authoring (DS-017, IP-017 ЭТАПЫ 1–3)

- `KnowledgeRelation.target_project_id` (additive; `""` = intra-project edge)
  — cross-project edges are now representable and validated (full traversal
  is roadmap v1.2).
- `RelationType` +3 engineering semantics: `BASED_ON`, `CAUSED_BY`,
  `MITIGATED_BY` (ФАКТ → РЕШЕНИЕ → СБОЙ traceability).
- `relations[]` in `save` (API + MCP): typed links to existing entities;
  deterministic validation in the Librarian (target exists — including
  cross-project — no self-loops); invalid links are dropped with reasons in
  `warnings`, never silently. `Librarian.validate_relations()` soft path;
  `register`/`update` strict backstop.
- Doctor: 5th check group `relations FK: dangling links` — flags dangling
  edges (same-project and cross-project), PASS/FAIL with examples.

### Added — save transparency (IP-017 ЭТАП 4)

- `KnowledgeClassifier.classify_with_rule()` returns stable rule ids
  (`rule:kind:negative`, `rule:marker:<CATEGORY>`, `rule:default:fact`);
  `Librarian.explain_category()` exposes the same decision pre-save.
- MCP `save` reports category overrides/invalid hints in `warnings` with the
  rule id — no more silent reclassification.

### Added — CLI & packaging (IP-017 ЭТАП 5)

- New `hkos` console script / `python -m hkos.cli`: `doctor` (exit 0/1/2/3),
  `status`, `validate`; `scripts/doctor_cli.py` is now a thin wrapper.
- `FileSnapshotPersistence` consolidated to `hkos.snapshot.file_persistence`
  (single canonical backend; `mcp_server.persistence` re-exports it).

### Added — ecosystem (IP-017 ЭТАП 6)

- IDE presets: `examples/cursor-mcp.json`, `examples/windsurf-mcp.json`;
  framework wiring in `examples/integrations.md` (LangChain / AutoGen).
- Demo «Git for agent memory»: `examples/demo_failure_recovery.py`.
- README «Ecosystem & integrations» section.

### Added — Failure Priority ranking (IP-017 ЭТАП 7)

- Deterministic `failure` ranking factor: knowledge with `kind=negative` /
  category FAILURE ranks above otherwise-equivalent candidates (weight
  `retrieval.ranking.failure_weight`, default 0.05); reason label
  «Failure Priority». Previously claimed but not implemented — now real and
  covered by tests and the demo.

## [1.0.1] — 2026-08-19 (patch)

### Fixed

- `LatencyTracker.percentile()` crashed with `statistics.StatisticsError`
  ("must have at least two data points") on a single measurement under
  Python 3.12 (the supported target; 3.14's stdlib masked it). A single
  sample now returns its own value — any percentile of one point is that
  point. Covered by `test_performance_manager` / `test_performance_integration`.

### CI

- Wall-clock SLA latency tests are marked `@pytest.mark.sla` and moved out of
  the default jobs into a dedicated informational `Perf SLA` job (2-core CI
  runners can miss <100 ms budgets). The PR gate (`verify`) is now stable.

## [1.0.0] — 2026-08-19 (public release)

### Added (since RC1)

- Public release preparation: English documentation set (README + 8 guides),
  publish-ready packaging (pyproject metadata, wheel/sdist), examples/quickstart.py.
- Version aligned to 1.0.0 across code, configuration and release artifacts.

### Added (1.0.0-prod RC1, 2026-08-07)

- DS-011 Migration Engine (Rev 1.2): 7 methods, FSM, backup/rollback,
  VersionManifest, migration lock.
- DS-012 Hermes Integration: tools/commands/schemas/security
  (AgentLock/permissions)/audit/fallback.
- DS-013 Performance Layer: MetricsEngine/LatencyTracker/Profiler/
  ResourceMonitor/CacheManager/ContextOptimizer + integration wrappers.
- DS-013 Stage 2: VersionManifest (detect 1470 ms → <25 ms at 100K).
- DS-013 Stage 3: IndexCache (warm 2120× faster than cold).
- DS-014: system qualification (51+ system tests; 100K stress; long-running).
- DS-015: production config, documentation (8 guides), operational procedures, sign-off.
- Post-Audit Refinement: classification_policy (unified classification),
  kernel/SnapshotDocument.

### Fixed (DS-015 Stage 4)

- O(N²) index build (KeywordIndex/TagIndex dedup) → O(1) set-dedup:
  build 30K 84.6 s → 1.5 s.
- MigrationEngine.rollback(): target-detect ordering (state-leak FAILED).
- Campaign memory: retrieval status filter (negative knowledge requires
  canonicalization).

### Security

- SSOT repository preserved at every stage; kill -9 safe (atomic writes).
