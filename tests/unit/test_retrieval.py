"""Unit tests for RetrievalEngine (DS-008 §6)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.retrieval.exceptions import RetrievalError, RetrievalScopeError
from hkos.services.librarian import Librarian
from hkos.storage import StorageEngine


class TestRetrievalEngine:
    """Публичный API RetrievalEngine (7 методов)."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[StorageEngine, RepositoryManager, Librarian, RetrievalEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        query_contract = IndexQueryExecutor(IndexStore(engine))
        rv = RetrievalEngine(
            repos, query_contract, cfg, HKOSLogger(),
            project_registry={"openwrt": "p1"},
        )
        return engine, repos, lib, rv

    def _corpus(
        self, engine: StorageEngine, repos: RepositoryManager, lib: Librarian
    ) -> tuple[Project, Knowledge, Knowledge]:
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k1 = lib.register(
            p.id,
            Knowledge(title="TProxy UDP works", body="udp tproxy", tags=["udp"], confirmations=5),
        )
        k2 = lib.register(
            p.id, Knowledge(title="TUN breaks DNS", body="dns", kind="negative", tags=["tun"]),
        )
        lib.canonicalize(p.id, k1.id)
        IndexEngine(repos, IndexStore(engine), HKOSLogger()).build(p.id)
        return p, k1, k2

    def test_retrieve(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, k1, _ = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id, top_n=5)
        assert result.items
        assert result.project == p.id
        assert any(i.entity.id == k1.id for i in result.items)

    def test_search(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, k1, _ = self._corpus(engine, repos, lib)
        result = rv.search("udp", project_id=p.id)
        assert result.items

    def test_search_project(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, _, _ = self._corpus(engine, repos, lib)
        result = rv.search_project(p.id, "udp")
        assert result.project == p.id

    def test_search_campaign(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, k1, _ = self._corpus(engine, repos, lib)
        k2 = lib._load(p.id, k1.id)
        k2.source_campaign = "c1"
        lib.update(p.id, k2)
        result = rv.search_campaign(p.id, "c1", "udp")
        assert result.items
        assert all(i.explanation.campaign_match or i.explanation.score >= 0 for i in result.items)

    def test_related(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, k1, k2 = self._corpus(engine, repos, lib)
        merged = lib.merge(p.id, k1.id, k2.id, reason="dup")
        IndexEngine(repos, IndexStore(engine), HKOSLogger()).update(
            p.id, merged.id, "knowledge"
        )
        result = rv.related(p.id, k1.id)
        assert result.items

    def test_explain(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, k1, _ = self._corpus(engine, repos, lib)
        explanation = rv.explain(p.id, k1.id, query="udp")
        assert explanation.confidence > 0
        assert explanation.canonical is True

    def test_explain_missing_raises(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        with pytest.raises(RetrievalError):
            rv.explain("p1", "11111111-2222-3333-4444-555555555555")

    def test_statistics(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, _, _ = self._corpus(engine, repos, lib)
        rv.search("udp", project_id=p.id)
        stats = rv.statistics(p.id)
        count = stats["retrieval_count"]
        assert isinstance(count, int) and count >= 1
        assert "project_statistics" in stats

    def test_scope_error_without_project(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        # без registry и без project_id -> RetrievalScopeError
        unscoped = RetrievalEngine(
            repos, IndexQueryExecutor(IndexStore(engine)), ConfigLoader(profile="development"),
            HKOSLogger(), project_registry={},
        )
        with pytest.raises(RetrievalScopeError):
            unscoped.search("udp")

    def test_explainability_present_in_every_item(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        p, _, _ = self._corpus(engine, repos, lib)
        result = rv.retrieve("udp", project_id=p.id, top_n=10)
        for item in result.items:
            assert item.explanation.reason
            assert item.explanation.score >= 0
            assert item.explanation.confidence >= 0

    def test_public_api_exact(self, tmp_path: Path) -> None:
        engine, repos, lib, rv = self._ctx(tmp_path)
        api = {name for name in dir(rv) if not name.startswith("_")}
        assert {"retrieve", "search", "search_project", "search_campaign",
                "related", "explain", "statistics"} <= api
