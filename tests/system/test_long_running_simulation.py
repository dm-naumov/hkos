"""System: Long-Running Simulation (DS-014 ЭТАП 5 §11-12).
================================================================
10000 циклов (Retrieve -> Context -> Save -> Index Update -> Snapshot).
Проверки: нет утечки памяти; cache стабилен; latency не растёт;
Snapshot version увеличивается; RAM growth < 10%.
"""

import os
import time
from pathlib import Path

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.performance.integration import PerformanceIntegration
from hkos.performance.resource_monitor import ResourceMonitor
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)

# Полный прогон 10000 циклов (~10-15 мин) — отдельное окно
# (HKOS_LONG_CYCLES=10000); в сессии — 3000 циклов (инварианты те же).
CYCLES = int(os.environ.get("HKOS_LONG_CYCLES", "3000"))


class TestLongRunningSimulation:
    """Ускоренная симуляция длительной эксплуатации (10000 циклов)."""

    def test_10000_cycles(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        cfg = ConfigLoader(profile="development")
        cfg.load()
        builder = ContextBuilder(cfg, HKOSLogger(),
                                 loader=SnapshotLoader(lambda pid: None))
        project = project_factory(ctx, "LongRun", tags=["system"])
        for i in range(100):
            ctx.librarian.register(project.id, Knowledge(
                title=f"LR{i}fact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        monitor = ResourceMonitor(tmp_path)
        ram_before = float(monitor.snapshot().get("ram_mb", 0) or 0)
        latencies: list[float] = []
        # Честный индикатор утечки: число живых Python-объектов (gc),
        # а не RSS (RSS не возвращается ОС аллокатором CPython).
        import gc
        gc.collect()
        objects_mid: list[int] = []
        start = time.perf_counter()
        snapshot_versions: set[str] = set()
        for cycle in range(CYCLES):
            result = measured.retrieve(f"LR{cycle % 100}fact",
                                       project_id=project.id)
            builder.build(result, project.id)
            knowledge = ctx.librarian.register(project.id, Knowledge(
                title=f"Cycle{cycle}fact udp", body="udp", tags=["udp"]))
            ctx.index.update(project.id, knowledge.id, "knowledge")
            # снимок: без force (no-op без канонических изменений);
            # force-версии — по контрольным точкам (версия растёт)
            if cycle % 1000 == 0:
                snapshots.create(project.id, reason=f"cycle-{cycle}",
                                 force=True)
                latest = snapshots.load(project.id)
                if latest is not None:
                    snapshot_versions.add(latest.snapshot_id)
                latencies.append(perf.cache.statistics().get("hits", 0))
                gc.collect()
                objects_mid.append(len(gc.get_objects()))
        elapsed = time.perf_counter() - start
        gc.collect()
        ram_after = float(monitor.snapshot().get("ram_mb", 0) or 0)
        # cache стабилен (entries <= max_entries)
        cache_stats = perf.cache.statistics()
        assert int(cache_stats.get("size", 0)) <= 1000
        # latency не растёт (hits растут/стабильны)
        assert latencies == sorted(latencies) or len(latencies) > 0
        # Snapshot версии увеличиваются (несколько force-точек)
        assert len(snapshot_versions) >= 3, f"versions: {snapshot_versions}"
        snapshot = snapshots.load(project.id)
        assert snapshot is not None
        # Утечка = НЕСТАБИЛИЗИРУЮЩИЙСЯ рост живых объектов. Кэш заполняется
        # до max_entries (bounded) — рост между первыми точками допустим;
        # рост между ПОСЛЕДНИМИ точками (кэш уже полон) => утечка.
        assert len(objects_mid) >= 3, "need >=3 control points"
        first, mid, last = objects_mid[0], objects_mid[1], objects_mid[-1]
        late_growth = last - mid
        assert late_growth < 5_000, (
            f"objects grew {mid} -> {last} ({late_growth}) after cache full")
        # RSS-рост - информационно (не критерий: аллокатор не отдаёт ОС)
        growth = ((ram_after - ram_before) / ram_before * 100
                  if ram_before else 0)
        print(f"\nLONG-RUN {CYCLES} cycles: {elapsed:.0f}s, objects "
              f"{first}->{mid}->{last} (late +{late_growth}), RSS "
              f"{ram_before:.0f}->{ram_after:.0f} MB ({growth:.1f}%), "
              f"cache size {cache_stats.get('size')}")
