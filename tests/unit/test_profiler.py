"""Unit tests: Profiler (DS-013 ЭТАП 4)."""

import time

from hkos.performance.metrics_engine import MetricsEngine
from hkos.performance.profiler import Profiler


class TestProfiler:
    """Контекстный профилировщик: измеряет, не изменяет выполнение."""

    def test_measures_duration(self) -> None:
        metrics = MetricsEngine()
        profiler = Profiler(metrics)
        with profiler.measure("retrieval"):
            time.sleep(0.02)
        stats = metrics.statistics("retrieval")
        assert stats[0].count == 1
        assert stats[0].average_ms >= 15.0  # ~20 ms

    def test_does_not_change_execution(self) -> None:
        metrics = MetricsEngine()
        profiler = Profiler(metrics)
        result = []
        with profiler.measure("op"):
            result.append("ran")
        assert result == ["ran"]  # выполнение не изменено

    def test_exception_preserved(self) -> None:
        """Исключение внутри блока не скрывается; метрика всё же пишется."""
        metrics = MetricsEngine()
        profiler = Profiler(metrics)
        try:
            with profiler.measure("op"):
                raise ValueError("boom")
        except ValueError:
            pass
        assert metrics.statistics("op")[0].count == 1

    def test_overhead_budget(self) -> None:
        """profiler <= 2 ms (бюджет DS-013)."""
        metrics = MetricsEngine()
        profiler = Profiler(metrics)
        start = time.perf_counter()
        for _ in range(100):
            with profiler.measure("op"):
                pass
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed <= 2.0, f"profiler {elapsed:.3f} ms"
