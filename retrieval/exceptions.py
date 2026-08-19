"""HKOS Retrieval Exceptions (DS-008)
===================================
Специализированные исключения Retrieval Layer.
Наследуют HKOSError. RuntimeError/Exception не используются.
"""

from hkos.core.exceptions import HKOSError

__all__ = ["RetrievalError", "RetrievalScopeError"]


class RetrievalError(HKOSError):
    """Базовое исключение Retrieval Engine."""

    def __init__(self, message: str, component: str = "retrieval") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class RetrievalScopeError(RetrievalError):
    """Невозможно определить область поиска (проект обязателен)."""
