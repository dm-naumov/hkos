"""DS-015 Assertions (ЭТАП 1 — скелет).

Общие проверки целостности (публичные API; SSOT = Repository).
"""

from tests.system.ds015.fixtures import DS015TestContext

__all__ = [
    "assert_knowledge_flow",
    "assert_index_projection",
    "assert_snapshot_state",
]


def assert_knowledge_flow(
    ctx: DS015TestContext, project_id: str, knowledge_id: str
) -> None:
    """Create -> save -> index -> snapshot -> retrieve (полный поток)."""
    assert ctx.repos.knowledge.exists(project_id, knowledge_id)
    index_stats = ctx.index.statistics(project_id)
    assert int(index_stats.get("knowledge", 0)) >= 1
    result = ctx.retrieval.retrieve(
        ctx.repos.knowledge.load(project_id, knowledge_id).title,
        project_id=project_id)
    assert result is not None


def assert_index_projection(
    ctx: DS015TestContext, project_id: str
) -> None:
    """Индекс — проекция Repository (SSOT)."""
    repository_count = ctx.repos.knowledge.count(project_id)
    index_count = int(ctx.index.statistics(project_id).get("knowledge", 0))
    assert index_count == repository_count


def assert_snapshot_state(
    ctx: DS015TestContext, snapshots: object, project_id: str
) -> None:
    """Снимок — состояние Repository (SSOT)."""
    snapshot = snapshots.load(project_id)  # type: ignore[union-attr]
    assert snapshot is not None
    expected = ctx.repos.knowledge.count(project_id)
    actual = int(snapshot.statistics.get("knowledge", 0))
    assert actual == expected
