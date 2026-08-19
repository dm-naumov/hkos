"""Unit tests for SnapshotBuilder (DS-010 §9)."""

from pathlib import Path

from hkos.context.snapshot_loader import SnapshotDocument
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.snapshot.snapshot_builder import SnapshotBuilder
from hkos.storage import StorageEngine


class TestSnapshotBuilder:
    """Построение Snapshot из Repository (+ Entity Index для классификации)."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[StorageEngine, RepositoryManager, Librarian, IndexEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        return engine, repos, lib, index

    def test_build_sections(self, tmp_path: Path) -> None:
        engine, repos, lib, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="UDP fix", body="udp", tags=["udp"], confirmations=5))
        k = lib.register(p.id, Knowledge(title="Canonical", body="c", tags=["c"], confirmations=9))
        lib.canonicalize(p.id, k.id)
        lib.register(p.id, Knowledge(title="Fail", body="f", kind="negative", tags=["f"]))
        index.build(p.id)
        qc = IndexQueryExecutor(IndexStore(engine))
        snapshot = SnapshotDocument(snapshot_id="snapshot-00001", project_id=p.id)
        builder = SnapshotBuilder(repos)
        result = builder.build(p.id, snapshot, qc.snapshot(p.id))
        canonical = result.sections["Canonical Knowledge"]
        assert isinstance(canonical, list) and canonical
        # Единая политика классификации (Post-Audit Refinement):
        # и канонизированное знание, и FACT-знание -> Canonical Knowledge
        # (одинаковая логическая категория для Context и Snapshot).
        titles = [e.get("title") for e in canonical if isinstance(e, dict)]
        assert "Canonical" in titles
        assert "UDP fix" in titles
        assert result.statistics["knowledge"] == 3
        assert result.references

    def test_build_without_index(self, tmp_path: Path) -> None:
        """Без Entity Index — секции пустые, статистика из Repository."""
        engine, repos, lib, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="UDP", body="udp", tags=["udp"]))
        index.build(p.id)
        snapshot = SnapshotDocument(snapshot_id="snapshot-1", project_id=p.id)
        result = SnapshotBuilder(repos).build(p.id, snapshot, None)
        assert result.statistics["knowledge"] == 1
        assert result.sections["Canonical Knowledge"] == []

    def test_project_metadata(self, tmp_path: Path) -> None:
        engine, repos, lib, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        index.build(p.id)
        snapshot = SnapshotDocument(snapshot_id="s1", project_id=p.id)
        qc = IndexQueryExecutor(IndexStore(engine))
        result = SnapshotBuilder(repos).build(p.id, snapshot, qc.snapshot(p.id))
        metadata = result.sections["Project Metadata"]
        assert isinstance(metadata, dict)
        assert metadata["name"] == "OpenWrt"
