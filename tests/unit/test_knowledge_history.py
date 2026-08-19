"""Unit tests for KnowledgeHistory (DS-006 §15, IP-006 §8)."""

from hkos.repository.models import Knowledge
from hkos.services.librarian.knowledge_history import (
    EVENT_ARCHIVED,
    EVENT_CREATED,
    EVENT_UPDATED,
    KnowledgeHistory,
)


class TestKnowledgeHistory:
    """History append-only: только добавление, без delete/update/rewrite."""

    def test_append_adds_entry(self) -> None:
        k = Knowledge(id="1")
        KnowledgeHistory.append(k, EVENT_CREATED, details="created")
        assert len(k.history) == 1
        assert k.history[0].event == EVENT_CREATED
        assert k.history[0].knowledge_id == "1"

    def test_append_only_growth(self) -> None:
        k = Knowledge(id="1")
        KnowledgeHistory.append(k, EVENT_CREATED)
        KnowledgeHistory.append(k, EVENT_UPDATED)
        KnowledgeHistory.append(k, EVENT_ARCHIVED)
        assert [e.event for e in k.history] == [
            EVENT_CREATED, EVENT_UPDATED, EVENT_ARCHIVED,
        ]

    def test_entries_are_read_only_view(self) -> None:
        k = Knowledge(id="1")
        KnowledgeHistory.append(k, EVENT_CREATED)
        view = KnowledgeHistory.entries(k)
        assert len(view) == 1
        # Изменение копии не влияет на оригинал
        view[0].event = "HACK"
        assert k.history[0].event == EVENT_CREATED

    def test_timestamp(self) -> None:
        k = Knowledge(id="1")
        KnowledgeHistory.append(k, EVENT_CREATED, timestamp="2026-01-01T00:00:00+00:00")
        assert k.history[0].timestamp == "2026-01-01T00:00:00+00:00"

    def test_no_delete_update_rewrite_api(self) -> None:
        """Нет API удаления/изменения/перезаписи записей истории.

        provider/set_provider добавлены в DS-006A (Provider Pattern)
        и не мутируют записи.
        """
        public = [m for m in dir(KnowledgeHistory) if not m.startswith("_")]
        assert set(public) <= {"append", "entries", "provider", "set_provider"}
