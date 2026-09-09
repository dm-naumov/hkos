"""Unit tests for the Knowledge eligibility policy."""

from hkos.repository.models import Knowledge
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.ranking_engine import RankedCandidate


def _candidate(kid: str, status: str, entity_type: str = "knowledge") -> RankedCandidate:
    return RankedCandidate(
        entity=Knowledge(id=kid, status=status, confidence=50),
        entity_type=entity_type,
        score=50.0,
        factors={"confidence": 0.5},
    )


class TestKnowledgeFilter:
    """Ordinary policy is a positive CANONICAL allowlist."""

    def test_default_keeps_only_canonical_knowledge(self) -> None:
        ranked = [
            _candidate("new", "NEW"),
            _candidate("verified", "VERIFIED"),
            _candidate("canonical", "CANONICAL"),
            _candidate("conflict", "CONFLICT"),
            _candidate("rejected", "REJECTED"),
            _candidate("superseded", "SUPERSEDED"),
            _candidate("archived", "ARCHIVED"),
        ]
        result = KnowledgeFilter.filter(ranked)
        assert [candidate.entity.id for candidate in result] == ["canonical"]

    def test_include_history_is_explicit_all_status_policy(self) -> None:
        ranked = [
            _candidate("new", "NEW"),
            _candidate("archived", "ARCHIVED"),
        ]
        assert KnowledgeFilter.filter(ranked, include_history=True) == ranked

    def test_non_knowledge_entity_is_not_subject_to_lifecycle_policy(self) -> None:
        decision = _candidate("d1", "ACCEPTED", entity_type="decision")
        assert KnowledgeFilter.filter([decision]) == [decision]

    def test_order_preserved(self) -> None:
        ranked = [
            _candidate("k1", "CANONICAL"),
            _candidate("k2", "NEW"),
            _candidate("k3", "CANONICAL"),
        ]
        result = KnowledgeFilter.filter(ranked)
        assert [candidate.entity.id for candidate in result] == ["k1", "k3"]
