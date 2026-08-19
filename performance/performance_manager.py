"""HKOS Performance Manager (DS-013 ЭТАП 4)
==============================================
Единый фасад Performance Layer: сбор метрик, профилирование, latency,
мониторинг ресурсов, наблюдаемость.

- stateless orchestration (DI всех зависимостей);
- БЕЗ бизнес-логики (не изменяет данные/порядок pipeline/результаты);
- журнал logs/performance.log — append-only:
    PROFILING_STARTED / PROFILING_FINISHED / METRIC_RECORDED /
    RESOURCE_WARNING; формат: timestamp event component details.
"""

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from hkos.core.logger import HKOSLogger
from hkos.performance.latency_tracker import LatencyTracker
from hkos.performance.metrics_engine import MetricsEngine
from hkos.performance.profiler import Profiler
from hkos.performance.resource_monitor import ResourceMonitor

__all__ = [
    "PerformanceManager",
    "PerformanceLogger",
    "EVENT_PROFILING_STARTED",
    "EVENT_PROFILING_FINISHED",
    "EVENT_METRIC_RECORDED",
    "EVENT_RESOURCE_WARNING",
]

EVENT_PROFILING_STARTED = "PROFILING_STARTED"
EVENT_PROFILING_FINISHED = "PROFILING_FINISHED"
EVENT_METRIC_RECORDED = "METRIC_RECORDED"
EVENT_RESOURCE_WARNING = "RESOURCE_WARNING"


