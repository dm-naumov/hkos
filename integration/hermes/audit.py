"""Hermes Audit Logging (DS-012 ЭТАП 4 §5)
==========================================
Append-only журнал аудита Hermes-операций. БЕЗ отдельной БД — только
append-only log (в памяти слоя интеграции; персистентность — вне слоя).

События: COMMAND_RECEIVED, COMMAND_ALLOWED, COMMAND_DENIED,
MIGRATION_STARTED, MIGRATION_COMPLETED, MIGRATION_FAILED,
KNOWLEDGE_READ, KNOWLEDGE_WRITTEN.

Формат записи: timestamp, agent_id, command, project_id, campaign_id,
result.
"""

from dataclasses import dataclass
from typing import Final

__all__ = [
    "AUDIT_COMMAND_RECEIVED",
    "AUDIT_COMMAND_ALLOWED",
    "AUDIT_COMMAND_DENIED",
    "AUDIT_MIGRATION_STARTED",
    "AUDIT_MIGRATION_COMPLETED",
    "AUDIT_MIGRATION_FAILED",
    "AUDIT_KNOWLEDGE_READ",
    "AUDIT_KNOWLEDGE_WRITTEN",
    "AuditEntry",
    "AuditLogger",
]

AUDIT_COMMAND_RECEIVED: Final[str] = "COMMAND_RECEIVED"
AUDIT_COMMAND_ALLOWED: Final[str] = "COMMAND_ALLOWED"
AUDIT_COMMAND_DENIED: Final[str] = "COMMAND_DENIED"
AUDIT_MIGRATION_STARTED: Final[str] = "MIGRATION_STARTED"
AUDIT_MIGRATION_COMPLETED: Final[str] = "MIGRATION_COMPLETED"
AUDIT_MIGRATION_FAILED: Final[str] = "MIGRATION_FAILED"
AUDIT_KNOWLEDGE_READ: Final[str] = "KNOWLEDGE_READ"
AUDIT_KNOWLEDGE_WRITTEN: Final[str] = "KNOWLEDGE_WRITTEN"


@dataclass(frozen=True)
class AuditEntry:
    """Запись аудита (append-only).

    Поля: event (тип события), timestamp, agent_id, command,
    project_id, campaign_id, result.
    """

    timestamp: str
    agent_id: str
    command: str
    project_id: str = ""
    campaign_id: str = ""
    result: str = ""
    event: str = ""


class AuditLogger:
    """Append-only журнал аудита (нет update/delete/clear)."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        """Добавить событие (только append)."""
        self._entries.append(entry)

    def entries(self) -> list[AuditEntry]:
        """Все события (порядок = порядок append; копия)."""
        return list(self._entries)

    def log(
        self,
        event: str,
        agent_id: str,
        command: str,
        project_id: str = "",
        campaign_id: str = "",
        result: str = "",
        timestamp: str | None = None,
    ) -> None:
        """Короткая форма: создать AuditEntry и добавить (append-only)."""
        self.append(AuditEntry(
            timestamp=timestamp or "",
            agent_id=agent_id,
            command=command,
            project_id=project_id,
            campaign_id=campaign_id,
            result=result,
            event=event,
        ))
