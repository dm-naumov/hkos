"""Unit tests: Hermes security model (DS-012 ЭТАП 4 §1-3)."""

from hkos.integration.hermes.schemas import MigrationErrorResponse
from hkos.integration.hermes.security import (
    COMMAND_PERMISSIONS,
    PERMISSION_ADMIN,
    PERMISSION_READ,
    PERMISSION_WRITE,
    AgentContext,
    MigrationSafetyGuard,
    check_permission,
)
from hkos.migration.exceptions import MigrationLockError


class _ProbeEngine:
    """Engine для guard-проб."""

    def __init__(self) -> None:
        self.lock_busy = False
        self.failed = False

    def acquire_lock(self) -> None:
        if self.lock_busy:
            raise MigrationLockError("busy")

    def release_lock(self) -> None:
        pass

    def history(self) -> list[object]:
        if self.failed:
            from hkos.migration.migration_history import MigrationRecord
            return [MigrationRecord("001", "t", "a", 1, 2, "failed", 0)]
        return []

    # ---- публичные методы фасада (для интеграционных сценариев) ----

    def status(self) -> str:
        return "COMPLETED; current=1; target=1"

    def detect(self) -> object:
        return None

    def migrate(self) -> None:
        if self.failed:
            from hkos.migration.exceptions import MigrationError
            raise MigrationError("migration failed")

    def rollback(self) -> None:
        pass

    def validate(self) -> None:
        pass


def _agent(project: str = "p1") -> AgentContext:
    return AgentContext(agent_id="agent-1", project_id=project)


class TestPermissionModel:
    """READ всегда; WRITE — project context; ADMIN — confirmation."""

    def test_read_always_allowed(self) -> None:
        for command in ("migration.detect", "migration.status", "migration.history"):
            result = check_permission(command, _agent())
            assert result.allowed is True
            assert COMMAND_PERMISSIONS[command] == PERMISSION_READ

    def test_write_requires_project(self) -> None:
        assert check_permission("knowledge.save", _agent("")).allowed is False
        assert check_permission("knowledge.save", _agent("p1")).allowed is True

    def test_admin_requires_confirmation(self) -> None:
        result = check_permission("migration.migrate", _agent(), confirmed=False)
        assert result.allowed is False
        assert result.required_confirmation is True
        result = check_permission("migration.migrate", _agent(), confirmed=True)
        assert result.allowed is True

    def test_admin_requires_project_even_confirmed(self) -> None:
        result = check_permission("migration.rollback", _agent(""), confirmed=True)
        assert result.allowed is False

    def test_mapping(self) -> None:
        assert COMMAND_PERMISSIONS["migration.migrate"] == PERMISSION_ADMIN
        assert COMMAND_PERMISSIONS["migration.rollback"] == PERMISSION_ADMIN
        assert COMMAND_PERMISSIONS["snapshot.refresh"] == PERMISSION_ADMIN
        assert COMMAND_PERMISSIONS["index.rebuild"] == PERMISSION_ADMIN
        assert COMMAND_PERMISSIONS["knowledge.save"] == PERMISSION_WRITE
        assert COMMAND_PERMISSIONS["context.update"] == PERMISSION_WRITE
        assert COMMAND_PERMISSIONS["retrieval.preview"] == PERMISSION_READ


class TestMigrationSafetyGuard:
    """Предохранитель опасных операций."""

    def test_allows_with_confirmation(self) -> None:
        guard = MigrationSafetyGuard(_ProbeEngine())  # type: ignore[arg-type]
        result = guard.check("migration.migrate", _agent(), confirmed=True)
        assert result is None

    def test_blocks_busy_lock(self) -> None:
        engine = _ProbeEngine()
        engine.lock_busy = True
        guard = MigrationSafetyGuard(engine)  # type: ignore[arg-type]
        result = guard.check("migration.migrate", _agent(), confirmed=True)
        assert isinstance(result, MigrationErrorResponse)
        assert result.error_type == "migration_lock"
        assert result.recoverable is True

    def test_blocks_without_project(self) -> None:
        guard = MigrationSafetyGuard(_ProbeEngine())  # type: ignore[arg-type]
        result = guard.check("migration.migrate", _agent(""), confirmed=True)
        assert isinstance(result, MigrationErrorResponse)
        assert result.recoverable is True

    def test_blocks_without_confirmation(self) -> None:
        guard = MigrationSafetyGuard(_ProbeEngine())  # type: ignore[arg-type]
        result = guard.check("migration.migrate", _agent(), confirmed=False)
        assert isinstance(result, MigrationErrorResponse)
        assert "confirmation" in result.message

    def test_blocks_failed_recovery(self) -> None:
        engine = _ProbeEngine()
        engine.failed = True
        guard = MigrationSafetyGuard(engine)  # type: ignore[arg-type]
        result = guard.check("migration.migrate", _agent(), confirmed=True)
        assert isinstance(result, MigrationErrorResponse)
        assert "failed" in result.message
