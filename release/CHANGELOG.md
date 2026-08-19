# HKOS Changelog

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
