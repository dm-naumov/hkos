"""HKOS Knowledge Merger (DS-006 §13, IP-006 §6, §13)
====================================================
Создаёт новое Canonical Knowledge из двух источников.

Правила:
- Merger НИКОГДА не удаляет Knowledge;
- Merger всегда создаёт новое Canonical Knowledge C (новый UUID);
- исходные A и B остаются неизменными (immutability);
- обязательно сохраняются: parent_ids, merge_timestamp, merge_reason.

Merger не обращается к Repository — только строит сущность.
"""

import uuid
from datetime import datetime, timezone

from hkos.repository.knowledge_relations import KnowledgeRelations
from hkos.repository.models import Knowledge, KnowledgeHistoryEntry
from hkos.services.librarian.category_merge import CategoryMergePolicy
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_CANONICAL,
)

__all__ = ["KnowledgeMerger"]

MERGE_DETAILS_EVENT: str = "Merged"


class KnowledgeMerger:
    """Объединение двух Knowledge в новое Canonical Knowledge."""

    @staticmethod
    def _now() -> str:
        """Текущее время ISO-8601 (UTC)."""
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    @classmethod
    def merge(
        cls,
        a: Knowledge,
        b: Knowledge,
        reason: str = "",
        merge_timestamp: str = "",
    ) -> Knowledge:
        """Создать Canonical Knowledge из A и B.

        Args:
            a: Первый источник (не изменяется).
            b: Второй источник (не изменяется).
            reason: Причина объединения (merge_reason).
            merge_timestamp: Метка объединения; по умолчанию — now.

        Returns:
            Новое Knowledge (новый UUID) со статусом CANONICAL,
            parent_ids=[a.id, b.id] и сохранёнными атрибутами объединения.
        """
        timestamp = merge_timestamp or cls._now()
        combined_title = a.title if a.title == b.title else f"{a.title} / {b.title}"
        combined_body = "\n".join(part for part in (a.body, b.body) if part)
        merged = Knowledge(
            id=str(uuid.uuid4()),
            project=a.project,
            kind=a.kind,
            title=combined_title,
            body=combined_body,
            status=KNOWLEDGE_STATUS_CANONICAL,
            # Выбор категории — через CategoryMergePolicy (DS-006A §6).
            category=CategoryMergePolicy.resolve(a.category, b.category),
            source_campaign=a.source_campaign or b.source_campaign,
            tags=sorted(set(a.tags + b.tags)),
            references=sorted(set(a.references + b.references)),
            parent_ids=[a.id, b.id],
            confirmations=a.confirmations + b.confirmations,
            independent_campaigns=(
                a.independent_campaigns + b.independent_campaigns
            ),
            successful_usage=a.successful_usage + b.successful_usage,
            failed_usage=a.failed_usage + b.failed_usage,
            conflicts=a.conflicts + b.conflicts,
        )
        # Двусторонние отношения (DS-006A §3):
        # A -> MERGED_FROM -> C; B -> MERGED_FROM -> C;
        # C -> DERIVED_FROM -> A; C -> DERIVED_FROM -> B.
        # Записи хранятся на C; A и B остаются неизменными.
        merged.relations = KnowledgeRelations.create_merge_relations(
            a.id, b.id, merged.id, timestamp
        )
        # merge_timestamp и merge_reason сохраняются в истории (details).
        merged.history.append(
            KnowledgeHistoryEntry(
                timestamp=timestamp,
                knowledge_id=merged.id,
                event=MERGE_DETAILS_EVENT,
                details=(
                    f"merge_reason={reason or 'not specified'}; "
                    f"parent_ids={a.id},{b.id}"
                ),
            )
        )
        return merged
