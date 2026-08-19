"""System: стресс (DS-014).

Генераторы Small/Medium/Large/Stress ОПИСАНЫ (не выполняются в обычном
прогоне). Реальные стресс-прогоны - отдельный этап DS-014.
"""

from tests.system.generators import (
    SCALE_LARGE,
    SCALE_MEDIUM,
    SCALE_SMALL,
    SCALE_STRESS,
    LoadPlan,
    load_plan,
)


class TestStressPlans:
    """Планы нагрузки определены (без генерации данных)."""

    def test_plans_defined(self) -> None:
        assert load_plan(SCALE_SMALL).total_knowledge == 100
        assert load_plan(SCALE_MEDIUM).total_knowledge == 10_000
        assert load_plan(SCALE_LARGE).total_knowledge == 100_000
        assert load_plan(SCALE_STRESS).total_knowledge == 1_000_000

    def test_load_plan_is_deterministic(self) -> None:
        first = load_plan(SCALE_MEDIUM)
        second = load_plan(SCALE_MEDIUM)
        assert first.projects == second.projects
        assert isinstance(first, LoadPlan)
