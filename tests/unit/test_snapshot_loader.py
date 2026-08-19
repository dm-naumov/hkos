"""Unit tests for SnapshotLoader (DS-010 §14)."""

import pytest

from hkos.context.snapshot_loader import SnapshotDocument
from hkos.snapshot.exceptions import SnapshotNotFoundError
from hkos.snapshot.snapshot_loader import SnapshotLoader


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



def _persistence() -> MemoryPersistence:
    """Порт с двумя снимками."""
    persistence = MemoryPersistence()
    persistence.save("p1", {
        "snapshot_id": "snapshot-00001", "project_id": "p1",
        "sections": {"Canonical Knowledge": []},
    })
    persistence.save("p1", {
        "snapshot_id": "snapshot-00002", "project_id": "p1",
        "sections": {"Canonical Knowledge": [{"id": "k1", "title": "A"}]},
    })
    return persistence


class TestSnapshotLoader:
    """Загрузка: последний / версия; делегирование Context Loader."""

    def test_load_latest(self) -> None:
        loader = SnapshotLoader(_persistence())
        doc = loader.load_latest("p1")
        assert doc is not None
        assert doc.snapshot_id == "snapshot-00002"

    def test_load_latest_none(self) -> None:
        loader = SnapshotLoader(MemoryPersistence())
        assert loader.load_latest("p1") is None

    def test_load_version(self) -> None:
        loader = SnapshotLoader(_persistence())
        doc = loader.load_version("p1", "00001")
        assert doc.snapshot_id == "snapshot-00001"

    def test_load_version_missing_raises(self) -> None:
        loader = SnapshotLoader(_persistence())
        with pytest.raises(SnapshotNotFoundError):
            loader.load_version("p1", "99999")

    def test_reuses_context_loader(self) -> None:
        """Разбор делегируется существующему Context SnapshotLoader."""
        loader = SnapshotLoader(_persistence())
        doc = loader.load_latest("p1")
        assert isinstance(doc, SnapshotDocument)
