"""Unit tests for StatisticsIndex (DS-007 §7)."""

from hkos.index.entity_index import EntityIndex
from hkos.index.statistics_index import StatisticsIndex
from hkos.repository.models import Knowledge


class TestStatisticsIndex:
    """Statistics Index: агрегированные счётчики."""

    def test_default_zeros(self) -> None:
        stats = StatisticsIndex()
        assert stats.get() == {
            "knowledge": 0, "decisions": 0, "campaigns": 0,
            "projects": 0, "artifacts": 0,
        }

    def test_increment(self) -> None:
        stats = StatisticsIndex()
        stats.increment("knowledge", 3)
        stats.increment("campaign", 1)
        assert stats.get()["knowledge"] == 3
        assert stats.get()["campaigns"] == 1

    def test_increment_never_negative(self) -> None:
        stats = StatisticsIndex()
        stats.increment("knowledge", -5)
        assert stats.get()["knowledge"] == 0

    def test_unknown_type_ignored(self) -> None:
        stats = StatisticsIndex()
        stats.increment("bogus", 5)
        assert stats.get()["knowledge"] == 0

    def test_recompute_from_entity_index(self) -> None:
        entities = EntityIndex()
        entities.upsert(Knowledge(id="k1", title="A"), "knowledge", "p1")
        entities.upsert(Knowledge(id="k2", title="B"), "knowledge", "p1")
        stats = StatisticsIndex()
        stats.recompute(entities)
        assert stats.get()["knowledge"] == 2

    def test_roundtrip(self) -> None:
        stats = StatisticsIndex()
        stats.increment("knowledge", 4)
        restored = StatisticsIndex(stats.data())
        assert restored.get()["knowledge"] == 4
