"""Unit tests: Performance Integration (DS-013 ЭТАП 5)."""

import time

from hkos.performance.cache_manager import CacheManager
from hkos.performance.context_profiles import (
    PROFILE_AGGRESSIVE,
    PROFILE_NORMAL,
    PerformanceContextOptimizer,
)
from hkos.performance.integration import (
    PerformanceIntegration,
    create_performance_layer,
)
from hkos.performance.performance_manager import PerformanceManager


class _FakeRetrieval:
    """Двойник RetrievalEngine (счётчик вызовов)."""

    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, query: str, **kwargs: object) -> str:
        self.calls += 1
        return f"result:{query}"


class TestPerformanceIntegration:
    """DI-подключение, profiler, metrics, cache, optimizer."""

    def test_create_layer_no_singleton(self) -> None:
        first = create_performance_layer()
        second = create_performance_layer()
        assert first is not second          # без глобальных singleton

    def test_wrapped_retrieval_measures(self) -> None:
        integration = PerformanceIntegration()
        fake = _FakeRetrieval()
        wrapped = integration.wrap_retrieval(fake, fingerprint=lambda p: "fp")
        wrapped.retrieve("udp", project_id="p1")
        stats = integration.manager.statistics()
        metrics = stats.get("metrics")
        assert isinstance(metrics, list) and metrics
        assert metrics[0].operation == "retrieval"

    def test_cache_hit_no_repository_access(self) -> None:
        integration = PerformanceIntegration()
        fake = _FakeRetrieval()
        wrapped = integration.wrap_retrieval(fake, fingerprint=lambda p: "fp")
        first = wrapped.retrieve("udp", project_id="p1")
        second = wrapped.retrieve("udp", project_id="p1")
        assert first == second
        assert fake.calls == 1              # второй запрос — cache hit
        ratio = integration.cache.statistics().get("hit_ratio", 0)
        assert isinstance(ratio, float) and ratio == 0.5

    def test_cache_miss_different_query(self) -> None:
        integration = PerformanceIntegration()
        fake = _FakeRetrieval()
        wrapped = integration.wrap_retrieval(fake, fingerprint=lambda p: "fp")
        wrapped.retrieve("udp", project_id="p1")
        wrapped.retrieve("tcp", project_id="p1")
        assert fake.calls == 2

    def test_context_optimizer_profiles(self) -> None:
        from hkos.performance.context_profiles import CompressedContext

        optimizer = PerformanceContextOptimizer(PROFILE_NORMAL)
        context = _FakeContext({"DECISIONS": ["d1", "d2", "d3", "d4"],
                                "OTHER": ["o1", "o2", "o3", "o4"]})
        compressed = optimizer.compress(context)
        assert isinstance(compressed, CompressedContext)
        # protected-секция сохранена полностью; OTHER сжата
        assert compressed.sections["DECISIONS"] == ["d1", "d2", "d3", "d4"]
        assert len(compressed.sections["OTHER"]) <= 3

    def test_semantic_equivalence(self) -> None:
        """protected-контент (решения/ограничения/причины) не удаляется."""
        from hkos.performance.context_profiles import CompressedContext

        optimizer = PerformanceContextOptimizer(PROFILE_AGGRESSIVE)
        context = _FakeContext({
            "DECISIONS": ["decision-1", "decision-2"],
            "FAILURES": ["cause-1"],
            "CONFIGURATION": ["dep-1"],
            "OPEN QUESTIONS": ["limit-1"],
            "CANONICAL KNOWLEDGE": ["k1", "k2", "k3"],
        })
        compressed = optimizer.compress(context)
        assert isinstance(compressed, CompressedContext)
        assert compressed.sections["DECISIONS"] == ["decision-1", "decision-2"]
        assert compressed.sections["FAILURES"] == ["cause-1"]
        assert compressed.sections["CONFIGURATION"] == ["dep-1"]
        assert compressed.sections["OPEN QUESTIONS"] == ["limit-1"]
        assert len(compressed.sections["CANONICAL KNOWLEDGE"]) == 0  # AGGRESSIVE

    def test_cache_manager_lru_ttl(self) -> None:
        cache = CacheManager(max_entries=2, ttl_seconds=100)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)                   # вытесняет "a" (LRU)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        cache.get("b")                      # hit
        hits = cache.statistics().get("hits", 0)
        assert isinstance(hits, int) and hits >= 1

    def test_cache_disabled(self) -> None:
        cache = CacheManager(enabled=False)
        cache.set("a", 1)
        assert cache.get("a") is None

    def test_optimize_reports(self) -> None:
        manager = PerformanceManager()
        with manager.measure("retrieval"):
            time.sleep(0.01)
        report = manager.optimize()
        assert "metrics" in report
        assert "recommendations" in report
        assert "warnings" in report


class _FakeContext:
    def __init__(self, sections: dict[str, list[object]]) -> None:
        self.sections = sections
