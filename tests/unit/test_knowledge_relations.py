"""Unit tests for KnowledgeRelation (DS-006A §2)."""

from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    KnowledgeRelations,
    RelationType,
)


class TestKnowledgeRelation:
    """Test suite for KnowledgeRelation model."""

    def test_relation_types_enum(self) -> None:
        """Все 9 типов отношений — члены enum RelationType."""
        assert set(RelationType.__members__.keys()) == {
            "PARENT_OF", "CHILD_OF", "MERGED_FROM", "SUPERSEDES",
            "SUPERSEDED_BY", "CONFLICTS_WITH", "CANONICAL_OF",
            "DERIVED_FROM", "REFERENCE_TO",
        }

    def test_enum_values(self) -> None:
        assert RelationType.MERGED_FROM.value == "MERGED_FROM"
        assert RelationType.DERIVED_FROM.value == "DERIVED_FROM"

    def test_no_string_literals_outside_enum(self) -> None:
        """Код relations использует только enum (проверка структуры)."""
        import inspect

        source = inspect.getsource(KnowledgeRelation)
        # relation_type аннотирован enum, а не str
        assert "relation_type: RelationType" in source

    def test_to_dict(self) -> None:
        rel = KnowledgeRelation(
            relation_id="r1", source_id="a", target_id="c",
            relation_type=RelationType.MERGED_FROM, created_at="t",
        )
        d = rel.to_dict()
        assert d["relation_type"] == "MERGED_FROM"
        assert d["source_id"] == "a"

    def test_from_dict_roundtrip(self) -> None:
        rel = KnowledgeRelation(
            relation_id="r1", source_id="a", target_id="c",
            relation_type=RelationType.CONFLICTS_WITH, created_at="t",
        )
        restored = KnowledgeRelation.from_dict(rel.to_dict())
        assert restored == rel
        assert restored.relation_type is RelationType.CONFLICTS_WITH

    def test_from_dict_unknown_type_falls_back(self) -> None:
        rel = KnowledgeRelation.from_dict({"relation_type": "BOGUS"})
        assert rel.relation_type is RelationType.REFERENCE_TO


class TestKnowledgeRelations:
    """Merge relations: двусторонние связи (DS-006A §3)."""

    def test_create_merge_relations_bidirectional(self) -> None:
        relations = KnowledgeRelations.create_merge_relations(
            "a-1", "b-1", "c-1", timestamp="2026-01-01T00:00:00+00:00"
        )
        assert len(relations) == 4
        pairs = {(r.source_id, r.target_id, r.relation_type) for r in relations}
        assert pairs == {
            ("a-1", "c-1", RelationType.MERGED_FROM),
            ("b-1", "c-1", RelationType.MERGED_FROM),
            ("c-1", "a-1", RelationType.DERIVED_FROM),
            ("c-1", "b-1", RelationType.DERIVED_FROM),
        }

    def test_relations_have_unique_ids(self) -> None:
        relations = KnowledgeRelations.create_merge_relations("a", "b", "c")
        ids = [r.relation_id for r in relations]
        assert len(set(ids)) == 4

    def test_timestamp(self) -> None:
        relations = KnowledgeRelations.create_merge_relations(
            "a", "b", "c", timestamp="2026-01-01T00:00:00+00:00"
        )
        assert all(r.created_at == "2026-01-01T00:00:00+00:00" for r in relations)
