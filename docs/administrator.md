# HKOS Administrator Guide

## Start and stop

- Initialization: StorageEngine.initialize() — idempotent.
- Log: hkos/logs/hkos.log (rotation max_size_mb/backup_count).
- Production profile: ConfigLoader(profile="production").

## Backup (DS-015)

Mandatory set: the repository (projects/), configuration, migration history.
Index/Snapshot are derived: they are regenerated (zero data loss; only
snapshot versions/reasons are lost).

## Migrations (DS-011)

- Run: MigrationEngine.migrate() (creates a backup before any change).
- Rollback: MigrationEngine.rollback() — restores the repository; Index/Snapshot
  are regenerated automatically (F-2 lifecycle).
- Migration log: append-only (do not edit).
- Lock: migration.lock file; stale threshold 30 minutes (auto-release).

## Health

- IndexEngine.validate() — index integrity.
- SnapshotEngine.validate / MigrationValidator — derived-state consistency.
- PerformanceManager.health() / optimize() — metrics, recommendations, warnings.

## Monitoring

- Performance layer: logs/performance.log (append-only).
- ResourceMonitor: RAM/CPU/repository/index/snapshot/cache sizes.

## Change rollback procedure (mandatory BEFORE system work)

1. Take a backup of the repository + config + history.
2. Record the current schema version (SchemaDetector.detect()).
3. Perform the work; on failure — rollback via MigrationEngine or restore from backup.
4. Regenerate derived artifacts (index rebuild + snapshot regenerate) and verify retrieval.
