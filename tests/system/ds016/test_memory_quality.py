"""DS-016 ЭТАП 3.4: Memory Quality Validation.
================================================================
Positive reuse: Campaign 2 повторяет задачу -> DECISION всплывает.
Negative reuse: повтор ошибочного пути -> FAILURE первым (cause/
recommendations/reason).
"""

from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context


class TestMemoryQuality:
    """Качество памяти: позитивный и негативный reuse."""

    def test_positive_reuse_decision_surfaces(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Pos", tags=["hermes"])
        ctx.save_after_task(project.id, Knowledge(
            title="Decision Route", body="policy routing",
            tags=["openwrt", "udp"], category="DECISION"))
        ctx.index.build(project.id)
        # Campaign 2 повторяет задачу Campaign 1
        bundle = ctx.retrieve_before_task("openwrt", project_id=project.id)
        titles = [str(i.entity.title) for i in bundle["retrieval_items"]]
        assert any("Decision" in t for t in titles), "DECISION not surfaced"

    def test_negative_reuse_failure_first(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Neg", tags=["hermes"])
        ctx.save_after_task(project.id, Knowledge(
            title="Failure Warp", body="cause: WARP datacenter IP\n"
                "recommendations: policy routing / VLESS",
            tags=["warp", "udp"], kind="negative"))
        ctx.index.build(project.id)
        # Попытка использовать Warp напрямую
        bundle = ctx.retrieve_before_task("warp", project_id=project.id)
        items = bundle["retrieval_items"]
        assert items, "no memory surfaced"
        failure = items[0]
        assert "Failure" in str(failure.entity.title), "FAILURE not first"
        assert "cause:" in failure.entity.body
        assert "recommendations:" in failure.entity.body
        assert failure.explanation.reason
