"""DS-015 ЭТАП 4: Memory Reuse Acceptance.
================================================================
Project A: Campaign 1 (Decision A/Failure A/Configuration A) ->
завершение -> Campaign 2 получает их; нет повторного решения старой
ошибки; отрицательная память используется; explanation содержит reason.
"""

from hkos.repository.models import Knowledge
from tests.system.ds015.fixtures import create_ds015_context


class TestMemoryReuse:
    """Память переносится между кампаниями; отрицательные знания работают."""

    def test_campaign2_receives_campaign1_memory(self, tmp_path: object) -> None:
        import tempfile
        from pathlib import Path

        ctx = create_ds015_context(Path(tempfile.mkdtemp()))
        project = ctx.project.create(name="ProjectA", tags=["reuse"])
        # Campaign 1
        c1 = ctx.campaign.create(project.id, goal="campaign-1")
        ctx.campaign.open(project.id, c1.id)
        ctx.campaign.open(project.id, c1.id)
        dec_k = ctx.librarian.register(project.id, Knowledge(
            title="DecisionA udp", body="use VLESS", tags=["vless", "udp"],
            category="DECISION", source_campaign=c1.id))
        fail_k = ctx.librarian.register(project.id, Knowledge(
            title="FailureA udp", body="cause: WARP datacenter IP",
            tags=["warp", "udp"], kind="negative", source_campaign=c1.id))
        cfg_k = ctx.librarian.register(project.id, Knowledge(
            title="ConfigA udp", body="AX3000T + OpenWRT", tags=["router", "udp"],
            category="CONFIGURATION", source_campaign=c1.id))
        # знания валидируются (status NEW -> VERIFIED; только такие
        # возвращаются Retrieval — статусный фильтр DS-008)
        for k in (dec_k, fail_k, cfg_k):
            ctx.librarian.validate(project.id, k.id)
        ctx.index.build(project.id)
        ctx.campaign.close(project.id, c1.id)
        # Campaign 2
        c2 = ctx.campaign.create(project.id, goal="campaign-2")
        ctx.campaign.open(project.id, c2.id)
        ctx.campaign.open(project.id, c2.id)
        result = ctx.retrieval.retrieve("udp", project_id=project.id, top_n=50)
        titles = [str(i.entity.title) for i in result.items]
        # Campaign 2 получает Decision/Failure/Configuration
        assert any("DecisionA" in t for t in titles)
        assert any("FailureA" in t for t in titles)
        assert any("ConfigA" in t for t in titles)
        # отрицательная память: FAILURE-знание видно (не повторяем ошибку)
        failure = next(i for i in result.items
                       if "FailureA" in str(i.entity.title))
        assert "cause:" in failure.entity.body
        # explanation содержит reason
        assert failure.explanation.reason, "explanation reason missing"

    def test_no_repeat_of_old_error(self, tmp_path: object) -> None:
        import tempfile
        from pathlib import Path

        ctx = create_ds015_context(Path(tempfile.mkdtemp()))
        project = ctx.project.create(name="NoRepeat", tags=["reuse"])
        error_k = ctx.librarian.register(project.id, Knowledge(
            title="OldError udp", body="cause: WARP datacenter\n"
                "recommendations: use VLESS/REALITY",
            tags=["warp", "udp"], kind="negative"))
        ctx.librarian.validate(project.id, error_k.id)
        ctx.index.build(project.id)
        # новая задача повторяет ошибочный путь -> FAILURE всплывает
        result = ctx.retrieval.retrieve("WARP", project_id=project.id)
        failures = [i for i in result.items
                    if "OldError" in str(i.entity.title)]
        assert failures, "negative memory not surfaced"
        assert "VLESS" in failures[0].entity.body  # рекомендация доступна
