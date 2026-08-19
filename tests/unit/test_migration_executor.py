"""Unit tests: MigrationExecutor (DS-011 §8/§14, IP-011 ЭТАП 5)."""

import pytest

from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_executor import MigrationExecutor
from hkos.migration.migration_registry import MigrationStep


class _StepWithApply:
    """Duck-typed шаг: предоставляет apply()."""

    def __init__(self, migration_id: str = "001", calls: list[str] | None = None) -> None:
        self.migration_id = migration_id
        self.calls = calls if calls is not None else []

    def apply(self) -> None:
        self.calls.append(self.migration_id)


class TestMigrationExecutor:
    """Применение шага; идемпотентность; без оркестрации."""

    def test_apply_with_step_apply(self) -> None:
        step = _StepWithApply("001")
        MigrationExecutor().apply(step)  # type: ignore[arg-type]
        assert step.calls == ["001"]

    def test_apply_with_handler(self) -> None:
        """Шаг Registry (frozen dataclass) применяется обработчиком по id."""
        calls: list[str] = []
        executor = MigrationExecutor({
            "001": lambda step: calls.append(step.migration_id),
        })
        executor.apply(MigrationStep("001", 1, 2))
        assert calls == ["001"]

    def test_repeated_apply_idempotent(self) -> None:
        """Повторный apply уже выполненного шага — корректно завершается."""
        calls: list[str] = []
        executor = MigrationExecutor({"001": lambda step: calls.append("x")})
        step = MigrationStep("001", 1, 2)
        executor.apply(step)
        executor.apply(step)
        assert len(calls) == 2  # идемпотентность — контракт шага; вызов допустим

    def test_missing_handler_raises(self) -> None:
        executor = MigrationExecutor({})
        with pytest.raises(MigrationError):
            executor.apply(MigrationStep("unknown", 1, 2))

    def test_handler_error_wrapped(self) -> None:
        def boom(step: MigrationStep) -> None:
            raise RuntimeError("boom")

        executor = MigrationExecutor({"001": boom})
        with pytest.raises(MigrationError):
            executor.apply(MigrationStep("001", 1, 2))

    def test_no_orchestration_api(self) -> None:
        api = {m for m in dir(MigrationExecutor) if not m.startswith("_")}
        assert api == {"apply"}
