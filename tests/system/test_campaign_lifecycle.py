"""System: жизненный цикл кампании (DS-014 ЭТАП 2).
================================================================
START (CREATED) -> READY -> RUNNING -> PAUSED -> RUNNING -> COMPLETED
-> REOPEN (новая кампания со старым контекстом).

Проверки: FSM корректен; память кампании сохраняется; повторное
открытие использует старый контекст; нет потери знаний.
"""

from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.assertions import assert_retrievable
from tests.system.fixtures import create_system_context, project_factory


class TestCampaignLifecycleSystem:
    """Полный жизненный цикл кампании (публичный FSM API)."""

    def _campaign(self, ctx, project_id: str, goal: str):
        campaign = ctx.campaigns.create(project_id, goal=goal)
        return campaign

    def test_fsm_transitions(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "FSM")
        campaign = self._campaign(ctx, project.id, "fsm-goal")
        assert campaign.status == "CREATED"
        # START -> READY -> RUNNING
        ctx.campaigns.open(project.id, campaign.id)
        assert ctx.campaigns.status(project.id, campaign.id).state == "READY"
        ctx.campaigns.open(project.id, campaign.id)
        assert ctx.campaigns.status(project.id, campaign.id).state == "RUNNING"
        # RUNNING -> PAUSED -> RUNNING
        ctx.campaigns.pause(project.id, campaign.id)
        assert ctx.campaigns.status(project.id, campaign.id).state == "PAUSED"
        ctx.campaigns.resume(project.id, campaign.id)
        assert ctx.campaigns.status(project.id, campaign.id).state == "RUNNING"
        # RUNNING -> COMPLETED
        ctx.campaigns.close(project.id, campaign.id)
        assert ctx.campaigns.status(project.id, campaign.id).state == "COMPLETED"

    def test_campaign_memory_preserved(self, tmp_path: Path) -> None:
        """Память кампании сохраняется на всех стадиях (нет потери)."""
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "Memory")
        campaign = self._campaign(ctx, project.id, "mem-goal")
        ctx.campaigns.open(project.id, campaign.id)
        ctx.campaigns.open(project.id, campaign.id)   # RUNNING
        knowledge = ctx.librarian.register(project.id, Knowledge(
            title="CampaignFact udp", body="udp", tags=["udp"],
            source_campaign=campaign.id))
        ctx.index.build(project.id)
        # знание доступно на RUNNING
        assert_retrievable(ctx, project.id, "CampaignFact", "CampaignFact")
        # PAUSED: знание сохраняется
        ctx.campaigns.pause(project.id, campaign.id)
        assert_retrievable(ctx, project.id, "CampaignFact", "CampaignFact")
        # COMPLETED: знание сохраняется
        ctx.campaigns.resume(project.id, campaign.id)
        ctx.campaigns.close(project.id, campaign.id)
        assert_retrievable(ctx, project.id, "CampaignFact", "CampaignFact")
        assert ctx.repos.knowledge.exists(project.id, knowledge.id)

    def test_reopen_uses_old_context(self, tmp_path: Path) -> None:
        """Повторное открытие (новая кампания) видит старый контекст."""
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "Reopen")
        first = self._campaign(ctx, project.id, "first-goal")
        ctx.campaigns.open(project.id, first.id)
        ctx.campaigns.open(project.id, first.id)
        ctx.librarian.register(project.id, Knowledge(
            title="OldContextFact udp", body="udp", tags=["udp"],
            source_campaign=first.id))
        ctx.index.build(project.id)
        ctx.campaigns.close(project.id, first.id)
        # REOPEN: новая кампания в том же проекте
        reopened = self._campaign(ctx, project.id, "reopen-goal")
        ctx.campaigns.open(project.id, reopened.id)
        ctx.campaigns.open(project.id, reopened.id)
        # старый контекст доступен (общая память проекта)
        assert_retrievable(ctx, project.id, "OldContextFact", "OldContextFact")
        # новое знание в новой кампании — тоже (индекс обновлён)
        new_knowledge = ctx.librarian.register(project.id, Knowledge(
            title="NewContextFact udp", body="udp", tags=["udp"],
            source_campaign=reopened.id))
        ctx.index.update(project.id, new_knowledge.id, "knowledge")
        assert_retrievable(ctx, project.id, "NewContextFact", "NewContextFact")
