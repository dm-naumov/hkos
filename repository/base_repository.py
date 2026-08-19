"""HKOS Base Repository (DS-003)
=============================
Общий CRUD-слой для объектов предметной области HKOS.

Правила слоя (IP-003):
- Repository не содержит бизнес-логики — только сохраняет и извлекает;
- обращение к файловой системе — исключительно через StorageEngine;
- сериализация — исключительно через JSONStore;
- пути — исключительно через PathManager;
- зависимости (StorageEngine, JSONStore) передаются извне (DI);
- UUID объектов не изменяются и не генерируются повторно.
"""

import os
import uuid
from typing import Any, Generic, TypeVar

from hkos.repository.exceptions import (
    RepositoryError,
    RepositoryNotFoundError,
    RepositoryParseError,
)
from hkos.storage.exceptions import StorageReadError
from hkos.storage.json_store import JSONStore
from hkos.storage.storage_engine import StorageEngine

__all__ = ["BaseRepository"]

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Базовый репозиторий: общий CRUD для JSON-документов HKOS.

    Специализированные репозитории наследуются только от него и
    переопределяют хуки адресации и преобразования сущностей.
    """

    # Тип объекта в конверте HKOS-08 (переопределяется в наследниках).
    _type_name: str = "object"

    def __init__(self, storage: StorageEngine, json_store: JSONStore) -> None:
        """Инициализация репозитория.

        Args:
            storage: StorageEngine (Sprint 2) — единственная точка доступа к ФС.
            json_store: JSONStore (Sprint 2) — сериализация документов.

        """
        self._storage = storage
        self._json = json_store

    @property
    def storage(self) -> StorageEngine:
        """Используемый StorageEngine."""
        return self._storage

    # --- Хуки адресации и преобразования (переопределяются) ---

    def _dir_path(self, project: str) -> str:
        """Вернуть каталог объектов репозитория в проекте."""
        raise NotImplementedError

    def _file_path(self, project: str, object_id: str) -> str:
        """Вернуть путь файла объекта."""
        raise NotImplementedError

    def _to_data(self, entity: T) -> dict[str, object]:
        """Преобразовать сущность в раздел data документа HKOS-08."""
        raise NotImplementedError

    def _from_data(self, doc: dict[str, Any]) -> T:
        """Преобразовать документ HKOS-08 в сущность."""
        raise NotImplementedError

    # --- Внутренние операции ---

    def _new_id(self) -> str:
        """Сгенерировать новый UUID (только при первом сохранении)."""
        return str(uuid.uuid4())

    def _entity_id(self, entity: T) -> str:
        """Вернуть id сущности, назначив UUID при его отсутствии."""
        eid: str = getattr(entity, "id")
        if not eid:
            eid = self._new_id()
            setattr(entity, "id", eid)
        return eid

    def _project_of(self, entity: T) -> str:
        """Вернуть проект сущности (для Project проект == его id).

        Raises:
            RepositoryError: Если сущность привязана к проекту,
                но проект не задан.

        """
        if hasattr(entity, "project"):
            project: str = getattr(entity, "project")
            if not project:
                raise RepositoryError(
                    f"{type(entity).__name__} has no project set"
                )
            return project
        return self._entity_id(entity)

    def _read_doc(self, project: str, object_id: str) -> dict[str, Any]:
        """Прочитать документ объекта или поднять RepositoryNotFoundError."""
        path = self._file_path(project, object_id)
        if not self._storage.exists(path):
            raise RepositoryNotFoundError(
                f"{self._type_name} not found: {object_id} in project {project}"
            )
        try:
            return self._storage.read_json(path)
        except StorageReadError as e:
            raise RepositoryNotFoundError(
                f"{self._type_name} not found: {object_id} in project {project}"
            ) from e

    def _parse_doc(self, doc: Any, object_id: str) -> T:
        """Проверить тип документа и преобразовать в сущность."""
        if not isinstance(doc, dict):
            raise RepositoryParseError(
                f"Document for {object_id} is not a JSON object"
            )
        if doc.get("type") != self._type_name:
            raise RepositoryParseError(
                f"Document {object_id} has type {doc.get('type')!r}, "
                f"expected {self._type_name!r}"
            )
        return self._from_data(doc)

    def _envelope(self, entity: T, existing: dict[str, Any] | None) -> dict[str, Any]:
        """Собрать конверт HKOS-08, сохранив created_at/version документа."""
        doc = self._json.create_envelope(
            self._to_data(entity), self._type_name
        )
        if existing is not None:
            doc[self._json.KEY_CREATED_AT] = existing.get(
                self._json.KEY_CREATED_AT, doc[self._json.KEY_CREATED_AT]
            )
            doc[self._json.KEY_VERSION] = existing.get(
                self._json.KEY_VERSION, doc[self._json.KEY_VERSION]
            )
        return doc

    # --- Публичный интерфейс (DS-003 §6) ---

    def save(self, entity: T) -> T:
        """Сохранить объект; при отсутствии id — назначить UUID один раз.

        Повторное сохранение не повреждает данные: сохраняются
        created_at и version существующего документа.
        """
        eid = self._entity_id(entity)
        project = self._project_of(entity)
        path = self._file_path(project, eid)
        self._storage.mkdir(os.path.dirname(path))
        existing = self._read_doc(project, eid) if self._storage.exists(path) else None
        self._storage.write_json(path, self._envelope(entity, existing))
        return entity

    def load(self, project: str, object_id: str) -> T:
        """Загрузить объект по проекту и id.

        Raises:
            RepositoryNotFoundError: Если объект отсутствует.
            RepositoryParseError: Если документ имеет неверный тип.

        """
        return self._parse_doc(self._read_doc(project, object_id), object_id)

    def update(self, entity: T) -> T:
        """Обновить существующий объект.

        UUID не изменяется; created_at и version сохраняются.

        Raises:
            RepositoryNotFoundError: Если объекта нет или id не задан.

        """
        eid = getattr(entity, "id")
        if not eid:
            raise RepositoryNotFoundError(
                "update requires entity with id"
            )
        project = self._project_of(entity)
        existing = self._read_doc(project, eid)
        path = self._file_path(project, eid)
        self._storage.mkdir(os.path.dirname(path))
        self._storage.write_json(path, self._envelope(entity, existing))
        return entity

    def delete(self, project: str, object_id: str) -> None:
        """Удалить объект.

        Raises:
            RepositoryNotFoundError: Если объект отсутствует.

        """
        path = self._file_path(project, object_id)
        if not self._storage.exists(path):
            raise RepositoryNotFoundError(
                f"{self._type_name} not found: {object_id} in project {project}"
            )
        self._storage.delete(path)

    def exists(self, project: str, object_id: str) -> bool:
        """Проверить существование объекта."""
        return self._storage.exists(self._file_path(project, object_id))

    def _list_ids(self, project: str) -> list[str]:
        """Вернуть id объектов в проекте (без чтения содержимого)."""
        if not self._storage.exists(self._dir_path(project)):
            return []
        return [
            name[: -len(".json")]
            for name in self._storage.list(self._dir_path(project))
            if name.endswith(".json")
        ]

    def list(self, project: str) -> list[T]:
        """Вернуть все объекты проекта (только необходимые документы)."""
        return [self.load(project, object_id) for object_id in self._list_ids(project)]

    def count(self, project: str) -> int:
        """Вернуть количество объектов проекта без загрузки документов."""
        return len(self._list_ids(project))
