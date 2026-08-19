"""HKOS Storage Layer (DS-002)
=============================
Storage Engine — единый слой работы с файловой системой HKOS.

Публичный API пакета:
- StorageEngine — фасад (initialize, exists, read_json, write_json,
  update_json, delete, list, mkdir, health);
- FileStore — низкоуровневые операции файловой системы;
- JSONStore — сериализация и хранение JSON-документов (HKOS-08);
- AtomicWriter — атомарная запись файлов;
- PathManager — построение путей файловой структуры HKOS;
- StorageError и специализированные исключения.
"""

from hkos.storage.atomic_writer import AtomicWriter
from hkos.storage.exceptions import (
    StorageError,
    StorageMigrationRequired,
    StoragePathError,
    StorageReadError,
    StorageSerializationError,
    StorageWriteError,
)
from hkos.storage.file_store import FileStore
from hkos.storage.json_store import JSONStore
from hkos.storage.path_manager import PathManager
from hkos.storage.storage_engine import StorageEngine

__all__ = [
    "StorageEngine",
    "FileStore",
    "JSONStore",
    "AtomicWriter",
    "PathManager",
    "StorageError",
    "StorageReadError",
    "StorageWriteError",
    "StorageSerializationError",
    "StoragePathError",
    "StorageMigrationRequired",
]
