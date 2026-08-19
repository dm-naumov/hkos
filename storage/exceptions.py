"""HKOS Storage Exceptions
========================
Специализированные исключения слоя хранения HKOS (DS-002).

Иерархия: все исключения Storage наследуют StorageError,
который наследует HKOSError из Sprint 1 (hkos/core/exceptions.py).
"""

from hkos.core.exceptions import HKOSError

__all__ = [
    "StorageError",
    "StorageReadError",
    "StorageWriteError",
    "StorageSerializationError",
    "StoragePathError",
    "StorageMigrationRequired",
]


class StorageError(HKOSError):
    """Базовое исключение Storage Engine."""

    def __init__(self, message: str, component: str = "storage") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class StorageReadError(StorageError):
    """Ошибка чтения файла или каталога."""


class StorageWriteError(StorageError):
    """Ошибка записи, удаления или создания объекта."""


class StorageSerializationError(StorageError):
    """Ошибка сериализации/десериализации JSON."""


class StoragePathError(StorageError):
    """Некорректный путь или недопустимый компонент пути."""


class StorageMigrationRequired(StorageError):
    """Документ имеет версию, требующую миграции (не поддерживается)."""
