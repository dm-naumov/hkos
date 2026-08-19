"""HKOS Knowledge Relations (DS-006A §2)
========================================
Модель отношений между Knowledge.

relation_type — ТОЛЬКО через enum RelationType; строковые литералы
вне enum запрещены (DS-006A §2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

__all__ = [
    "RelationType",
    "KnowledgeRelation",
    "KnowledgeRelations",
]


class RelationType(str, Enum):
    """Типы отношений между Knowledge (единственный источник значений)."""

    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    MERGED_FROM = "MERGED_FROM"
    SUPERSEDES = "SUPERSEDES"
    SUPERSEDED_BY = "SUPERSEDED_BY"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    CANONICAL_OF = "CANONICAL_OF"
    DERIVED_FROM = "DERIVED_FROM"
    REFERENCE_TO = "REFERENCE_TO"


@dataclass
class KnowledgeRelation:
    """Отношение между двумя Knowledge.

    Attributes:
        relation_id: UUID отношения.
        source_id: UUID источника отношения.
        target_id: UUID цели отношения.
        relation_type: Тип отношения (RelationType).
        created_at: Метка создания (ISO-8601).
    """

    relation_id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation_type: RelationType = RelationType.REFERENCE_TO
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        """Отношение как словарь (сериализация)."""
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "KnowledgeRelation":
        """Отношение из словаря (десериализация)."""
        relation_type = RelationType.REFERENCE_TO
        raw_type = data.get("relation_type", "")
        if isinstance(raw_type, str):
            try:
                relation_type = RelationType(raw_type)
            except ValueError:
                relation_type = RelationType.REFERENCE_TO
        return cls(
            relation_id=str(data.get("relation_id", "")),
            source_id=str(data.get("source_id", "")),
            target_id=str(data.get("target_id", "")),
            relation_type=relation_type,
            created_at=str(data.get("created_at", "")),
        )


class KnowledgeRelations:
    """Построение наборов отношений (фабрика отношений)."""

    @staticmethod
    def _now() -> str:
        """Текущее время ISO-8601 (UTC)."""
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    @classmethod
    def create_merge_relations(
        cls,
        first_id: str,
        second_id: str,
        merged_id: str,
        timestamp: str = "",
    ) -> list[KnowledgeRelation]:
        """Двусторонние отношения для Merge (DS-006A §3).

        A + B -> C:
            A -> MERGED_FROM -> C
            B -> MERGED_FROM -> C
            C -> DERIVED_FROM -> A
            C -> DERIVED_FROM -> B

        Все 4 записи хранятся на C (владельце графа объединения);
        A и B остаются неизменными.

        Args:
            first_id: UUID первого источника (A).
            second_id: UUID второго источника (B).
            merged_id: UUID объединённого Knowledge (C).
            timestamp: Метка создания; по умолчанию — now.

        Returns:
            Список из 4 KnowledgeRelation.
        """
        ts = timestamp or cls._now()

        def rel(source: str, target: str, rtype: RelationType) -> KnowledgeRelation:
            return KnowledgeRelation(
                relation_id=str(uuid.uuid4()),
                source_id=source,
                target_id=target,
                relation_type=rtype,
                created_at=ts,
            )

        return [
            rel(first_id, merged_id, RelationType.MERGED_FROM),
            rel(second_id, merged_id, RelationType.MERGED_FROM),
            rel(merged_id, first_id, RelationType.DERIVED_FROM),
            rel(merged_id, second_id, RelationType.DERIVED_FROM),
        ]
