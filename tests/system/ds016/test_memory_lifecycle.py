"""DS-016 ЭТАП 2: Memory Lifecycle (G).
================================================================
Campaign 1 (OpenWRT: DECISION/CONFIGURATION/FAILURE) -> Task -> Save ->
Snapshot -> Campaign 2 -> Retrieval -> Reuse (Decision/Failure/Config).
Negative knowledge: повторение ошибочного пути -> FAILURE всплывает.
"""

from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context


class TestMemoryLifecycle:
    """Полный lifecycle памяти Hermes (Campaign 1 -> Campaign 2)."""

    def test_campaign2_reuses_campaign1_memory(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="OpenWRT", tags=["hermes"])
        # Campaign 1: задача "Настроить OpenWRT selective routing"
        c1 = ctx.campaign.create(project.id, goal="OpenWRT selective routing")
        ctx.campaign.open(project.id, c1.id)
        ctx.campaign.open(project.id, c1.id)
        ctx.save_after_task(project.id, Knowledge(
            title="Decision Route", body="использовать policy routing",
            tags=["openwrt", "routing", "udp"], category="DECISION"))
        ctx.save_after_task(project.id, Knowledge(
            title="Config Net", body="lan=192.168.1.0/24, tun=tun0",
            tags=["openwrt", "config", "udp"], category="CONFIGURATION"))
        ctx.save_after_task(project.id, Knowledge(
            title="Failure Rule", body="cause: неправильный routing rule\n"
                "recommendations: policy routing",
            tags=["openwrt", "routing", "udp"], kind="negative"))
        ctx.index.build(project.id)
        ctx.snapshots.create(project.id, reason="c1")
        ctx.campaign.close(project.id, c1.id)
        # Campaign 2: "Продолжить настройку OpenWRT"
        c2 = ctx.campaign.create(project.id, goal="продолжить OpenWRT")
        ctx.campaign.open(project.id, c2.id)
        ctx.campaign.open(project.id, c2.id)
        bundle = ctx.retrieve_before_task(
            "openwrt routing", project_id=project.id, campaign_id=c2.id)
        titles = [str(i.entity.title) for i in bundle["retrieval_items"]]
        # прошлые решения/ограничения/ошибки/рекомендации
        assert any("Decision" in t for t in titles)
        assert any("Failure" in t for t in titles)
        assert any("Config" in t for t in titles)
        # explanation.reason существует
        assert bundle["retrieval_items"][0].explanation.reason

    def test_failure_recall(self, tmp_path: Path) -> None:
        """Campaign 2 повторяет ошибку -> FAILURE всплывает с причиной."""
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="FailRecall", tags=["hermes"])
        ctx.save_after_task(project.id, Knowledge(
            title="OldFailure", body="cause: WARP datacenter IP\n"
                "recommendations: use VLESS/REALITY",
            tags=["warp", "udp"], kind="negative"))
        ctx.index.build(project.id)
        # повторение ошибочного пути
        bundle = ctx.retrieve_before_task(
            "warp", project_id=project.id)
        failures = [i for i in bundle["retrieval_items"]
                    if "OldFailure" in str(i.entity.title)]
        assert failures, "FAILURE not surfaced"
        assert "cause:" in failures[0].entity.body
        assert "VLESS" in failures[0].entity.body
        assert failures[0].explanation.reason
