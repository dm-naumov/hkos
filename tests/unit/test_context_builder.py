"""Unit tests for ContextBuilder (DS-009 §6)."""

from pathlib import Path

from hkos.context import (
    ContextBuilder,
    SnapshotDocument,
    SnapshotLoader,
)
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.librarian import Librarian
from hkos.storage import StorageEngine


class TestContextBuilder:
    """Публичный API ContextBuilder (7 методов)."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[
        StorageEngine, RepositoryManager, Librarian, IndexEngine,
        RetrievalEngine, ContextBuilder,
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
        rv = RetrievalEngine(
            repos, IndexQueryExecutor(IndexStore(engine)), cfg, HKOSLogger(),
            project_registry={"openwrt": "p1"},
        )
        snapshot = SnapshotDocument(
            snapshot_id="snapshot-1", timestamp="2026-01-01T00:00:00Z"
        )
        cb = ContextBuilder(
            cfg, HKOSLogger(),
            loader=SnapshotLoader(lambda pid: snapshot.as_dict()),
        )
        return engine, repos, lib, index, rv, cb

    def _corpus(
        self, engine: StorageEngine, repos: RepositoryManager, lib: Librarian
    ) -> Project:
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k1 = lib.register(p.id, Knowledge(title="TProxy UDP", body="udp tproxy", tags=["udp"]))
        lib.canonicalize(p.id, k1.id)
        lib.register(p.id, Knowledge(title="TUN fail", body="dns", kind="negative", tags=["tun"]))
        IndexEngine(repos, IndexStore(engine), HKOSLogger()).build(p.id)
        return p

    def test_build(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id, top_n=10)
        context = cb.build(result, p.id, profile="SMALL")
        assert context.items
        assert context.project_id == p.id
        assert context.snapshot is not None
        assert context.validation is not None
        assert context.validation.valid is True
        assert context.estimates.estimated_tokens > 0

    def test_optimize(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id)
        context = cb.build(result, p.id)
        optimized = cb.optimize(context)
        assert optimized is not None

    def test_serialize(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id)
        context = cb.build(result, p.id)
        text = cb.serialize(context)
        assert "## TASK" in text
        assert "## CANONICAL KNOWLEDGE" in text

    def test_statistics(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id)
        context = cb.build(result, p.id)
        stats = cb.statistics(context)
        total = stats["total_items"]
        assert isinstance(total, int) and total >= 1
        assert "estimated_tokens" in stats

    def test_validate(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id)
        context = cb.build(result, p.id)
        validation = cb.validate(context)
        assert validation.valid is True

    def test_estimate_tokens(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        estimate = cb.estimate_tokens("hello world context")
        assert estimate.words == 3
        assert estimate.estimated_tokens >= 1

    def test_explain(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id)
        context = cb.build(result, p.id)
        explanations = cb.explain(context)
        assert explanations
        for explanation in explanations:
            assert explanation.why_included or explanation.why_excluded
            assert explanation.source

    def test_public_api_exact(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        api = {name for name in dir(cb) if not name.startswith("_")}
        assert {"build", "optimize", "serialize", "statistics", "validate",
                "estimate_tokens", "explain", "loader"} <= api
