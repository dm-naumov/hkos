"""HKOS Repository Exceptions
===========================
Специализированные исключения слоя репозиториев (DS-003).

Иерархия: RepositoryError -> HKOSError (Sprint 1).
Использование общих RuntimeError/Exception запрещено.
"""

from hkos.core.exceptions import HKOSError

__all__ = [
    "RepositoryError",
    "RepositoryNotFoundError",
    "RepositoryParseError",
]


class RepositoryError(HKOSError):
    """Базовое исключение Repository."""

    def __init__(self, message: str, component: str = "repository") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class RepositoryNotFoundError(RepositoryError):
    """Объект не найден (load/update/delete отсутствующего объекта)."""


class RepositoryParseError(RepositoryError):
    """Документ не соответствует ожидаемому типу или структуре."""
