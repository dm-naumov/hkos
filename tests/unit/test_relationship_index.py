"""Unit tests for RelationshipIndex + RelationshipReader (DS-007 §7, Freeze)."""

from hkos.index.relationship_index import (
    RelationshipIndex,
    RelationshipReader,
)
from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    KnowledgeRelations,
    RelationType,
)


class TestRelationshipIndex:
    """Relationship Index: рёбра графа, read-контракт."""

    def _relations(self) -> list[KnowledgeRelation]:
        return KnowledgeRelations.create_merge_relations(
            "a-1", "b-1", "c-1", timestamp="2026-01-01T00:00:00+00:00"
        )

    def test_add_relations(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        assert index.edge_count() == 4

    def test_relations_of_knowledge(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        rels = index.relations_of_knowledge("c-1")
        assert len(rels) == 4
        types = {r.relation_type for r in rels}
        assert RelationType.MERGED_FROM in types
        assert RelationType.DERIVED_FROM in types

    def test_relations_of_knowledge_source_side(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        # a-1 участвует как источник MERGED_FROM
        rels = index.relations_of_knowledge("a-1")
        assert len(rels) == 2  # a->c MERGED_FROM, c->a DERIVED_FROM

    def test_relations_of_project(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        rels = index.relations_of_project()
        assert len(rels) == 4

    def test_replace_relations(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        index.add_relations("c-1", [])  # замена на пустое
        assert index.edge_count() == 0

    def test_remove_relations(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        index.remove_relations("c-1")
        assert index.edge_count() == 0
        assert index.relations_of_project() == []

    def test_no_duplicates(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        index.add_relations("c-1", self._relations())  # повторно
        assert index.edge_count() == 4

    def test_reader_protocol_implemented(self) -> None:
        """RelationshipIndex — реализация RelationshipReader (Freeze, усл. 2)."""
        index = RelationshipIndex()
        assert isinstance(index, RelationshipReader)

    def test_enum_roundtrip(self) -> None:
        index = RelationshipIndex()
        index.add_relations("c-1", self._relations())
        rels = index.relations_of_project()
        assert all(isinstance(r.relation_type, RelationType) for r in rels)
