"""HKOS System Assertions (DS-014 ЭТАП 2).
================================================================
Общие проверки целостности ЧЕРЕЗ публичные интерфейсы HKOS.

- Repository — единственный SSOT (проверки читают через Repository);
- Index/Snapshot — производные (проверяются на соответствие Repository);
- Librarian не обходится (знания проверяются через Repository чтение).
"""

from hkos.performance.performance_manager import PerformanceManager
from tests.system.fixtures import HkosSystemContext

__all__ = [
    "assert_knowledge_exists",
    "assert_retrievable",
    "assert_snapshot_consistent",
    "assert_project_integrity",
    "assert_campaign_integrity",
    "assert_performance_recorded",
    "assert_index_matches_repository",
    "assert_snapshot_matches_repository",
]


def assert_knowledge_exists(
    ctx: HkosSystemContext, project_id: str, knowledge_id: str
) -> None:
    """Знание существует в Repository (SSOT; публичное чтение)."""
    assert ctx.repos.knowledge.exists(project_id, knowledge_id), (
        f"knowledge {knowledge_id} missing in repository")


def assert_retrievable(
    ctx: HkosSystemContext, project_id: str, query: str, expected_title: str
) -> None:
    """Знание находится через Retrieval (публичный API)."""
    result = ctx.retrieval.retrieve(query, project_id=project_id)
    titles = [item.entity.title for item in result.items]
    assert any(expected_title in str(t) for t in titles), (
        f"{expected_title!r} not retrievable by {query!r}")


def assert_snapshot_consistent(
    ctx: HkosSystemContext, snapshots: object, project_id: str
) -> None:
    """Снимок согласован с Repository (счётчики; SSOT)."""
    snapshot = snapshots.load(project_id)  # type: ignore[union-attr]
    assert snapshot is not None, "snapshot missing"
    expected = ctx.repos.knowledge.count(project_id)
    actual = snapshot.statistics.get("knowledge")
    assert actual is not None and int(actual) == expected, (
        f"snapshot knowledge={actual}, repository={expected}")


def assert_project_integrity(
    ctx: HkosSystemContext, project_id: str, expected_knowledge: int
) -> None:
    """Проект цел: существует; счётчик знаний совпадает."""
    info = ctx.projects.info(project_id)
    assert info.id == project_id
    assert ctx.repos.knowledge.count(project_id) == expected_knowledge


def assert_campaign_integrity(
    ctx: HkosSystemContext, project_id: str, campaign_id: str
) -> None:
    """Кампания существует и имеет корректный статус."""
    status = ctx.campaigns.status(project_id, campaign_id)
    assert status.campaign_id == campaign_id


def assert_performance_recorded(
    manager: PerformanceManager, operation: str
) -> None:
    """Метрика операции записана Performance Layer'ом."""
    stats = manager.statistics().get("metrics")
    assert isinstance(stats, list), "no metrics"
    assert any(
        getattr(s, "operation", None) == operation for s in stats
    ), f"operation {operation!r} not recorded"


def assert_index_matches_repository(
    ctx: HkosSystemContext, project_id: str
) -> None:
    """Индекс (производное) соответствует Repository (SSOT)."""
    index_stats = ctx.index.statistics(project_id)
    repository_count = ctx.repos.knowledge.count(project_id)
    index_count = index_stats.get("knowledge")
    assert index_count is not None and int(index_count) == repository_count, (
        f"index knowledge={index_count}, repository={repository_count}")


def assert_snapshot_matches_repository(
    ctx: HkosSystemContext, snapshots: object, project_id: str
) -> None:
    """Снимок (производное) соответствует Repository по всем типам."""
    snapshot = snapshots.load(project_id)  # type: ignore[union-attr]
    assert snapshot is not None, "snapshot missing"
    for entity_type, repo in (
        ("knowledge", ctx.repos.knowledge),
        ("decisions", ctx.repos.decisions),
        ("campaigns", ctx.repos.campaigns),
        ("artifacts", ctx.repos.artifacts),
    ):
        expected = repo.count(project_id)
        actual = snapshot.statistics.get(entity_type)
        assert actual is not None and int(actual) == expected, (
            f"snapshot {entity_type}={actual}, repository={expected}")
