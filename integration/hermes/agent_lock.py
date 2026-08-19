"""Hermes Agent Lock (DS-012 ЭТАП 4 §7)
==========================================
Блокировки уровня агентов (НЕ путать с MigrationEngine lock).

- Migration lock: защищает миграции (полная эксклюзивность).
- Agent lock: защищает изменение памяти.

Правила:
- READ: много агентов одновременно;
- WRITE: один писатель (эксклюзив среди писателей);
- MIGRATION: полная эксклюзивность (блокирует READ и WRITE).
"""

import threading
from typing import Final

__all__ = ["AgentLock", "LOCK_MODE_READ", "LOCK_MODE_WRITE", "LOCK_MODE_MIGRATION"]

LOCK_MODE_READ: Final[str] = "READ"
LOCK_MODE_WRITE: Final[str] = "WRITE"
LOCK_MODE_MIGRATION: Final[str] = "MIGRATION"


class AgentLock:
    """RW-блокировка уровня агентов (readers-writer-migration)."""

    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._readers = 0
        self._writer = False
        self._migration = False

    def acquire(self, mode: str) -> None:
        """Захват режима (блокирующий).

        Args:
            mode: LOCK_MODE_READ / LOCK_MODE_WRITE / LOCK_MODE_MIGRATION.

        """
        if mode == LOCK_MODE_READ:
            self._acquire_read()
        elif mode == LOCK_MODE_WRITE:
            self._acquire_write()
        else:
            self._acquire_migration()

    def release(self, mode: str) -> None:
        """Освобождение режима."""
        with self._mutex:
            if mode == LOCK_MODE_READ:
                self._readers = max(0, self._readers - 1)
            elif mode == LOCK_MODE_WRITE:
                self._writer = False
            else:
                self._migration = False

    def _acquire_read(self) -> None:
        while True:
            with self._mutex:
                if not self._writer and not self._migration:
                    self._readers += 1
                    return
            # ждём завершения писателя/миграции
            threading.Event().wait(0.01)

    def _acquire_write(self) -> None:
        while True:
            with self._mutex:
                if not self._writer and not self._migration and self._readers == 0:
                    self._writer = True
                    return
            threading.Event().wait(0.01)

    def _acquire_migration(self) -> None:
        while True:
            with self._mutex:
                if not self._writer and not self._migration and self._readers == 0:
                    self._migration = True
                    return
            threading.Event().wait(0.01)

    # ---- наблюдатели (для тестов/диагностики) ----

    @property
    def readers(self) -> int:
        with self._mutex:
            return self._readers

    @property
    def writer_active(self) -> bool:
        with self._mutex:
            return self._writer

    @property
    def migration_active(self) -> bool:
        with self._mutex:
            return self._migration
