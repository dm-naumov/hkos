"""System: консистентность Index (DS-014 ЭТАП 3).
================================================================
build -> update -> remove -> rebuild. После каждого действия Retrieval
совпадает с Repository: отсутствующие не находятся; новые находятся;
удалённые исчезают.
"""

from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.assertions import (
    assert_index_matches_repository,
    assert_retrievable,
)
from tests.system.fixtures import create_system_context, project_factory


class TestIndexConsistencySystem:
    """Индекс — производное Repository (build/update/remove/rebuild)."""

    def test_build_then_retrieval_matches(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "IndexBuild", tags=["system"])
        ctx.librarian.register(project.id, Knowledge(
            title="BuildFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        assert_index_matches_repository(ctx, project.id)
        assert_retrievable(ctx, project.id, "BuildFact", "BuildFact")

    def test_update_new_knowledge_found(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "IndexUpdate", tags=["system"])
        ctx.index.build(project.id)
        assert_index_matches_repository(ctx, project.id)
        # новое знание + index.update -> находится
        knowledge = ctx.librarian.register(project.id, Knowledge(
            title="UpdateFact udp", body="udp", tags=["udp"]))
        # ДО update индекса знание НЕ находится
        before = ctx.retrieval.retrieve("UpdateFact", project_id=project.id)
        assert len(before.items) == 0, "not-yet-indexed knowledge found"
        ctx.index.update(project.id, knowledge.id, "knowledge")
        assert_index_matches_repository(ctx, project.id)
        assert_retrievable(ctx, project.id, "UpdateFact", "UpdateFact")

    def test_remove_knowledge_disappears(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "IndexRemove", tags=["system"])
        k1 = ctx.librarian.register(project.id, Knowledge(
            title="RemoveFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        assert_retrievable(ctx, project.id, "RemoveFact", "RemoveFact")
        # удаление из Repository (публичный API) + index.remove
        ctx.repos.knowledge.delete(project.id, k1.id)
        ctx.index.remove(project.id, k1.id, "knowledge")
        result = ctx.retrieval.retrieve("RemoveFact", project_id=project.id)
        assert len(result.items) == 0, "removed knowledge still found"
        assert_index_matches_repository(ctx, project.id)

    def test_rebuild_restores_consistency(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "IndexRebuild", tags=["system"])
        for i in range(20):
            ctx.librarian.register(project.id, Knowledge(
                title=f"Rebuild{i}fact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        assert_index_matches_repository(ctx, project.id)
        # удалить конкретное знание из Repository БЕЗ index.remove
        target = next(
            k for k in ctx.repos.knowledge.list(project.id)
            if "Rebuild0fact" in k.title)
        ctx.repos.knowledge.delete(project.id, target.id)
        # rebuild восстанавливает консистентность
        ctx.index.rebuild(project.id)
        assert_index_matches_repository(ctx, project.id)
        result = ctx.retrieval.retrieve("Rebuild0fact", project_id=project.id)
        assert len(result.items) == 0, "deleted knowledge found after rebuild"
