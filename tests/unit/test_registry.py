"""Unit tests: MigrationRegistry (DS-011 §8)."""

import pytest

from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_registry import MigrationRegistry, MigrationStep


class TestMigrationRegistry:
    """Статический каталог: тотальный порядок, непрерывность, валидации."""

    def test_register_and_contains(self) -> None:
        registry = MigrationRegistry()
        step = MigrationStep("001_initial", 1, 2)
        registry.register(step)
        assert registry.contains("001_initial") is True
        assert registry.contains("nope") is False

    def test_ordering_simple_chain(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        registry.register(MigrationStep("002", 2, 3))
        path = registry.ordered(1, 3)
        assert [s.migration_id for s in path] == ["001", "002"]

    def test_ordering_from_intermediate(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        registry.register(MigrationStep("002", 2, 3))
        assert [s.migration_id for s in registry.ordered(2, 3)] == ["002"]

    def test_ordering_same_version_empty(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        assert registry.ordered(1, 1) == []

    def test_ordering_current_above_target_raises(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        with pytest.raises(MigrationError):
            registry.ordered(3, 2)

    def test_ordering_chain_break_raises(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        registry.register(MigrationStep("003", 3, 4))  # разрыв 2->3
        with pytest.raises(MigrationError):
            registry.ordered(1, 4)

    def test_duplicate_id_identical_is_noop(self) -> None:
        """Идемпотентность (§14): идентичный повторный register = no-op."""
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        registry.register(MigrationStep("001", 1, 2))  # no-op
        assert registry.ordered(1, 2) == [MigrationStep("001", 1, 2)]

    def test_duplicate_id_different_transition_raises(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        with pytest.raises(MigrationError):
            registry.register(MigrationStep("001", 1, 3))

    def test_duplicate_transition_raises(self) -> None:
        """Запрет неоднозначных переходов: (1->2) дважды с разными id."""
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        with pytest.raises(MigrationError):
            registry.register(MigrationStep("002", 1, 2))

    def test_from_above_to_raises(self) -> None:
        """from_version < to_version обязателен (ацикличность)."""
        registry = MigrationRegistry()
        with pytest.raises(MigrationError):
            registry.register(MigrationStep("bad", 3, 2))

    def test_from_equal_to_raises(self) -> None:
        registry = MigrationRegistry()
        with pytest.raises(MigrationError):
            registry.register(MigrationStep("bad", 2, 2))

    def test_aggregated_migration_explicit(self) -> None:
        """Агрегат (1->3) явно зарегистрирован — прямой переход допустим (§12)."""
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        registry.register(MigrationStep("002", 2, 3))
        registry.register(MigrationStep("agg_1_3", 1, 3))  # агрегат
        # агрегат предпочтителен (детерминированно)
        assert [s.migration_id for s in registry.ordered(1, 3)] == ["agg_1_3"]
        # единичный шаг тоже доступен
        assert [s.migration_id for s in registry.ordered(1, 2)] == ["001"]

    def test_ambiguous_transition_raises(self) -> None:
        """Неоднозначность при построении цепочки -> MigrationError."""
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        registry.register(MigrationStep("agg_1_3", 1, 3))  # вторая исходящая из 1
        with pytest.raises(MigrationError):
            registry.ordered(1, 4)

    def test_empty_registry_ordered(self) -> None:
        registry = MigrationRegistry()
        assert registry.ordered(1, 1) == []
        with pytest.raises(MigrationError):
            registry.ordered(1, 2)

    def test_no_global_state(self) -> None:
        """Два независимых реестра не влияют друг на друга."""
        r1 = MigrationRegistry()
        r2 = MigrationRegistry()
        r1.register(MigrationStep("001", 1, 2))
        assert r2.contains("001") is False
        assert r1.contains("001") is True

    def test_steps_deterministic_order(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("003", 3, 4))
        registry.register(MigrationStep("001", 1, 2))
        registry.register(MigrationStep("002", 2, 3))
        assert [s.migration_id for s in registry.steps()] == ["001", "002", "003"]
