"""Unit tests: AuditLogger (DS-012 ЭТАП 4 §5)."""

from hkos.integration.hermes.audit import (
    AUDIT_COMMAND_ALLOWED,
    AUDIT_COMMAND_DENIED,
    AUDIT_COMMAND_RECEIVED,
    AUDIT_MIGRATION_COMPLETED,
    AuditEntry,
    AuditLogger,
)


class TestAuditLogger:
    """Append-only журнал аудита."""

    def test_events_created(self) -> None:
        logger = AuditLogger()
        logger.log(AUDIT_COMMAND_RECEIVED, "agent-1", "migration.status")
        logger.log(AUDIT_COMMAND_ALLOWED, "agent-1", "migration.status", "p1")
        logger.log(AUDIT_COMMAND_DENIED, "agent-1", "migration.migrate", "p1")
        logger.log(AUDIT_MIGRATION_COMPLETED, "agent-1", "migration.migrate",
                   "p1", "c1", "completed")
        entries = logger.entries()
        assert [e.command for e in entries] == [
            "migration.status", "migration.status", "migration.migrate",
            "migration.migrate",
        ]
        assert entries[3].project_id == "p1"
        assert entries[3].campaign_id == "c1"

    def test_event_order_preserved(self) -> None:
        logger = AuditLogger()
        logger.append(AuditEntry("t1", "a", "c1"))
        logger.append(AuditEntry("t2", "a", "c2"))
        assert [e.timestamp for e in logger.entries()] == ["t1", "t2"]

    def test_append_only(self) -> None:
        """Нет update/delete/clear."""
        AuditLogger()
        assert not hasattr(AuditLogger, "clear")
        assert not hasattr(AuditLogger, "remove")
        assert not hasattr(AuditLogger, "update")
        api = {m for m in dir(AuditLogger) if not m.startswith("_")}
        assert api <= {"append", "entries", "log"}

    def test_entries_copy(self) -> None:
        audit_logger = AuditLogger()
        audit_logger.append(AuditEntry("t", "a", "c"))
        entries = audit_logger.entries()
        entries.append(AuditEntry("t2", "a", "c2"))
        assert len(audit_logger.entries()) == 1
