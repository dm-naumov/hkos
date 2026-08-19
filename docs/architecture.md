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
- **index**: IndexEngine (build/rebuild/update/remove/validate/statistics) + Query Contract Q1–Q5 (IndexQueryExecutor, IndexSnapshot) + IndexCache (internal parse cache).
- **retrieval**: RetrievalEngine (query → candidates → ranking → explanation); reads ONLY the index and the repository by UUID.
- **context**: ContextBuilder (task/project/campaign/snapshot → ContextDocument); SnapshotLoader.
- **snapshot**: SnapshotEngine (create/load/history) — a derived representation of the repository (classification via the entity index + classification_policy).
- **services**: ProjectManager, CampaignManager (FSM), Librarian (register/update/canonicalize/archive/restore/reject/validate), MemoryService (full-cycle orchestration), classification_policy (single source of categories).
- **migration**: MigrationEngine (7 methods) → MigrationManager (FSM) + Registry/Detector/Executor/Backup/Rollback/Validator/History/VersionManifest. A maintenance layer; imported by nobody except integration.
- **integration**: Hermes adapters (MigrationTools/Commands), security (permissions/AgentLock/AgentContext), audit, fallback, schemas.
- **performance**: PerformanceManager + MetricsEngine/LatencyTracker/Profiler/ResourceMonitor/CacheManager/ContextOptimizer/integration wrappers. Measurement only; zero business logic.
- **kernel**: SnapshotDocument (shared type).

## Key invariants

- Repository = SSOT; Index/Snapshot/Manifest/Cache are derived (rebuildable).
- The Librarian is the only write path for knowledge.
- Migration: FSM IDLE→…→COMPLETED/FAILED; rollback restores the repository, derived artifacts are regenerated.
- The performance layer never changes data, ordering, or results.
