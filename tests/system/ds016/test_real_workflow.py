"""DS-016 ЭТАП 3.1: Real Hermes Workflow Validation.
================================================================
User task -> Hermes startup -> retrieve_before_task -> Context injection
-> Agent execution (mock LLM) -> save_after_task -> Repository -> Index
-> Snapshot -> Future retrieval.
"""

from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context


class TestRealWorkflow:
    """Полный агентный цикл: OpenWRT Multi Agent Router."""

    def test_full_hermes_cycle(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        # Hermes startup
        ctx.hooks.startup()
        project = ctx.project.create(name="OpenWRT Multi Agent Router",
                                     tags=["openwrt"])
        # Campaign 1: "Initial deployment"
        c1 = ctx.campaign.create(project.id, goal="Initial deployment")
        ctx.campaign.open(project.id, c1.id)
        ctx.campaign.open(project.id, c1.id)
        # DECISION'ы
        ctx.save_after_task(project.id, Knowledge(
            title="Decision OpenWRT", body="Использовать OpenWRT",
            tags=["openwrt", "udp"], category="DECISION"))
        ctx.save_after_task(project.id, Knowledge(
            title="Decision Podkop", body="Использовать Podkop",
            tags=["podkop", "udp"], category="DECISION"))
        ctx.save_after_task(project.id, Knowledge(
            title="Decision VLESS", body="VLESS routing",
            tags=["vless", "udp"], category="DECISION"))
        ctx.save_after_task(project.id, Knowledge(
            title="Decision Users", body="отдельные правила пользователей",
            tags=["users", "udp"], category="DECISION"))
        # CONFIGURATION
        ctx.save_after_task(project.id, Knowledge(
            title="Config Router", body="Xiaomi AX3000T",
            tags=["router", "udp"], category="CONFIGURATION"))
        ctx.save_after_task(project.id, Knowledge(
            title="Config Version", body="OpenWRT 25.12.5",
            tags=["openwrt", "udp"], category="CONFIGURATION"))
        ctx.save_after_task(project.id, Knowledge(
            title="Config Topology", body="lan=10.10.0.0/24, tun=tun0",
            tags=["topology", "udp"], category="CONFIGURATION"))
        # FAILURE
        ctx.save_after_task(project.id, Knowledge(
            title="Failure Warp", body="cause: WARP использует datacenter IP\n"
                "recommendations: использовать другой routing strategy",
            tags=["warp", "udp"], kind="negative"))
        ctx.save_after_task(project.id, Knowledge(
            title="Failure Akamai", body="cause: Akamai блокирует\n"
                "recommendations: другой routing strategy",
            tags=["akamai", "udp"], kind="negative"))
        ctx.index.build(project.id)
        ctx.snapshots.create(project.id, reason="c1")
        ctx.campaign.close(project.id, c1.id)
        # Campaign 2: "Continue OpenWRT project"
        c2 = ctx.campaign.create(project.id, goal="Continue OpenWRT project")
        ctx.campaign.open(project.id, c2.id)
        ctx.campaign.open(project.id, c2.id)
        bundle = ctx.retrieve_before_task(
            "openwrt routing", project_id=project.id, campaign_id=c2.id)
        titles = [str(i.entity.title) for i in bundle["retrieval_items"]]
        # предыдущие решения
        assert any("Decision" in t for t in titles)
        # конфигурации
        assert any("Config" in t for t in titles)
        # failures
        assert any("Failure" in t for t in titles)
        # explanation.reason существует
        assert bundle["retrieval_items"][0].explanation.reason
        # память: 9 сохранённых знаний
        assert ctx.repos.knowledge.count(project.id) == 9
        # snapshot согласован
        snapshot = ctx.snapshots.load(project.id)
        assert int(snapshot.statistics.get("knowledge", 0)) == 9
