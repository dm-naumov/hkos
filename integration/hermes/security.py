"""Hermes Integration Security (DS-012 ЭТАП 4)
================================================
Безопасная граница между внешним агентом и HKOS.

- CommandPermission: READ/WRITE/ADMIN модель разрешений;
- AgentContext: идентичность агента на каждую операцию;
- MigrationSafetyGuard: предохранитель опасных операций (migrate/rollback):
  свободный lock, активный project context, подтверждение, отсутствие
  FAILED-recovery состояния, отсутствие другого агента-мигранта.
"""

from dataclasses import dataclass
from typing import Callable, Final

from hkos.integration.hermes.schemas import (
    ERROR_TYPE_MIGRATION_FAILED,
    MigrationErrorResponse,
)
from hkos.migration.exceptions import MigrationLockError
from hkos.migration.migration_engine import MigrationEngine
from hkos.migration.migration_history import MigrationRecord

__all__ = [
    "PERMISSION_READ", "PERMISSION_WRITE", "PERMISSION_ADMIN",
    "COMMAND_PERMISSIONS", "AgentContext", "PermissionResult",
    "permission_for", "check_permission", "MigrationSafetyGuard",
]

PERMISSION_READ: Final[str] = "READ"
PERMISSION_WRITE: Final[str] = "WRITE"
PERMISSION_ADMIN: Final[str] = "ADMIN"

COMMAND_PERMISSIONS: Final[dict[str, str]] = {
    # READ — доступен всегда
    "migration.detect": PERMISSION_READ,
    "migration.status": PERMISSION_READ,
    "migration.history": PERMISSION_READ,
    "retrieval.preview": PERMISSION_READ,
    # WRITE — требует активный project context
    "knowledge.save": PERMISSION_WRITE,
    "context.update": PERMISSION_WRITE,
    # ADMIN — требует явное подтверждение
    "migration.migrate": PERMISSION_ADMIN,
    "migration.rollback": PERMISSION_ADMIN,
    "snapshot.refresh": PERMISSION_ADMIN,
    "index.rebuild": PERMISSION_ADMIN,
}


@dataclass(frozen=True)
class AgentContext:
    """Идентичность агента для каждой Hermes-операции (DS-012 §4)."""

    agent_id: str
    agent_type: str = "agent"
    session_id: str = ""
    project_id: str = ""
    campaign_id: str = ""


@dataclass(frozen=True)
class PermissionResult:
    """Результат проверки разрешения."""

    allowed: bool
    reason: str = ""
    required_confirmation: bool = False


def permission_for(command: str) -> str:
    """Уровень разрешения команды (PERMISSION_*; неизвестная — READ).

    Неизвестная команда обрабатывается реестром как unknown_command;
    здесь возвращается READ для совместимости с routing.
    """
    return COMMAND_PERMISSIONS.get(command, PERMISSION_READ)


def check_permission(
    command: str,
    agent: AgentContext,
    confirmed: bool = False,
) -> PermissionResult:
    """Правила (DS-012 §2):

    - READ доступен всегда;
    - WRITE требует активный project context (project_id не пуст);
    - ADMIN требует явное подтверждение (confirmed=True).
    """
    permission = permission_for(command)
    if permission == PERMISSION_READ:
        return PermissionResult(allowed=True)
    if permission == PERMISSION_WRITE:
        if not agent.project_id:
            return PermissionResult(
                allowed=False, reason="active project context required")
        return PermissionResult(allowed=True)
    # ADMIN
    if not confirmed:
        return PermissionResult(
            allowed=False, reason="explicit confirmation required",
            required_confirmation=True)
    if not agent.project_id:
        return PermissionResult(
            allowed=False, reason="active project context required")
    return PermissionResult(allowed=True)


class MigrationSafetyGuard:
    """Предохранитель опасных операций миграции (DS-012 §3)."""

    def __init__(
        self,
        engine: MigrationEngine,
        history_provider: Callable[[], list[MigrationRecord]] | None = None,
    ) -> None:
        """Инициализация.

        Args:
            engine: Публичный фасад MigrationEngine.
            history_provider: Источник истории (по умолчанию engine.history).

        """
        self._engine = engine
        self._history_provider = history_provider or engine.history

    def check(
        self, operation: str, agent: AgentContext, confirmed: bool
    ) -> MigrationErrorResponse | None:
        """Проверка перед опасной операцией.

        Returns:
            None — операция разрешена; иначе MigrationErrorResponse
            (recoverable=True) с причиной.

        """
        # 1. Migration lock свободен (пробой через публичный API)
        try:
            self._engine.acquire_lock()
            self._engine.release_lock()
        except MigrationLockError as exc:
            # исходное сообщение не теряется (DS-012 §3)
            return MigrationErrorResponse(
                error_type="migration_lock",
                message=f"Migration lock is held: {exc}",
                component="security",
                recoverable=True,
            )
        # 2. Активный project context
        if not agent.project_id:
            return MigrationErrorResponse(
                error_type=ERROR_TYPE_MIGRATION_FAILED,
                message="active project context required for migration",
                component="security",
                recoverable=True,
            )
        # 3. Подтверждение операции
        if not confirmed:
            return MigrationErrorResponse(
                error_type=ERROR_TYPE_MIGRATION_FAILED,
                message=f"{operation} requires explicit confirmation",
                component="security",
                recoverable=True,
            )
        # 4. Последняя миграция не в FAILED recovery состоянии
        last = self._history_provider()[-1] if self._history_provider() else None
        if last is not None and last.status == "failed":
            return MigrationErrorResponse(
                error_type=ERROR_TYPE_MIGRATION_FAILED,
                message="last migration failed (recovery required: validate/rollback)",
                component="security",
                recoverable=True,
            )
        return None
