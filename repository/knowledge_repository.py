"""HKOS Knowledge Repository (DS-003 §9)
=====================================
Работа с объектами Knowledge: create/load/update/archive/list,
линейный поиск по тегу и типу (без индексации).
"""

from typing import Any

from hkos.repository.base_repository import BaseRepository
from hkos.repository.exceptions import RepositoryParseError
from hkos.repository.models import (
    KNOWLEDGE_STATUS_ARCHIVED,
    Knowledge,
    KnowledgeHistoryEntry,
    KnowledgeRelation,
)
from hkos.storage.path_manager import PathManager

__all__ = ["KnowledgeRepository"]


class KnowledgeRepository(BaseRepository[Knowledge]):
    """Репозиторий знаний проекта.

    Документ — projects/<p>/knowledge/<id>.json (HKOS-08 §5).
    Никакой индексации: только линейный поиск по полям.
    """

    _type_name: str = "knowledge"

    def _dir_path(self, project: str) -> str:
        """Каталог знаний проекта: projects/<p>/knowledge."""
        return PathManager.knowledge(self._storage.root, project)

    def _file_path(self, project: str, object_id: str) -> str:
        """Путь документа знания."""
        return PathManager.knowledge_file(self._storage.root, project, object_id)

    def _to_data(self, entity: Knowledge) -> dict[str, object]:
        """Раздел data документа (HKOS-08 §5)."""
        return {
            "id": entity.id,
            "project": entity.project,
            "kind": entity.kind,
            "title": entity.title,
            "body": entity.body,
            "confidence": entity.confidence,
            "status": entity.status,
            "source_campaign": entity.source_campaign,
            "source_cycle": entity.source_cycle,
            "references": entity.references,
            "tags": entity.tags,
            "category": entity.category,
            "parent_ids": entity.parent_ids,
            "canonical_id": entity.canonical_id,
            "confirmations": entity.confirmations,
            "independent_campaigns": entity.independent_campaigns,
            "successful_usage": entity.successful_usage,
            "failed_usage": entity.failed_usage,
            "conflicts": entity.conflicts,
            "history": [entry.to_dict() for entry in entity.history],
            "relations": [rel.to_dict() for rel in entity.relations],
        }

    def _from_data(self, doc: dict[str, Any]) -> Knowledge:
        """Сущность из документа HKOS-08."""
        data = doc.get("data", {})
        if not isinstance(data, dict):
            raise RepositoryParseError("Knowledge document has invalid 'data' section")
        history_data = data.get("history", [])
        if not isinstance(history_data, list):
            raise RepositoryParseError(
                "Knowledge document has invalid 'history' section"
            )
        history = [
            KnowledgeHistoryEntry.from_dict(item)
            for item in history_data
            if isinstance(item, dict)
        ]
        relations_data = data.get("relations", [])
        if not isinstance(relations_data, list):
            raise RepositoryParseError(
                "Knowledge document has invalid 'relations' section"
            )
        relations = [
            KnowledgeRelation.from_dict(item)
            for item in relations_data
            if isinstance(item, dict)
        ]
        return Knowledge(
            id=data.get("id", ""),
            project=data.get("project", ""),
            kind=data.get("kind", "fact"),
            title=data.get("title", ""),
            body=data.get("body", ""),
            confidence=data.get("confidence", 0),
            status=data.get("status", "new"),
            source_campaign=data.get("source_campaign", ""),
            source_cycle=data.get("source_cycle", 0),
            references=data.get("references", []),
            tags=data.get("tags", []),
            category=data.get("category", ""),
            parent_ids=data.get("parent_ids", []),
            canonical_id=data.get("canonical_id", ""),
            confirmations=data.get("confirmations", 0),
            independent_campaigns=data.get("independent_campaigns", 0),
            successful_usage=data.get("successful_usage", 0),
            failed_usage=data.get("failed_usage", 0),
            conflicts=data.get("conflicts", 0),
            history=history,
            relations=relations,
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        )

    def create(self, knowledge: Knowledge) -> Knowledge:
        """Создать знание."""
        return self.save(knowledge)

    def archive(self, project: str, object_id: str) -> Knowledge:
        """Архивировать знание (статус archived; явная команда)."""
        knowledge = self.load(project, object_id)
        knowledge.status = KNOWLEDGE_STATUS_ARCHIVED
        self.update(knowledge)
        return knowledge

    def search_by_tag(self, project: str, tag: str) -> list[Knowledge]:
        """Линейный поиск знаний по тегу."""
        return [k for k in self.list(project) if tag in k.tags]

    def search_by_type(self, project: str, kind: str) -> list[Knowledge]:
        """Линейный поиск знаний по типу (kind)."""
        return [k for k in self.list(project) if k.kind == kind]
