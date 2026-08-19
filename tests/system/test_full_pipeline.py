"""System: полный pipeline (DS-014 ЭТАП 2).
================================================================
Create Project -> Campaign -> Knowledge (Librarian) -> Index ->
Snapshot -> Retrieval -> Context -> Save -> Verify.

Проверки: порядок вызовов; data flow; производительность (Performance
Layer); отсутствие прямого доступа к Repository (знания — только через
Librarian; pipeline — через публичные фасады).
"""

import time
from pathlib import Path

from pytest import MonkeyPatch

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.performance.integration import PerformanceIntegration
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_knowledge_exists,
    assert_performance_recorded,
    assert_retrievable,
    assert_snapshot_consistent,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    knowledge_generator,
    project_factory,
)


class _FullPipelineContext:
    """Композиция pipeline с Performance-обёртками (DI)."""

    def __init__(self, tmp_path: Path):
        self.base = create_system_context(tmp_path)
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.perf = PerformanceIntegration()
        self.snapshots = SnapshotEngine(
            self.base.repos, _MemoryPersistence(), HKOSLogger(),
            index_provider=self.base.qc.snapshot)
        self.retrieval = self.perf.wrap_retrieval(
            self.base.retrieval, fingerprint=self.base.store.fingerprint)
        loader = SnapshotLoader(lambda pid: self._load_snapshot(pid))
        builder = ContextBuilder(cfg, HKOSLogger(), loader=loader)
        self.context = self.perf.wrap_context(builder)

    def _load_snapshot(self, pid: str):
        snapshot = self.snapshots.load(pid)
        return snapshot.as_dict() if snapshot is not None else None


class TestFullPipelineSystem:
    """Сквозной сценарий: все слои HKOS как единая система."""

    def test_full_pipeline_order_and_flow(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        ctx = _FullPipelineContext(tmp_path)
        order: list[str] = []

        def recorder(name: str, fn: object) -> object:
            def wrapper(*args: object, **kwargs: object) -> object:
                order.append(name)
                return fn(*args, **kwargs)  # type: ignore[operator]
            return wrapper

        targets = [
            (ctx.base.projects, "create", "project_create"),
            (ctx.base.campaigns, "create", "campaign_create"),
            (ctx.base.librarian, "register", "knowledge_register"),
            (ctx.base.index, "build", "index_build"),
            (ctx.snapshots, "create", "snapshot_create"),
            (ctx.retrieval, "retrieve", "retrieval"),
            (ctx.context, "build", "context_build"),
        ]
        for target, attr, step in targets:
            original = getattr(target, attr)
            monkeypatch.setattr(target, attr, recorder(step, original))

        # 1. Project -> Campaign
        project = ctx.base.projects.create(name="Pipeline", tags=["sys"])
        ctx.base.campaigns.create(project.id, goal="task-1")
        # 2. Knowledge через Librarian
        knowledge_generator(ctx.base, project.id, 20, prefix="P")
        # 3. Index
        ctx.base.index.build(project.id)
        # 4. Snapshot
        ctx.snapshots.create(project.id, reason="pipeline")
        # 5. Retrieval (обёртка: измерение + кэш)
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        assert len(result.items) >= 1
        # 6. Context
        context = ctx.context.build(result, project.id)
        assert context is not None
        # 7. Save нового знания (через Librarian)
        saved = ctx.base.librarian.register(project.id, __import__(
            "hkos.repository.models", fromlist=["Knowledge"]).Knowledge(
                title="Pipeline result udp", body="udp fixed", tags=["udp"]))
        ctx.base.index.update(project.id, saved.id, "knowledge")
        # 7b. Snapshot обновляется (актуальное состояние)
        ctx.snapshots.create(project.id, reason="post_save", force=True)
        # 8. Verify: новое знание retrievable; Snapshot согласован
        assert_knowledge_exists(ctx.base, project.id, saved.id)
        assert_retrievable(ctx.base, project.id, "Pipeline result", "Pipeline result")
        assert_snapshot_consistent(ctx.base, ctx.snapshots, project.id)
        # порядок вызовов соответствует pipeline
        for step in ("project_create", "campaign_create", "knowledge_register",
                     "index_build", "snapshot_create", "retrieval", "context_build"):
            assert step in order, step
        assert order.index("project_create") < order.index("knowledge_register")
        assert order.index("knowledge_register") < order.index("index_build")
        assert order.index("index_build") < order.index("retrieval")
        assert order.index("retrieval") < order.index("context_build")
        # performance metrics записаны
        assert_performance_recorded(ctx.perf.manager, "retrieval")
        assert_performance_recorded(ctx.perf.manager, "context_build")

    def test_no_direct_repository_access(self, tmp_path: Path) -> None:
        """Знания пишутся ТОЛЬКО через Librarian (не напрямую в Repository)."""
        ctx = _FullPipelineContext(tmp_path)
        project = project_factory(ctx.base, "NoDirect")
        # знание создаётся через Librarian (публичный сервисный API)
        knowledge = ctx.base.librarian.register(project.id, __import__(
            "hkos.repository.models", fromlist=["Knowledge"]).Knowledge(
                title="Via librarian udp", body="b", tags=["udp"]))
        assert knowledge.id
        assert_knowledge_exists(ctx.base, project.id, knowledge.id)

    def test_performance_budgets(self, tmp_path: Path) -> None:
        """Retrieval <100 мс; Context <200 мс; Save <150 мс (DS-013/014)."""
        ctx = _FullPipelineContext(tmp_path)
        project = project_factory(ctx.base, "Perf")
        ids = knowledge_generator(ctx.base, project.id, 200, prefix="PF")
        assert len(ids) == 200
        ctx.base.index.build(project.id)

        start = time.perf_counter()
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        retrieval_ms = (time.perf_counter() - start) * 1000
        assert retrieval_ms < 100, f"retrieval {retrieval_ms:.1f} ms"

        start = time.perf_counter()
        ctx.context.build(result, project.id)
        context_ms = (time.perf_counter() - start) * 1000
        assert context_ms < 200, f"context {context_ms:.1f} ms"

        start = time.perf_counter()
        ctx.base.librarian.register(project.id, __import__(
            "hkos.repository.models", fromlist=["Knowledge"]).Knowledge(
                title="Save udp", body="b", tags=["udp"]))
        save_ms = (time.perf_counter() - start) * 1000
        assert save_ms < 150, f"save {save_ms:.1f} ms"
