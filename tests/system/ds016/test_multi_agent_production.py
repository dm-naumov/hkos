"""DS-016 ЭТАП 3.2: Multi-Agent Qualification.
================================================================
Planner (DECISION) -> Executor (CONFIGURATION, использует память
Planner) -> Reviewer (FAILURE, использует обе памяти). Общий проект.
Нет потери; нет пересечения кампаний; нет дубликатов; счётчики сходятся.
"""

from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context


class TestMultiAgentProduction:
    """Planner/Executor/Reviewer на общей памяти HKOS."""

    def test_three_agent_pipeline(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="OpenWRT", tags=["hermes"])
        # Planner: DECISION (архитектура сети)
        planner_c = ctx.campaign.create(project.id, goal="planner")
        ctx.campaign.open(project.id, planner_c.id)
        ctx.campaign.open(project.id, planner_c.id)
        ctx.save_after_task(project.id, Knowledge(
            title="Planner Decision", body="архитектура: policy routing",
            tags=["openwrt", "udp"], category="DECISION"))
        ctx.index.build(project.id)
        # Executor: получает память Planner, создаёт CONFIGURATION
        executor_c = ctx.campaign.create(project.id, goal="executor")
        ctx.campaign.open(project.id, executor_c.id)
        ctx.campaign.open(project.id, executor_c.id)
        planner_memory = ctx.retrieve_before_task(
            "openwrt", project_id=project.id, campaign_id=executor_c.id)
        assert len(planner_memory["retrieval_items"]) >= 1
        ctx.save_after_task(project.id, Knowledge(
            title="Executor Config", body="lan=192.168.1.0/24",
            tags=["openwrt", "udp"], category="CONFIGURATION"))
        ctx.index.update(project.id,
                         planner_memory["retrieval_items"][0].entity.id,
                         "knowledge")
        # Reviewer: получает обе памяти, создаёт FAILURE
        reviewer_c = ctx.campaign.create(project.id, goal="reviewer")
        ctx.campaign.open(project.id, reviewer_c.id)
        ctx.campaign.open(project.id, reviewer_c.id)
        both = ctx.retrieve_before_task(
            "openwrt", project_id=project.id, campaign_id=reviewer_c.id)
        assert len(both["retrieval_items"]) >= 2
        ctx.save_after_task(project.id, Knowledge(
            title="Reviewer Failure", body="cause: misconfig\n"
                "recommendations: fix routing",
            tags=["openwrt", "udp"], kind="negative"))
        # Проверки
        assert ctx.repos.knowledge.count(project.id) == 3  # нет потери
        ids = [k.id for k in ctx.repos.knowledge.list(project.id)]
        assert len(ids) == len(set(ids))                  # нет дубликатов
        ctx.index.rebuild(project.id)
        assert int(ctx.index.statistics(project.id).get("knowledge", 0)) == 3
        ctx.snapshots.create(project.id, reason="multi-agent", force=True)
        assert int(ctx.snapshots.load(project.id).statistics.get("knowledge", 0)) == 3
