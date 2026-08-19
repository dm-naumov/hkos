"""HKOS Load Generators (DS-014 ЭТАП 1).
================================================================
Генераторы данных для нагрузочных сценариев. Работают ЧЕРЕЗ публичные
интерфейсы HKOS (Librarian.register / CampaignManager / ProjectManager).

Масштабы:
- Small:   100 Knowledge
- Medium:  10 000 Knowledge
- Large:   100 000 Knowledge
- Stress:  1 000 000 Knowledge

ВАЖНО: генераторы описаны и импортируемы; реальные Large/Stress прогоны
запускаются ТОЛЬКО отдельными этапами DS-014 (не в обычном pytest).
"""

from hkos.repository.models import Knowledge
from tests.system.fixtures import HkosSystemContext

__all__ = [
    "SCALE_SMALL",
    "SCALE_MEDIUM",
    "SCALE_LARGE",
    "SCALE_STRESS",
    "LoadPlan",
    "load_plan",
    "generate_knowledge",
]


SCALE_SMALL: int = 100
SCALE_MEDIUM: int = 10_000
SCALE_LARGE: int = 100_000
SCALE_STRESS: int = 1_000_000


class LoadPlan:
    """План нагрузки: проекты x знания x кампании (детерминированный)."""

    def __init__(self, projects: int, knowledge_per_project: int,
                 campaigns_per_project: int) -> None:
        """Инициализация плана."""
        self.projects = projects
        self.knowledge_per_project = knowledge_per_project
        self.campaigns_per_project = campaigns_per_project

    @property
    def total_knowledge(self) -> int:
        return self.projects * self.knowledge_per_project


def load_plan(scale: int) -> LoadPlan:
    """План нагрузки по масштабу (DS-013/014 согласование)."""
    if scale == SCALE_SMALL:
        return LoadPlan(projects=1, knowledge_per_project=100, campaigns_per_project=1)
    if scale == SCALE_MEDIUM:
        return LoadPlan(projects=5, knowledge_per_project=2_000, campaigns_per_project=2)
    if scale == SCALE_LARGE:
        return LoadPlan(projects=50, knowledge_per_project=2_000, campaigns_per_project=10)
    if scale == SCALE_STRESS:
        return LoadPlan(projects=100, knowledge_per_project=10_000, campaigns_per_project=10)
    raise ValueError(f"unknown scale: {scale}")


def generate_knowledge(
    ctx: HkosSystemContext, project_id: str, count: int, prefix: str = "S"
) -> list[str]:
    """Создать знания через Librarian.register (публичный API)."""
    ids: list[str] = []
    for i in range(count):
        knowledge = ctx.librarian.register(project_id, Knowledge(
            title=f"{prefix}{i} load", body=f"body {i} udp load",
            tags=["load", "udp" if i % 2 == 0 else "bulk"]))
        ids.append(knowledge.id)
    return ids
