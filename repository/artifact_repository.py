"""HKOS Artifact Repository (DS-003 §11)
=====================================
Работа с артефактами: отчёты, конфигурации, изображения, схемы, документы.
"""

from typing import Any

from hkos.repository.base_repository import BaseRepository
from hkos.repository.exceptions import RepositoryParseError
from hkos.repository.models import ARTIFACT_STATUS_ARCHIVED, Artifact
from hkos.storage.path_manager import PathManager

__all__ = ["ArtifactRepository"]


class ArtifactRepository(BaseRepository[Artifact]):
    """Репозиторий артефактов проекта.

    Документ — projects/<p>/artifacts/<id>.json (HKOS-08 §9).
    """

    _type_name: str = "artifact"

    def _dir_path(self, project: str) -> str:
        """Каталог артефактов проекта: projects/<p>/artifacts."""
        return PathManager.artifacts(self._storage.root, project)

    def _file_path(self, project: str, object_id: str) -> str:
        """Путь документа артефакта."""
        return PathManager.artifact_file(self._storage.root, project, object_id)

    def _to_data(self, entity: Artifact) -> dict[str, object]:
        """Раздел data документа (HKOS-08 §9)."""
        return {
            "id": entity.id,
            "project": entity.project,
            "kind": entity.kind,
            "path": entity.path,
            "checksum": entity.checksum,
            "campaign": entity.campaign,
            "cycle": entity.cycle,
            "status": entity.status,
        }

    def _from_data(self, doc: dict[str, Any]) -> Artifact:
        """Сущность из документа HKOS-08."""
        data = doc.get("data", {})
        if not isinstance(data, dict):
            raise RepositoryParseError("Artifact document has invalid 'data' section")
        return Artifact(
            id=data.get("id", ""),
            project=data.get("project", ""),
            kind=data.get("kind", ""),
            path=data.get("path", ""),
            checksum=data.get("checksum", ""),
            campaign=data.get("campaign", ""),
            cycle=data.get("cycle", 0),
            status=data.get("status", "active"),
        )

    def archive(self, project: str, object_id: str) -> Artifact:
        """Архивировать артефакт (статус archived; явная команда)."""
        artifact = self.load(project, object_id)
        artifact.status = ARTIFACT_STATUS_ARCHIVED
        self.update(artifact)
        return artifact
