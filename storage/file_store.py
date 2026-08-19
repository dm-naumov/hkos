"""HKOS File Store
===============
Низкоуровневые операции с файловой системой (DS-002).

File Store работает только с файловой системой и не принимает
решений о содержимом данных. Все записи выполняются атомарно
через AtomicWriter.
"""

import os

from hkos.core.logger import HKOSLogger
from hkos.storage.atomic_writer import AtomicWriter
from hkos.storage.exceptions import (
    StorageReadError,
    StorageWriteError,
)

__all__ = ["FileStore"]


class FileStore:
    """Базовые операции файловой системы HKOS.

    Методы покрывают область ответственности Storage Engine (DS-002 §4):
    создание каталогов, чтение/запись/удаление файлов,
    проверка существования, список содержимого каталога.
    """

    def __init__(self, logger: HKOSLogger, writer: AtomicWriter | None = None) -> None:
        """Инициализация File Store.

        Args:
            logger: Экземпляр HKOSLogger (hkos.core.logger).
            writer: AtomicWriter для атомарной записи; создаётся по умолчанию.
        """
        self._logger = logger
        self._writer = writer if writer is not None else AtomicWriter(logger)

    def exists(self, path: str) -> bool:
        """Проверить существование файла или каталога."""
        return os.path.exists(path)

    def is_dir(self, path: str) -> bool:
        """Проверить, что путь является каталогом."""
        return os.path.isdir(path)

    def is_file(self, path: str) -> bool:
        """Проверить, что путь является файлом."""
        return os.path.isfile(path)

    def read_text(self, path: str) -> str:
        """Прочитать файл как текст (UTF-8).

        Raises:
            StorageReadError: Если файл отсутствует или не читается.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            raise StorageReadError(f"Read failed for {path}: {e}") from e
        self._logger.info(f"Read OK: {path}")
        return content

    def write_text(self, path: str, content: str) -> None:
        """Атомарно записать текст в файл.

        Raises:
            StorageWriteError: Если каталог не существует или запись не удалась.
        """
        self._writer.write(path, content)

    def delete(self, path: str) -> None:
        """Удалить файл. Каталоги на DS-002 не удаляются.

        Raises:
            StorageWriteError: Если файл отсутствует или удаление не удалось.
        """
        if not os.path.exists(path):
            raise StorageWriteError(f"Delete failed: path does not exist: {path}")
        if os.path.isdir(path):
            raise StorageWriteError(
                f"Delete failed: directory deletion is not supported: {path}"
            )
        try:
            os.remove(path)
        except OSError as e:
            raise StorageWriteError(f"Delete failed for {path}: {e}") from e
        self._logger.info(f"Delete OK: {path}")

    def list(self, path: str) -> list[str]:
        """Вернуть отсортированный список имён содержимого каталога.

        Raises:
            StorageReadError: Если каталог отсутствует или не является каталогом.
        """
        if not os.path.isdir(path):
            raise StorageReadError(f"List failed: not a directory: {path}")
        try:
            names = sorted(os.listdir(path))
        except OSError as e:
            raise StorageReadError(f"List failed for {path}: {e}") from e
        return names

    def mkdir(self, path: str) -> None:
        """Создать каталог (включая родительские каталоги).

        Raises:
            StorageWriteError: Если создание не удалось.
        """
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise StorageWriteError(f"Mkdir failed for {path}: {e}") from e
        self._logger.info(f"Mkdir OK: {path}")
