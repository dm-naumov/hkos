# HKOS Architecture

## Layered scheme (dependencies strictly downward)

```
core <- storage <- repository <- index <- retrieval/context/snapshot
      <- services (project/campaign/librarian/memory) <- migration
      <- integration (Hermes) ; performance (core only) ; kernel (shared bottom)
```

## Components

- **core**: configuration (ConfigLoader, development/production profiles), logging, versions, exceptions.
- **storage**: StorageEngine + JSONStore (file storage, HKOS-08 envelopes); the only access to the filesystem.
- **repository**: RepositoryManager + BaseRepository (projects/campaigns/knowledge/decisions/artifacts). **The repository is the single source of truth (SSOT)**; only services write through it.
- **index**: IndexEngine (build/rebuild/update/remove/validate/statistics) + Query Contract Q1–Q5 (IndexQueryExecutor, IndexSnapshot) + IndexCache (internal parse cache). Два официальных бэкенда персистентности (конфиг `hkos.index.backend`): JSON `*.idx` (default — человекочитаемый, git-diff) и SQLite `indexes/index_store.db` (DS-017 v1.2): дельта-записи O(размер сущности) в транзакциях WAL, Q1–Q5 исполняются SQL, миграция — только явной командой `hkos migrate`. SSOT (repository) не затрагивается ни одним бэкендом.
- **retrieval**: RetrievalEngine (query → candidates → ranking → explanation); reads ONLY the index and the repository by UUID. RelationshipTraverser (Q4) обходит связи; кросс-проектные цели (`target_project_id`) — через снапшоты целевых проектов (детерминированный BFS, DS-017 v1.2).
- **context**: ContextBuilder (task/project/campaign/snapshot → ContextDocument); SnapshotLoader.
- **snapshot**: SnapshotEngine (create/load/history) — a derived representation of the repository (classification via the entity index + classification_policy).
- **services**: ProjectManager, CampaignManager (FSM), Librarian (register/update/canonicalize/archive/restore/reject/validate), MemoryService (full-cycle orchestration), classification_policy (single source of categories).
- **migration**: MigrationEngine (7 methods) → MigrationManager (FSM) + Registry/Detector/Executor/Backup/Rollback/Validator/History/VersionManifest. A maintenance layer; imported by nobody except integration.
- **integration**: Hermes adapters (MigrationTools/Commands), security (permissions/AgentLock/AgentContext), audit, fallback, schemas.
- **performance**: PerformanceManager + MetricsEngine/LatencyTracker/Profiler/ResourceMonitor/CacheManager/ContextOptimizer/integration wrappers. Measurement only; zero business logic.
- **kernel**: SnapshotDocument (shared type).


## Knowledge Integrity Contract

Target integrity contract for lifecycle, retrieval eligibility and the
write path — see
[ADR-001 — Knowledge Integrity Contract](design/adr-001-knowledge-integrity-contract.md).
v1.2.0 implements it incrementally; known deviations are tracked as
KI-001…KI-009 with characterization and executable contract tests.

- Repository is canonical (SSOT); indexes/snapshots/manifests/caches are
  rebuildable derived projections.
- Retrieval eligibility is explicit: ordinary retrieval/agent context
  admits CANONICAL only (positive rule, not a denylist).
- Graph traversal cannot bypass eligibility: relation-added candidates
  pass the same policy as direct candidates.
- Observation is not canonical knowledge: agent writes start as NEW;
  verification (NEW → VERIFIED) and canonicalization (VERIFIED → CANONICAL)
  are separate actions.
- One authoritative status vocabulary (uppercase); legacy lowercase values
  are normalized at the read boundary only.
- Revision, temporal validity and provenance are planned additive
  extensions; retrieval explanation (why_retrieved) is distinct from
  provenance/trust (why_trusted).
- Semantic retrieval, when added, is a candidate provider only — never a
  source of truth, never required by the deterministic core.

## Key invariants

- Repository = SSOT; Index/Snapshot/Manifest/Cache are derived (rebuildable).
- The Librarian is the only write path for knowledge.
- Migration: FSM IDLE→…→COMPLETED/FAILED; rollback restores the repository, derived artifacts are regenerated.
- The performance layer never changes data, ordering, or results.
