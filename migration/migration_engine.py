"""HKOS Migration Engine (DS-011 Rev.1.2 §6, IP-011 ЭТАП 6)
================================================================
ТОНКИЙ ФАСАД Migration Engine. НЕ содержит собственной оркестрации/FSM
(FSM принадлежит MigrationManager). Обязанности фасада:
- публичный API (7 методов: detect/migrate/rollback/validate/backup/
  history/status);
- миграционный замок (§15a): одна миграция одновременно; stale timeout
  30 минут; проверка при входе в detect()/migrate(); авто-снятие stale;
  снятие при COMPLETED/FAILED;
- журнал MigrationHistory (append-only, без дедупликации);
- получение списка проектов (RepositoryManager — публичный интерфейс);
- делегирование выполнения MigrationManager;
- ПОЛНЫЙ жизненный цикл rollback (F-2): manager.rollback() (restore +
  delete производных) -> Index rebuild -> Snapshot regenerate ->
  Validation (RollbackManager остаётся «глупым» восстановлением файлов).
"""

import json
import os as _os
import time
from pathlib import Path
from typing import Any

from hkos.core.logger import HKOSLogger
from hkos.index.index_engine import IndexEngine
from hkos.migration.exceptions import MigrationLockError
from hkos.migration.migration_history import (
    STATUS_APPLIED,
    MigrationHistory,
    MigrationRecord,
)
from hkos.migration.migration_manager import MigrationManager
from hkos.migration.migration_validator import MigrationValidator
from hkos.migration.schema_detector import SchemaInfo
from hkos.migration.version_manifest import VersionManifest
from hkos.repository.repository_manager import RepositoryManager
from hkos.snapshot.snapshot_engine import SnapshotEngine

__all__ = ["MigrationEngine"]

STATUS_STARTED = "started"
STATUS_BACKUP_CREATED = "backup_created"
STATUS_ROLLBACK = "rollback"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED)


