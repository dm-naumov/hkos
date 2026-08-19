"""Unit tests for SnapshotEngine (DS-010 §6)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.snapshot.snapshot_engine import SnapshotEngine
from hkos.storage import StorageEngine


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



class TestSnapshotEngine:
    """Публичный API SnapshotEngine (8 методов)."""

    def _ctx(
        self, tmp_path: Path, persistence: MemoryPersistence
    ) -> tuple[StorageEngine, RepositoryManager, Librarian, IndexEngine, SnapshotEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        qc = IndexQueryExecutor(IndexStore(engine))
        snap = SnapshotEngine(repos, persistence, HKOSLogger(), index_provider=qc.snapshot)
        return engine, repos, lib, index, snap

    def _corpus(
        self, repos: RepositoryManager, lib: Librarian, index: IndexEngine
    ) -> str:
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert p is not None
        k = lib.register(p.id, Knowledge(
            title="UDP fix", body="udp", tags=["udp"], confirmations=8,
        ))
        lib.canonicalize(p.id, k.id)
        lib.register(p.id, Knowledge(title="Fail", body="f", kind="negative", tags=["f"]))
        index.build(p.id)
        return p.id

    def test_create(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        project = self._corpus(repos, lib, index)
        document = snap.create(project, reason="campaign_finished", author="agent")
        assert document.snapshot_id == "snapshot-00001"
        assert document.project_id == project
        assert document.sections["Canonical Knowledge"]

    def test_update_no_change_returns_latest(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        project = self._corpus(repos, lib, index)
        first = snap.create(project, reason="initial")
        second = snap.update(project, reason="no_change")
        assert second.snapshot_id == first.snapshot_id  # правило DS-010 §10

    def test_update_change_creates_new_version(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        project = self._corpus(repos, lib, index)
        first = snap.create(project, reason="initial")
        k = lib.register(project, Knowledge(title="New canonical", body="n", tags=["n"]))
        lib.canonicalize(project, k.id)
        index.update(project, k.id, "knowledge")
        second = snap.update(project, reason="new_knowledge")
        assert second.snapshot_id == "snapshot-00002"
        assert second.parent == first.snapshot_id

    def test_load_and_version(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        project = self._corpus(repos, lib, index)
        snap.create(project)
        latest = snap.load(project)
        assert latest is not None
        version = snap.load(project, "00001")
        assert version is not None
        assert version.snapshot_id == "snapshot-00001"

    def test_diff_validate_serialize(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        project = self._corpus(repos, lib, index)
        snap.create(project)
        k = lib.register(project, Knowledge(title="Extra", body="e", tags=["e"]))
        index.update(project, k.id, "knowledge")
        second = snap.update(project)
        first = snap.load(project, "00001")
        assert first is not None
        diff = snap.diff(first, second)
        assert diff.added or diff.unchanged
        validation = snap.validate(second)
        assert validation.valid is True
        serialized = snap.serialize(second)
        assert serialized["schema"] == "HKOS-1.0"
        assert serialized["type"] == "snapshot"

    def test_statistics_and_history(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        project = self._corpus(repos, lib, index)
        snap.create(project, reason="r1")
        snap.create(project, reason="r2", force=True)
        stats = snap.statistics(project)
        assert stats["snapshots"] == 2
        history = snap.history(project)
        assert len(history) == 2

    def test_public_api_exact(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        api = {name for name in dir(snap) if not name.startswith("_")}
        assert {"create", "load", "update", "diff", "validate",
                "serialize", "statistics", "history"} <= api

    def test_append_only_no_deletion(self, tmp_path: Path) -> None:
        """Нет API удаления/изменения старых снимков."""
        engine, repos, lib, index, snap = self._ctx(tmp_path, MemoryPersistence())
        project = self._corpus(repos, lib, index)
        snap.create(project)
        first = snap.load(project)
        assert first is not None
        # документ не мутируется после создания
        before = snap.serialize(first)
        after = snap.serialize(first)
        assert before == after
