"""HKOS Migration Manager (DS-011 Rev.1.2 §12/§15, IP-011 ЭТАП 5)
================================================================
Оркестратор миграции по одноразовому FSM (БЕЗ бизнес-логики):

    DETECT -> BACKUP -> MIGRATING (Registry.ordered)
    -> REBUILD_INDEX -> REGENERATE_SNAPSHOT -> VALIDATE -> COMPLETED

Любая ошибка ПОСЛЕ успешного BACKUP -> ROLLBACK -> FAILED.
Ошибка до/во время BACKUP -> FAILED без rollback (данные не изменялись;
DS-011 §15 упрощённое правило отказа).

Manager только координирует через существующие публичные интерфейсы:
SchemaDetector, MigrationRegistry, MigrationExecutor, BackupManager,
RollbackManager, MigrationValidator, IndexEngine, SnapshotEngine.
Без доступа к внутренностям Repository (project_ids передаются
параметрами); без глобальных переменных; без singleton; DI.
"""

from hkos.core.logger import HKOSLogger
from hkos.index.index_engine import IndexEngine
from hkos.migration.backup_manager import BackupManager
from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_executor import MigrationExecutor
from hkos.migration.migration_registry import MigrationRegistry
from hkos.migration.migration_validator import MigrationValidator
from hkos.migration.rollback_manager import RollbackManager
from hkos.migration.schema_detector import SchemaDetector, SchemaInfo
from hkos.snapshot.snapshot_engine import SnapshotEngine

__all__ = ["MigrationManager"]

STATE_IDLE = "IDLE"
STATE_DETECTING = "DETECTING"
STATE_BACKUP = "BACKUP"
STATE_MIGRATING = "MIGRATING"
STATE_REBUILD_INDEX = "REBUILD_INDEX"
STATE_REGENERATE_SNAPSHOT = "REGENERATE_SNAPSHOT"
STATE_VALIDATING = "VALIDATING"
STATE_COMPLETED = "COMPLETED"
STATE_ROLLBACK = "ROLLBACK"
STATE_FAILED = "FAILED"


class MigrationManager:
    """Оркестратор конвейера миграции (FSM; DS-011 §15)."""

    def __init__(
        self,
        detector: SchemaDetector,
        registry: MigrationRegistry,
        executor: MigrationExecutor,
        backup: BackupManager,
        rollback: RollbackManager,
        validator: MigrationValidator,
        index_engine: IndexEngine,
        snapshot_engine: SnapshotEngine,
        logger: HKOSLogger | None = None,
    ) -> None:
        """Инициализация оркестратора (dependency injection)."""
        self._detector = detector
        self._registry = registry
        self._executor = executor
        self._backup = backup
        self._rollback = rollback
        self._validator = validator
        self._index_engine = index_engine
        self._snapshot_engine = snapshot_engine
        self._logger = logger or HKOSLogger()
        self._state: str = STATE_IDLE
        self._last_backup_dir: str = ""
        self._last_target: int = 1

    def detect(self, project_ids: list[str]) -> SchemaInfo:
        """DETECT: определение версии и списка миграций.

        При ошибке состояние переводится в FAILED (F-1, IP-011 ЭТАП 6/7).

        Args:
            project_ids: UUID проектов рабочей области.

        """
        self._state = STATE_DETECTING
        try:
            info = self._detector.detect(project_ids)
        except Exception:
            self._state = STATE_FAILED
            raise
        self._last_target = info.target_version
        return info

    def migrate(self, project_ids: list[str]) -> None:
        """Полный конвейер миграции по FSM (DS-011 §15).

        Args:
            project_ids: UUID проектов рабочей области.

        Raises:
            MigrationError: ошибка до/во время BACKUP (rollback не
                выполняется; данные не изменялись).

        """
        self._state = STATE_DETECTING
        try:
            info = self._detector.detect(project_ids)
        except MigrationError:
            self._state = STATE_FAILED
            raise
        self._last_target = info.target_version
        if not info.pending:
            self._state = STATE_COMPLETED  # up-to-date
            self._logger.info("Migration Finished: up-to-date")
            return
        try:
            backup_dir = self._backup.create(info.pending[0], info.target_version)
        except Exception as exc:
            self._state = STATE_FAILED  # ошибка до backup — без rollback
            self._logger.error(f"Migration Failed (backup): {exc}")
            raise MigrationError(f"Backup failed: {exc}") from exc
        self._last_backup_dir = backup_dir
        try:
            self._state = STATE_MIGRATING
            steps = self._registry.ordered(info.current_version, info.target_version)
            for step in steps:
                self._executor.apply(step)
            self._state = STATE_REBUILD_INDEX
            for project in project_ids:
                self._index_engine.rebuild(project)
            self._state = STATE_REGENERATE_SNAPSHOT
            for project in project_ids:
                self._snapshot_engine.create(
                    project, reason="migration", author="migration", force=True,
                )
            self._state = STATE_VALIDATING
            self._validator.validate(info.target_version)
        except Exception as exc:
            # любая ошибка после успешного BACKUP -> ROLLBACK -> FAILED
            self._state = STATE_ROLLBACK
            self._logger.error(f"Migration Failed: {exc}; rolling back")
            try:
                self._rollback.rollback(backup_dir)
            except Exception as rollback_exc:
                self._state = STATE_FAILED
                raise MigrationError(
                    f"Migration failed: {exc}; rollback failed: {rollback_exc}"
                ) from rollback_exc
            self._state = STATE_FAILED
            raise MigrationError(f"Migration failed: {exc}; rolled back") from exc
        self._state = STATE_COMPLETED
        self._logger.info("Migration Finished")

    def rollback(self) -> None:
        """ROLLBACK: восстановление последнего backup (повторный
        rollback — новая попытка; RollbackManager идемпотентен).
        """
        if not self._last_backup_dir:
            raise MigrationError("No backup from the last run to roll back")
        self._state = STATE_ROLLBACK
        try:
            self._rollback.rollback(self._last_backup_dir)
        except Exception:
            self._state = STATE_FAILED
            raise
        self._state = STATE_FAILED

    def validate(self, project_ids: list[str]) -> None:
        """VALIDATE: итоговая валидация на детектированной версии.

        При ошибке состояние переводится в FAILED (F-1, IP-011 ЭТАП 6).
        """
        self._state = STATE_VALIDATING
        try:
            info = self._detector.detect(project_ids)
            self._validator.validate(info.target_version)
        except Exception:
            self._state = STATE_FAILED
            raise
        self._state = STATE_COMPLETED

    def backup(self, migration_id: str, target_version: int) -> str:
        """BACKUP: резервная копия по ключу (standalone).

        При ошибке состояние переводится в FAILED (F-1, IP-011 ЭТАП 6).
        """
        self._state = STATE_BACKUP
        try:
            backup_dir = self._backup.create(migration_id, target_version)
        except Exception:
            self._state = STATE_FAILED
            raise
        self._last_backup_dir = backup_dir
        self._last_target = target_version
        return backup_dir

    def status(self) -> str:
        """Текущее состояние FSM (DS-011 §6/§15)."""
        return self._state
