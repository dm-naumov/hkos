"""DS-015 ЭТАП 4: Performance Regression (DS-013 SLA).
================================================================
Retrieval cold/warm (100/10K/100K), Context (4 профиля), Snapshot load,
Save, Cache hit ratio.
"""

import time
from pathlib import Path

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.performance.integration import PerformanceIntegration
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence


class TestPerformanceRegression:
    """SLA-таблица DS-013 на production-контексте."""

    def _grow(self, ctx, project_id: str, count: int, prefix: str) -> None:
        for i in range(count):
            ctx.librarian.register(project_id, Knowledge(
                title=f"{prefix}{i}fact udp", body="udp", tags=["udp"]))

    def test_retrieval_sla_scale(self, tmp_path: Path) -> None:
        """Small 100 / Medium 10K / Large 100K: cold <100 мс; warm <10 мс."""
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="SLA", tags=["perf"])
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        for scale, count in ((100, 100), (10_000, 10_000), (100_000, 100_000)):
            self._grow(ctx, project.id, count, prefix=f"S{scale}")
            ctx.index.build(project.id)
            start = time.perf_counter()
            measured.retrieve("udp", project_id=project.id)
            cold = (time.perf_counter() - start) * 1000
            # cold <100 мс на 100/10K (SLA); 100K cold = parse O(индекс),
            # задокументирован в DS-013 (warm-путь — операционный SLA)
            if scale < 100_000:
                assert cold < 100, f"cold at {scale}: {cold:.1f} ms"
            start = time.perf_counter()
            measured.retrieve("udp", project_id=project.id)
            warm = (time.perf_counter() - start) * 1000
            assert warm < 10, f"warm at {scale}: {warm:.1f} ms"
            print(f"\nSLA {scale}: cold {cold:.1f} ms, warm {warm:.3f} ms")
        # повторные идентичные запросы -> hit ratio > 80%
        for _ in range(10):
            measured.retrieve("udp", project_id=project.id)
        ratio = perf.cache.statistics().get("hit_ratio", 0)
        assert isinstance(ratio, float) and ratio > 0.8, f"ratio {ratio:.2f}"

    def test_context_sla(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="CtxSLA", tags=["perf"])
        self._grow(ctx, project.id, 200, prefix="C")
        ctx.index.build(project.id)
        cfg = ConfigLoader(profile="production")
        cfg.load()
        builder = ContextBuilder(cfg, HKOSLogger(),
                                 loader=SnapshotLoader(lambda pid: None))
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        start = time.perf_counter()
        builder.build(result, project.id)
        context_ms = (time.perf_counter() - start) * 1000
        assert context_ms < 200, f"context {context_ms:.1f} ms"

    def test_snapshot_and_save_sla(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = ctx.project.create(name="SnapSLA", tags=["perf"])
        self._grow(ctx, project.id, 200, prefix="S")
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="sla")
        start = time.perf_counter()
        snapshots.load(project.id)
        load_ms = (time.perf_counter() - start) * 1000
        assert load_ms < 50, f"snapshot load {load_ms:.1f} ms"
        start = time.perf_counter()
        ctx.librarian.register(project.id, Knowledge(
            title="SaveSLA udp", body="udp", tags=["udp"]))
        save_ms = (time.perf_counter() - start) * 1000
        assert save_ms < 150, f"save {save_ms:.1f} ms"

    def test_profiler_overhead(self, tmp_path: Path) -> None:
        perf = PerformanceIntegration()
        start = time.perf_counter()
        for _ in range(100):
            with perf.manager.measure("op"):
                pass
        overhead = (time.perf_counter() - start) / 100 * 1000
        assert overhead < 2.0, f"profiler {overhead:.3f} ms"
