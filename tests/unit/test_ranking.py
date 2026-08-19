"""Unit tests for RankingEngine (DS-008 §10, IP-008)."""

from datetime import datetime, timedelta, timezone
from typing import cast

from hkos.index.query_contract import IndexEntry
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval.candidate_builder import CandidateSet
from hkos.retrieval.query_parser import ParsedQuery
from hkos.retrieval.ranking_engine import RankingEngine

WEIGHTS = {
    "topic": 0.25, "confidence": 0.15, "project": 0.10, "freshness": 0.10,
    "usage": 0.05, "canonical": 0.15, "references": 0.05, "success": 0.05,
    "campaign": 0.05, "decision": 0.05,
}
CAPS = {"usage": 10, "references": 10, "confirmations": 10}


def _fresh(updated_at: str) -> Knowledge:
    return Knowledge(
        id="k-fresh", project="p1", title="TProxy UDP", body="",
        status="NEW", category="FACT", tags=["udp"], confidence=90,
        updated_at=updated_at,
    )


class FakeRepos:
    """RepositoryManager-заглушка: load по UUID."""

    def __init__(self, entities: dict[str, Knowledge]) -> None:
        self.entities = entities
        self.knowledge = self
        self.decisions = self
        self.artifacts = self
        self.campaigns = self

    def load(self, project: str, entity_id: str) -> Knowledge | None:
        return self.entities.get(entity_id)


class TestRankingEngine:
    """Детерминированное ранжирование с коэффициентами из конфигурации."""

    def _engine(self, repos: FakeRepos) -> RankingEngine:
        return RankingEngine(
            cast(RepositoryManager, repos), WEIGHTS, CAPS, half_life_days=90.0
        )

    def test_topic_factor(self) -> None:
        k = Knowledge(
            id="k1", project="p1", title="UDP routing",
            category="FACT", tags=[], status="NEW", confidence=50,
        )
        engine = self._engine(FakeRepos({"k1": k}))
        parsed = ParsedQuery(topic="udp", keywords=["udp"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            parsed, "p1",
        )
        assert result[0].factors["topic"] == 1.0

    def test_canonical_factor(self) -> None:
        k = Knowledge(id="k1", project="p1", title="X", status="CANONICAL", confidence=50)
        engine = self._engine(FakeRepos({"k1": k}))
        parsed = ParsedQuery(keywords=["x"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            parsed, "p1",
        )
        assert result[0].factors["canonical"] == 1.0

    def test_canonical_ranks_higher(self) -> None:
        canonical = Knowledge(
            id="k1", project="p1", title="UDP fix",
            status="CANONICAL", confidence=50,
        )
        plain = Knowledge(id="k2", project="p1", title="UDP fix", status="NEW", confidence=50)
        engine = self._engine(FakeRepos({"k1": canonical, "k2": plain}))
        parsed = ParsedQuery(topic="udp", keywords=["udp"])
        result = engine.rank(
            CandidateSet(entries=[
                IndexEntry(id="k1", type="knowledge", project="p1"),
                IndexEntry(id="k2", type="knowledge", project="p1"),
            ]),
            parsed, "p1",
        )
        assert result[0].entity.id == "k1"

    def test_deterministic_order(self) -> None:
        entities = {
            f"k{i}": Knowledge(
                id=f"k{i}", project="p1", title=f"Topic {i}",
                status="NEW", confidence=50,
            )
            for i in range(3)
        }
        engine = self._engine(FakeRepos(entities))
        parsed = ParsedQuery(topic="topic", keywords=["topic"])
        entries = [IndexEntry(id=f"k{i}", type="knowledge", project="p1") for i in range(3)]
        first = [c.entity.id for c in engine.rank(CandidateSet(entries=entries), parsed, "p1")]
        second = [c.entity.id for c in engine.rank(CandidateSet(entries=entries), parsed, "p1")]
        assert first == second

    def test_confidence_factor(self) -> None:
        k = Knowledge(id="k1", project="p1", title="X", status="NEW", confidence=80)
        engine = self._engine(FakeRepos({"k1": k}))
        parsed = ParsedQuery(keywords=["x"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            parsed, "p1",
        )
        assert result[0].factors["confidence"] == 0.8

    def test_freshness_decay(self) -> None:
        now = datetime.now(timezone.utc)
        recent = _fresh((now - timedelta(days=1)).isoformat())
        old = _fresh((now - timedelta(days=500)).isoformat())
        engine = self._engine(FakeRepos({"recent": recent, "old": old}))
        parsed = ParsedQuery(topic="udp")
        result = engine.rank(
            CandidateSet(entries=[
                IndexEntry(id="recent", type="knowledge", project="p1"),
                IndexEntry(id="old", type="knowledge", project="p1"),
            ]),
            parsed, "p1",
        )
        assert result[0].factors["freshness"] > result[1].factors["freshness"]

    def test_score_bounded(self) -> None:
        k = Knowledge(id="k1", project="p1", title="X", status="CANONICAL", confidence=100,
                      successful_usage=100, confirmations=100, references=["a"] * 100)
        engine = self._engine(FakeRepos({"k1": k}))
        parsed = ParsedQuery(topic="x", keywords=["x"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            parsed, "p1",
        )
        assert 0.0 <= result[0].score <= 100.0

    def test_campaign_match_factor(self) -> None:
        k = Knowledge(
            id="k1", project="p1", title="X", status="NEW",
            confidence=50, source_campaign="c1",
        )
        engine = self._engine(FakeRepos({"k1": k}))
        parsed = ParsedQuery(keywords=["x"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            parsed, "p1", campaign_id="c1",
        )
        assert result[0].factors["campaign"] == 1.0

    def test_decision_priority(self) -> None:
        k = Knowledge(id="k1", project="p1", title="X", status="NEW", confidence=50)
        engine = self._engine(FakeRepos({"k1": k}))
        parsed = ParsedQuery(keywords=["x"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="decision", project="p1")]),
            parsed, "p1",
        )
        assert result[0].factors["decision"] == 1.0
