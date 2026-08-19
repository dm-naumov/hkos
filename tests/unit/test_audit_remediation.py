"""DS-009A Audit Remediation tests.

Задача 1: serializer body limit из конфигурации.
Задача 2: validation compatibility (services vs index — distinct but compatible).
Задача 3: ranking измерения (last_stats: candidates/refined/stub).
Задача 4: configuration override (коэффициенты — из конфигурации).
"""

from pathlib import Path
from typing import Any, cast

from hkos.context.context_serializer import ContextSerializer
from hkos.context.models import ContextDocument, ContextItem
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager

SECTIONS = ["TASK", "PROJECT", "CURRENT STATE", "CANONICAL KNOWLEDGE",
            "DECISIONS", "FAILURES", "ARTIFACTS", "CONFIGURATION",
            "OPEN QUESTIONS"]


class TestSerializerBodyLimit:
    """Задача 1: context.serializer.body_limit."""

    def _context(self) -> ContextDocument:
        return ContextDocument(
            task="t", project_id="p1",
            items=[
                ContextItem(
                    entity=Knowledge(id="k1", title="Long", body="x" * 500),
                    entity_type="knowledge",
                )
            ],
        )

    def test_default_limit_200(self) -> None:
        serializer = ContextSerializer(SECTIONS)
        text = serializer.serialize(self._context())
        assert "x" * 200 in text
        assert "x" * 201 not in text

    def test_override_limit_100(self) -> None:
        serializer = ContextSerializer(SECTIONS, body_limit=100)
        text = serializer.serialize(self._context())
        assert "x" * 100 in text
        assert "x" * 101 not in text

    def test_zero_limit_no_truncation(self) -> None:
        serializer = ContextSerializer(SECTIONS, body_limit=0)
        text = serializer.serialize(self._context())
        assert "x" * 500 in text

    def test_behavior_unchanged_by_default(self) -> None:
        default = ContextSerializer(SECTIONS).serialize(self._context())
        explicit = ContextSerializer(SECTIONS, body_limit=200).serialize(self._context())
        assert default == explicit


