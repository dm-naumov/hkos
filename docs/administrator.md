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

## CLI (hkos)

Console script `hkos` (и `python -m hkos.cli`), `--root` до/после команды
(или env `HKOS_DATA_ROOT`):

- `hkos status` — версия, data root, число проектов/записей.
- `hkos doctor --project <id|name>` — согласованность repo == index ==
  snapshot + relations FK (exit 0 PASS / 1 FAIL).
- `hkos validate --project <id|name>` — индексная целостность (exit 1 —
  INVALID).
- `hkos migrate [--project <id|name>] [--check] [--force]` — явная
  конвертация JSON-индексов проекта в `indexes/index_store.db`
  (DS-017 v1.2). `--check` — сухой прогон без записи; повторный запуск
  без `--force` пропускает уже мигрированные проекты; SSOT не
  затрагивается.

## SQLite index backend (DS-017 v1.2)

Бэкенд индексов выбирается конфигом `hkos.index.backend: json|sqlite`
(default json) в `config/hkos-development.yaml` / `hkos-production.yaml`.

- json: 5 файлов `*.idx` на проект (человекочитаемые, git diff) — default.
- sqlite: один `indexes/index_store.db` на проект; запись — дельта
  O(размер сущности) в WAL-транзакции (устраняет write amplification
  полной перезаписи .idx); чтение Q1–Q5 — SQL-запросы.

Переход на sqlite (только явная команда, авто-триггера нет):

    hkos migrate --check          # сухой прогон: что будет перенесено
    hkos migrate                  # перенести индексы всех проектов
    # затем в конфиге:
    hkos.index.backend: sqlite    # новые записи идут в SQLite (дельта)

Данные репозитория (SSOT) при миграции не изменяются; откат — вернуть
`backend: json` (старые `*.idx` сохраняются) и при необходимости
`hkos migrate --force` в обратную сторону из JSON.


## Change rollback procedure (mandatory BEFORE system work)

1. Take a backup of the repository + config + history.
2. Record the current schema version (SchemaDetector.detect()).
3. Perform the work; on failure — rollback via MigrationEngine or restore from backup.
4. Regenerate derived artifacts (index rebuild + snapshot regenerate) and verify retrieval.
