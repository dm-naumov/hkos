"""Hermes Integration Schemas (DS-012 ЭТАП 2)
================================================
Формальный контракт интеграции Hermes <-> HKOS MigrationEngine.

ТОЛЬКО typed contracts: dataclass-модели ответов + константы типов
ошибок + статический mapping исключений. НИКАКОЙ бизнес-логики.

Правила (DS-012 §5):
- НЕ импортирует MigrationManager/BackupManager/RollbackManager/
  Registry/Executor/Validator/FSM-состояния;
- разрешены: публичные типы MigrationEngine (исключения), стандартная
  типизация;
- внутренние классы migration НЕ копируются (внешние response-модели).
"""

from dataclasses import dataclass, field
from typing import Final, Type

from hkos.migration.exceptions import (
    MigrationError,
    MigrationLockError,
    MigrationValidationError,
)

__all__ = [
    "MigrationStatusResponse",
    "MigrationDetectResponse",
    "MigrationRecordResponse",
    "MigrationHistoryResponse",
    "MigrationOperationResponse",
    "MigrationErrorResponse",
    "ERROR_TYPE_MIGRATION_LOCK",
    "ERROR_TYPE_VALIDATION_FAILED",
    "ERROR_TYPE_MIGRATION_FAILED",
    "MIGRATION_ERROR_MAPPING",
]

# ---- типы ошибок (контракт DS-012 §3) ----

ERROR_TYPE_MIGRATION_LOCK: Final[str] = "migration_lock"
ERROR_TYPE_VALIDATION_FAILED: Final[str] = "validation_failed"
ERROR_TYPE_MIGRATION_FAILED: Final[str] = "migration_failed"

MIGRATION_ERROR_MAPPING: Final[dict[Type[Exception], str]] = {
    MigrationLockError: ERROR_TYPE_MIGRATION_LOCK,
    MigrationValidationError: ERROR_TYPE_VALIDATION_FAILED,
    MigrationError: ERROR_TYPE_MIGRATION_FAILED,
}


# ---- response-модели (внешний контракт) ----

@dataclass(frozen=True)
class MigrationStatusResponse:
    """Ответ команды migration.status (DS-012 §4)."""

    state: str
    current_version: int
    target_version: int
    lock_active: bool


@dataclass(frozen=True)
class MigrationDetectResponse:
    """Ответ команды migration.detect (DS-012 §4)."""

    current_version: int
    target_version: int
    pending_count: int
    mixed: bool


@dataclass(frozen=True)
class MigrationRecordResponse:
    """Запись истории миграции (внешнее представление; DS-012 §2)."""

    migration_id: str
    timestamp: str
    agent: str
    from_version: int
    to_version: int
    status: str
    duration_ms: int
    rolled_back: bool = False


@dataclass(frozen=True)
class MigrationHistoryResponse:
    """Ответ команды migration.history (DS-012 §4)."""

    entries: list[MigrationRecordResponse] = field(default_factory=list)


@dataclass(frozen=True)
class MigrationOperationResponse:
    """Ответ операционной команды (migrate/rollback/validate; DS-012 §4)."""

    operation: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class MigrationErrorResponse:
    """Единый error response Hermes (DS-012 §3)."""

    error_type: str
    message: str
    component: str = "migration"
    recoverable: bool = False
