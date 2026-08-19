"""Integration tests: Retrieval Engine (DS-008 §20, IP-008).

Сценарии: OpenWrt, Phoenix Contact, Campaign Search, Unknown Topic,
Relationship Expansion, Archived Knowledge, Canonical Priority.
+ производительность (10K Knowledge, <100 ms).
"""

import time
from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.librarian import Librarian
from hkos.storage import StorageEngine


class TestRetrievalIntegration:
    """Полные сценарии Retrieval."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[
        StorageEngine, RepositoryManager, Librarian, IndexEngine, RetrievalEngine
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
            project_registry={"openwrt": "owrt", "phoenix contact": "phx"},
        )
        return engine, repos, lib, index, rv

    def _openwrt_corpus(
        self, repos: RepositoryManager, lib: Librarian, index: IndexEngine
    ) -> tuple[Project, Knowledge, Knowledge, Knowledge]:
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k1 = lib.register(p.id, Knowledge(
            title="TProxy UDP works", body="udp tproxy nftables sing-box",
            tags=["tproxy", "udp"], confirmations=5, successful_usage=4))
        lib.register(p.id, Knowledge(
            title="TUN breaks DNS", body="tun dns failure", kind="negative",
            tags=["tun", "dns"], confirmations=2))
        k3 = lib.register(p.id, Knowledge(
            title="nftables fwmark", body="policy routing fwmark",
            tags=["nftables"], confirmations=3))
        k4 = lib.register(p.id, Knowledge(
            title="UDP routing fix", body="fwmark udp",
            tags=["udp"], confirmations=8, successful_usage=7))
        lib.canonicalize(p.id, k4.id)
        k5 = lib.register(p.id, Knowledge(
            title="Old approach", body="obsolete", tags=["udp"]))
        lib.archive(p.id, k5.id)
        k6 = lib.register(p.id, Knowledge(
            title="Bad idea", body="wrong", tags=["udp"]))
        lib.reject(p.id, k6.id)
        merged = lib.merge(p.id, k1.id, k3.id, reason="same topic")
        index.build(p.id)
        index.update(p.id, merged.id, "knowledge")
        return p, k1, k4, merged

    def test_scenario_openwrt(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p, k1, k4, merged = self._openwrt_corpus(repos, lib, index)
        result = rv.retrieve("udp routing", project_id=p.id, top_n=10)
        assert result.items
        # Каноническое знание — в результатах
        ids = [i.entity.id for i in result.items]
        assert k4.id in ids
        # Архив/отклонённые исключены
        titles = [i.entity.title for i in result.items]
        assert "Old approach" not in titles
        assert "Bad idea" not in titles

    def test_scenario_project_hint(self, tmp_path: Path) -> None:
        """Project hint из реестра имён (без явного project_id)."""
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="TProxy UDP", body="udp", tags=["udp"]))
        index.build(p.id)
        rv = RetrievalEngine(
            repos, IndexQueryExecutor(IndexStore(engine)), cfg, HKOSLogger(),
            project_registry={"openwrt": p.id},
        )
        result = rv.search("udp в OpenWrt")
        assert result.project == p.id
        assert result.items

    def test_scenario_phoenix_contact(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="Phoenix Contact", tags=["terminal"]))
        lib.register(p.id, Knowledge(
            title="Phoenix terminal blocks", body="industrial automation",
            tags=["terminal"], confirmations=3))
        index.build(p.id)
        result = rv.search("аналог Phoenix Contact", project_id=p.id)
        assert result.items

    def test_scenario_campaign_search(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k = lib.register(p.id, Knowledge(
            title="Campaign result", body="tproxy udp", tags=["udp"],
            source_campaign="camp-17", confirmations=2))
        lib.register(p.id, Knowledge(
            title="Other", body="udp", tags=["udp"], confirmations=1))
        index.build(p.id)
        result = rv.search_campaign(p.id, "camp-17", "udp")
        assert result.items
        assert any(i.entity.id == k.id for i in result.items)

    def test_scenario_unknown_topic(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="TProxy", body="udp", tags=["udp"]))
        index.build(p.id)
        result = rv.retrieve("zzzqqqx", project_id=p.id)
        assert result.items == []

    def test_scenario_relationship_expansion(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p, k1, k4, merged = self._openwrt_corpus(repos, lib, index)
        result = rv.retrieve("tproxy", project_id=p.id, top_n=10)
        # Связанные знания (merge) попадают в результат с relation_path
        has_path = any(i.explanation.relation_path for i in result.items)
        assert has_path or any(i.entity.id == merged.id for i in result.items)

    def test_scenario_archived_knowledge(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="UDP one", body="udp", tags=["udp"]))
        archived = lib.register(p.id, Knowledge(title="UDP old", body="udp", tags=["udp"]))
        lib.archive(p.id, archived.id)
        index.build(p.id)
        default = rv.search("udp", project_id=p.id)
        assert all(i.entity.id != archived.id for i in default.items)
        with_history = rv.search("udp", project_id=p.id, include_history=True)
        assert any(i.entity.id == archived.id for i in with_history.items)

    def test_scenario_canonical_priority(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        canonical = lib.register(p.id, Knowledge(
            title="UDP best practice", body="udp", tags=["udp"], confirmations=4))
        lib.canonicalize(p.id, canonical.id)
        lib.register(p.id, Knowledge(
            title="UDP note", body="udp", tags=["udp"], confirmations=6))
        index.build(p.id)
        result = rv.search("udp", project_id=p.id, top_n=10)
        assert result.items
        # Каноническое знание ранжируется выше
        first = result.items[0]
        assert first.entity.id == canonical.id or first.explanation.canonical

    def test_performance_10k(self, tmp_path: Path) -> None:
        """Производительность: 10K Knowledge, retrieval < 100 ms."""
        engine, repos, lib, index, rv = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        for i in range(10000):
            repos.knowledge.save(Knowledge(
                project=p.id, title=f"Knowledge {i}",
                body=f"body {i} udp", tags=["bulk"] if i % 2 else ["udp"]))
        index.build(p.id)
        start = time.monotonic()
        result = rv.retrieve("udp", project_id=p.id, top_n=20)
        duration = (time.monotonic() - start) * 1000.0
        assert result.items
        assert duration < 100.0, f"retrieval took {duration:.1f} ms"
