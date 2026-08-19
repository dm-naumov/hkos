"""HKOS Migration History (DS-011 Rev.1.2 §14, IP-011 ЭТАП 4)
=============================================================
Append-only EVENT LOG. История НЕ является источником истины
(истина — schema_version документов); хранит события.

Правила:
- несколько записей для одной миграции ДОПУСКАЮТСЯ (applied,
  rolled_back, повторные попытки — отдельные события); дедупликации НЕТ;
- порядок = порядок append; детерминированно;
- clear() НЕ реализован (append-only);
- операции чтения возвращают копии (иммутабельность представления).
"""

from dataclasses import dataclass

__all__ = ["MigrationRecord", "MigrationHistory", "STATUS_APPLIED", "STATUS_ROLLED_BACK"]

STATUS_APPLIED: str = "applied"
STATUS_ROLLED_BACK: str = "rolled_back"


@dataclass(frozen=True)
class MigrationRecord:
    """Запись события миграции (DS-011 §14)."""

    migration_id: str
    timestamp: str
    agent: str
    from_version: int
    to_version: int
    status: str
    duration_ms: int
    rolled_back: bool = False


class MigrationHistory:
    """Журнал миграций (append-only event log)."""

    def __init__(self) -> None:
        self._records: list[MigrationRecord] = []

    def append(self, record: MigrationRecord) -> None:
        """Добавить событие (только append; DS-011 §14)."""
        self._records.append(record)

    def entries(self) -> list[MigrationRecord]:
        """Все события (от старых к новым; копия)."""
        return list(self._records)

    def last(self) -> MigrationRecord | None:
        """Последнее событие (или None)."""
        if not self._records:
            return None
        return self._records[-1]

    def last_success(self) -> MigrationRecord | None:
        """Последнее УСПЕШНО применённое событие (applied, без rollback)."""
        for record in reversed(self._records):
            if record.status == STATUS_APPLIED and not record.rolled_back:
                return record
        return None

    def last_for_migration(self, migration_id: str) -> MigrationRecord | None:
        """Последнее событие для указанной миграции (или None)."""
        for record in reversed(self._records):
            if record.migration_id == migration_id:
                return record
        return None
