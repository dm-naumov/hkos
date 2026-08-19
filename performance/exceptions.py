"""HKOS Performance Layer Exceptions (DS-013 ЭТАП 4)."""

from hkos.core.exceptions import HKOSError

__all__ = ["PerformanceError"]


class PerformanceError(HKOSError):
    """Базовое исключение Performance Layer."""

    def __init__(self, message: str, component: str = "performance") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)
