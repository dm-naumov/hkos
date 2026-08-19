"""Unit tests: FallbackPolicy (DS-012 ЭТАП 4 §6)."""

from hkos.integration.hermes.fallback import FallbackPolicy


class TestFallbackPolicy:
    """Graceful degradation: пустой контекст, pending queue, без Snapshot."""

    def test_retrieval_unavailable_returns_empty(self) -> None:
        policy = FallbackPolicy()
        result = policy.retrieval_unavailable("agent-1")
        assert result == []  # пустой контекст; выполнение продолжается

    def test_librarian_unavailable_queues(self) -> None:
        policy = FallbackPolicy()
        policy.librarian_unavailable({"title": "k1"})
        policy.librarian_unavailable({"title": "k2"})
        assert policy.pending_count() == 2  # результат не теряется

    def test_pending_drain(self) -> None:
        policy = FallbackPolicy()
        policy.librarian_unavailable({"title": "k1"})
        pending = policy.drain_pending()
        assert len(pending) == 1
        assert policy.pending_count() == 0

    def test_snapshot_unavailable(self) -> None:
        policy = FallbackPolicy()
        assert policy.snapshot_unavailable() is True  # retrieval без Snapshot
