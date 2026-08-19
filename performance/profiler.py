"""HKOS Profiler (DS-013 ЭТАП 4)
==================================
Контекстный профилировщик: with profiler.measure("retrieval"): ...

Измеряет время выполнения; записывает в MetricsEngine; НЕ изменяет
выполнение/результаты. Overhead <= 2 ms (бюджет DS-013).
"""

import time
from contextlib import contextmanager
from typing import Iterator

from hkos.performance.metrics_engine import MetricsEngine

__all__ = ["Profiler"]


class Profiler:
    """Профилировщик операций (контекстный менеджер)."""

    def __init__(self, metrics: MetricsEngine) -> None:
        """Инициализация.

        Args:
            metrics: MetricsEngine (запись замеров).
        """
        self._metrics = metrics

    @contextmanager
    def measure(
        self,
        operation: str,
        project_id: str = "",
        campaign_id: str = "",
        agent_id: str = "",
    ) -> Iterator[None]:
        """Измерить время блока (не изменяет выполнение).

        Args:
            operation: Имя операции (retrieval/ranking/context/save/...).
            project_id: Проект (опционально).
            campaign_id: Кампания (опционально).
            agent_id: Агент (опционально).
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self._metrics.record(
                operation=operation,
                duration_ms=duration_ms,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                project_id=project_id,
                campaign_id=campaign_id,
                agent_id=agent_id,
            )
