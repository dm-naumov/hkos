"""Unit tests: MigrationCommandRegistry (DS-012 ЭТАП 3)."""

import inspect

from hkos.integration.hermes.migration_commands import (
    UNKNOWN_COMMAND_ERROR,
    MigrationCommandRegistry,
)
from hkos.integration.hermes.schemas import (
    MigrationDetectResponse,
    MigrationErrorResponse,
    MigrationHistoryResponse,
    MigrationOperationResponse,
    MigrationStatusResponse,
)


class _FakeTools:
    """Двойник MigrationTools (запись вызовов)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def detect(self, agent: object = None, confirmed: bool = False) -> MigrationDetectResponse:
        self.calls.append("migration.detect")
        return MigrationDetectResponse(1, 2, 1, False)

    def status(self, agent: object = None, confirmed: bool = False) -> MigrationStatusResponse:
        self.calls.append("migration.status")
        return MigrationStatusResponse("COMPLETED", 1, 2, False)

    def migrate(self, agent: object = None, confirmed: bool = False) -> MigrationOperationResponse:
        self.calls.append("migration.migrate")
        return MigrationOperationResponse("migrate", "completed")

    def rollback(self, agent: object = None, confirmed: bool = False) -> MigrationOperationResponse:
        self.calls.append("migration.rollback")
        return MigrationOperationResponse("rollback", "rolled_back")

    def validate(self, agent: object = None, confirmed: bool = False) -> MigrationOperationResponse:
        self.calls.append("migration.validate")
        return MigrationOperationResponse("validate", "passed")

    def history(self, agent: object = None, confirmed: bool = False) -> MigrationHistoryResponse:
        self.calls.append("migration.history")
        return MigrationHistoryResponse()


class TestMigrationCommandRegistry:
    """Реестр команд: routing, детерминизм, неизвестная команда."""

    def _registry(self) -> tuple[MigrationCommandRegistry, _FakeTools]:
        tools = _FakeTools()
        return MigrationCommandRegistry(tools), tools  # type: ignore[arg-type]

    def test_six_commands_registered(self) -> None:
        registry, _ = self._registry()
        assert registry.commands() == [
            "migration.detect", "migration.history", "migration.migrate",
            "migration.rollback", "migration.status", "migration.validate",
        ]

    def test_routing_all_commands(self) -> None:
        registry, tools = self._registry()
        for command in registry.commands():
            response = registry.execute(command)
            assert response is not None
        assert tools.calls == registry.commands()  # каждый вызов -> своя команда

    def test_routing_correct_response_types(self) -> None:
        registry, _ = self._registry()
        assert isinstance(registry.execute("migration.detect"), MigrationDetectResponse)
        assert isinstance(registry.execute("migration.status"), MigrationStatusResponse)
        assert isinstance(registry.execute("migration.migrate"), MigrationOperationResponse)
        assert isinstance(registry.execute("migration.rollback"), MigrationOperationResponse)
        assert isinstance(registry.execute("migration.validate"), MigrationOperationResponse)
        assert isinstance(registry.execute("migration.history"), MigrationHistoryResponse)

    def test_unknown_command_error(self) -> None:
        registry, _ = self._registry()
        response = registry.execute("migration.unknown")
        assert isinstance(response, MigrationErrorResponse)
        assert response.error_type == UNKNOWN_COMMAND_ERROR
        assert "Unknown command" in response.message

    def test_deterministic_no_state(self) -> None:
        """Реестр детерминирован и без состояния (два вызова — тот же результат)."""
        registry, _ = self._registry()
        first = registry.execute("migration.status")
        second = registry.execute("migration.status")
        assert first == second

    def test_forbidden_imports(self) -> None:
        """migration_commands.py не импортирует внутренние компоненты migration."""
        import hkos.integration.hermes.migration_commands as module

        source = inspect.getsource(module)
        for forbidden in (
            "migration_manager", "backup_manager", "rollback_manager",
            "migration_registry", "migration_executor", "migration_validator",
            "schema_detector", "migration_history",
        ):
            assert forbidden not in source, forbidden
        # разрешён только интеграционный слой
        assert "migration_tools" in source
        assert "schemas" in source

    def test_no_repository_storage_access(self) -> None:
        source = inspect.getsource(MigrationCommandRegistry)
        for forbidden in ("repository", "storage", "snapshot", "index"):
            assert f"from hkos.{forbidden}" not in source, forbidden
            assert f"import hkos.{forbidden}" not in source, forbidden
