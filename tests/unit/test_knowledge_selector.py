"""Unit tests for KnowledgeSelector (DS-008 §13-14)."""

from hkos.repository.models import Knowledge
from hkos.retrieval.knowledge_selector import KnowledgeSelector
from hkos.retrieval.ranking_engine import RankedCandidate


def _candidate(kid: str, score: float) -> RankedCandidate:
    return RankedCandidate(
        entity=Knowledge(id=kid, confidence=50),
        entity_type="knowledge",
        score=score,
        factors={},
    )


class TestKnowledgeSelector:
    """Minimal Sufficient Context: Top N."""

    def test_top_n(self) -> None:
        ranked = [_candidate(f"k{i}", float(100 - i)) for i in range(5)]
        result = KnowledgeSelector.select(ranked, top_n=2)
        assert [c.entity.id for c in result] == ["k0", "k1"]

    def test_default_top_20(self) -> None:
        ranked = [_candidate(f"k{i}", float(i)) for i in range(30)]
        assert len(KnowledgeSelector.select(ranked)) == 20

    def test_never_returns_whole_set_beyond_n(self) -> None:
        ranked = [_candidate(f"k{i}", float(i)) for i in range(100)]
        assert len(KnowledgeSelector.select(ranked, top_n=10)) == 10

    def test_empty(self) -> None:
        assert KnowledgeSelector.select([], top_n=20) == []

    def test_negative_top_n(self) -> None:
        ranked = [_candidate("k1", 50.0)]
        assert KnowledgeSelector.select(ranked, top_n=-1) == []

    def test_top_n_larger_than_set(self) -> None:
        ranked = [_candidate("k1", 50.0)]
        assert len(KnowledgeSelector.select(ranked, top_n=100)) == 1
