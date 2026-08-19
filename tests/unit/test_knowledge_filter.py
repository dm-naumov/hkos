"""Unit tests for KnowledgeFilter (DS-008 §11)."""

from hkos.repository.models import Knowledge
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.ranking_engine import RankedCandidate


def _candidate(kid: str, status: str) -> RankedCandidate:
    return RankedCandidate(
        entity=Knowledge(id=kid, status=status, confidence=50),
        entity_type="knowledge",
        score=50.0,
        factors={"confidence": 0.5},
    )


class TestKnowledgeFilter:
    """По умолчанию исключаются ARCHIVED/REJECTED/SUPERSEDED."""

    def test_excludes_archived(self) -> None:
        ranked = [_candidate("k1", "NEW"), _candidate("k2", "ARCHIVED")]
        result = KnowledgeFilter.filter(ranked)
        assert [c.entity.id for c in result] == ["k1"]

    def test_excludes_rejected(self) -> None:
        ranked = [_candidate("k1", "REJECTED")]
        assert KnowledgeFilter.filter(ranked) == []

    def test_excludes_superseded(self) -> None:
        ranked = [_candidate("k1", "SUPERSEDED")]
        assert KnowledgeFilter.filter(ranked) == []

    def test_include_history_keeps_all(self) -> None:
        ranked = [_candidate("k1", "ARCHIVED"), _candidate("k2", "REJECTED")]
        result = KnowledgeFilter.filter(ranked, include_history=True)
        assert len(result) == 2

    def test_keeps_valid_statuses(self) -> None:
        ranked = [_candidate("k1", "NEW"), _candidate("k2", "VERIFIED"),
                  _candidate("k3", "CANONICAL"), _candidate("k4", "CONFLICT")]
        assert len(KnowledgeFilter.filter(ranked)) == 4

    def test_order_preserved(self) -> None:
        ranked = [_candidate("k1", "NEW"), _candidate("k2", "ARCHIVED"),
                  _candidate("k3", "VERIFIED")]
        result = KnowledgeFilter.filter(ranked)
        assert [c.entity.id for c in result] == ["k1", "k3"]
