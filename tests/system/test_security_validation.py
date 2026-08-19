"""System: security validation (DS-014 ЭТАП 4 §4).
================================================================
WRITE без project context -> BLOCK; ADMIN без confirmation -> BLOCK;
ADMIN с confirmation -> ALLOW; Audit: RECEIVED/ALLOWED/DENIED.
"""

from hkos.integration.hermes.audit import (
    AUDIT_COMMAND_ALLOWED,
    AUDIT_COMMAND_DENIED,
    AUDIT_COMMAND_RECEIVED,
    AuditLogger,
)
from hkos.integration.hermes.migration_tools import MigrationTools
from hkos.integration.hermes.schemas import (
    MigrationErrorResponse,
    MigrationOperationResponse,
)
from hkos.integration.hermes.security import AgentContext


class _ProbeEngine:
    """Двойник MigrationEngine (публичные методы)."""

    def __init__(self) -> None:
        self.rollback_calls = 0

    def acquire_lock(self) -> None:
        pass

    def release_lock(self) -> None:
        pass

    def history(self) -> list[object]:
        return []

    def status(self) -> str:
        return "COMPLETED; current=1; target=1"

    def detect(self) -> object:
        return None

    def migrate(self) -> None:
        pass

    def rollback(self) -> None:
        self.rollback_calls += 1

    def validate(self) -> None:
        pass


class TestSecuritySystemValidation:
    """Разрешения: WRITE/ADMIN; аудит событий."""

    def test_write_without_project_blocked(self) -> None:
        tools = MigrationTools(_ProbeEngine())  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1")  # БЕЗ project context
        response = tools.migrate(agent, confirmed=True)
        assert isinstance(response, MigrationErrorResponse)  # BLOCK

    def test_admin_without_confirmation_blocked(self) -> None:
        tools = MigrationTools(_ProbeEngine())  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1", project_id="p1")
        response = tools.rollback(agent, confirmed=False)
        assert isinstance(response, MigrationErrorResponse)  # BLOCK
        assert "confirmation" in response.message

    def test_admin_with_confirmation_allowed(self) -> None:
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="admin", project_id="p1")
        response = tools.rollback(agent, confirmed=True)
        assert isinstance(response, MigrationOperationResponse)  # ALLOW
        assert engine.rollback_calls == 1

    def test_audit_events(self) -> None:
        engine = _ProbeEngine()
        audit = AuditLogger()
        tools = MigrationTools(engine, audit=audit)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1", project_id="p1")
        tools.rollback(agent, confirmed=False)   # DENIED
        tools.status(agent)                      # ALLOWED
        events = {e.event for e in audit.entries()}
        assert AUDIT_COMMAND_RECEIVED in events
        assert AUDIT_COMMAND_ALLOWED in events
        assert AUDIT_COMMAND_DENIED in events
