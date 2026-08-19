"""HKOS Librarian Exceptions (DS-006)
===================================
Специализированные исключения сервисного слоя Librarian.
Наследуют HKOSError. RuntimeError/Exception не используются.
"""

from hkos.core.exceptions import HKOSError

__all__ = [
    "LibrarianError",
    "KnowledgeNotFoundError",
    "KnowledgeStatusError",
]


class LibrarianError(HKOSError):
    """Базовое исключение Librarian."""

    def __init__(self, message: str, component: str = "librarian") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class KnowledgeNotFoundError(LibrarianError):
    """Knowledge не найдено."""


class KnowledgeStatusError(LibrarianError):
    """Запрещённый переход статуса Knowledge."""
