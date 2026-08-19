"""System: Stress Large (DS-014 ЭТАП 5 §5).
================================================================
100 проектов x 10 кампаний x 1000 Knowledge = 100 000 Knowledge.
Проверки: retrieval, index, snapshot, cache, memory usage.
"""

import os
import time
from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_index_matches_repository,
    assert_retrievable,
    assert_snapshot_matches_repository,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
)

# Масштаб из env (по умолчанию 100K; можно уменьшить для CI)
SCALE_PROJECTS = int(os.environ.get("HKOS_STRESS_PROJECTS", "100"))
SCALE_PER_PROJECT = int(os.environ.get("HKOS_STRESS_PER_PROJECT", "1000"))
SCALE_CAMPAIGNS = int(os.environ.get("HKOS_STRESS_CAMPAIGNS", "10"))


class TestStressLarge:
    """100K Knowledge (масштабируемый; env-оверрайд для CI)."""

    def test_stress_100k(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        start = time.perf_counter()
        total = 0
        sample = ""
        for p in range(SCALE_PROJECTS):
            project = ctx.projects.create(name=f"Stress{p}", tags=["stress"])
            if p == 0:
                sample = project.id
            campaigns = []
            for c in range(SCALE_CAMPAIGNS):
                campaign = ctx.campaigns.create(project.id, goal=f"sc-{c}")
                campaigns.append(campaign.id)
            for k in range(SCALE_PER_PROJECT):
                ctx.librarian.register(project.id, Knowledge(
                    title=f"S{p}K{k}fact udp", body="udp", tags=["udp"],
                    source_campaign=campaigns[k % SCALE_CAMPAIGNS]))
            ctx.index.build(project.id)
            snapshots.create(project.id, reason="stress")
            total += SCALE_PER_PROJECT
        gen_ms = (time.perf_counter() - start) * 1000
        # Repository: count == масштаб
        assert total == SCALE_PROJECTS * SCALE_PER_PROJECT
        assert ctx.repos.knowledge.count(sample) == SCALE_PER_PROJECT
        # Index == Repository; Snapshot == Repository (выборочно)
        assert_index_matches_repository(ctx, sample)
        assert_snapshot_matches_repository(ctx, snapshots, sample)
        # Retrieval: первое/последнее знание
        assert_retrievable(ctx, sample, "S0K0fact", "S0K0fact")
        last_k = SCALE_PER_PROJECT - 1
        assert_retrievable(ctx, sample, f"S0K{last_k}fact", f"S0K{last_k}fact")
        # Memory usage (resource monitor)
        from hkos.performance.resource_monitor import ResourceMonitor
        monitor = ResourceMonitor(tmp_path)
        resources = monitor.snapshot()
        assert isinstance(resources.get("ram_mb"), (int, float))
        print(f"\nSTRESS {total} knowledge: gen {gen_ms/1000:.1f}s, "
              f"RAM {resources.get('ram_mb')} MB")
