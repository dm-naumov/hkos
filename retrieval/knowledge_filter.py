"""Knowledge eligibility policy for ordinary HKOS retrieval.

Ordinary retrieval admits only CANONICAL Knowledge. Non-canonical Knowledge
is available only through the explicit ``include_history`` policy. Entities
outside the Knowledge lifecycle are not filtered here.
"""

from hkos.retrieval.ranking_engine import RankedCandidate
from hkos.services.librarian.knowledge_status import KNOWLEDGE_STATUS_CANONICAL

__all__ = ["KnowledgeFilter"]


class KnowledgeFilter:
    """Apply the explicit Knowledge eligibility policy without mutation."""

    @staticmethod
    def is_eligible(
        candidate: RankedCandidate,
        include_history: bool = False,
    ) -> bool:
        """Return whether a candidate may enter the requested result policy."""
        if candidate.entity_type != "knowledge":
            return True
        if include_history:
            return True
        return candidate.entity.status == KNOWLEDGE_STATUS_CANONICAL

    @classmethod
    def filter(
        cls,
        ranked: list[RankedCandidate],
        include_history: bool = False,
    ) -> list[RankedCandidate]:
        """Keep eligible candidates while preserving their order."""
        return [
            candidate for candidate in ranked
            if cls.is_eligible(candidate, include_history)
        ]
