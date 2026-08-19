"""DS-015 Load Generators (ЭТАП 1 — планы; НЕ запускать).

SMALL 100 / MEDIUM 10K / LARGE 100K / STRESS 1M.
"""

from tests.system.ds015.fixtures import DS015TestContext

__all__ = [
    "SCALE_SMALL", "SCALE_MEDIUM", "SCALE_LARGE", "SCALE_STRESS",
    "load_plan_ds015", "generate_ds015_knowledge",
]

SCALE_SMALL: int = 100
SCALE_MEDIUM: int = 10_000
SCALE_LARGE: int = 100_000
SCALE_STRESS: int = 1_000_000


def load_plan_ds015(scale: int) -> dict[str, int]:
    """План нагрузки DS-015 (проекты x знания; детерминированный)."""
    if scale == SCALE_SMALL:
        return {"projects": 1, "knowledge": 100, "campaigns": 1}
    if scale == SCALE_MEDIUM:
        return {"projects": 5, "knowledge": 2_000, "campaigns": 2}
    if scale == SCALE_LARGE:
        return {"projects": 50, "knowledge": 2_000, "campaigns": 10}
    if scale == SCALE_STRESS:
        return {"projects": 100, "knowledge": 10_000, "campaigns": 10}
    raise ValueError(f"unknown scale: {scale}")


def generate_ds015_knowledge(
    ctx: DS015TestContext, project_id: str, count: int, prefix: str = "D"
) -> list[str]:
    """Создать знания через Librarian (публичный API; не в обход)."""
    from hkos.repository.models import Knowledge

    ids: list[str] = []
    for i in range(count):
        knowledge = ctx.librarian.register(project_id, Knowledge(
            title=f"{prefix}{i}fact udp", body="udp", tags=["udp"]))
        ids.append(knowledge.id)
    return ids
