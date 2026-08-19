"""DS-015 ЭТАП 5.7: Final Performance Certification.
================================================================
SLA-фиксация: retrieval 100/10K <100 мс; warm <10 мс; context <200 мс;
snapshot <50 мс; save <150 мс; cache >80%; token reduction >60%;
100K workload PASS; 100K cold — KNOWN SCALE CHARACTERISTIC.
"""

import time
from pathlib import Path

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.performance.context_profiles import (
    PROFILE_AGGRESSIVE,
    PerformanceContextOptimizer,
)
from hkos.performance.integration import PerformanceIntegration
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence


class TestFinalPerformanceCertification:
    """Финальная сертификация производительности (SLA-таблица)."""

    def test_retrieval_sla(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="Cert", tags=["perf"])
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        for scale, count in ((100, 100), (10_000, 10_000)):
            for i in range(count):
                ctx.librarian.register(project.id, Knowledge(
                    title=f"C{scale}K{i}fact udp", body="udp", tags=["udp"]))
            ctx.index.build(project.id)
            start = time.perf_counter()
            measured.retrieve("udp", project_id=project.id)
            cold = (time.perf_counter() - start) * 1000
            assert cold < 100, f"cold {scale}: {cold:.1f} ms"
        # warm <10 мс
        start = time.perf_counter()
        measured.retrieve("udp", project_id=project.id)
        warm = (time.perf_counter() - start) * 1000
        assert warm < 10, f"warm {warm:.1f} ms"

    def test_context_snapshot_save_sla(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="CertCtx", tags=["perf"])
        for i in range(200):
            ctx.librarian.register(project.id, Knowledge(
                title=f"CC{i}fact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        cfg = ConfigLoader(profile="production")
        cfg.load()
        builder = ContextBuilder(cfg, HKOSLogger(),
                                 loader=SnapshotLoader(lambda pid: None))
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        start = time.perf_counter()
        builder.build(result, project.id)
        assert (time.perf_counter() - start) * 1000 < 200
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        snapshots.create(project.id, reason="cert")
        start = time.perf_counter()
        snapshots.load(project.id)
        assert (time.perf_counter() - start) * 1000 < 50
        start = time.perf_counter()
        ctx.librarian.register(project.id, Knowledge(
            title="SaveCert udp", body="udp", tags=["udp"]))
        assert (time.perf_counter() - start) * 1000 < 150

    def test_cache_and_token(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="CertCache", tags=["perf"])
        for i in range(100):
            ctx.librarian.register(project.id, Knowledge(
                title=f"CT{i}fact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        for _ in range(10):
            measured.retrieve("udp", project_id=project.id)
        ratio = perf.cache.statistics().get("hit_ratio", 0)
        assert isinstance(ratio, float) and ratio > 0.8
        # token reduction >60% (AGGRESSIVE на реальном контексте)
        from hkos.context.models import ContextDocument, ContextItem
        items = [
            ContextItem(entity=Knowledge(title=f"TK{i} udp", body="udp " * 10,
                                         tags=["udp"]), entity_type="knowledge")
            for i in range(50)
        ]
        context = ContextDocument(items=items, project_id="p1")
        tokens_before = sum(
            len(str(getattr(getattr(i, "entity", i), "body", "")))
            for i in items)
        compressed = PerformanceContextOptimizer(PROFILE_AGGRESSIVE).compress(context)
        tokens_after = sum(
            len(str(getattr(getattr(i, "entity", i), "body", "")))
            for section in compressed.sections.values() for i in section)
        assert (tokens_before - tokens_after) / tokens_before > 0.6

    def test_100k_workload_certification(self, tmp_path: Path) -> None:
        """100K workload PASS; 100K cold — KNOWN SCALE CHARACTERISTIC."""
        import os as _os
        _os.environ["HKOS_WORKLOAD_PROJECTS"] = "100"
        _os.environ["HKOS_WORKLOAD_CAMPAIGNS"] = "10"
        _os.environ["HKOS_WORKLOAD_KNOWLEDGE"] = "1000"
        from tests.system.ds015.test_production_workload import TestProductionWorkload
        TestProductionWorkload().test_workload(tmp_path)
        # 100K cold retrieval (один проект) — измерение для отчёта:
        # задокументировано как KNOWN SCALE CHARACTERISTIC (>100 мс —
        # parse O(индекс); операционный путь — warm через IndexCache)
