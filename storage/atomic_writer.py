"""HKOS Atomic Writer
===================
Атомарная запись файлов (DS-002).

Схема записи:
1. создать временный файл в том же каталоге;
2. записать данные и сбросить на диск (fsync);
3. проверить корректность JSON (если запрашивается);
4. заменить основной файл атомарной операцией os.replace.

Прямая перезапись рабочего файла запрещена.
При неудачной записи существующие данные не повреждаются.
"""

import json
import os
import tempfile

from hkos.core.logger import HKOSLogger
from hkos.storage.exceptions import StorageSerializationError, StorageWriteError

__all__ = ["AtomicWriter"]


class AtomicWriter:
    """Выполняет атомарную запись текстовых файлов.

    Временный файл создаётся в каталоге целевого файла, поэтому
    os.replace выполняется в пределах одной файловой системы.
    """

    # Суффикс временного файла.
    TEMP_SUFFIX: str = ".tmp"

    def __init__(self, logger: HKOSLogger) -> None:
        """Инициализация с Logger HKOS из Sprint 1.

        Args:
            logger: Экземпляр HKOSLogger (hkos.core.logger).
        """
        self._logger = logger

    def write(
        self,
        path: str,
        content: str,
        validate_json: bool = False,
    ) -> None:
        """Атомарно записать содержимое в файл.

        Args:
            path: Путь целевого файла.
            content: Текстовое содержимое (UTF-8).
            validate_json: Проверить, что содержимое является корректным JSON.

        Raises:
            StorageWriteError: Если каталог не существует или запись не удалась.
            StorageSerializationError: Если validate_json=True и JSON некорректен.
        """
        target_dir = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(target_dir):
            raise StorageWriteError(
                f"Write failed: directory does not exist: {target_dir}"
            )

        if validate_json:
            self._validate_json(content)

        tmp_path = ""
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=target_dir, suffix=self.TEMP_SUFFIX
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except OSError as e:
            raise StorageWriteError(f"Write failed for {path}: {e}") from e
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass  # Best effort — временный файл уже не нужен

        self._logger.info(f"Atomic write OK: {path}")

    def _validate_json(self, content: str) -> None:
        """Проверить корректность JSON до атомарной замены.

        Args:
            content: Сериализованный JSON.

        Raises:
            StorageSerializationError: Если содержимое не является JSON.
        """
        try:
            json.loads(content)
        except ValueError as e:
            raise StorageSerializationError(
                f"Invalid JSON content: {e}"
            ) from e
