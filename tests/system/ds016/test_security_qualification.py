"""DS-016 ЭТАП 3.6: Security Qualification.
================================================================
WRITE без project -> BLOCK; ADMIN без confirmation -> BLOCK; с
confirmation -> ALLOW; Audit RECEIVED/ALLOWED/DENIED. Hermes не может:
писать JSON напрямую / обходить Librarian / менять Index напрямую.
"""

import os
from pathlib import Path

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


class TestSecurityQualification:
    """Квалификация безопасности Hermes-интеграции."""

    def test_permissions(self) -> None:
        tools = MigrationTools(_Probe())  # type: ignore[arg-type]
        no_project = tools.migrate(AgentContext(agent_id="a"), confirmed=True)
        assert isinstance(no_project, MigrationErrorResponse)  # BLOCK
        no_confirm = tools.rollback(
            AgentContext(agent_id="a", project_id="p"), confirmed=False)
        assert isinstance(no_confirm, MigrationErrorResponse)  # BLOCK
        probe = _Probe()
        allowed = MigrationTools(probe).rollback(  # type: ignore[arg-type]
            AgentContext(agent_id="admin", project_id="p"), confirmed=True)
        assert isinstance(allowed, MigrationOperationResponse)  # ALLOW
        assert probe.calls == 1

    def test_audit(self) -> None:
        audit = AuditLogger()
        tools = MigrationTools(_Probe(), audit=audit)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="a", project_id="p")
        tools.rollback(agent, confirmed=False)
        tools.status(agent)
        events = {e.event for e in audit.entries()}
        assert AUDIT_COMMAND_RECEIVED in events
        assert AUDIT_COMMAND_ALLOWED in events
        assert AUDIT_COMMAND_DENIED in events

    def test_no_direct_repository_access(self) -> None:
        """Hermes-слой не пишет JSON/Repository/Index напрямую (статически)."""
        integration_dir = str(Path(__file__).resolve().parents[3] / "integration")
        for root, _dirs, files in os.walk(integration_dir):
            for name in files:
                if not name.endswith(".py"):
                    continue
                source = open(os.path.join(root, name), encoding="utf-8").read()
                assert "json.dump" not in source, f"{name}: json.dump"
                assert "write_text" not in source, f"{name}: write_text"
                for forbidden in ("hkos.repository.repository_manager",
                                  "hkos.storage.storage_engine",
                                  "hkos.index.index_store"):
                    assert forbidden not in source, f"{name}: {forbidden}"

    def test_save_only_through_librarian(self, tmp_path: object) -> None:
        import tempfile
        from pathlib import Path

        from hkos.repository.models import Knowledge
        from tests.system.ds016.hermes_context import create_hermes_context

        ctx = create_hermes_context(Path(tempfile.mkdtemp()))
        project = ctx.project.create(name="SecQ", tags=["hermes"])
        result = ctx.save_after_task(project.id, Knowledge(
            title="SecQFact udp", body="udp", tags=["udp"]))
        assert result["saved"]
        assert ctx.repos.knowledge.count(project.id) == 1
