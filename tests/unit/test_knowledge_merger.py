"""Unit tests for KnowledgeMerger (DS-006 §13, IP-006 §6)."""

from hkos.repository.models import Knowledge
from hkos.services.librarian.knowledge_merger import KnowledgeMerger
from hkos.services.librarian.knowledge_status import KNOWLEDGE_STATUS_CANONICAL


class TestKnowledgeMerger:
    """Merger создаёт новое Canonical Knowledge; исходники не изменяются."""

    def _pair(self) -> tuple[Knowledge, Knowledge]:
        a = Knowledge(id="a-1", project="p1", title="TProxy UDP works",
                      body="body A", tags=["tproxy"], kind="fact")
        b = Knowledge(id="b-1", project="p1", title="tproxy udp works",
                      body="body B", tags=["udp"], kind="fact")
        return a, b

    def test_creates_new_canonical(self) -> None:
        a, b = self._pair()
        merged = KnowledgeMerger.merge(a, b, reason="same observation")
        assert merged.id != a.id and merged.id != b.id
        assert merged.status == KNOWLEDGE_STATUS_CANONICAL
        assert merged.project == "p1"

    def test_parent_ids_preserved(self) -> None:
        a, b = self._pair()
        merged = KnowledgeMerger.merge(a, b, reason="r")
        assert merged.parent_ids == ["a-1", "b-1"]

    def test_originals_unchanged(self) -> None:
        a, b = self._pair()
        a_before = (a.id, a.title, a.body, a.tags)
        b_before = (b.id, b.title, b.body, b.tags)
        KnowledgeMerger.merge(a, b, reason="r")
        assert (a.id, a.title, a.body, a.tags) == a_before
        assert (b.id, b.title, b.body, b.tags) == b_before

    def test_merge_reason_in_history(self) -> None:
        a, b = self._pair()
        merged = KnowledgeMerger.merge(a, b, reason="duplicate evidence")
        assert len(merged.history) == 1
        assert "merge_reason=duplicate evidence" in merged.history[0].details
        assert "a-1,b-1" in merged.history[0].details

    def test_merge_timestamp(self) -> None:
        a, b = self._pair()
        merged = KnowledgeMerger.merge(
            a, b, reason="r",
            merge_timestamp="2026-01-01T00:00:00+00:00",
        )
        assert merged.history[0].timestamp == "2026-01-01T00:00:00+00:00"

    def test_combined_fields(self) -> None:
        a, b = self._pair()
        merged = KnowledgeMerger.merge(a, b, reason="r")
        assert "body A" in merged.body and "body B" in merged.body
        assert set(merged.tags) == {"tproxy", "udp"}

    def test_sums_factors(self) -> None:
        a, b = self._pair()
        a.confirmations = 2
        b.confirmations = 3
        merged = KnowledgeMerger.merge(a, b, reason="r")
        assert merged.confirmations == 5

    def test_merge_creates_bidirectional_relations(self) -> None:
        """DS-006A §3: A->MERGED_FROM->C, B->MERGED_FROM->C,
        C->DERIVED_FROM->A, C->DERIVED_FROM->B."""
        from hkos.repository.knowledge_relations import RelationType

        a, b = self._pair()
        merged = KnowledgeMerger.merge(a, b, reason="r")
        pairs = {(r.source_id, r.target_id, r.relation_type) for r in merged.relations}
        assert pairs == {
            (a.id, merged.id, RelationType.MERGED_FROM),
            (b.id, merged.id, RelationType.MERGED_FROM),
            (merged.id, a.id, RelationType.DERIVED_FROM),
            (merged.id, b.id, RelationType.DERIVED_FROM),
        }
        # Исходники не несут отношений (не изменены)
        assert a.relations == []
        assert b.relations == []

    def test_merge_relations_persist_on_merged(self) -> None:
        a, b = self._pair()
        merged = KnowledgeMerger.merge(a, b, reason="r")
        assert len(merged.relations) == 4
