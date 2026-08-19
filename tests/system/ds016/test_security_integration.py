"""DS-016 ЭТАП 2: Security в интеграционном контуре.
================================================================
Save hook не обходит Librarian; DS-012 security controls не обойдены
(WRITE без project -> BLOCK; ADMIN без confirmation -> BLOCK; audit).
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


class TestSecurityInIntegration:
    """Интеграция не обходит security controls (DS-012)."""

    def test_save_hook_uses_librarian(self, tmp_path: object) -> None:
        """Save hook пишет через Librarian (не напрямую в Repository)."""
        import tempfile
        from pathlib import Path

        from hkos.repository.models import Knowledge
        from tests.system.ds016.hermes_context import create_hermes_context

        ctx = create_hermes_context(Path(tempfile.mkdtemp()))
        project = ctx.project.create(name="SecSave", tags=["hermes"])
        result = ctx.save_after_task(project.id, Knowledge(
            title="SecFact udp", body="udp", tags=["udp"]))
        assert result["saved"]
        assert ctx.repos.knowledge.count(project.id) == 1

    def test_write_without_project_blocked(self) -> None:
        tools = MigrationTools(_Probe())  # type: ignore[arg-type]
        response = tools.migrate(AgentContext(agent_id="a1"), confirmed=True)
        assert isinstance(response, MigrationErrorResponse)

    def test_admin_without_confirmation_blocked(self) -> None:
        tools = MigrationTools(_Probe())  # type: ignore[arg-type]
        response = tools.rollback(
            AgentContext(agent_id="a1", project_id="p1"), confirmed=False)
        assert isinstance(response, MigrationErrorResponse)

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
