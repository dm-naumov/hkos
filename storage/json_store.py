"""HKOS JSON Store
===============
Сериализация и хранение JSON-документов HKOS (DS-002, HKOS-08).

JSON Store отвечает за сериализацию:
- UTF-8;
- pretty print (indent=2);
- детерминированный порядок ключей (sort_keys=True);
- сохранение version документа;
- поддержку будущих миграций (StorageMigrationRequired при version > 1).

Каждый документ HKOS имеет единый конверт (HKOS-08 §2):
{schema, type, version, created_at, updated_at, data}.
"""

import json
from datetime import datetime, timezone
from typing import Any, Callable, cast

from hkos.core.logger import HKOSLogger
from hkos.storage.atomic_writer import AtomicWriter
from hkos.storage.exceptions import (
    StorageMigrationRequired,
    StorageSerializationError,
)
from hkos.storage.file_store import FileStore

__all__ = ["JSONStore"]


class JSONStore:
    """Чтение, запись и обновление JSON-документов с единым конвертом.

    Документ считается корректным, если содержит конверт HKOS-08:
    schema = "HKOS-1.0" и целочисленный version.
    """

    # Имя схемы (HKOS-08).
    SCHEMA_NAME: str = "HKOS-1.0"

    # Текущая поддерживаемая версия конверта.
    CURRENT_VERSION: int = 1

    # Ключи конверта (HKOS-08 §2).
    KEY_SCHEMA: str = "schema"
    KEY_TYPE: str = "type"
    KEY_VERSION: str = "version"
    KEY_CREATED_AT: str = "created_at"
    KEY_UPDATED_AT: str = "updated_at"
    KEY_DATA: str = "data"

    def __init__(
        self,
        logger: HKOSLogger,
        file_store: FileStore,
        writer: AtomicWriter | None = None,
    ) -> None:
        """Инициализация JSON Store.

        Args:
            logger: Экземпляр HKOSLogger (hkos.core.logger).
            file_store: Экземпляр FileStore для чтения файлов.
            writer: AtomicWriter для атомарной записи; создаётся по умолчанию.

        """
        self._logger = logger
        self._file_store = file_store
        self._writer = writer if writer is not None else AtomicWriter(logger)

    @staticmethod
    def _now() -> str:
        """Текущее время в формате ISO-8601 (UTC).

        Точность до микросекунд: обеспечивает детерминированный порядок
        документов, созданных в одну секунду (используется latest()).
        """
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    @staticmethod
    def serialize(obj: Any) -> str:
        """Сериализовать объект в JSON-строку.

        Детерминированный порядок ключей (sort_keys), pretty print (indent=2),
        UTF-8 (ensure_ascii=False).

        Raises:
            StorageSerializationError: Если объект не сериализуется.

        """
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
        except (TypeError, ValueError) as e:
            raise StorageSerializationError(f"Serialization failed: {e}") from e

    @staticmethod
    def deserialize(text: str) -> Any:
        """Разобрать JSON-строку.

        Raises:
            StorageSerializationError: Если строка не является корректным JSON.

        """
        try:
            return json.loads(text)
        except ValueError as e:
            raise StorageSerializationError(f"Deserialization failed: {e}") from e

    def validate_envelope(self, doc: Any) -> int:
        """Проверить конверт документа HKOS-08 и вернуть его version.

        Args:
            doc: Документ (объект после десериализации).

        Raises:
            StorageSerializationError: Если конверт отсутствует или некорректен.
            StorageMigrationRequired: Если version документа выше поддерживаемой.

        """
        if not isinstance(doc, dict):
            raise StorageSerializationError(
                "Document must be a JSON object (dict)"
            )
        if doc.get(self.KEY_SCHEMA) != self.SCHEMA_NAME:
            raise StorageSerializationError(
                f"Missing or invalid '{self.KEY_SCHEMA}' in document"
            )
        version = doc.get(self.KEY_VERSION)
        if not isinstance(version, int) or isinstance(version, bool):
            raise StorageSerializationError(
                f"Missing or invalid '{self.KEY_VERSION}' in document"
            )
        if version > self.CURRENT_VERSION:
            raise StorageMigrationRequired(
                f"Document version {version} requires migration "
                f"(supported: {self.CURRENT_VERSION})"
            )
        return version

    def create_envelope(
        self,
        data: Any,
        obj_type: str,
        version: int = 1,
    ) -> dict[str, Any]:
        """Создать конверт HKOS-08 вокруг данных.

        Args:
            data: Содержимое документа (раздел data).
            obj_type: Тип объекта (project, knowledge и т.п.).
            version: Версия документа (по умолчанию 1).

        Returns:
            Полный документ с конвертом и метками времени.

        """
        now = self._now()
        return {
            self.KEY_SCHEMA: self.SCHEMA_NAME,
            self.KEY_TYPE: obj_type,
            self.KEY_VERSION: version,
            self.KEY_CREATED_AT: now,
            self.KEY_UPDATED_AT: now,
            self.KEY_DATA: data,
        }

    def read(self, path: str) -> dict[str, Any]:
        """Прочитать и проверить JSON-документ.

        Raises:
            StorageReadError: Если файл отсутствует или не читается.
            StorageSerializationError: Если документ некорректен.
            StorageMigrationRequired: Если требуется миграция.

        """
        text = self._file_store.read_text(path)
        obj = self.deserialize(text)
        self.validate_envelope(obj)
        self._logger.info(f"JSON read OK: {path}")
        return cast(dict[str, Any], obj)

    def write(self, path: str, doc: dict[str, Any]) -> None:
        """Атомарно записать JSON-документ с конвертом.

        Сохраняет version документа, обновляет updated_at, заполняет
        created_at при отсутствии. Запись выполняется атомарно.

        Raises:
            StorageSerializationError: Если конверт некорректен.
            StorageWriteError: Если каталог не существует или запись не удалась.

        """
        self.validate_envelope(doc)
        now = self._now()
        out = dict(doc)
        out[self.KEY_UPDATED_AT] = now
        if self.KEY_CREATED_AT not in out:
            out[self.KEY_CREATED_AT] = now
        content = self.serialize(out)
        self._writer.write(path, content, validate_json=True)
        self._logger.info(f"JSON write OK: {path}")

    def write_data(
        self,
        path: str,
        data: Any,
        obj_type: str,
        version: int = 1,
    ) -> None:
        """Создать конверт и атомарно записать документ.

        Args:
            path: Путь файла.
            data: Содержимое раздела data.
            obj_type: Тип объекта.
            version: Версия документа.

        """
        self.write(path, self.create_envelope(data, obj_type, version))

    def update(
        self,
        path: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Прочитать документ, применить updater и атомарно записать.

        Args:
            path: Путь файла.
            updater: Функция, принимающая документ и возвращающая
                изменённый документ (с валидным конвертом).

        Raises:
            StorageSerializationError: Если конверт некорректен.
            StorageMigrationRequired: Если требуется миграция.

        """
        doc = self.read(path)
        updated = updater(doc)
        self.write(path, updated)
        self._logger.info(f"JSON update OK: {path}")
