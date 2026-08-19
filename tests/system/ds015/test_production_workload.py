"""DS-015 ЭТАП 4: Production Workload Simulation.
================================================================
100 проектов / 1000 кампаний / 100000 Knowledge. Repository/Index/
Snapshot count; retrieval первых/последних; RAM/CPU метрики.
"""

import os
import time
from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence

PROJECTS = int(os.environ.get("HKOS_WORKLOAD_PROJECTS", "100"))
CAMPAIGNS_PER = int(os.environ.get("HKOS_WORKLOAD_CAMPAIGNS", "10"))
KNOWLEDGE_PER = int(os.environ.get("HKOS_WORKLOAD_KNOWLEDGE", "1000"))


class TestProductionWorkload:
    """Имитация production-нагрузки (100K по умолчанию)."""

    def test_workload(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        start = time.perf_counter()
        sample = ""
        for p in range(PROJECTS):
            project = ctx.project.create(name=f"W{p}", tags=["workload"])
            if p == 0:
                sample = project.id
            campaigns = []
            for c in range(CAMPAIGNS_PER):
                campaign = ctx.campaign.create(project.id, goal=f"wc-{c}")
                campaigns.append(campaign.id)
            for k in range(KNOWLEDGE_PER):
                ctx.librarian.register(project.id, Knowledge(
                    title=f"WK{k}fact udp", body="udp", tags=["udp"],
                    source_campaign=campaigns[k % CAMPAIGNS_PER]))
            ctx.index.build(project.id)
            snapshots.create(project.id, reason="workload")
        gen_s = time.perf_counter() - start
        # Repository count
        assert ctx.repos.knowledge.count(sample) == KNOWLEDGE_PER
        # Index count
        assert int(ctx.index.statistics(sample).get("knowledge", 0)) == KNOWLEDGE_PER
        # Snapshot count
        snapshot = snapshots.load(sample)
        assert snapshot is not None
        assert int(snapshot.statistics.get("knowledge", 0)) == KNOWLEDGE_PER
        # Retrieval первых/последних знаний
        for marker in ("WK0fact", f"WK{KNOWLEDGE_PER - 1}fact"):
            result = ctx.retrieval.retrieve(marker, project_id=sample)
            assert any(marker in str(i.entity.title) for i in result.items)
        # Метрики: RAM/CPU (информационно; корректные значения)
        from hkos.performance.resource_monitor import ResourceMonitor
        monitor = ResourceMonitor(tmp_path)
        resources = monitor.snapshot()
        ram = resources.get("ram_mb")
        assert isinstance(ram, (int, float)) and ram >= 0
        print(f"\nWORKLOAD {PROJECTS}x{CAMPAIGNS_PER}x{KNOWLEDGE_PER} "
              f"= {PROJECTS*KNOWLEDGE_PER} knowledge: gen {gen_s:.0f}s, "
              f"RAM {ram:.0f} MB")
