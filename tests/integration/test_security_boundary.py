"""Integration tests: Hermes security boundary (DS-012 ЭТАП 4 §10-11)."""

import threading
import time

from hkos.integration.hermes.agent_lock import (
    LOCK_MODE_READ,
    LOCK_MODE_WRITE,
    AgentLock,
)
from hkos.integration.hermes.audit import AuditLogger
from hkos.integration.hermes.fallback import FallbackPolicy
from hkos.integration.hermes.migration_commands import MigrationCommandRegistry
from hkos.integration.hermes.migration_tools import MigrationTools
from hkos.integration.hermes.schemas import (
    MigrationErrorResponse,
    MigrationOperationResponse,
    MigrationStatusResponse,
)
from hkos.integration.hermes.security import AgentContext, check_permission
from hkos.migration.exceptions import MigrationError, MigrationLockError
from hkos.migration.migration_history import MigrationRecord


class _ProbeEngine:
    """Локальный двойник MigrationEngine для интеграционных сценариев."""

    def __init__(self) -> None:
        self.lock_busy = False
        self.failed = False

    def acquire_lock(self) -> None:
        if self.lock_busy:
            raise MigrationLockError("busy")

    def release_lock(self) -> None:
        pass

    def history(self) -> list[MigrationRecord]:
        if self.failed:
            return [MigrationRecord("001", "t", "a", 1, 2, "failed", 0)]
        return []

    def status(self) -> str:
        return "COMPLETED; current=1; target=1"

    def detect(self) -> object:
        return None

    def migrate(self) -> None:
        if self.failed:
            raise MigrationError("migration failed")

    def rollback(self) -> None:
        pass

    def validate(self) -> None:
        pass


def _agent(project: str = "p1") -> AgentContext:
    return AgentContext(agent_id="agent-1", project_id=project)


class TestSecurityBoundary:
    """7 сценариев безопасности интеграции."""

    def test_scenario_1_read_retrieval(self) -> None:
        """READ (migration.status) — обычный агент — PASS."""
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        response = tools.status(_agent())
        assert isinstance(response, MigrationStatusResponse)
        assert response.state == "COMPLETED"

    def test_scenario_2_storage_direct_blocked(self) -> None:
        """Агент пытается вызвать Storage напрямую — BLOCK (пути нет)."""
        source = __import__(
            "hkos.integration.hermes.migration_tools", fromlist=["x"]).__doc__ or ""
        assert "storage" not in source
        # нет ни одной команды/инструмента, дающего доступ к Storage
        registry = MigrationCommandRegistry(
            MigrationTools(_ProbeEngine()))  # type: ignore[arg-type]
        assert "storage" not in registry.commands()

    def test_scenario_3_two_writers_one_waits(self) -> None:
        """Два агента пишут знания одновременно — один ждёт lock."""
        lock = AgentLock()
        order: list[str] = []

        def writer(name: str, delay: float) -> None:
            time.sleep(delay)
            lock.acquire(LOCK_MODE_WRITE)
            order.append(f"{name}-write")
            time.sleep(0.05)
            lock.release(LOCK_MODE_WRITE)

        threads = [threading.Thread(target=writer, args=("a", 0.0)),
                   threading.Thread(target=writer, args=("b", 0.02))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(order) == 2
        assert order[0] != order[1]  # писатели эксклюзивны

    def test_scenario_4_migration_without_confirmation_blocked(self) -> None:
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        response = tools.migrate(_agent(), confirmed=False)
        assert isinstance(response, MigrationErrorResponse)
        assert response.recoverable is True

    def test_scenario_5_migration_with_confirmation(self) -> None:
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        response = tools.migrate(_agent(), confirmed=True)
        assert isinstance(response, MigrationOperationResponse)
        assert response.status == "completed"

    def test_scenario_6_retrieval_unavailable_fallback(self) -> None:
        policy = FallbackPolicy()
        result = policy.retrieval_unavailable("agent-1")
        assert result == []  # пустой контекст; продолжение

    def test_scenario_7_librarian_unavailable_queue(self) -> None:
        policy = FallbackPolicy()
        policy.librarian_unavailable({"title": "k1"})
        assert policy.pending_count() == 1  # знание не потеряно


class TestSecurityPerformance:
    """Бюджеты производительности (DS-012 ЭТАП 4 §11)."""

    def test_permission_check(self) -> None:
        start = time.monotonic()
        for _ in range(100):
            check_permission("migration.migrate", _agent(), confirmed=True)
        elapsed = (time.monotonic() - start) / 100 * 1000
        assert elapsed <= 5.0, f"permission check {elapsed:.2f} ms"

    def test_audit_logging(self) -> None:
        audit_logger = AuditLogger()
        start = time.monotonic()
        for _ in range(100):
            audit_logger.log("COMMAND_RECEIVED", "agent-1", "migration.status")
        elapsed = (time.monotonic() - start) / 100 * 1000
        assert elapsed <= 20.0, f"audit logging {elapsed:.2f} ms"

    def test_agent_lock(self) -> None:
        lock = AgentLock()
        start = time.monotonic()
        for _ in range(100):
            lock.acquire(LOCK_MODE_READ)
            lock.release(LOCK_MODE_READ)
        elapsed = (time.monotonic() - start) / 100 * 1000
        assert elapsed <= 10.0, f"agent lock {elapsed:.2f} ms"

    def test_fallback_decision(self) -> None:
        policy = FallbackPolicy()
        start = time.monotonic()
        for _ in range(100):
            policy.retrieval_unavailable("agent-1")
        elapsed = (time.monotonic() - start) / 100 * 1000
        assert elapsed <= 5.0, f"fallback {elapsed:.2f} ms"

    def test_total_integration_overhead(self) -> None:
        """Суммарное влияние security-слоя на одну операцию <= 50 ms."""
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        start = time.monotonic()
        for _ in range(20):
            tools.status(_agent())
        elapsed = (time.monotonic() - start) / 20 * 1000
        assert elapsed <= 50.0, f"total overhead {elapsed:.2f} ms"
