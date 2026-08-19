"""DS-015 ЭТАП 5.8: Final Security Sign-off.
================================================================
WRITE без project -> BLOCK; ADMIN без confirmation -> BLOCK; ADMIN с
confirmation -> ALLOW; Audit: COMMAND_RECEIVED/ALLOWED/DENIED.
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


class _Probe:
    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1

    def validate(self) -> None:
        pass


class TestFinalSecuritySignoff:
    """Финальный security sign-off (permissions + audit)."""

    def test_write_without_project_blocked(self) -> None:
        tools = MigrationTools(_Probe())  # type: ignore[arg-type]
        response = tools.migrate(AgentContext(agent_id="a1"), confirmed=True)
        assert isinstance(response, MigrationErrorResponse)

    def test_admin_without_confirmation_blocked(self) -> None:
        tools = MigrationTools(_Probe())  # type: ignore[arg-type]
        response = tools.rollback(
            AgentContext(agent_id="a1", project_id="p1"), confirmed=False)
        assert isinstance(response, MigrationErrorResponse)

    def test_admin_with_confirmation_allowed(self) -> None:
        probe = _Probe()
        tools = MigrationTools(probe)  # type: ignore[arg-type]
        response = tools.rollback(
            AgentContext(agent_id="admin", project_id="p1"), confirmed=True)
        assert isinstance(response, MigrationOperationResponse)
        assert probe.calls == 1

    def test_audit_events(self) -> None:
        audit = AuditLogger()
        tools = MigrationTools(_Probe(), audit=audit)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="a1", project_id="p1")
        tools.rollback(agent, confirmed=False)   # DENIED
        tools.status(agent)                      # ALLOWED
        events = {e.event for e in audit.entries()}
        assert AUDIT_COMMAND_RECEIVED in events
        assert AUDIT_COMMAND_ALLOWED in events
        assert AUDIT_COMMAND_DENIED in events