class TestConfigurationOverride:
    """Задача 4: коэффициенты переопределяются через конфигурацию."""

    def test_body_limit_from_config(self, tmp_path: Path) -> None:
        from hkos.context import ContextBuilder
        from hkos.core.config import ConfigLoader
        from hkos.core.logger import HKOSLogger

        cfg = ConfigLoader(profile="development")
        cfg.load()
        cfg.set("context.serializer.body_limit", 50)
        builder = ContextBuilder(cfg, HKOSLogger())
        context = ContextDocument(
            task="t", project_id="p1",
            items=[
                ContextItem(
                    entity=Knowledge(id="k1", title="T", body="y" * 300),
                    entity_type="knowledge",
                )
            ],
        )
        text = builder.serialize(context)
        assert "y" * 50 in text
        assert "y" * 51 not in text

    def test_ranking_weights_from_config(self) -> None:
        from hkos.core.config import ConfigLoader
        from hkos.index.query_contract import IndexEntry
        from hkos.retrieval.candidate_builder import CandidateSet
        from hkos.retrieval.query_parser import ParsedQuery
        from hkos.retrieval.ranking_engine import RankingEngine

        cfg = ConfigLoader(profile="development")
        cfg.load()
        weights = {
            name: float(cfg.get(f"retrieval.ranking.{name}_weight", 0.0))
            for name in ("topic", "confidence", "project", "freshness", "usage",
                         "canonical", "references", "success", "campaign", "decision")
        }
        engine = RankingEngine(
            cast(RepositoryManager, _FakeRepositories(
                {"k1": Knowledge(id="k1", project="p1", title="X", confidence=50)}
            )),
            weights, caps={}, half_life_days=90,
        )
        parsed = ParsedQuery(topic="x", keywords=["x"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            parsed, "p1",
        )
        assert result[0].factors["topic"] == 1

    def test_caps_disable_factors_by_default(self) -> None:
        from hkos.index.query_contract import IndexEntry
        from hkos.retrieval.candidate_builder import CandidateSet
        from hkos.retrieval.query_parser import ParsedQuery
        from hkos.retrieval.ranking_engine import RankingEngine

        rich = Knowledge(
            id="k1", project="p1", title="X", confidence=50,
            successful_usage=100, confirmations=100, references=["r"] * 50,
        )
        engine = RankingEngine(
            cast(RepositoryManager, _FakeRepositories({"k1": rich})),
            weights={"usage": 1.0, "references": 1.0, "success": 1.0},
            caps={},
            half_life_days=90,
        )
        parsed = ParsedQuery(keywords=["x"])
        result = engine.rank(
            CandidateSet(entries=[IndexEntry(id="k1", type="knowledge", project="p1")]),
            parsed, "p1",
        )
        assert result[0].factors["usage"] == 0
        assert result[0].factors["references"] == 0
        assert result[0].factors["success"] == 0


class TestValidationCompatibility:
    """Задача 2: services.ValidationResult и index.ValidationResult
    — разные классы, поведенчески совместимые.
    """

    def test_services_validation_result_works(self) -> None:
        from hkos.services.project_validator import ValidationResult as Svc

        result = Svc(valid=False, errors=["e1"], warnings=["w1"])
        assert result.valid is False
        assert result.errors == ["e1"]
        assert result.warnings == ["w1"]
        assert bool(result) is False
        assert result.as_dict()["valid"] is False

    def test_index_validation_result_works(self) -> None:
        from hkos.index.validation import ValidationResult as Idx

        result = Idx(valid=True, errors=[], warnings=[])
        assert result.valid is True
        assert bool(result) is True
        assert result.as_dict()["valid"] is True

    def test_distinct_classes(self) -> None:
        from hkos.index.validation import ValidationResult as Idx
        from hkos.services.project_validator import ValidationResult as Svc

        assert Idx.__module__ != Svc.__module__

    def test_consumers_unaffected(self) -> None:
        from hkos.index.validation import ValidationResult

        result = ValidationResult(valid=False, errors=["not found"])
        assert result.valid is False
        assert bool(result) is False


class TestRankingMeasurements:
    """Задача 3: last_stats — измерения для изменения refine_limit."""

    def _engine(self) -> Any:
        from hkos.retrieval.ranking_engine import RankingEngine

        entities = {
            f"k{i}": Knowledge(id=f"k{i}", project="p1", title=f"Topic {i}", confidence=50)
            for i in range(5)
        }
        return RankingEngine(
            cast(RepositoryManager, _FakeRepositories(entities)),
            weights={}, caps={}, half_life_days=90,
        )

    def test_last_stats_recorded(self) -> None:
        from hkos.index.query_contract import IndexEntry
        from hkos.retrieval.candidate_builder import CandidateSet
        from hkos.retrieval.query_parser import ParsedQuery

        engine = self._engine()
        entries = [IndexEntry(id=f"k{i}", type="knowledge", project="p1") for i in range(5)]
        engine.rank(
            CandidateSet(entries=entries), ParsedQuery(topic="topic"),
            "p1", snapshot=_FakeIndexSnapshot(),
        )
        stats = engine.last_stats
        assert stats["candidates"] == 5
        assert stats["refined"] == 5
        assert stats["stub"] == 0

    def test_last_stats_with_refine_limit(self) -> None:
        from hkos.index.query_contract import IndexEntry
        from hkos.retrieval.candidate_builder import CandidateSet
        from hkos.retrieval.query_parser import ParsedQuery

        engine = self._engine()
        entries = [IndexEntry(id=f"k{i}", type="knowledge", project="p1") for i in range(5)]
        engine.rank(
            CandidateSet(entries=entries), ParsedQuery(topic="topic"),
            "p1", snapshot=_FakeIndexSnapshot(), refine_limit=2,
        )
        stats = engine.last_stats
        assert stats["candidates"] == 5
        assert stats["refined"] == 2
        assert stats["stub"] == 3


class _FakeRepositories:
    """Заглушка RepositoryManager (load по UUID)."""

    def __init__(self, entities: dict[str, Knowledge]) -> None:
        self.entities = entities
        self.knowledge = self
        self.decisions = self
        self.artifacts = self
        self.campaigns = self

    def load(self, project: str, entity_id: str) -> Knowledge | None:
        return self.entities.get(entity_id)


class _FakeIndexSnapshot:
    """Заглушка IndexSnapshot: entity_get по id."""

    def __init__(self) -> None:
        from hkos.index.query_contract import EntityRecord

        self._records = {
            f"k{i}": EntityRecord(id=f"k{i}", project="p1", type="knowledge",
                                  title=f"Topic {i}", status="NEW")
            for i in range(10)
        }

    def entity_get(self, entity_id: str) -> Any:
        return self._records.get(entity_id)
