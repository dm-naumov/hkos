"""DS-016: Assertions (ЭТАП 1).

Проверки интеграции: знания доступны через Retrieval; SSOT = Repository;
explanation.reason существует.
"""

from tests.system.ds016.hermes_context import HermesRuntimeContext

__all__ = [
    "assert_retrievable_by_hermes",
    "assert_reason_exists",
    "assert_memory_reused",
]


def assert_retrievable_by_hermes(
    ctx: HermesRuntimeContext, project_id: str, query: str, marker: str
) -> None:
    """Знание находится через Retrieval (публичный API Hermes)."""
    bundle = ctx.retrieve_before_task(query, project_id)
    items = bundle["retrieval_items"]
    assert any(marker in str(i.entity.title) for i in items), (
        f"{marker!r} not retrievable by {query!r}")


def assert_reason_exists(
    ctx: HermesRuntimeContext, project_id: str, query: str
) -> None:
    """explanation.reason существует (объяснимость DS-008)."""
    bundle = ctx.retrieve_before_task(query, project_id)
    items = bundle["retrieval_items"]
    assert len(items) >= 1
    assert items[0].explanation.reason, "explanation reason missing"


def assert_memory_reused(
    ctx: HermesRuntimeContext, project_id: str, query: str,
    expected_markers: list[str],
) -> None:
    """Память переиспользуется (решения/ошибки/конфигурации возвращаются)."""
    bundle = ctx.retrieve_before_task(query, project_id)
    titles = [str(i.entity.title) for i in bundle["retrieval_items"]]
    for marker in expected_markers:
        assert any(marker in t for t in titles), f"{marker} not reused"
