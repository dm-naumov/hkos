"""HKOS Relationship Index (DS-007 §7) + Relationship Read Contract
================================================================
Индекс связей между сущностями (граф рёбер).

RelationshipReader — ЕДИНЫЙ READ-контракт чтения отношений
(Architectural Freeze Review, условие 2): единственная точка
получения relations of knowledge / relations of project для
будущего Graph Index и Retriever. Никакого Graph Search/Traversal
в DS-007 — только чтение.

Хранение (JSON):
    {"out": {source: [relation...]},
     "in":  {target: [relation...]},
     "entity_relations": {entity_id: [relation...]}}
"""

from typing import Any, Protocol, runtime_checkable

from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    RelationType,
)

__all__ = ["RelationshipReader", "RelationshipIndex"]


@runtime_checkable
class RelationshipReader(Protocol):
    """Единый контракт чтения отношений (Freeze, условие 2).

    Реализации: RelationshipIndex (через IndexManager).
    Позже может быть расширен/заменён Graph Index без изменения
    потребителей контракта.
    """

    def relations_of_knowledge(
        self, project: str, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        """Все отношения, затрагивающие Knowledge."""
        ...

    def relations_of_project(self, project: str) -> list[KnowledgeRelation]:
        """Все отношения проекта."""
        ...


def _relation_to_record(relation: KnowledgeRelation) -> dict[str, str]:
    """KnowledgeRelation -> запись индекса."""
    return {
        "relation_id": relation.relation_id,
        "source_id": relation.source_id,
        "target_id": relation.target_id,
        "relation_type": relation.relation_type.value,
        "created_at": relation.created_at,
    }


def _record_to_relation(record: dict[str, Any]) -> KnowledgeRelation:
    """Запись индекса -> KnowledgeRelation."""
    relation_type = RelationType.REFERENCE_TO
    raw_type = record.get("relation_type", "")
    if isinstance(raw_type, str):
        try:
            relation_type = RelationType(raw_type)
        except ValueError:
            relation_type = RelationType.REFERENCE_TO
    return KnowledgeRelation(
        relation_id=str(record.get("relation_id", "")),
        source_id=str(record.get("source_id", "")),
        target_id=str(record.get("target_id", "")),
        relation_type=relation_type,
        created_at=str(record.get("created_at", "")),
    )


class RelationshipIndex:
    """Индекс рёбер графа (out/in adjacency)."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Инициализация из данных (None — пустой индекс)."""
        self._data: dict[str, Any] = data or {
            "out": {},
            "in": {},
            "entity_relations": {},
        }

    def add_relations(
        self,
        entity_id: str,
        relations: list[KnowledgeRelation],
    ) -> None:
        """Заменить рёбра сущности (сначала удаляются старые)."""
        self.remove_relations(entity_id)
        if not relations:
            return
        out: dict[str, list[dict[str, str]]] = self._data["out"]
        inn: dict[str, list[dict[str, str]]] = self._data["in"]
        stored: list[dict[str, str]] = []
        for relation in relations:
            record = _relation_to_record(relation)
            source_entries = out.setdefault(relation.source_id, [])
            if not any(r["relation_id"] == relation.relation_id for r in source_entries):
                source_entries.append(record)
            target_entries = inn.setdefault(relation.target_id, [])
            if not any(r["relation_id"] == relation.relation_id for r in target_entries):
                target_entries.append(record)
            stored.append(record)
        self._data["entity_relations"][entity_id] = stored

    def remove_relations(self, entity_id: str) -> None:
        """Удалить рёбра сущности."""
        stored: list[dict[str, str]] = self._data["entity_relations"].pop(
            entity_id, []
        )
        out: dict[str, list[dict[str, str]]] = self._data["out"]
        inn: dict[str, list[dict[str, str]]] = self._data["in"]
        for record in stored:
            for container, key in ((out, record["source_id"]), (inn, record["target_id"])):
                entries = container.get(key)
                if not entries:
                    continue
                remaining = [
                    e for e in entries if e["relation_id"] != record["relation_id"]
                ]
                if remaining:
                    container[key] = remaining
                else:
                    del container[key]

    def relations_of_knowledge(
        self, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        """Все рёбра, где knowledge_id — источник или цель (dedup)."""
        out = self._data["out"].get(knowledge_id, [])
        inn = self._data["in"].get(knowledge_id, [])
        seen: set[str] = set()
        result: list[KnowledgeRelation] = []
        for record in out + inn:
            relation_id = record["relation_id"]
            if relation_id in seen:
                continue
            seen.add(relation_id)
            result.append(_record_to_relation(record))
        result.sort(key=lambda r: r.created_at)
        return result

    def relations_of_project(self) -> list[KnowledgeRelation]:
        """Все рёбра проекта (flatten, dedup по relation_id)."""
        seen: set[str] = set()
        result: list[KnowledgeRelation] = []
        for records in self._data["out"].values():
            for record in records:
                relation_id = record["relation_id"]
                if relation_id in seen:
                    continue
                seen.add(relation_id)
                result.append(_record_to_relation(record))
        result.sort(key=lambda r: r.created_at)
        return result

    def edge_count(self) -> int:
        """Количество уникальных рёбер."""
        seen: set[str] = set()
        for records in self._data["out"].values():
            for record in records:
                seen.add(record["relation_id"])
        return len(seen)

    def data(self) -> dict[str, Any]:
        """Данные для персистентности."""
        return self._data
