"""HKOS Context Exceptions (DS-009)
==============================
Специализированные исключения Context Layer.
Наследуют HKOSError. RuntimeError/Exception не используются.
"""

from hkos.core.exceptions import HKOSError

__all__ = ["ContextError", "ContextValidationError"]


class ContextError(HKOSError):
    """Базовое исключение Context Builder."""

    def __init__(self, message: str, component: str = "context") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class ContextValidationError(ContextError):
    """Контекст не прошёл валидацию."""
