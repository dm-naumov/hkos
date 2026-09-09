"""Unit tests for SnapshotDiff (DS-010 §11)."""

from hkos.context.snapshot_loader import SnapshotDocument
from hkos.snapshot.snapshot_diff import SnapshotDiff


def _snapshot(sections: dict[str, object]) -> SnapshotDocument:
    return SnapshotDocument(snapshot_id="s1", project_id="p1", sections=sections)


class TestSnapshotDiff:
    """Сравнение снимков: Added/Removed/Modified/Unchanged."""

    def test_identical_snapshots(self) -> None:
        a = _snapshot({"Canonical Knowledge": [{"id": "k1", "title": "A"}]})
        b = _snapshot({"Canonical Knowledge": [{"id": "k1", "title": "A"}]})
        result = SnapshotDiff().diff(a, b)
        assert result.added == []
        assert result.removed == []
        assert result.modified == []
        assert result.unchanged == ["k1"]

    def test_added(self) -> None:
        a = _snapshot({"Canonical Knowledge": []})
        b = _snapshot({"Canonical Knowledge": [{"id": "k1", "title": "A"}]})
        result = SnapshotDiff().diff(a, b)
        assert result.added == ["k1"]
        assert result.changed_count == 1

    def test_removed(self) -> None:
        a = _snapshot({"Canonical Knowledge": [{"id": "k1", "title": "A"}]})
        b = _snapshot({"Canonical Knowledge": []})
        result = SnapshotDiff().diff(a, b)
        assert result.removed == ["k1"]

    def test_modified(self) -> None:
        a = _snapshot({"Canonical Knowledge": [{"id": "k1", "title": "A"}]})
        b = _snapshot({"Canonical Knowledge": [{"id": "k1", "title": "B"}]})
        result = SnapshotDiff().diff(a, b)
        assert result.modified == ["k1"]

    def test_modified_body_only(self) -> None:
        """Изменение body без изменения title должно давать Modified."""
        a = _snapshot(
            {"Canonical Knowledge": [{"id": "k1", "title": "A", "body": "old body"}]}
        )
        b = _snapshot(
            {"Canonical Knowledge": [{"id": "k1", "title": "A", "body": "new body"}]}
        )
        result = SnapshotDiff().diff(a, b)
        assert result.modified == ["k1"]
        assert result.unchanged == []

    def test_modified_content_only(self) -> None:
        """Изменение content (alias for body) без изменения title → Modified."""
        a = _snapshot(
            {"Canonical Knowledge": [{"id": "k1", "title": "A", "content": "v1"}]}
        )
        b = _snapshot(
            {"Canonical Knowledge": [{"id": "k1", "title": "A", "content": "v2"}]}
        )
        result = SnapshotDiff().diff(a, b)
        assert result.modified == ["k1"]
        assert result.unchanged == []

    def test_unchanged_when_body_identical(self) -> None:
        """Одинаковые title + body → Unchanged."""
        a = _snapshot(
            {"Canonical Knowledge": [{"id": "k1", "title": "A", "body": "same"}]}
        )
        b = _snapshot(
            {"Canonical Knowledge": [{"id": "k1", "title": "A", "body": "same"}]}
        )
        result = SnapshotDiff().diff(a, b)
        assert result.unchanged == ["k1"]
        assert result.modified == []

    def test_section_changes(self) -> None:
        a = _snapshot({"Canonical Knowledge": []})
        b = _snapshot({"Accepted Decisions": [{"id": "d1", "title": "D"}]})
        result = SnapshotDiff().diff(a, b)
        assert "Accepted Decisions" in result.section_changes
        assert result.section_changes["Accepted Decisions"] == ["d1"]

    def test_works_without_repository(self) -> None:
        """Diff не обращается к Repository (только документы)."""
        import inspect

        source = inspect.getsource(SnapshotDiff)
        # Никаких импортов/атрибутов репозитория в коде (docstring не в счёт)
        code = source.split('"""')[-1]
        assert "repository" not in code.lower()
        assert "self._repositories" not in source
