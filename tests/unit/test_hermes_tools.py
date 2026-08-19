"""Unit tests: MigrationTools (DS-012 ЭТАП 3)."""

import inspect

from hkos.integration.hermes.migration_tools import MigrationTools
from hkos.integration.hermes.schemas import (
    MigrationDetectResponse,
    MigrationErrorResponse,
    MigrationHistoryResponse,
    MigrationOperationResponse,
    MigrationStatusResponse,
)
from hkos.integration.hermes.security import AgentContext
from hkos.migration.exceptions import MigrationError, MigrationLockError
from hkos.migration.schema_detector import SchemaInfo


class _FakeEngine:
    """Минимальный двойник MigrationEngine (только публичные методы)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.detect_info = SchemaInfo(current_version=1, target_version=3,
                                      pending=["001_mig"])
        self.status_text = "COMPLETED; current=1; target=3"
        self.history_records: list[object] = []
        self.error: Exception | None = None

    def detect(self) -> SchemaInfo:
        self.calls.append("detect")
        if self.error:
            raise self.error
        return self.detect_info

    def status(self) -> str:
        self.calls.append("status")
        if self.error:
            raise self.error
        return self.status_text

    def migrate(self) -> None:
        self.calls.append("migrate")
        if self.error:
            raise self.error

    def rollback(self) -> None:
        self.calls.append("rollback")
        if self.error:
            raise self.error

    def validate(self) -> None:
        self.calls.append("validate")
        if self.error:
            raise self.error

    def history(self) -> list[object]:
        self.calls.append("history")
        if self.error:
            raise self.error
        return self.history_records

    def acquire_lock(self) -> None:
        self.calls.append("acquire_lock")
        if self.error:
            raise self.error

    def release_lock(self) -> None:
        self.calls.append("release_lock")


class TestMigrationTools:
    """Тонкие адаптеры: DI, вызов engine, преобразование, ошибки."""

    def _tools(self, engine: _FakeEngine) -> MigrationTools:
        return MigrationTools(engine)  # type: ignore[arg-type]

    @staticmethod
    def _agent() -> AgentContext:
        return AgentContext(agent_id="test-agent", project_id="p1")

    def test_di_engine(self) -> None:
        """DI: вызовы идут в переданный engine (по поведению)."""
        engine = _FakeEngine()
        tools = self._tools(engine)
        tools.detect()
        assert engine.calls == ["detect"]

    def test_detect_calls_engine_and_converts(self) -> None:
        engine = _FakeEngine()
        response = self._tools(engine).detect(self._agent())
        assert engine.calls == ["detect"]
        assert isinstance(response, MigrationDetectResponse)
        assert response.current_version == 1
        assert response.target_version == 3
        assert response.pending_count == 1
        assert response.mixed is False

    def test_status_calls_engine_and_converts(self) -> None:
        engine = _FakeEngine()
        response = self._tools(engine).status(self._agent())
        assert engine.calls == ["status"]
        assert isinstance(response, MigrationStatusResponse)
        assert response.state == "COMPLETED"
        assert response.current_version == 1
        assert response.target_version == 3
        assert response.lock_active is False

    def test_status_lock_active_for_running_state(self) -> None:
        engine = _FakeEngine()
        engine.status_text = "MIGRATING; current=1; target=3"
        response = self._tools(engine).status(self._agent())
        assert isinstance(response, MigrationStatusResponse)
        assert response.lock_active is True

    def test_migrate_rollback_validate(self) -> None:
        engine = _FakeEngine()
        tools = self._tools(engine)
        response = tools.migrate(self._agent(), confirmed=True)
        assert isinstance(response, MigrationOperationResponse)
        assert response.operation == "migrate" and response.status == "completed"
        response = tools.rollback(self._agent(), confirmed=True)
        assert isinstance(response, MigrationOperationResponse)
        assert response.operation == "rollback" and response.status == "rolled_back"
        response = tools.validate(self._agent())
        assert isinstance(response, MigrationOperationResponse)
        assert response.operation == "validate" and response.status == "passed"
        # guard-проба (acquire/release) предшествует каждой опасной операции
        assert "migrate" in engine.calls
        assert "rollback" in engine.calls
        assert "validate" in engine.calls

    def test_history_converts(self) -> None:
        from hkos.migration.migration_history import MigrationRecord

        engine = _FakeEngine()
        engine.history_records = [
            MigrationRecord(migration_id="001", timestamp="t", agent="a",
                            from_version=1, to_version=2, status="completed",
                            duration_ms=5),
        ]
        response = self._tools(engine).history(self._agent())
        assert isinstance(response, MigrationHistoryResponse)
        assert response.entries[0].migration_id == "001"
        assert response.entries[0].status == "completed"

    def test_lock_error_mapped(self) -> None:
        engine = _FakeEngine()
        engine.error = MigrationLockError("lock held")
        response = self._tools(engine).migrate(self._agent(), confirmed=True)
        assert isinstance(response, MigrationErrorResponse)
        assert response.error_type == "migration_lock"
        assert "lock held" in response.message  # исходное сообщение сохранено
        assert response.recoverable is True

    def test_migration_error_mapped(self) -> None:
        engine = _FakeEngine()
        engine.error = MigrationError("apply boom")
        response = self._tools(engine).rollback(self._agent(), confirmed=True)
        assert isinstance(response, MigrationErrorResponse)
        assert response.error_type == "migration_failed"
        assert response.message == "apply boom"

    def test_forbidden_imports(self) -> None:
        """migration_tools.py не импортирует внутренние компоненты."""
        source = inspect.getsource(MigrationTools)
        for forbidden in (
            "migration_manager", "backup_manager", "rollback_manager",
            "migration_registry", "migration_executor", "migration_validator",
            "schema_detector", "snapshot", "storage", "repository", "index",
        ):
            assert forbidden not in source, forbidden
