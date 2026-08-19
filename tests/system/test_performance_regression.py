"""System: Performance Regression (DS-014 ЭТАП 5 §7).
================================================================
SLA-таблица с Performance Layer: retrieval cold <100 мс, warm <10 мс,
context <200 мс, snapshot load <50 мс, save <150 мс, cache hit >80%.
"""

import time
from pathlib import Path

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.performance.integration import PerformanceIntegration
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestPerformanceRegression:
    """SLA с Performance Layer (DS-013/014)."""

    def _setup(self, tmp_path: Path, n: int = 500):
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "PerfReg", tags=["system"])
        for i in range(n):
            ctx.librarian.register(project.id, Knowledge(
                title=f"PR{i}fact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        cfg = ConfigLoader(profile="development")
        cfg.load()
        builder = ContextBuilder(cfg, HKOSLogger(),
                                 loader=SnapshotLoader(lambda pid: None))
        return ctx, project, measured, perf, snapshots, builder

    def test_retrieval_cold_warm(self, tmp_path: Path) -> None:
        ctx, project, measured, perf, snapshots, builder = self._setup(tmp_path)
        start = time.perf_counter()
        measured.retrieve("udp", project_id=project.id)
        cold = (time.perf_counter() - start) * 1000
        assert cold < 100, f"cold {cold:.1f} ms"
        start = time.perf_counter()
        measured.retrieve("udp", project_id=project.id)
        warm = (time.perf_counter() - start) * 1000
        assert warm < 10, f"warm {warm:.1f} ms"

    def test_context_and_save(self, tmp_path: Path) -> None:
        ctx, project, measured, perf, snapshots, builder = self._setup(tmp_path)
        result = measured.retrieve("udp", project_id=project.id)
        start = time.perf_counter()
        builder.build(result, project.id)
        context_ms = (time.perf_counter() - start) * 1000
        assert context_ms < 200, f"context {context_ms:.1f} ms"
        start = time.perf_counter()
        ctx.librarian.register(project.id, Knowledge(
            title="Save udp", body="udp", tags=["udp"]))
        save_ms = (time.perf_counter() - start) * 1000
        assert save_ms < 150, f"save {save_ms:.1f} ms"

    def test_snapshot_load(self, tmp_path: Path) -> None:
        ctx, project, measured, perf, snapshots, builder = self._setup(tmp_path)
        snapshots.create(project.id, reason="perf")
        start = time.perf_counter()
        snapshots.load(project.id)
        load_ms = (time.perf_counter() - start) * 1000
        assert load_ms < 50, f"snapshot load {load_ms:.1f} ms"

    def test_cache_hit_ratio(self, tmp_path: Path) -> None:
        ctx, project, measured, perf, snapshots, builder = self._setup(tmp_path)
        for _ in range(10):
            measured.retrieve("udp", project_id=project.id)
        ratio = perf.cache.statistics().get("hit_ratio", 0)
        assert isinstance(ratio, float) and ratio > 0.8, f"hit_ratio {ratio:.2f}"
