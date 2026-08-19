"""DS-015 ЭТАП 3: Data Integrity Validation.
================================================================
Repository == Knowledge Truth: количество, уникальность ID, отсутствие
дубликатов, категории, отсутствие битых ссылок. Отрицательные знания
(FAILURE/DECISION/CONFIGURATION) сохраняются и возвращаются Retrieval.
"""

from hkos.repository.models import Knowledge
from tests.system.ds015.fixtures import create_ds015_context


class TestDataIntegrity:
    """Целостность Repository (SSOT) и отрицательных знаний."""

    def test_repository_truth(self, tmp_path: object) -> None:
        import tempfile
        from pathlib import Path

        ctx = create_ds015_context(Path(tempfile.mkdtemp()))
        project = ctx.project.create(name="Integrity", tags=["di"])
        ids: list[str] = []
        for i in range(25):
            knowledge = ctx.librarian.register(project.id, Knowledge(
                title=f"DI{i}fact udp", body=f"body {i}", tags=["udp"]))
            ids.append(knowledge.id)
        # количество
        assert ctx.repos.knowledge.count(project.id) == 25
        # уникальность ID
        loaded = ctx.repos.knowledge.list(project.id)
        assert len({k.id for k in loaded}) == len(loaded) == 25
        # категории корректны (классификация замкнута)
        from hkos.services.classification_policy import VALID_CATEGORIES
        for knowledge in loaded:
            assert knowledge.category in VALID_CATEGORIES
        # отсутствие битых ссылок (все id существуют)
        for knowledge in loaded:
            assert ctx.repos.knowledge.exists(project.id, knowledge.id)

    def test_negative_knowledge_preserved(self, tmp_path: object) -> None:
        import tempfile
        from pathlib import Path

        ctx = create_ds015_context(Path(tempfile.mkdtemp()))
        project = ctx.project.create(name="Negative", tags=["di"])
        ctx.librarian.register(project.id, Knowledge(
            title="FailFact udp", body="cause: datacenter\nrecommendations: vless",
            tags=["udp"], kind="negative"))
        ctx.librarian.register(project.id, Knowledge(
            title="DecFact udp", body="use VLESS", tags=["udp"],
            category="DECISION"))
        ctx.librarian.register(project.id, Knowledge(
            title="CfgFact udp", body="AX3000T", tags=["udp"],
            category="CONFIGURATION"))
        ctx.index.build(project.id)
        # сохраняются (SSOT)
        assert ctx.repos.knowledge.count(project.id) == 3
        # возвращаются Retrieval (FAILURE -> категория, содержимое intact)
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        titles = [str(i.entity.title) for i in result.items]
        assert any("FailFact" in t for t in titles)
        assert any("DecFact" in t for t in titles)
        assert any("CfgFact" in t for t in titles)
        failure = next(i.entity for i in result.items
                       if "FailFact" in str(i.entity.title))
        assert "cause:" in failure.body and "recommendations:" in failure.body
