"""HKOS Decision Repository (DS-003 §10)
=====================================
Работа с Decision и DecisionHistory. Удаление решений запрещено.
"""

from typing import Any

from hkos.repository.base_repository import BaseRepository
from hkos.repository.exceptions import (
    RepositoryError,
    RepositoryNotFoundError,
    RepositoryParseError,
)
from hkos.repository.models import DECISION_ACCEPT, Decision, DecisionHistory
from hkos.storage.path_manager import PathManager

__all__ = ["DecisionRepository"]


class DecisionRepository(BaseRepository[Decision]):
    """Репозиторий решений проекта (append-only).

    Документ — projects/<p>/decisions/<id>.json (HKOS-08 §8).
    """

    _type_name: str = "decision"

    def _dir_path(self, project: str) -> str:
        """Каталог решений проекта: projects/<p>/decisions."""
        return PathManager.decisions(self._storage.root, project)

    def _file_path(self, project: str, object_id: str) -> str:
        """Путь документа решения."""
        return PathManager.decision_file(self._storage.root, project, object_id)

    def _to_data(self, entity: Decision) -> dict[str, object]:
        """Раздел data документа (HKOS-08 §8)."""
        return {
            "id": entity.id,
            "project": entity.project,
            "decision": entity.decision,
            "campaign": entity.campaign,
            "cycle": entity.cycle,
            "reason": entity.reason,
            "confidence": entity.confidence,
        }

    def _from_data(self, doc: dict[str, Any]) -> Decision:
        """Сущность из документа HKOS-08."""
        data = doc.get("data", {})
        if not isinstance(data, dict):
            raise RepositoryParseError("Decision document has invalid 'data' section")
        return Decision(
            id=data.get("id", ""),
            project=data.get("project", ""),
            decision=data.get("decision", DECISION_ACCEPT),
            campaign=data.get("campaign", ""),
            cycle=data.get("cycle", 0),
            reason=data.get("reason", ""),
            confidence=data.get("confidence", 0),
        )

    def append(self, decision: Decision) -> Decision:
        """Добавить решение (сохранить с назначением UUID при необходимости)."""
        return self.save(decision)

    def history(self, project: str) -> DecisionHistory:
        """Вся история решений проекта (append-only)."""
        return DecisionHistory(entries=self.list(project))

    def latest(self, project: str) -> Decision:
        """Последнее решение проекта (по created_at документа).

        Raises:
            RepositoryNotFoundError: Если решений нет.

        """
        object_ids = self._list_ids(project)
        if not object_ids:
            raise RepositoryNotFoundError(
                f"No decisions found in project {project}"
            )
        newest = max(
            object_ids,
            key=lambda object_id: self._read_doc(project, object_id).get(
                "created_at", ""
            ),
        )
        return self.load(project, newest)

    def delete(self, project: str, object_id: str) -> None:
        """Удаление решений запрещено (DS-003 §10)."""
        raise RepositoryError(
            f"Deletion of decisions is forbidden (DS-003 §10): {object_id}"
        )
