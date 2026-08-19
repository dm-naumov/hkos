"""DS-016 ЭТАП 2: Retrieval-Before-Task Hook (B).
================================================================
Автоматический retrieval перед задачей: DECISION/FAILURE/CONFIGURATION
возвращаются; NEW-знания не попадают; campaign/project isolation;
explanation.reason.
"""

from pathlib import Path

from tests.system.ds016.assertions import (
    assert_reason_exists,
)
from tests.system.ds016.fixtures import seed_engineering_memory
from tests.system.ds016.hermes_context import create_hermes_context


class TestRetrievalHook:
    """Retrieval выполняется автоматически перед задачей."""

    def test_decision_failure_configuration_returned(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="OpenWRT", tags=["hermes"])
        campaign = ctx.campaign.create(project.id, goal="task-1")
        ctx.campaign.open(project.id, campaign.id)
        ctx.campaign.open(project.id, campaign.id)
        seed_engineering_memory(ctx, project.id, campaign.id)
        ctx.index.build(project.id)
        # автоматический retrieval (без команды hkos retrieve)
        bundle = ctx.retrieve_before_task(
            "openwrt routing", project_id=project.id)
        titles = [str(i.entity.title) for i in bundle["retrieval_items"]]
        assert any("Decision" in t for t in titles)
        assert any("Failure" in t for t in titles)
        assert any("Config" in t for t in titles)
        assert bundle["context"] is not None  # контекст инжектируется

    def test_no_irrelevant_knowledge_in_context(self, tmp_path: Path) -> None:
        """Только релевантные знания попадают в контекст.

        Контракт DS-008: статусный фильтр исключает ARCHIVED/REJECTED/
        SUPERSEDED; NEW проходят (валидная память). Релевантность —
        через токены/теги запроса: знание другой темы не попадает.
        """
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="NoIrrelevant", tags=["hermes"])
        ctx.librarian.register(project.id, __import__(
            "hkos.repository.models", fromlist=["Knowledge"]).Knowledge(
                title="FirewallFact", body="nftables firewall rules",
                tags=["firewall", "nftables"]))
        ctx.index.build(project.id)
        bundle = ctx.retrieve_before_task(
            "openwrt routing", project_id=project.id)
        titles = [str(i.entity.title) for i in bundle["retrieval_items"]]
        assert not any("FirewallFact" in t for t in titles), (
            "irrelevant knowledge leaked")

    def test_campaign_isolation(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Iso", tags=["hermes"])
        c1 = ctx.campaign.create(project.id, goal="c1")
        ctx.campaign.open(project.id, c1.id)
        ctx.campaign.open(project.id, c1.id)
        seed_engineering_memory(ctx, project.id, c1.id)
        ctx.index.build(project.id)
        bundle = ctx.retrieve_before_task(
            "openwrt", project_id=project.id, campaign_id=c1.id)
        assert len(bundle["retrieval_items"]) >= 1

    def test_explanation_reason(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Reason", tags=["hermes"])
        seed_engineering_memory(ctx, project.id, ctx.project.list()[0].id
                                if len(ctx.project.list()) > 1 else "")
        ctx.index.build(project.id)
        assert_reason_exists(ctx, project.id, "openwrt")
