"""Unit tests for RelationshipTraverser (DS-008 §12, IP-008)."""

from typing import cast

from hkos.index.query_contract import EntityRecord
from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    RelationType,
)
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval.ranking_engine import RankedCandidate
from hkos.retrieval.relationship_traverser import RelationshipTraverser


class FakeQuery:
    """In-memory снимок Query Contract: k1 связан с k2, k2 связан с k3."""

    def relations_of_knowledge(
        self, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        if knowledge_id == "k1":
            return [
                KnowledgeRelation(relation_id="r1", source_id="k1", target_id="k2",
                                  relation_type=RelationType.DERIVED_FROM, created_at="t1"),
            ]
        if knowledge_id == "k2":
            return [
                KnowledgeRelation(relation_id="r2", source_id="k2", target_id="k3",
                                  relation_type=RelationType.DERIVED_FROM, created_at="t2"),
            ]
        return []

    def relations_of_project(self) -> list[KnowledgeRelation]:
        return []

    def keyword_search(self, word: str) -> list[object]:
        return []

    def tag_search(self, tag: str) -> list[object]:
        return []

    def entity_get(self, entity_id: str) -> EntityRecord | None:
        if entity_id in ("k1", "k2", "k3"):
            return EntityRecord(id=entity_id, project="p1", type="knowledge")
        return None

    def statistics(self) -> dict[str, int]:
        return {"knowledge": 0, "decisions": 0, "campaigns": 0, "projects": 0, "artifacts": 0}


class FakeRepos:
    def __init__(self) -> None:
        self.knowledge = self
        self.decisions = self
        self.artifacts = self
        self.campaigns = self

    def load(self, project: str, entity_id: str) -> Knowledge | None:
        if entity_id in ("k1", "k2", "k3"):
            return Knowledge(id=entity_id, project="p1", title=entity_id, confidence=50)
        return None


class TestRelationshipTraverser:
    """Обход через Q4: расширение, без циклов, без повторов."""

    def _seed(self, kid: str = "k1") -> RankedCandidate:
        return RankedCandidate(
            entity=Knowledge(id=kid, project="p1", confidence=50),
            entity_type="knowledge",
            score=50.0,
            factors={},
        )

    def test_expands_one_hop(self) -> None:
        traverser = RelationshipTraverser(
            cast(RepositoryManager, FakeRepos()), max_depth=1, max_related=10,
        )
        result = traverser.traverse([self._seed()], "p1", FakeQuery())
        ids = [c.entity.id for c in result]
        assert "k2" in ids

    def test_depth_limit(self) -> None:
        traverser = RelationshipTraverser(
            cast(RepositoryManager, FakeRepos()), max_depth=0, max_related=10,
        )
        result = traverser.traverse([self._seed()], "p1", FakeQuery())
        assert [c.entity.id for c in result] == ["k1"]

    def test_max_related_bound(self) -> None:
        traverser = RelationshipTraverser(
            cast(RepositoryManager, FakeRepos()), max_depth=3, max_related=1,
        )
        result = traverser.traverse([self._seed()], "p1", FakeQuery())
        assert len(result) <= 2  # seed + 1 related

    def test_no_cycles(self) -> None:
        """k2 связан с k3; при глубине 2 нет повторов k2."""
        traverser = RelationshipTraverser(
            cast(RepositoryManager, FakeRepos()), max_depth=2, max_related=10,
        )
        result = traverser.traverse([self._seed()], "p1", FakeQuery())
        ids = [c.entity.id for c in result]
        assert len(ids) == len(set(ids))

    def test_relation_path_recorded(self) -> None:
        traverser = RelationshipTraverser(
            cast(RepositoryManager, FakeRepos()), max_depth=2, max_related=10,
        )
        result = traverser.traverse([self._seed()], "p1", FakeQuery())
        k2 = next(c for c in result if c.entity.id == "k2")
        assert k2.relation_path

    def test_score_decay(self) -> None:
        traverser = RelationshipTraverser(
            cast(RepositoryManager, FakeRepos()),
            max_depth=1, max_related=10, relation_decay=0.5,
        )
        result = traverser.traverse([self._seed()], "p1", FakeQuery())
        k2 = next(c for c in result if c.entity.id == "k2")
        assert k2.score == 25.0  # 50 * 0.5

    def test_uses_only_q4_for_relations(self) -> None:
        """Traverser не читает relations из документов."""
        import inspect

        source = inspect.getsource(RelationshipTraverser)
        assert "entity.relations" not in source
        assert "knowledge.relations" not in source
