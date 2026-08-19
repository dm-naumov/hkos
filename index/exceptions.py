"""HKOS Index Exceptions (DS-007)
==============================
Специализированные исключения Index Layer.
Наследуют HKOSError. RuntimeError/Exception не используются.
"""

from hkos.core.exceptions import HKOSError

__all__ = [
    "IndexError",
    "IndexNotFoundError",
    "IndexCorruptedError",
]


class IndexError(HKOSError):
    """Базовое исключение Index Engine."""

    def __init__(self, message: str, component: str = "index") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class IndexNotFoundError(IndexError):
    """Индекс не найден (файл отсутствует или не создан)."""


class IndexCorruptedError(IndexError):
    """Индекс повреждён (не парсится, битые ссылки, невалидная структура)."""
