"""Unit tests for History Provider Pattern (DS-006A §7)."""

from hkos.repository.models import Knowledge, KnowledgeHistoryEntry
from hkos.services.librarian.knowledge_history import (
    EVENT_CREATED,
    HistoryProvider,
    KnowledgeHistory,
    MemoryHistoryProvider,
)


class DummyProvider:
    """Тестовый провайдер (замена для проверки Pattern)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def append(
        self,
        knowledge: Knowledge,
        event: str,
        details: str = "",
        timestamp: str = "",
    ) -> Knowledge:
        self.calls.append(event)
        return knowledge

    def entries(
        self, knowledge: Knowledge
    ) -> list[KnowledgeHistoryEntry]:
        return []


class TestHistoryProvider:
    """Provider Pattern: интерфейс + замена провайдера."""

    def test_memory_provider_implements_interface(self) -> None:
        assert isinstance(MemoryHistoryProvider(), HistoryProvider)

    def test_default_provider_is_memory(self) -> None:
        assert isinstance(KnowledgeHistory.provider(), MemoryHistoryProvider)

    def test_behavior_unchanged(self) -> None:
        k = Knowledge(id="1")
        KnowledgeHistory.append(k, EVENT_CREATED)
        assert len(k.history) == 1
        assert k.history[0].event == EVENT_CREATED

    def test_provider_swappable(self) -> None:
        dummy = DummyProvider()
        KnowledgeHistory.set_provider(dummy)
        try:
            k = Knowledge(id="1")
            KnowledgeHistory.append(k, EVENT_CREATED)
            assert dummy.calls == [EVENT_CREATED]
            assert k.history == []  # провайдер не хранит внутри Knowledge
        finally:
            KnowledgeHistory.set_provider(MemoryHistoryProvider())

    def test_provider_restored(self) -> None:
        assert isinstance(KnowledgeHistory.provider(), MemoryHistoryProvider)
