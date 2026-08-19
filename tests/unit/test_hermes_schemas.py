"""Unit tests: Hermes Integration Schemas (DS-012 ЭТАП 2)."""

import inspect

from hkos.integration.hermes.schemas import (
    ERROR_TYPE_MIGRATION_FAILED,
    ERROR_TYPE_MIGRATION_LOCK,
    ERROR_TYPE_VALIDATION_FAILED,
    MIGRATION_ERROR_MAPPING,
    MigrationDetectResponse,
    MigrationErrorResponse,
    MigrationHistoryResponse,
    MigrationOperationResponse,
    MigrationRecordResponse,
    MigrationStatusResponse,
)
from hkos.migration.exceptions import (
    MigrationError,
    MigrationLockError,
    MigrationValidationError,
)


class TestHermesSchemas:
    """Контракт интеграции: модели, поля, mapping, чистота."""

    def test_all_schemas_constructible(self) -> None:
        status = MigrationStatusResponse(
            state="COMPLETED", current_version=2, target_version=3, lock_active=False)
        detect = MigrationDetectResponse(
            current_version=1, target_version=3, pending_count=2, mixed=False)
        record = MigrationRecordResponse(
            migration_id="001", timestamp="t", agent="a", from_version=1,
            to_version=2, status="completed", duration_ms=10)
        history = MigrationHistoryResponse(entries=[record])
        operation = MigrationOperationResponse(operation="migrate", status="completed")
        error = MigrationErrorResponse(error_type="migration_failed", message="m")
        assert status.state == "COMPLETED"
        assert detect.pending_count == 2
        assert history.entries[0].migration_id == "001"
        assert operation.operation == "migrate"
        assert error.component == "migration"

    def test_required_fields_present(self) -> None:
        assert {f.name for f in MigrationStatusResponse.__dataclass_fields__.values()} == {
            "state", "current_version", "target_version", "lock_active",
        }
        assert {f.name for f in MigrationDetectResponse.__dataclass_fields__.values()} == {
            "current_version", "target_version", "pending_count", "mixed",
        }
        assert {f.name for f in MigrationRecordResponse.__dataclass_fields__.values()} == {
            "migration_id", "timestamp", "agent", "from_version", "to_version",
            "status", "duration_ms", "rolled_back",
        }
        assert {f.name for f in MigrationHistoryResponse.__dataclass_fields__.values()} == {
            "entries",
        }
        assert {f.name for f in MigrationOperationResponse.__dataclass_fields__.values()} == {
            "operation", "status", "message",
        }
        assert {f.name for f in MigrationErrorResponse.__dataclass_fields__.values()} == {
            "error_type", "message", "component", "recoverable",
        }

    def test_error_mapping(self) -> None:
        assert MIGRATION_ERROR_MAPPING[MigrationLockError] == ERROR_TYPE_MIGRATION_LOCK
        assert MIGRATION_ERROR_MAPPING[MigrationValidationError] == ERROR_TYPE_VALIDATION_FAILED
        assert MIGRATION_ERROR_MAPPING[MigrationError] == ERROR_TYPE_MIGRATION_FAILED
        assert MIGRATION_ERROR_MAPPING[MigrationLockError] == "migration_lock"
        assert MIGRATION_ERROR_MAPPING[MigrationValidationError] == "validation_failed"
        assert MIGRATION_ERROR_MAPPING[MigrationError] == "migration_failed"

    def test_no_internal_migration_imports(self) -> None:
        """schemas.py не импортирует внутренние компоненты migration."""
        source = inspect.getsource(
            __import__("hkos.integration.hermes.schemas", fromlist=["x"]))
        for forbidden in (
            "migration_manager", "backup_manager", "rollback_manager",
            "migration_registry", "migration_executor", "migration_validator",
            "schema_detector", "migration_engine",
        ):
            assert f"hkos.migration.{forbidden}" not in source, forbidden

    def test_no_business_logic(self) -> None:
        """schemas.py: только dataclass-модели и константы (нет функций)."""
        source = inspect.getsource(
            __import__("hkos.integration.hermes.schemas", fromlist=["x"]))
        assert "def " not in source
        assert "lambda" not in source

    def test_migration_engine_api_unchanged(self) -> None:
        """MigrationEngine API не изменён (7 публичных методов)."""
        from hkos.migration.migration_engine import MigrationEngine

        public = {m for m in dir(MigrationEngine) if not m.startswith("_")}
        assert {"detect", "migrate", "rollback", "validate",
                "backup", "history", "status"} <= public
