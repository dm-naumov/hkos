"""HKOS Project Repository (DS-003 §7)
====================================
Загрузка, сохранение, обновление и список проектов.
Ничего, кроме проектов: изменение Campaign/Knowledge запрещено.
"""

from typing import Any

from hkos.repository.base_repository import BaseRepository
from hkos.repository.exceptions import RepositoryParseError
from hkos.repository.models import PROJECT_STATUS_ACTIVE, Project
from hkos.storage.path_manager import PathManager


class ProjectRepository(BaseRepository[Project]):
    """Репозиторий проектов.

    Проект адресуется собственным id (slug по HKOS-08 §3 или UUID);
    документ хранится в projects/<id>/project.json.
    """

    _type_name: str = "project"

    def _dir_path(self, project: str) -> str:
        """Каталог всех проектов: <root>/projects."""
        return PathManager.projects(self._storage.root)

    def _file_path(self, project: str, object_id: str) -> str:
        """Путь документа проекта: projects/<id>/project.json."""
        return PathManager.project_file(self._storage.root, object_id)

    def _to_data(self, entity: Project) -> dict[str, object]:
        """Раздел data документа (HKOS-08 §3)."""
        return {
            "id": entity.id,
            "name": entity.name,
            "description": entity.description,
            "status": entity.status,
            "tags": entity.tags,
            "current_snapshot": entity.current_snapshot,
            "campaigns": entity.campaigns,
            "owner": entity.owner,
            "schema_version": entity.schema_version,
            "statistics": entity.statistics,
        }

    def _from_data(self, doc: dict[str, Any]) -> Project:
        """Сущность из документа HKOS-08."""
        data = doc.get("data", {})
        if not isinstance(data, dict):
            raise RepositoryParseError("Project document has invalid 'data' section")
        statistics = data.get("statistics", {})
        if not isinstance(statistics, dict):
            raise RepositoryParseError(
                "Project document has invalid 'statistics' section"
            )
        return Project(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            status=data.get("status", PROJECT_STATUS_ACTIVE),
            tags=data.get("tags", []),
            current_snapshot=data.get("current_snapshot", ""),
            campaigns=data.get("campaigns", []),
            owner=data.get("owner", ""),
            schema_version=data.get("schema_version", "1.0"),
            statistics=statistics,
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        )

    def load(self, project_id: str, object_id: str = "") -> Project:
        """Загрузить проект по id (проект адресуется только id)."""
        return super().load(project_id, object_id or project_id)

    def delete(self, project_id: str, object_id: str = "") -> None:
        """Удалить документ проекта (каталог проекта остаётся)."""
        super().delete(project_id, object_id or project_id)

    def exists(self, project_id: str, object_id: str = "") -> bool:
        """Проверить существование проекта."""
        return super().exists(project_id, object_id or project_id)

    def _list_ids(self, project: str) -> list[str]:
        """Id проектов: каталоги в projects/, содержащие project.json."""
        projects_root = PathManager.projects(self._storage.root)
        if not self._storage.exists(projects_root):
            return []
        return [
            name
            for name in self._storage.list(projects_root)
            if self._storage.exists(
                PathManager.project_file(self._storage.root, name)
            )
        ]

    def list(self, project: str = "") -> list[Project]:
        """Список всех проектов."""
        return [self.load(object_id) for object_id in self._list_ids(project)]

    def count(self, project: str = "") -> int:
        """Количество проектов."""
        return super().count(project)
