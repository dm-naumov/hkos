"""Unit tests for EntityIndex (DS-007 §7)."""

from hkos.index.entity_index import EntityIndex
from hkos.repository.models import Knowledge, Project


class TestEntityIndex:
    """Entity Index: реестр проиндексированных сущностей."""

    def test_upsert_and_get(self) -> None:
        index = EntityIndex()
        index.upsert(
            Knowledge(id="k1", title="T", status="NEW", category="FACT", tags=["x"]),
            "knowledge", "p1",
        )
        record = index.get("k1")
        assert record is not None
        assert record["type"] == "knowledge"
        assert record["title"] == "T"
        assert record["tags"] == ["x"]

    def test_project_title_uses_name(self) -> None:
        index = EntityIndex()
        index.upsert(Project(id="p1", name="OpenWrt"), "project", "p1")
        record = index.get("p1")
        assert record is not None
        assert record["title"] == "OpenWrt"

    def test_upsert_overwrites(self) -> None:
        index = EntityIndex()
        index.upsert(Knowledge(id="k1", title="A"), "knowledge", "p1")
        index.upsert(Knowledge(id="k1", title="B"), "knowledge", "p1")
        assert index.count() == 1
        record = index.get("k1")
        assert record is not None
        assert record["title"] == "B"

    def test_remove(self) -> None:
        index = EntityIndex()
        index.upsert(Knowledge(id="k1", title="A"), "knowledge", "p1")
        index.remove("k1")
        assert index.get("k1") is None
        assert index.count() == 0

    def test_count_by_type(self) -> None:
        index = EntityIndex()
        index.upsert(Knowledge(id="k1", title="A"), "knowledge", "p1")
        index.upsert(Knowledge(id="k2", title="B"), "knowledge", "p1")
        index.upsert(Project(id="p1", name="P"), "project", "p1")
        counts = index.count_by_type()
        assert counts["knowledge"] == 2
        assert counts["project"] == 1

    def test_ids(self) -> None:
        index = EntityIndex()
        index.upsert(Knowledge(id="k1", title="A"), "knowledge", "p1")
        index.upsert(Knowledge(id="k2", title="B"), "knowledge", "p1")
        assert set(index.ids()) == {"k1", "k2"}
