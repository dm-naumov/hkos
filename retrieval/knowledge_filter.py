"""HKOS Knowledge Filter (DS-008 §11, IP-008)
==========================================
По умолчанию исключаются Knowledge со статусами:

    ARCHIVED, REJECTED, SUPERSEDED

если пользователь явно не запросил исторические данные
(include_history / constraint запроса).
"""

from hkos.retrieval.ranking_engine import RankedCandidate
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_REJECTED,
    KNOWLEDGE_STATUS_SUPERSEDED,
)

__all__ = ["KnowledgeFilter"]


class KnowledgeFilter:
    """Фильтрация кандидатов по статусам (без изменения сущностей)."""

    @staticmethod
    def filter(
        ranked: list[RankedCandidate],
        include_history: bool = False,
    ) -> list[RankedCandidate]:
        """Отфильтровать архивные/отклонённые/замещённые знания.

        Args:
            ranked: Ранжированные кандидаты.
            include_history: Включить исторические статусы.

        Returns:
            Отфильтрованный список (порядок сохранён).

        """
        if include_history:
            return ranked
        return [
            candidate
            for candidate in ranked
            if candidate.entity.status
            not in (
                KNOWLEDGE_STATUS_ARCHIVED,
                KNOWLEDGE_STATUS_REJECTED,
                KNOWLEDGE_STATUS_SUPERSEDED,
            )
        ]
