"""Unit tests for SnapshotHistory (DS-010 §13)."""

from hkos.snapshot.snapshot_history import SnapshotHistory


class TestSnapshotHistory:
    """История Snapshot: append-only."""

    def test_append_and_entries(self) -> None:
        history = SnapshotHistory(MemoryPersistence())
        entry = history.append(
            "p1", "snapshot-00001", "agent", "camp-1",
            "campaign_finished", "первый", "",
        )
        assert entry["snapshot_id"] == "snapshot-00001"
        assert entry["reason"] == "campaign_finished"
        assert entry["previous_version"] == ""
        entries = history.entries("p1")
        assert len(entries) == 1

    def test_append_order_preserved(self) -> None:
        history = SnapshotHistory(MemoryPersistence())
        history.append("p1", "snapshot-00001", "a", "", "r1", "", "")
        history.append("p1", "snapshot-00002", "a", "", "r2", "", "snapshot-00001")
        entries = history.entries("p1")
        assert [e["snapshot_id"] for e in entries] == ["snapshot-00001", "snapshot-00002"]
        assert entries[1]["previous_version"] == "snapshot-00001"

    def test_no_mutation_api(self) -> None:
        """История append-only: нет update/delete."""
        api = {m for m in dir(SnapshotHistory) if not m.startswith("_")}
        assert api <= {"append", "entries"}

    def test_empty_history(self) -> None:
        history = SnapshotHistory(MemoryPersistence())
        assert history.entries("p1") == []

class MemoryPersistence:
    """In-memory реализация порта SnapshotPersistence (для тестов)."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, dict[str, object]]] = {}
        self._order: dict[str, list[str]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def latest(self, project: str) -> dict[str, object] | None:
        order = self._order.get(project, [])
        if not order:
            return None
        return self._docs.get(project, {}).get(order[-1])

    def version(self, project: str, version: str) -> dict[str, object] | None:
        return self._docs.get(project, {}).get(f"snapshot-{version}")

    def save(self, project: str, doc: dict[str, object]) -> str:
        snapshot_id = str(doc.get("snapshot_id", ""))
        self._docs.setdefault(project, {})[snapshot_id] = doc
        self._order.setdefault(project, []).append(snapshot_id)
        return snapshot_id

    def history(self, project: str) -> list[dict[str, object]]:
        return self._history.get(project, [])

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        self._history.setdefault(project, []).append(entry)