class MigrationEngine:
    """Фасад Migration Engine (7 публичных методов; DS-011 §6)."""

    def __init__(
        self,
        manager: MigrationManager,
        history: MigrationHistory,
        repository: RepositoryManager,
        index_engine: IndexEngine,
        snapshot_engine: SnapshotEngine,
        validator: MigrationValidator,
        lock_path: Path,
        lock_timeout_seconds: int = 1800,
        agent: str = "migration",
        logger: HKOSLogger | None = None,
        manifest: VersionManifest | None = None,
    ) -> None:
        """Инициализация фасада (dependency injection).

        Args:
            manager: Оркестратор FSM (вся оркестрация — там).
            history: Журнал миграций (append-only).
            repository: RepositoryManager (перечисление проектов).
            index_engine: IndexEngine (rebuild в жизненном цикле rollback).
            snapshot_engine: SnapshotEngine (regenerate в rollback).
            validator: MigrationValidator (валидация после rollback).
            lock_path: Путь к файлу замка.
            lock_timeout_seconds: Stale timeout замка (по умолчанию 1800).
            agent: Имя агента/оператора для записей истории.
            logger: Логгер.
            manifest: Производный кэш версий (DS-013 ЭТАП 2); НЕ
                источник истины. Обновляется после успешной миграции;
                инвалидируется после rollback («Repository wins»).

        """
        self._manager = manager
        self._history = history
        self._repository = repository
        self._index_engine = index_engine
        self._snapshot_engine = snapshot_engine
        self._validator = validator
        self._lock_path = Path(lock_path)
        self._lock_timeout = lock_timeout_seconds
        self._agent = agent
        self._logger = logger or HKOSLogger()
        self._manifest = manifest
        self._last_info = SchemaInfo(current_version=1, target_version=1)

    # ---- публичный API (7 методов) ----

    def detect(self) -> SchemaInfo:
        """Определить текущую/целевую версию и список миграций.

        Raises:
            MigrationLockError: миграция уже выполняется.

        """
        with self._locked():
            project_ids = self._project_ids()
            info = self._manager.detect(project_ids)
        self._last_info = info
        return info

    def migrate(self) -> None:
        """Выполнить миграцию (делегирование MigrationManager).

        Raises:
            MigrationLockError: миграция уже выполняется.
            MigrationError: ошибка миграции (manager уже выполнил
                rollback при ошибке после backup).

        """
        with self._locked():
            project_ids = self._project_ids()
            info = self._manager.detect(project_ids)  # для журнала (до migrate)
            self._last_info = info
            self._append(STATUS_STARTED)
            try:
                # делегирование: FSM полностью в MigrationManager
                self._manager.migrate(project_ids)
            except Exception as exc:
                self._journal_failure(exc)
                raise
        if info.pending:
            # прогон выполнил backup + apply (вывод по outcome, без
            # дублирования FSM)
            self._append(STATUS_BACKUP_CREATED)
            self._append(STATUS_APPLIED)
        self._append(STATUS_COMPLETED)
        self._refresh_manifest(target_version=info.target_version)

    def rollback(self) -> None:
        """Полный жизненный цикл отката (F-2, DS-011 §10):

        Repository restore (manager) -> Index rebuild ->
        Snapshot regenerate -> Validation. Индекс/снимки из backup
        НЕ восстанавливаются (запрет stale-индексов).
        """
        try:
            project_ids = self._project_ids()
            # target фиксируется ДО rollback (manager.detect не должен
            # перезатирать терминальное состояние FAILED после отката)
            target = self._manager.detect(project_ids).target_version
            self._manager.rollback()
            for project in project_ids:
                self._index_engine.rebuild(project)
            for project in project_ids:
                self._snapshot_engine.create(
                    project, reason="rollback", author=self._agent, force=True,
                )
            self._validator.validate(target)
        except Exception:
            self._append(STATUS_FAILED)
            raise
        self._append(STATUS_ROLLBACK)
        if self._manifest is not None:
            # «Repository wins»: после восстановления manifest
            # инвалидируется; следующий detect пересоздаст его сканом.
            self._manifest.invalidate()

    def validate(self) -> None:
        """Итоговая валидация (делегирование MigrationManager)."""
        self._manager.validate(self._project_ids())

    def backup(self, migration_id: str, target_version: int) -> str:
        """Резервная копия Repository (делегирование MigrationManager)."""
        return self._manager.backup(migration_id, target_version)

    def history(self) -> list[MigrationRecord]:
        """Журнал миграций (append-only event log)."""
        return self._history.entries()

    def status(self) -> str:
        """Текущее состояние FSM + текущая и целевая версии схемы (§6)."""
        return (
            f"{self._manager.status()}; "
            f"current={self._last_info.current_version}; "
            f"target={self._last_info.target_version}"
        )

    # ---- миграционный замок (§15a) ----

    def _locked(self) -> "_LockGuard":
        """Контекстный менеджер замка: проверка/авто-снятие stale при
        входе; снятие при выходе (COMPLETED/FAILED — всегда).
        """
        return _LockGuard(self)

    def acquire_lock(self) -> None:
        """Приобрести замок; отказ при активной миграции.

        Raises:
            MigrationLockError: миграция уже выполняется.

        """
        if self._lock_path.exists():
            stale = self._lock_is_stale()
            terminal = self._lock_history_terminal()
            if not stale and not terminal:
                raise MigrationLockError(
                    "Migration already in progress (lock active)"
                )
            # stale ИЛИ терминальная история -> авто-снятие
            self._lock_path.unlink()
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": time.time(),
            "agent": self._agent,
        }
        try:
            fd = _os.open(
                self._lock_path, _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY
            )
        except FileExistsError as exc:
            raise MigrationLockError(
                "Migration already in progress (lock race)"
            ) from exc
        with _os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)

    def release_lock(self) -> None:
        """Снять замок (вызывается при COMPLETED/FAILED и всегда при
        выходе из контекста).
        """
        if self._lock_path.exists():
            try:
                self._lock_path.unlink()
            except OSError:
                pass

    def _lock_is_stale(self) -> bool:
        """Замок старше lock_timeout_seconds -> stale."""
        try:
            payload = json.loads(self._lock_path.read_text())
            timestamp = float(payload.get("timestamp", 0.0))
        except Exception:
            return True  # повреждённый файл замка -> stale
        return (time.time() - timestamp) > self._lock_timeout

    def _lock_history_terminal(self) -> bool:
        """Последняя запись истории — терминальное событие
        (completed/failed) -> замок осиротел -> авто-снятие.
        """
        last = self._history.last()
        if last is None:
            return False
        return last.status in _TERMINAL_STATUSES

    # ---- журнал (§14) ----

    def _append(self, status: str) -> None:
        """Запись события в журнал (append-only, без дедупликации)."""
        self._history.append(MigrationRecord(
            migration_id=self._run_id(),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            agent=self._agent,
            from_version=self._last_info.current_version,
            to_version=self._last_info.target_version,
            status=status,
            duration_ms=0,
        ))

    def _run_id(self) -> str:
        """Идентификатор текущего прогона (последняя миграция или 'detect')."""
        last = self._history.last()
        return last.migration_id if last is not None else "detect"

    def _journal_failure(self, exc: Exception) -> None:
        """Зафиксировать неуспех в журнале: rollback (если manager его
        выполнил) + failed. Определяется по сообщению исключения
        (manager: «rolled back» / «rollback failed» — rollback был;
        «Backup failed» — до backup, rollback не выполнялся).
        """
        message = str(exc)
        if "rolled back" in message or "rollback failed" in message:
            self._append(STATUS_ROLLBACK)
        self._append(STATUS_FAILED)

    # ---- version manifest (DS-013 ЭТАП 2; производный кэш) ----

    def _refresh_manifest(self, target_version: int) -> None:
        """Обновить manifest после успешной миграции: все проекты ->
        целевая версия (миграция применила её ко всем документам).
        """
        if self._manifest is None:
            return
        try:
            for project in self._project_ids():
                self._manifest.set(project, target_version)
            self._manifest.save()
        except Exception:
            # manifest — кэш; сбой записи не ломает миграцию
            self._logger.warning("Version manifest refresh failed")

    # ---- проекты ----

    def _project_ids(self) -> list[str]:
        """UUID проектов через публичный интерфейс RepositoryManager."""
        return [project.id for project in self._repository.projects.list()]


class _LockGuard:
    """Контекстный менеджер миграционного замка."""

    def __init__(self, engine: "MigrationEngine") -> None:
        self._engine = engine

    def __enter__(self) -> "_LockGuard":
        self._engine.acquire_lock()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._engine.release_lock()
