"""HKOS Knowledge History (DS-006 §15, IP-006 §8, DS-006A §7)
========================================================
Append-only история изменений Knowledge.

Architecture (DS-006A §7): Provider Pattern.
    HistoryProvider — интерфейс;
    MemoryHistoryProvider — текущая реализация (хранение внутри Knowledge).

Цель: вынесение истории в отдельный Repository в будущем спринте
без изменения Librarian. Поведение не изменено.

Запрещены delete/update/rewrite существующих записей.
Каждое изменение Knowledge — новая запись.
События: Created, Updated, Canonicalized, Merged, Archived,
Restored, Rejected, Conflict detected, Confidence changed.
"""

from typing import Final, Protocol, runtime_checkable

from hkos.repository.models import Knowledge, KnowledgeHistoryEntry

__all__ = [
    "EVENT_CREATED",
    "EVENT_UPDATED",
    "EVENT_CANONICALIZED",
    "EVENT_MERGED",
    "EVENT_ARCHIVED",
    "EVENT_RESTORED",
    "EVENT_REJECTED",
    "EVENT_CONFLICT_DETECTED",
    "EVENT_CONFIDENCE_CHANGED",
    "HistoryProvider",
    "MemoryHistoryProvider",
    "KnowledgeHistory",
]

EVENT_CREATED: Final[str] = "Created"
EVENT_UPDATED: Final[str] = "Updated"
EVENT_CANONICALIZED: Final[str] = "Canonicalized"
EVENT_MERGED: Final[str] = "Merged"
EVENT_ARCHIVED: Final[str] = "Archived"
EVENT_RESTORED: Final[str] = "Restored"
EVENT_REJECTED: Final[str] = "Rejected"
EVENT_CONFLICT_DETECTED: Final[str] = "Conflict detected"
EVENT_CONFIDENCE_CHANGED: Final[str] = "Confidence changed"


@runtime_checkable
class HistoryProvider(Protocol):
    """Интерфейс провайдера истории (DS-006A §7)."""

    def append(
        self,
        knowledge: Knowledge,
        event: str,
        details: str = "",
        timestamp: str = "",
    ) -> Knowledge:
        """Добавить запись (append-only)."""
        ...

    def entries(
        self, knowledge: Knowledge
    ) -> list[KnowledgeHistoryEntry]:
        """Только чтение записей."""
        ...


class MemoryHistoryProvider:
    """Провайдер истории: хранение внутри Knowledge (текущее поведение)."""

    def append(
        self,
        knowledge: Knowledge,
        event: str,
        details: str = "",
        timestamp: str = "",
    ) -> Knowledge:
        """Добавить запись в историю (append-only).

        Args:
            knowledge: Знание (мутируется: history += запись).
            event: Событие из набора EVENT_*.
            details: Описание изменения.
            timestamp: Метка времени; по умолчанию — now.

        Returns:
            То же знание с дополненной историей.
        """
        from datetime import datetime, timezone

        ts = timestamp or datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        )
        knowledge.history.append(
            KnowledgeHistoryEntry(
                timestamp=ts,
                knowledge_id=knowledge.id,
                event=event,
                details=details,
            )
        )
        return knowledge

    def entries(
        self, knowledge: Knowledge
    ) -> list[KnowledgeHistoryEntry]:
        """Только чтение: копии записей (мутация результата не влияет)."""
        import copy

        return [copy.deepcopy(entry) for entry in knowledge.history]


class KnowledgeHistory:
    """Фасад истории Knowledge (делегирует MemoryHistoryProvider)."""

    _provider: HistoryProvider = MemoryHistoryProvider()

    @classmethod
    def provider(cls) -> HistoryProvider:
        """Текущий провайдер истории."""
        return cls._provider

    @classmethod
    def set_provider(cls, provider: HistoryProvider) -> None:
        """Заменить провайдер (для будущего выноса в Repository)."""
        cls._provider = provider

    @classmethod
    def append(
        cls,
        knowledge: Knowledge,
        event: str,
        details: str = "",
        timestamp: str = "",
    ) -> Knowledge:
        """Добавить запись через провайдер (append-only)."""
        return cls._provider.append(
            knowledge, event, details=details, timestamp=timestamp
        )

    @classmethod
    def entries(cls, knowledge: Knowledge) -> list[KnowledgeHistoryEntry]:
        """Только чтение через провайдер."""
        return cls._provider.entries(knowledge)
