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
    "campaign": 0.05, "decision": 0.05, "failure": 0.05,
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


class TestFailurePriority:
    """IP-017 ЭТАП 7: фактор Failure Priority (прошлые сбои выше среди равных)."""

    def _engine(self, repos: FakeRepos) -> RankingEngine:
        return RankingEngine(
            cast(RepositoryManager, repos), WEIGHTS, CAPS, half_life_days=90.0
        )

    def test_failure_factor_negative_kind(self) -> None:
        k = Knowledge(
            id="k1", project="p1", title="X", kind="negative",
            status="NEW", confidence=50,
        )
        engine = self._engine(FakeRepos({"k1": k}))
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            ParsedQuery(keywords=["x"]), "p1",
        )
        assert result[0].factors["failure"] == 1.0

    def test_failure_factor_failure_category(self) -> None:
        k = Knowledge(
            id="k1", project="p1", title="X", category="FAILURE",
            status="NEW", confidence=50,
        )
        engine = self._engine(FakeRepos({"k1": k}))
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            ParsedQuery(keywords=["x"]), "p1",
        )
        assert result[0].factors["failure"] == 1.0

    def test_failure_factor_zero_for_plain_fact(self) -> None:
        k = Knowledge(id="k1", project="p1", title="X", status="NEW", confidence=50)
        engine = self._engine(FakeRepos({"k1": k}))
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            ParsedQuery(keywords=["x"]), "p1",
        )
        assert result[0].factors["failure"] == 0.0

    def test_failure_factor_not_applied_to_decisions(self) -> None:
        """Decision c категорией FAILURE не получает failure-фактор (тип ≠ knowledge)."""
        k = Knowledge(id="k1", project="p1", title="X", category="FAILURE", status="NEW")
        engine = self._engine(FakeRepos({"k1": k}))
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="decision", project="p1")]),
            ParsedQuery(keywords=["x"]), "p1",
        )
        assert result[0].factors["failure"] == 0.0
        assert result[0].factors["decision"] == 1.0

    def test_failure_ranks_first_among_equals(self) -> None:
        """При равных прочих факторах FAILURE выше FACT и DECISION."""
        failure = Knowledge(
            id="f1", project="p1", title="mtu tunnel udp", kind="negative",
            status="CANONICAL", confidence=50,
        )
        fact = Knowledge(
            id="a1", project="p1", title="mtu tunnel udp",
            status="CANONICAL", confidence=50,
        )
        decision = Knowledge(
            id="d1", project="p1", title="mtu tunnel udp",
            status="CANONICAL", confidence=50,
        )
        engine = self._engine(FakeRepos({
            "f1": failure, "a1": fact, "d1": decision}))
        parsed = ParsedQuery(topic="mtu", keywords=["mtu", "tunnel", "udp"])
        result = engine.rank(
            CandidateSet(entries=[
                IndexEntry(id="f1", type="knowledge", project="p1"),
                IndexEntry(id="a1", type="knowledge", project="p1"),
                IndexEntry(id="d1", type="knowledge", project="p1"),
            ]),
            parsed, "p1",
        )
        ids = [c.entity.id for c in result]
        assert ids[0] == "f1", f"FAILURE must rank first among equals: {ids}"
        assert result[0].factors["failure"] == 1.0

    def test_topic_match_still_beats_failure_priority(self) -> None:
        """Сильное topic-совпадение (не сбой) не глушится слабым FAILURE."""
        matched = Knowledge(
            id="m1", project="p1", title="exact relevant fact",
            status="CANONICAL", confidence=90,
        )
        weak_failure = Knowledge(
            id="f1", project="p1", title="old unrelated", kind="negative",
            status="CANONICAL", confidence=50,
        )
        engine = self._engine(FakeRepos({"m1": matched, "f1": weak_failure}))
        parsed = ParsedQuery(topic="exact", keywords=["exact", "relevant"])
        result = engine.rank(
            CandidateSet(entries=[
                IndexEntry(id="m1", type="knowledge", project="p1"),
                IndexEntry(id="f1", type="knowledge", project="p1"),
            ]),
            parsed, "p1",
        )
        assert result[0].entity.id == "m1", (
            "topic weight must dominate the small failure boost")