class PerformanceLogger:
    """Append-only журнал performance (logs/performance.log)."""

    def __init__(self, path: Path | None = None) -> None:
        """Инициализация.

        Args:
            path: Путь к журналу (по умолчанию hkos/logs/performance.log).
        """
        self._path = path or Path(__file__).resolve().parent.parent / "logs" / "performance.log"

    def log(self, event: str, component: str, details: str = "") -> None:
        """Записать событие (append-only)."""
        line = (
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
            f"{event} {component} {details}\n"
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    @property
    def path(self) -> Path:
        """Путь к журналу."""
        return self._path


class PerformanceManager:
    """Фасад Performance Layer (DI; без бизнес-логики)."""

    def __init__(
        self,
        metrics: MetricsEngine | None = None,
        latency: LatencyTracker | None = None,
        profiler: Profiler | None = None,
        resource: ResourceMonitor | None = None,
        logger: PerformanceLogger | None = None,
        sys_logger: HKOSLogger | None = None,
    ) -> None:
        """Инициализация (все зависимости инжектируются)."""
        self._metrics = metrics or MetricsEngine()
        self._latency = latency or LatencyTracker()
        self._profiler = profiler or Profiler(self._metrics)
        self._resource = resource
        self._logger = logger or PerformanceLogger()
        self._sys_logger = sys_logger or HKOSLogger()
        self._enabled = True

    # ---- жизненный цикл ----

    def start(self) -> None:
        """Включить измерение (PROFILING_STARTED)."""
        self._enabled = True
        self._logger.log(EVENT_PROFILING_STARTED, "performance", "started")

    def stop(self) -> None:
        """Выключить измерение (PROFILING_FINISHED)."""
        self._enabled = False
        self._logger.log(EVENT_PROFILING_FINISHED, "performance", "stopped")

    def reset(self) -> None:
        """Сбросить метрики/историю (без остановки)."""
        self._metrics.clear()
        self._latency = LatencyTracker()

    # ---- профилирование ----

    @contextmanager
    def measure(
        self,
        operation: str,
        project_id: str = "",
        campaign_id: str = "",
        agent_id: str = "",
    ) -> Iterator[None]:
        """Измерить блок (если enabled; иначе — no-op)."""
        if not self._enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self._metrics.record(
                operation=operation, duration_ms=duration_ms,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                project_id=project_id, campaign_id=campaign_id, agent_id=agent_id)
            self._latency.record(operation, duration_ms)
            self._logger.log(
                EVENT_METRIC_RECORDED, operation, f"{duration_ms:.3f} ms")

    @contextmanager
    def profile(
        self,
        operation: str,
        project_id: str = "",
        campaign_id: str = "",
        agent_id: str = "",
    ) -> Iterator[None]:
        """Псевдоним measure: with manager.profile("retrieval"): ..."""
        with self.measure(operation, project_id, campaign_id, agent_id):
            yield

    # ---- наблюдаемость ----

    def statistics(self) -> dict[str, object]:
        """Статистика метрик + latency."""
        return {
            "metrics": self._metrics.statistics(),
            "latency": {
                "recent": {
                    metric.operation: self._latency.recent(metric.operation)
                    for metric in self._metrics.entries()[-1:]
                },
                "p50": self._percentiles(50),
                "p95": self._percentiles(95),
                "p99": self._percentiles(99),
            },
        }

    def health(self) -> dict[str, object]:
        """Состояние Performance Layer."""
        resource: dict[str, object] = {}
        if self._resource is not None:
            resource = self._resource.snapshot()
            ram = resource.get("ram_mb", 0)
            if isinstance(ram, (int, float)) and float(ram) > 4096:
                self._logger.log(
                    EVENT_RESOURCE_WARNING, "resource",
                    f"RAM {resource['ram_mb']:.0f} MB > 4096")
        return {
            "enabled": self._enabled,
            "metrics_count": len(self._metrics.entries()),
            "log_path": str(self._logger.path),
            "resources": resource,
        }

    def resource_warning(self, message: str) -> None:
        """Записать RESOURCE_WARNING в журнал."""
        self._logger.log(EVENT_RESOURCE_WARNING, "resource", message)

    # ---- авто-оптимизация (DS-013 ЭТАП 5 §8) ----

    def optimize(
        self, cache: object | None = None
    ) -> dict[str, object]:
        """Анализ статистики, очистка устаревшего кэша, рекомендации по
        Snapshot, предупреждения о деградации.

        ЗАПРЕЩЕНО автоматически: менять Knowledge, удалять данные,
        перестраивать Repository (только наблюдение/рекомендации).
        """
        metrics_report = [s.__dict__ for s in self._metrics.statistics()]
        recommendations: list[str] = []
        warnings: list[str] = []
        for stat in self._metrics.statistics():
            if stat.count > 10 and stat.average_ms > 200:
                warnings.append(
                    f"{stat.operation}: avg {stat.average_ms:.1f} ms > 200 ms")
                self._logger.log(
                    EVENT_RESOURCE_WARNING, "degradation",
                    f"{stat.operation} avg {stat.average_ms:.1f} ms")
            if stat.operation == "retrieval" and stat.average_ms > 100:
                recommendations.append(
                    "retrieval avg > 100 ms: check cache hit ratio / index size")
            if stat.operation == "context_build" and stat.average_ms > 200:
                recommendations.append(
                    "context_build avg > 200 ms: consider LIGHT/NORMAL compression")
        if cache is not None:
            stats = cache.statistics() if hasattr(cache, "statistics") else {}
            if isinstance(stats, dict) and stats.get("hit_ratio", 1.0) < 0.5:
                recommendations.append(
                    "cache hit ratio < 50%: review cache keys / TTL")
        # рекомендации по Snapshot (из размеров ресурсов)
        if self._resource is not None:
            resources = self._resource.snapshot()
            snapshot_size = resources.get("snapshot_size_bytes")
            if isinstance(snapshot_size, int) and snapshot_size > 100 * 1024 * 1024:
                recommendations.append(
                    "snapshot store > 100 MB: consider regeneration policy")
        return {
            "metrics": metrics_report,
            "recommendations": recommendations,
            "warnings": warnings,
        }

    # ---- внутренние ----

    def _percentiles(self, percentile: float) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for metric in self._metrics.entries():
            result.setdefault(metric.operation,
                              self._latency.percentile(metric.operation, percentile))
        return result
