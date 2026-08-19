"""Unit tests for TagIndex (DS-007 §7)."""

from hkos.index.tag_index import TagIndex, indexable_tags
from hkos.repository.models import Knowledge, Project


class TestTagIndex:
    """Tag Index: add/get_by_tag/remove."""

    def test_indexable_tags(self) -> None:
        k = Knowledge(id="1", tags=["tproxy", "udp"])
        assert indexable_tags(k) == ["tproxy", "udp"]
        assert indexable_tags(Project(id="2")) == []

    def test_add_and_get_by_tag(self) -> None:
        index = TagIndex()
        index.add("k1", "knowledge", "p1", ["tproxy", "udp"])
        index.add("p1", "project", "p1", ["router"])
        assert len(index.get_by_tag("tproxy")) == 1
        assert len(index.get_by_tag("router")) == 1
        assert index.get_by_tag("tproxy")[0]["id"] == "k1"

    def test_multi_type_tag(self) -> None:
        index = TagIndex()
        index.add("k1", "knowledge", "p1", ["tproxy"])
        index.add("p1", "project", "p1", ["tproxy"])
        results = index.get_by_tag("tproxy")
        assert len(results) == 2

    def test_remove_cleans(self) -> None:
        index = TagIndex()
        index.add("k1", "knowledge", "p1", ["tproxy", "udp"])
        index.add("k2", "knowledge", "p1", ["tproxy"])
        index.remove("k1")
        results = index.get_by_tag("tproxy")
        assert [r["id"] for r in results] == ["k2"]
        assert index.get_by_tag("udp") == []

    def test_entity_tags_tracked(self) -> None:
        index = TagIndex()
        index.add("k1", "knowledge", "p1", ["a", "b"])
        assert set(index.entity_tags("k1")) == {"a", "b"}

    def test_tag_count(self) -> None:
        index = TagIndex()
        index.add("k1", "knowledge", "p1", ["a", "b"])
        index.add("k2", "knowledge", "p1", ["b", "c"])
        assert index.tag_count() == 3
