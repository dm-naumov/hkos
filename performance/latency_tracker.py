"""HKOS Latency Tracker (DS-013 ЭТАП 4)
==========================================
История задержек операций + перцентили p50/p95/p99.

Только измерение; не изменяет выполнение.
"""

import statistics
from collections import deque
from typing import Final

__all__ = ["LatencyTracker"]

_P50: Final[float] = 50.0
_P95: Final[float] = 95.0
_P99: Final[float] = 99.0


class LatencyTracker:
    """Кольцевая история задержек (по операциям)."""

    def __init__(self, max_history: int = 10_000) -> None:
        """Инициализация.

        Args:
            max_history: Максимум замеров на операцию.
        """
        self._history: dict[str, deque[float]] = {}
        self._max_history = max_history

    def record(self, operation: str, duration_ms: float) -> None:
        """Записать задержку операции."""
        history = self._history.setdefault(operation, deque(maxlen=self._max_history))
        history.append(float(duration_ms))

    def recent(self, operation: str, limit: int = 10) -> list[float]:
        """Последние замеры операции (новые в конце)."""
        history = self._history.get(operation)
        if history is None:
            return []
        return list(history)[-limit:]

    def average(self, operation: str) -> float | None:
        """Средняя задержка операции (None — нет замеров)."""
        history = self._history.get(operation)
        if not history:
            return None
        return sum(history) / len(history)

    def percentile(self, operation: str, percentile: float) -> float | None:
        """Перцентиль задержек операции (p50/p95/p99)."""
        history = self._history.get(operation)
        if not history:
            return None
        if len(history) < 2:
            # Один замер: любой перцентиль = это значение
            # (statistics.quantiles требует >=2 точек).
            return float(history[0])
        quantiles = statistics.quantiles(
            sorted(history), n=100, method="inclusive")
        # quantiles содержит n-1=99 точек (индексы 0..98)
        index = int(percentile) * (len(quantiles)) // 100
        return quantiles[index]
