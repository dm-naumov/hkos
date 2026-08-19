"""System: рост памяти (DS-014 ЭТАП 3).
================================================================
1 проект x 100 кампаний x 10000 Knowledge (только через Librarian).

Проверки: регистрация; индекс обновлён; retrieval находит старые и
новые знания (C0K0/C50K50/C99K99); кампании не смешивают память;
performance метрики; масштабирование 100/1000/10000 (retrieval <100 мс).
"""

import time
from pathlib import Path

import pytest

from hkos.core.logger import HKOSLogger
from hkos.performance.integration import PerformanceIntegration
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_index_matches_repository,
    assert_performance_recorded,
    assert_retrievable,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestMemoryGrowthSystem:
    """Устойчивость инженерной памяти при росте (10K/100 кампаний)."""

    def _grow(self, ctx, snapshots, project_id: str, campaigns: int,
              per_campaign: int) -> None:
        campaign_ids = []
        for c in range(campaigns):
            campaign = ctx.campaigns.create(project_id, goal=f"growth-{c}")
            ctx.campaigns.open(project_id, campaign.id)
            ctx.campaigns.open(project_id, campaign.id)  # RUNNING
            campaign_ids.append(campaign.id)
        for c in range(campaigns):
            for k in range(per_campaign):
                ctx.librarian.register(project_id, Knowledge(
                    title=f"C{c}K{k}fact udp", body=f"body {c}-{k} udp",
                    tags=["udp"], source_campaign=campaign_ids[c]))
        ctx.index.build(project_id)
        snapshots.create(project_id, reason="growth")

    def test_memory_growth_10k(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "Growth10K", tags=["system"])
        self._grow(ctx, snapshots, project.id, campaigns=100, per_campaign=100)
        # все 10000 зарегистрированы (SSOT)
        assert ctx.repos.knowledge.count(project.id) == 10_000
        # индекс соответствует Repository
        assert_index_matches_repository(ctx, project.id)
        # выборочные знания retrievable: первое/среднее/последнее
        assert_retrievable(ctx, project.id, "C0K0fact", "C0K0fact")
        assert_retrievable(ctx, project.id, "C50K50fact", "C50K50fact")
        assert_retrievable(ctx, project.id, "C99K99fact", "C99K99fact")
        # кампании не смешивают память (контентная проверка)
        result = ctx.retrieval.retrieve("C0K0fact", project_id=project.id,
                                        campaign_id=self._campaign_of(ctx, project.id, 0))
        titles = [str(i.entity.title) for i in result.items]
        assert any("C0K0fact" in t for t in titles)

    def test_campaign_isolation(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "Isolation", tags=["system"])
        self._grow(ctx, snapshots, project.id, campaigns=5, per_campaign=20)
        campaign_0 = self._campaign_of(ctx, project.id, 0)
        result = ctx.retrieval.retrieve("C0K0fact", project_id=project.id,
                                        campaign_id=campaign_0)
        c0_titles = [str(i.entity.title) for i in result.items]
        assert any("C0K0fact" in t for t in c0_titles)
        # знания кампании 1 не входят в контекст кампании 0
        assert not any("C1K" in t for t in c0_titles)

    def test_performance_metrics_collected(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        project = project_factory(ctx, "PerfMetrics", tags=["system"])
        # небольшой корпус (метрики)
        for i in range(50):
            ctx.librarian.register(project.id, Knowledge(
                title=f"PM{i}fact udp", body="b", tags=["udp"]))
        ctx.index.build(project.id)
        measured.retrieve("udp", project_id=project.id)
        assert_performance_recorded(perf.manager, "retrieval")

    @pytest.mark.sla
    def test_retrieval_scaling(self, tmp_path: Path) -> None:
        """100/1000/10000: retrieval <100 мс; cache hit; контекст."""
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "Scaling", tags=["system"])
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        results = []
        for scale, per in ((100, 100), (1000, 1000), (10_000, 10_000)):
            self._grow_simple(ctx, project.id, per, prefix=f"S{scale}")
            ctx.index.build(project.id)
            start = time.perf_counter()
            measured.retrieve("udp", project_id=project.id)
            latency = (time.perf_counter() - start) * 1000
            results.append((scale, latency))
            assert latency < 100, f"retrieval at {scale}: {latency:.1f} ms"
        # cache hit на повторном запросе
        measured.retrieve("udp", project_id=project.id)
        ratio = perf.cache.statistics().get("hit_ratio", 0)
        assert isinstance(ratio, float) and ratio > 0
        print(f"\nscaling={results}")

    @staticmethod
    def _campaign_of(ctx, project_id: str, index: int) -> str:
        return ctx.campaigns.list(project_id)[index].id

    @staticmethod
    def _grow_simple(ctx, project_id: str, per: int, prefix: str) -> None:
        for k in range(per):
            ctx.librarian.register(project_id, Knowledge(
                title=f"{prefix}K{k}fact udp", body="b", tags=["udp"]))
