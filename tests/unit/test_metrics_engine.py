"""Unit tests: MetricsEngine (DS-013 ЭТАП 4)."""

import time

from hkos.performance.metrics_engine import MetricsEngine


class TestMetricsEngine:
    """Хранилище метрик: record/statistics/clear."""

    def test_record_and_entries(self) -> None:
        engine = MetricsEngine()
        engine.record("retrieval", 12.5, project_id="p1", agent_id="a1")
        engine.record("retrieval", 7.5, project_id="p1")
        engine.record("save", 3.0)
        assert len(engine.entries()) == 3
        assert engine.entries()[0].operation == "retrieval"
        assert engine.entries()[0].duration_ms == 12.5
        assert engine.entries()[0].project_id == "p1"

    def test_statistics(self) -> None:
        engine = MetricsEngine()
        engine.record("retrieval", 10.0)
        engine.record("retrieval", 20.0)
        engine.record("retrieval", 30.0)
        stats = engine.statistics("retrieval")
        assert len(stats) == 1
        stat = stats[0]
        assert stat.count == 3
        assert stat.average_ms == 20.0
        assert stat.min_ms == 10.0
        assert stat.max_ms == 30.0

    def test_statistics_per_operation(self) -> None:
        engine = MetricsEngine()
        engine.record("a", 1.0)
        engine.record("b", 2.0)
        assert {s.operation for s in engine.statistics()} == {"a", "b"}

    def test_clear(self) -> None:
        engine = MetricsEngine()
        engine.record("a", 1.0)
        engine.clear()
        assert engine.entries() == []

    def test_overhead_budget(self) -> None:
        """record <= 1 ms (бюджет DS-013)."""
        engine = MetricsEngine()
        start = time.perf_counter()
        for _ in range(100):
            engine.record("op", 1.0)
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed <= 1.0, f"record {elapsed:.3f} ms"
