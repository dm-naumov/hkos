"""HKOS Snapshot Exceptions (DS-010)
==================================
Специализированные исключения Snapshot Layer.
Наследуют HKOSError. RuntimeError/Exception не используются.
"""

from hkos.core.exceptions import HKOSError

__all__ = ["SnapshotError", "SnapshotNotFoundError", "SnapshotValidationError"]


class SnapshotError(HKOSError):
    """Базовое исключение Snapshot Engine."""

    def __init__(self, message: str, component: str = "snapshot") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class SnapshotNotFoundError(SnapshotError):
    """Snapshot не найден (нет снимков / версия отсутствует)."""


class SnapshotValidationError(SnapshotError):
    """Snapshot не прошёл валидацию."""
