"""HKOS Metrics Engine (DS-013 ЭТАП 4)
======================================
Хранит ТОЛЬКО метрики (operation/timestamp/duration_ms/project_id/
campaign_id/agent_id). Статистика: count/average/min/max по операции.

- НЕ изменяет данные; НЕ влияет на pipeline; НЕ знает о бизнес-логике;
- overhead записи <= 1 ms (бюджет DS-013).
"""

from dataclasses import dataclass

__all__ = ["Metric", "MetricsEngine"]


@dataclass(frozen=True)
class Metric:
    """Одна запись метрики (иммутабельна)."""

    operation: str
    timestamp: str
    duration_ms: float
    project_id: str = ""
    campaign_id: str = ""
    agent_id: str = ""


@dataclass(frozen=True)
class MetricStatistics:
    """Агрегированная статистика по операции."""

    operation: str
    count: int
    average_ms: float
    min_ms: float
    max_ms: float


class MetricsEngine:
    """Хранилище метрик (append-only; clear() для сброса)."""

    def __init__(self, max_records: int = 100_000) -> None:
        """Инициализация.

        Args:
            max_records: Ограничение объёма (FIFO-вытеснение).
        """
        self._records: list[Metric] = []
        self._max_records = max_records

    def record(
        self,
        operation: str,
        duration_ms: float,
        timestamp: str = "",
        project_id: str = "",
        campaign_id: str = "",
        agent_id: str = "",
    ) -> None:
        """Записать метрику (O(1); append-only)."""
        self._records.append(Metric(
            operation=operation,
            timestamp=timestamp,
            duration_ms=float(duration_ms),
            project_id=project_id,
            campaign_id=campaign_id,
            agent_id=agent_id,
        ))
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

    def statistics(self, operation: str | None = None) -> list[MetricStatistics]:
        """Статистика по операциям (count/average/min/max)."""
        groups: dict[str, list[float]] = {}
        for metric in self._records:
            if operation is not None and metric.operation != operation:
                continue
            groups.setdefault(metric.operation, []).append(metric.duration_ms)
        result: list[MetricStatistics] = []
        for name, durations in sorted(groups.items()):
            result.append(MetricStatistics(
                operation=name,
                count=len(durations),
                average_ms=sum(durations) / len(durations),
                min_ms=min(durations),
                max_ms=max(durations),
            ))
        return result

    def entries(self) -> list[Metric]:
        """Все записи (копия; порядок = порядок записи)."""
        return list(self._records)

    def clear(self) -> None:
        """Полная очистка."""
        self._records = []
