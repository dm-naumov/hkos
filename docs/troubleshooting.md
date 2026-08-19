# HKOS Troubleshooting

## Diagnostics

- Logs: hkos/logs/hkos.log; performance: logs/performance.log; audit: AuditLogger.
- Integrity checks: IndexEngine.validate(project), MigrationValidator.validate(target),
  assert_snapshot_consistent (counters vs repository).

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| MigrationError: lock | active/stuck lock | stale > 30 min auto-releases; otherwise delete migration.lock |
| Retrieval misses knowledge | index not updated | IndexEngine.update/rebuild |
| Snapshot counters ≠ repository | stale snapshot | SnapshotEngine.create(force=True) |
| StorageSerializationError | corrupted JSON file | restore from backup; otherwise remove the corrupted file (loses 1 record) |
| Index read failure | broken .idx | IndexEngine.rebuild(project) |
| Slow detect (100K+) | envelope scan | VersionManifest (refreshed after migrations) |
| Retrieval perf test >100 ms under load | known flake (SLA under full suite) | run in isolation; index cache (DS-013) |

## Recovery after a failure

1. Restore repository from (external) backup → 2. Index rebuild → 3. Snapshot
   regenerate → 4. MigrationValidator.validate → 5. Retrieval check.

## Index recovery

```python
ctx.index.rebuild(project_id)   # full rebuild from the repository
```
