"""HKOS Storage Engine
====================
Единый слой работы с файловой системой HKOS (DS-002).

Storage Engine — единственный компонент, имеющий право работать
с файловой системой HKOS напрямую. Он не принимает решений
о содержимом данных и не содержит бизнес-логики.
"""

import os
from typing import Any, Callable

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.storage.atomic_writer import AtomicWriter
from hkos.storage.file_store import FileStore
from hkos.storage.json_store import JSONStore
from hkos.storage.path_manager import PathManager

__all__ = ["StorageEngine"]


class StorageEngine:
    """Фасад Storage Engine: файловая система + JSON-документы.

    Публичный API (DS-002 §6): initialize, exists, read_json, write_json,
    update_json, delete, list, mkdir, health.

    Пути принимаются абсолютными или относительными к корню рабочей
    области (root). Для построения путей используйте PathManager.
    """

    # Ключ конфигурации корня рабочей области (config/hkos-*.yaml).
    CONFIG_ROOT_KEY: str = "hkos.root"

    # Значение по умолчанию корня рабочей области.
    DEFAULT_ROOT: str = "./hkos"

    def __init__(
        self,
        root: str | None,
        config: ConfigLoader,
        logger: HKOSLogger,
        version: VersionManager,
    ) -> None:
        """Инициализация Storage Engine.

        Args:
            root: Корень рабочей области; если None — из config.get("hkos.root").
            config: Существующий ConfigLoader (Sprint 1).
            logger: Существующий HKOSLogger (Sprint 1).
            version: Существующий VersionManager (Sprint 1).
        """
        self._config = config
        self._logger = logger
        self._version = version
        resolved_root = root if root is not None else config.get(
            self.CONFIG_ROOT_KEY, self.DEFAULT_ROOT
        )
        self._root: str = os.path.abspath(resolved_root)
        self._path_manager = PathManager()
        self._writer = AtomicWriter(logger)
        self._file_store = FileStore(logger, self._writer)
        self._json_store = JSONStore(logger, self._file_store, self._writer)
        self._initialized: bool = False

    @property
    def root(self) -> str:
        """Абсолютный путь корня рабочей области."""
        return self._root

    @property
    def path_manager(self) -> PathManager:
        """Экземпляр PathManager для построения путей."""
        return self._path_manager

    @property
    def json_store(self) -> JSONStore:
        """Экземпляр JSONStore для сериализации документов (DI)."""
        return self._json_store

    @property
    def is_initialized(self) -> bool:
        """Признак выполненной инициализации."""
        return self._initialized

    def _resolve(self, path: str) -> str:
        """Привести путь к абсолютному относительно корня рабочей области."""
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self._root, path))

    def initialize(self) -> None:
        """Создать корень рабочей области и подготовить Storage Engine.

        Raises:
            StorageWriteError: Если создание корня не удалось.
        """
        self._file_store.mkdir(self._root)
        self._initialized = True
        self._logger.info(
            f"StorageEngine initialized: root={self._root}, "
            f"version={self._version.version_string}"
        )

    def exists(self, path: str) -> bool:
        """Проверить существование файла или каталога."""
        return self._file_store.exists(self._resolve(path))

    def mkdir(self, path: str) -> None:
        """Создать каталог (включая родительские)."""
        self._file_store.mkdir(self._resolve(path))

    def list(self, path: str) -> list[str]:
        """Вернуть отсортированный список содержимого каталога.

        Raises:
            StorageReadError: Если каталог отсутствует.
        """
        return self._file_store.list(self._resolve(path))

    def delete(self, path: str) -> None:
        """Удалить файл.

        Raises:
            StorageWriteError: Если файл отсутствует или путь является каталогом.
        """
        self._file_store.delete(self._resolve(path))

    def read_json(self, path: str) -> dict[str, Any]:
        """Прочитать JSON-документ с проверкой конверта HKOS-08.

        Raises:
            StorageReadError: Если файл отсутствует.
            StorageSerializationError: Если документ некорректен.
            StorageMigrationRequired: Если требуется миграция.
        """
        return self._json_store.read(self._resolve(path))

    def write_json(self, path: str, doc: dict[str, Any]) -> None:
        """Атомарно записать JSON-документ (конверт обязателен).

        Raises:
            StorageSerializationError: Если конверт некорректен.
            StorageWriteError: Если запись не удалась.
        """
        self._json_store.write(self._resolve(path), doc)

    def update_json(
        self,
        path: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Прочитать документ, применить updater и атомарно записать.

        Raises:
            StorageSerializationError: Если конверт некорректен.
        """
        self._json_store.update(self._resolve(path), updater)

    def health(self) -> dict[str, Any]:
        """Вернуть состояние Storage Engine.

        Проверяются: инициализация, существование корня, доступность
        записи. Ошибок не выбрасывает — состояние возвращается в dict.
        """
        root_exists = os.path.isdir(self._root)
        writable = (
            os.access(self._root, os.W_OK) if root_exists else False
        )
        ok = self._initialized and root_exists and writable
        status = "PASS" if ok else "FAIL"
        if not ok:
            self._logger.warning(
                f"StorageEngine health: {status} (initialized="
                f"{self._initialized}, root_exists={root_exists}, "
                f"writable={writable})"
            )
        return {
            "status": status,
            "initialized": self._initialized,
            "root": self._root,
            "root_exists": root_exists,
            "writable": writable,
            "version": self._version.version_string,
        }
