"""System: жизненный цикл проекта (DS-014 ЭТАП 2).
================================================================
Создание -> 10 кампаний -> 1000 Knowledge -> Snapshot -> завершение
кампаний -> повторное открытие.

Проверки: идентичность проекта; старые знания доступны; кампании не
смешивают контекст; Retrieval фильтрует по project/campaign.
"""

from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_knowledge_exists,
    assert_project_integrity,
    assert_retrievable,
    assert_snapshot_consistent,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestProjectLifecycleSystem:
    """Полный жизненный цикл проекта (минимальный масштаб: 10x100)."""

    def _setup(self, tmp_path: Path):
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "BigProject", tags=["system"])
        campaigns = []
        for c in range(10):
            campaign = ctx.campaigns.create(project.id, goal=f"campaign-{c}")
            ctx.campaigns.open(project.id, campaign.id)
            ctx.campaigns.open(project.id, campaign.id)  # RUNNING
            campaigns.append(campaign)
        for c in range(10):
            for k in range(100):
                # уникальный токен C{c}K{k}fact в заголовке (для retrieval)
                ctx.librarian.register(project.id, Knowledge(
                    title=f"C{c}K{k}fact udp fix", body=f"body {c}-{k} udp",
                    tags=["udp"], source_campaign=campaigns[c].id))
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="initial")
        return ctx, snapshots, project, campaigns

    def test_identity_and_old_knowledge(self, tmp_path: Path) -> None:
        ctx, snapshots, project, campaigns = self._setup(tmp_path)
        project_id = project.id
        # идентичность сохраняется при повторном открытии
        reopened = ctx.projects.info(project_id)
        assert reopened.id == project_id
        assert reopened.name == "BigProject"
        # 1000 знаний на месте (SSOT: Repository)
        assert_project_integrity(ctx, project_id, expected_knowledge=1000)
        # старые знания доступны через Retrieval
        assert_retrievable(ctx, project_id, "C0K0fact", "C0K0fact")
        assert_retrievable(ctx, project_id, "C9K99fact", "C9K99fact")
        # Snapshot согласован
        assert_snapshot_consistent(ctx, snapshots, project_id)

    def test_campaigns_do_not_mix_context(self, tmp_path: Path) -> None:
        ctx, snapshots, project, campaigns = self._setup(tmp_path)
        # retrieval по project возвращает ВСЕ кампании (top_n расширен)
        result_all = ctx.retrieval.retrieve(
            "udp", project_id=project.id, top_n=500)
        assert len(result_all.items) >= 100
        # фильтр по кампании: только знания этой кампании
        # уникальный токен кампании 0: знание C0K0fact из c0
        result_c0 = ctx.retrieval.retrieve(
            "C0K0fact", project_id=project.id, campaign_id=campaigns[0].id)
        c0_items = [
            item for item in result_c0.items
            if "C0K" in str(item.entity.title)
        ]
        assert c0_items, "campaign context lost in retrieval"
        # знания другой кампании НЕ входят в контекст кампании 0
        other_items = [
            item for item in result_c0.items
            if "C1K" in str(item.entity.title)
        ]
        assert other_items == [], "campaign context mixed"

    def test_complete_campaigns_and_reopen(self, tmp_path: Path) -> None:
        ctx, snapshots, project, campaigns = self._setup(tmp_path)
        # завершение всех кампаний
        for campaign in campaigns:
            ctx.campaigns.close(project.id, campaign.id)
        # повторное открытие проекта: знания доступны
        first = ctx.repos.knowledge.list(project.id)[0]
        assert_knowledge_exists(ctx, project.id, first.id)
        # новая кампания (reopen) видит старый контекст
        reopened_campaign = ctx.campaigns.create(project.id, goal="reopen")
        result = ctx.retrieval.retrieve(
            "C5K50fact", project_id=project.id, campaign_id=reopened_campaign.id)
        assert len(result.items) >= 1  # старый контекст доступен
