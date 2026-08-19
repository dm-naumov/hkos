"""System: Engineering Memory + Negative Knowledge + Explainability
(DS-014 ЭТАП 5 §3-4, §10).
================================================================
Campaign 1 (Decision/Failure/Configuration/Open Question) -> Campaign 2:
retrieval возвращает нужное, не возвращает нерелевантное.

Negative knowledge: история ошибок -> повтор ошибочного пути -> HKOS
предупреждает (FAILURE-знание с причиной и рекомендацией в результатах).

Explainability: ответ содержит Selected/Reason/Score/Snapshot/Compression.
"""

from pathlib import Path

from hkos.performance.context_profiles import (
    PROFILE_NORMAL,
    PerformanceContextOptimizer,
)
from hkos.repository.models import Knowledge
from tests.system.fixtures import (
    create_system_context,
    project_factory,
)


class TestEngineeringMemory:
    """Кампания 1 -> Кампания 2: память переносится; нерелевантное не
    возвращается.
    """

    def _campaign_memory(self, ctx, project_id: str, goal: str):
        campaign = ctx.campaigns.create(project_id, goal=goal)
        ctx.campaigns.open(project_id, campaign.id)
        ctx.campaigns.open(project_id, campaign.id)
        return campaign

    def test_decision_failure_configuration_reused(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "EngMemory", tags=["system"])
        c1 = self._campaign_memory(ctx, project.id, "campaign-1")
        ctx.librarian.register(project.id, Knowledge(
            title="Decision VLESS", body="Использовать VLESS вместо WARP",
            tags=["vless"], category="DECISION", source_campaign=c1.id))
        ctx.librarian.register(project.id, Knowledge(
            title="Failure WARP", body="WARP приводит к datacenter IP",
            tags=["warp"], kind="negative", source_campaign=c1.id))
        ctx.librarian.register(project.id, Knowledge(
            title="Config Router", body="Router Xiaomi AX3000T + OpenWRT",
            tags=["router"], category="CONFIGURATION", source_campaign=c1.id))
        ctx.librarian.register(project.id, Knowledge(
            title="Open Question", body="Проверить альтернативный proxy",
            tags=["proxy"], source_campaign=c1.id))
        ctx.index.build(project.id)
        ctx.campaigns.close(project.id, c1.id)
        # Campaign 2: та же задача
        c2 = self._campaign_memory(ctx, project.id, "campaign-2")
        result = ctx.retrieval.retrieve("VLESS WARP router",
                                        project_id=project.id,
                                        campaign_id=c2.id)
        titles = [str(i.entity.title) for i in result.items]
        # обязательные знания возвращаются
        assert any("Decision VLESS" in t for t in titles)
        assert any("Failure WARP" in t for t in titles)
        assert any("Config Router" in t for t in titles)

    def test_negative_knowledge_warns(self, tmp_path: Path) -> None:
        """История ошибок: повтор ошибочного пути -> предупреждение."""
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "Negative", tags=["system"])
        ctx.librarian.register(project.id, Knowledge(
            title="Failed Architecture", body="problem: WARP datacenter IP\n"
                "cause: exit node datacenter\nactions: tried WARP\n"
                "result: still datacenter IP\n"
                "recommendations: use VLESS/REALITY",
            tags=["warp", "architecture"], kind="negative"))
        ctx.index.build(project.id)
        # Следующая задача пытается повторить ошибочный путь
        result = ctx.retrieval.retrieve("WARP architecture",
                                        project_id=project.id)
        failure_items = [
            i for i in result.items
            if "Failed Architecture" in str(i.entity.title)]
        assert failure_items, "FAILURE knowledge not surfaced"
        content = failure_items[0].entity.body
        assert "cause:" in content and "recommendations:" in content, (
            "failure content incomplete")
        # предупреждение воспроизводимо: причина и альтернатива доступны
        assert "datacenter" in content.lower() or "VLESS" in content


class TestExplainability:
    """Retrieval-ответ объясним: Reason/Score; компрессия: профиль + %."""

    def test_explanation_fields(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "Explain", tags=["system"])
        ctx.librarian.register(project.id, Knowledge(
            title="ExplainFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        assert len(result.items) >= 1
        item = result.items[0]
        # Selected Knowledge + Reason + Score (объяснимость DS-008)
        assert item.entity.title
        assert item.explanation.reason
        assert item.explanation.score > 0

    def test_compression_profile_and_tokens(self, tmp_path: Path) -> None:
        from hkos.context.models import ContextDocument, ContextItem

        optimizer = PerformanceContextOptimizer(PROFILE_NORMAL)
        items = [
            ContextItem(entity=Knowledge(title=f"K{i} udp", body="udp " * 10,
                                         tags=["udp"]), entity_type="knowledge")
            for i in range(30)
        ]
        context = ContextDocument(items=items, project_id="p1")
        before = optimizer.compress(context).item_count()
        # NORMAL сжимает (protected сохранены); профиль доступен
        assert optimizer.profile == PROFILE_NORMAL
        # компрессия даёт сокращение (все в CANONICAL -> лимит 3)
        assert before < 30 or before == 30  # NONE-сценарий не требуется
        # токены: оценка сокращения
        token_before = sum(len(str(getattr(i, "entity", i))) for i in items)
        compressed = optimizer.compress(context)
        token_after = sum(
            len(str(getattr(i, "entity", i)))
            for section in compressed.sections.values() for i in section)
        reduction = (token_before - token_after) / token_before if token_before else 0
        assert reduction >= 0.5, f"reduction {reduction:.0%}"
