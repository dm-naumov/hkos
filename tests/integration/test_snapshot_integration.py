"""Integration tests: Snapshot Engine (DS-010 §21, IP-010).

Сценарии: Campaign Finished -> Snapshot Created; Snapshot Loaded ->
Context Builder; Snapshot A -> B -> Diff; Invalid Snapshot ->
Validation Error. + производительность (Load/Create/Diff).
"""

import time
from pathlib import Path

from hkos.context import ContextBuilder
from hkos.context import SnapshotLoader as ContextSnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.librarian import Librarian
from hkos.snapshot import SnapshotEngine
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



class TestSnapshotIntegration:
    """Полные сценарии Snapshot Engine."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[
        StorageEngine, RepositoryManager, Librarian, IndexEngine,
        IndexQueryExecutor, MemoryPersistence, SnapshotEngine, ConfigLoader,
    ]:
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
        persistence = MemoryPersistence()
        snap = SnapshotEngine(repos, persistence, HKOSLogger(), index_provider=qc.snapshot)
        return engine, repos, lib, index, qc, persistence, snap, cfg

    def test_scenario_campaign_finished(self, tmp_path: Path) -> None:
        """Campaign Finished -> Snapshot Created."""
        engine, repos, lib, index, qc, persistence, snap, cfg = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k = lib.register(p.id, Knowledge(
            title="UDP fix", body="udp", tags=["udp"], confirmations=8,
        ))
        lib.canonicalize(p.id, k.id)
        index.build(p.id)
        snapshot = snap.create(
            p.id, campaign_id="camp-1", reason="campaign_finished", author="agent",
        )
        assert snapshot.snapshot_id == "snapshot-00001"
        assert snapshot.campaign_id == "camp-1"
        assert snapshot.sections["Canonical Knowledge"]
        assert snap.history(p.id)[0]["reason"] == "campaign_finished"

    def test_scenario_context_builder(self, tmp_path: Path) -> None:
        """Snapshot Loaded -> Context Builder (read-only интеграция)."""
        engine, repos, lib, index, qc, persistence, snap, cfg = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k = lib.register(p.id, Knowledge(
            title="UDP fix", body="udp", tags=["udp"], confirmations=8,
        ))
        lib.canonicalize(p.id, k.id)
        index.build(p.id)
        snap.create(p.id, reason="initial")
        # Context Builder использует Snapshot через существующий Context Loader
        def _load_latest(pid: str) -> dict[str, object] | None:
            loaded = snap.load(pid)
            return loaded.as_dict() if loaded is not None else None

        ctx_loader = ContextSnapshotLoader(_load_latest)
        cb = ContextBuilder(cfg, HKOSLogger(), loader=ctx_loader)
        rv = RetrievalEngine(repos, qc, cfg, HKOSLogger())
        result = rv.retrieve("udp", project_id=p.id)
        context = cb.build(result, p.id)
        assert context.snapshot is not None
        assert context.snapshot.snapshot_id == "snapshot-00001"
        assert context.validation.valid is True
        text = cb.serialize(context)
        assert "snapshot-00001" in text

    def test_scenario_diff(self, tmp_path: Path) -> None:
        """Snapshot A -> B -> Diff."""
        engine, repos, lib, index, qc, persistence, snap, cfg = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="UDP", body="udp", tags=["udp"]))
        index.build(p.id)
        a = snap.create(p.id, reason="initial")
        k = lib.register(p.id, Knowledge(title="New canonical", body="n", tags=["n"]))
        lib.canonicalize(p.id, k.id)
        index.update(p.id, k.id, "knowledge")
        b = snap.update(p.id, reason="added_canonical")
        diff = snap.diff(a, b)
        assert k.id in diff.added
        assert diff.changed_count >= 1

    def test_scenario_invalid_snapshot(self, tmp_path: Path) -> None:
        """Invalid Snapshot -> Validation Error."""
        engine, repos, lib, index, qc, persistence, snap, cfg = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        index.build(p.id)
        from hkos.context.snapshot_loader import SnapshotDocument

        broken = SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=p.id,
            references=["99999999-9999-4999-8999-999999999999"],
        )
        validation = snap.validate(broken)
        assert validation.valid is False
        assert any("Broken" in e for e in validation.errors)

    def test_performance(self, tmp_path: Path) -> None:
        """Производительность: Create <= 300 ms, Load <= 50 ms, Diff <= 500 ms
        на проекте с 10 000 Knowledge (масштаб 100K — экстраполяция через
        in-memory классификацию; требование DS-010 §22).
        """
        engine, repos, lib, index, qc, persistence, snap, cfg = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        for i in range(10000):
            repos.knowledge.save(Knowledge(
                project=p.id, title=f"Knowledge {i}", body=f"body {i} udp",
                tags=["udp"] if i % 2 else ["bulk"]))
        index.build(p.id)

        start = time.monotonic()
        snap.create(p.id, reason="mass")
        create_ms = (time.monotonic() - start) * 1000.0
        assert create_ms < 300.0, f"create took {create_ms:.1f} ms"

        start = time.monotonic()
        loaded = snap.load(p.id)
        load_ms = (time.monotonic() - start) * 1000.0
        assert loaded is not None
        assert load_ms < 50.0, f"load took {load_ms:.1f} ms"

        # вторая версия для diff
        k = lib.register(p.id, Knowledge(title="Delta", body="d", tags=["d"]))
        lib.canonicalize(p.id, k.id)
        index.update(p.id, k.id, "knowledge")
        second = snap.update(p.id)
        start = time.monotonic()
        diff = snap.diff(loaded, second)
        diff_ms = (time.monotonic() - start) * 1000.0
        assert diff_ms < 500.0, f"diff took {diff_ms:.1f} ms"
        assert diff.changed_count >= 1
