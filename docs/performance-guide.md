# HKOS Performance Guide

## SLA budgets (DS-013/014)

| Operation | Budget |
|---|---|
| Retrieval cold | <100 ms (10K); warm (cache) ~0.03 ms |
| Context build | <200 ms |
| Snapshot load | <50 ms |
| Save | <150 ms |
| Migration detect (100K) | <100 ms (with VersionManifest) |
| Migration backup / rollback / validate | <5 s / <10 s / <10 s |
| Profiler / metrics overhead | <2 ms / <1 ms |

## Mechanisms

- **IndexCache** (index/): parsed IndexSnapshot per project; fingerprint
  (mtime/size); invalidated on update/rebuild. Warm queries: 2120× faster than cold.
- **CacheManager** (performance/): retrieval results (LRU + TTL 3600, max 1000).
- **VersionManifest** (migration/): schema versions without a full scan
  (detect 1470 ms → <25 ms).
- **ContextOptimizer**: profiles NONE/LIGHT/NORMAL/AGGRESSIVE; protected
  categories (DECISIONS/FAILURES/CONFIGURATION/OPEN QUESTIONS) are never compressed.

## Observability

- PerformanceManager: measure/profile/statistics (count/avg/min/max, p50/p95/p99)/health/optimize.
- ResourceMonitor: RAM/CPU/repository/index/snapshot/cache sizes.
- logs/performance.log: PROFILING_STARTED/FINISHED, METRIC_RECORDED, RESOURCE_WARNING.

## Scaling

- 100K knowledge: generation 19.4 s; RAM 85 MB; retrieval <100 ms.
- 1M: mechanism validated (200K in-session); full run is a dedicated window
  (HKOS_STRESS_SCALE=1000000).
- Cold retrieval costs O(index) — paid once per (project, fingerprint); warm is O(1).
