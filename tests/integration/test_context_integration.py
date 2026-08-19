"""Integration tests: Context Builder (DS-009 §21, IP-009).

Сценарии: OpenWrt (Retrieve->Build->Serialize), Phoenix Contact
(+ Snapshot), Large Project (Optimization->Token Limit),
Repeated Knowledge (Deduplication). + производительность (<200 ms).
"""

import time
from pathlib import Path

from hkos.context import ContextBuilder, SnapshotDocument, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.librarian import Librarian
from hkos.storage import StorageEngine


class TestContextIntegration:
    """Полные сценарии Context Builder."""

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
            project_registry={"openwrt": "owrt"},
        )
        cb = ContextBuilder(cfg, HKOSLogger(), loader=SnapshotLoader())
        return engine, repos, lib, index, rv, cb

    def test_scenario_openwrt(self, tmp_path: Path) -> None:
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(
            title="TProxy UDP", body="udp tproxy", tags=["udp"], confirmations=5,
        ))
        k = lib.register(p.id, Knowledge(
            title="UDP fix", body="fwmark udp", tags=["udp"], confirmations=8,
        ))
        lib.canonicalize(p.id, k.id)
        index.build(p.id)
        result = rv.retrieve("udp", project_id=p.id, top_n=10)
        context = cb.build(result, p.id)
        assert context.items
        assert context.validation.valid is True
        text = cb.serialize(context)
        assert "## CANONICAL KNOWLEDGE" in text
        assert "UDP fix" in text

    def test_scenario_snapshot(self, tmp_path: Path) -> None:
        """Phoenix Contact + Snapshot -> Context (CURRENT STATE секция)."""
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        p = repos.projects.save(Project(name="Phoenix Contact", tags=["terminal"]))
        lib.register(p.id, Knowledge(
            title="Terminal blocks", body="phoenix", tags=["terminal"],
        ))
        index.build(p.id)
        snapshot = SnapshotDocument(
            snapshot_id="snapshot-00041", timestamp="2026-07-26T21:43:00Z",
            project_id=p.id, knowledge_version="graph-183",
        )
        cb = ContextBuilder(
            cfg, HKOSLogger(),
            loader=SnapshotLoader(lambda pid: snapshot.as_dict()),
        )
        rv = RetrievalEngine(repos, IndexQueryExecutor(IndexStore(engine)), cfg, HKOSLogger())
        result = rv.retrieve("phoenix", project_id=p.id)
        context = cb.build(result, p.id)
        assert context.snapshot is not None
        text = cb.serialize(context)
        assert "snapshot-00041" in text
        assert context.validation.valid is True

    def test_scenario_token_limit(self, tmp_path: Path) -> None:
        """Large Project: оптимизация и лимит токенов."""
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        for i in range(30):
            lib.register(p.id, Knowledge(
                title=f"UDP knowledge {i}", body=f"udp topic {i}",
                tags=["udp"], confirmations=i,
            ))
        index.build(p.id)
        result = rv.retrieve("udp", project_id=p.id, top_n=30)
        context_small = cb.build(result, p.id, profile="SMALL")
        context_full = cb.build(result, p.id, profile="FULL")
        assert context_small.estimates.estimated_tokens <= context_full.estimates.estimated_tokens
        assert len(context_small.items) <= len(context_full.items)

    def test_scenario_deduplication(self, tmp_path: Path) -> None:
        """Repeated Knowledge: дубликаты удаляются."""
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="UDP best", body="udp", tags=["udp"]))
        index.build(p.id)
        result = rv.retrieve("udp", project_id=p.id, top_n=10)
        # Дублируем элемент вручную (имитация повторного попадания)
        result.items.append(result.items[0])
        context = cb.build(result, p.id)
        ids = [getattr(i.entity, "id", "") for i in context.items]
        assert len(ids) == len(set(ids))

    def test_performance_10k(self, tmp_path: Path) -> None:
        """Производительность: 10K Knowledge, Context Build < 200 ms."""
        engine, repos, lib, index, rv, cb = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        for i in range(10000):
            repos.knowledge.save(Knowledge(
                project=p.id, title=f"Knowledge {i}", body=f"body {i} udp",
                tags=["bulk"] if i % 2 else ["udp"]))
        index.build(p.id)
        result = rv.retrieve("udp", project_id=p.id, top_n=50)
        start = time.monotonic()
        context = cb.build(result, p.id, profile="LARGE")
        duration = (time.monotonic() - start) * 1000.0
        assert context.items
        assert duration < 200.0, f"context build took {duration:.1f} ms"
