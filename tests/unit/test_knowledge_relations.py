"""Unit tests for KnowledgeRelation (DS-006A §2)."""

from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    KnowledgeRelations,
    RelationType,
)


class TestKnowledgeRelation:
    """Test suite for KnowledgeRelation model."""

    def test_relation_types_enum(self) -> None:
        """Все 12 типов отношений — члены enum RelationType."""
        assert set(RelationType.__members__.keys()) == {
            "PARENT_OF", "CHILD_OF", "MERGED_FROM", "SUPERSEDES",
            "SUPERSEDED_BY", "CONFLICTS_WITH", "CANONICAL_OF",
            "DERIVED_FROM", "BASED_ON", "CAUSED_BY", "MITIGATED_BY",
            "REFERENCE_TO",
        }

    def test_enum_values(self) -> None:
        assert RelationType.MERGED_FROM.value == "MERGED_FROM"
        assert RelationType.DERIVED_FROM.value == "DERIVED_FROM"
        assert RelationType.BASED_ON.value == "BASED_ON"
        assert RelationType.CAUSED_BY.value == "CAUSED_BY"
        assert RelationType.MITIGATED_BY.value == "MITIGATED_BY"

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

    # --- DS-017 ЭТАП 1: target_project_id (additive, кросс-проектные рёбра) ---

    def test_to_dict_includes_target_project_id(self) -> None:
        rel = KnowledgeRelation(
            relation_id="r1", source_id="a", target_id="c",
            relation_type=RelationType.CAUSED_BY, created_at="t",
            target_project_id="proj-b",
        )
        d = rel.to_dict()
        assert d["target_project_id"] == "proj-b"

    def test_to_dict_target_project_id_empty_for_intra_project(self) -> None:
        rel = KnowledgeRelation(
            relation_id="r1", source_id="a", target_id="c",
            relation_type=RelationType.BASED_ON, created_at="t",
        )
        assert rel.to_dict()["target_project_id"] == ""

    def test_from_dict_roundtrip_preserves_target_project_id(self) -> None:
        rel = KnowledgeRelation(
            relation_id="r1", source_id="a", target_id="c",
            relation_type=RelationType.MITIGATED_BY, created_at="t",
            target_project_id="proj-b",
        )
        restored = KnowledgeRelation.from_dict(rel.to_dict())
        assert restored == rel
        assert restored.target_project_id == "proj-b"

    def test_from_dict_missing_target_project_id_is_backward_compatible(
        self,
    ) -> None:
        """Старый формат (до DS-017) без ключа читается как внутрипроектный."""
        rel = KnowledgeRelation.from_dict({
            "relation_id": "r1", "source_id": "a", "target_id": "c",
            "relation_type": "MERGED_FROM", "created_at": "t",
        })
        assert rel.target_project_id == ""

    def test_from_dict_non_string_target_project_id_is_empty(self) -> None:
        rel = KnowledgeRelation.from_dict({
            "relation_type": "REFERENCE_TO", "target_project_id": None,
        })
        assert rel.target_project_id == ""

    def test_new_semantic_types_parse(self) -> None:
        """Инженерные типы DS-017 §4.2.2 валидны в from_dict."""
        for raw in ("BASED_ON", "CAUSED_BY", "MITIGATED_BY"):
            rel = KnowledgeRelation.from_dict({"relation_type": raw})
            assert rel.relation_type.value == raw


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
