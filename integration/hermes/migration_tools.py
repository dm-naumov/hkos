"""Hermes Migration Tools (DS-012 ЭТАП 3)
==========================================
Тонкие адаптеры: Hermes <-> MigrationEngine (публичный фасад DS-011 §6).

- ТОЛЬКО вызов публичных методов MigrationEngine и преобразование
  результата в схемы контракта (schemas.py);
- НЕ содержит миграционной логики; НЕ знает внутренних компонентов
  (Manager/Backup/Rollback/Registry/Executor/Validator);
- ошибки MigrationError-семейства преобразуются в MigrationErrorResponse
  с сохранением исходного сообщения; traceback фиксируется в логе
  (не скрывается).
"""

from hkos.core.logger import HKOSLogger
from hkos.integration.hermes.audit import (
    AUDIT_COMMAND_ALLOWED,
    AUDIT_COMMAND_DENIED,
    AUDIT_COMMAND_RECEIVED,
    AUDIT_MIGRATION_COMPLETED,
    AUDIT_MIGRATION_FAILED,
    AUDIT_MIGRATION_STARTED,
    AuditLogger,
)
from hkos.integration.hermes.schemas import (
    MIGRATION_ERROR_MAPPING,
    MigrationDetectResponse,
    MigrationErrorResponse,
    MigrationHistoryResponse,
    MigrationOperationResponse,
    MigrationRecordResponse,
    MigrationStatusResponse,
)
from hkos.integration.hermes.security import (
    AgentContext,
    MigrationSafetyGuard,
    check_permission,
)
from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_engine import MigrationEngine

__all__ = ["MigrationTools"]

# Состояния, при которых engine удерживает миграционный замок (§15a):
# замок активен от DETECTING до ROLLBACK; снят при IDLE/COMPLETED/FAILED.
_LOCKED_STATES = frozenset({
    "DETECTING", "BACKUP", "MIGRATING", "REBUILD_INDEX",
    "REGENERATE_SNAPSHOT", "VALIDATING", "ROLLBACK",
})

_DEFAULT_AGENT = AgentContext(agent_id="hermes")


class MigrationTools:
    """Адаптер команд Hermes к MigrationEngine (constructor DI).

    Safety boundary (DS-012 ЭТАП 4): каждая операция проходит
    permission check + audit; опасные операции (migrate/rollback) —
    дополнительно MigrationSafetyGuard.
    """

    def __init__(
        self,
        engine: MigrationEngine,
        logger: HKOSLogger | None = None,
        audit: AuditLogger | None = None,
        guard: MigrationSafetyGuard | None = None,
    ) -> None:
        """Инициализация адаптера.

        Args:
            engine: Публичный фасад MigrationEngine (единственная точка).
            logger: Логгер (traceback при ошибках не скрывается).
            audit: Журнал аудита (append-only).
            guard: Предохранитель опасных операций.

        """
        self._engine = engine
        self._logger = logger or HKOSLogger()
        self._audit = audit or AuditLogger()
        self._guard = guard or MigrationSafetyGuard(engine)

    def detect(
        self, agent: AgentContext | None = None
    ) -> MigrationDetectResponse | MigrationErrorResponse:
        """migration.detect -> MigrationDetectResponse."""
        agent = agent or _DEFAULT_AGENT
        denied = self._authorize("migration.detect", agent)
        if denied is not None:
            return denied
        try:
            info = self._engine.detect()
        except MigrationError as exc:
            return self._error(exc, agent, "migration.detect")
        return MigrationDetectResponse(
            current_version=info.current_version,
            target_version=info.target_version,
            pending_count=len(info.pending),
            mixed=info.mixed,
        )

    def status(
        self, agent: AgentContext | None = None
    ) -> MigrationStatusResponse | MigrationErrorResponse:
        """migration.status -> MigrationStatusResponse.

        Парсинг строки engine.status() ("STATE; current=N; target=M").
        """
        agent = agent or _DEFAULT_AGENT
        denied = self._authorize("migration.status", agent)
        if denied is not None:
            return denied
        try:
            raw = self._engine.status()
        except MigrationError as exc:
            return self._error(exc, agent, "migration.status")
        state, current, target = self._parse_status(raw)
        return MigrationStatusResponse(
            state=state,
            current_version=current,
            target_version=target,
            lock_active=state in _LOCKED_STATES,
        )

    def migrate(
        self, agent: AgentContext | None = None, confirmed: bool = False
    ) -> MigrationOperationResponse | MigrationErrorResponse:
        """migration.migrate -> MigrationOperationResponse.

        Опасная операция: permission (ADMIN) + MigrationSafetyGuard.
        """
        agent = agent or _DEFAULT_AGENT
        denied = self._authorize("migration.migrate", agent, confirmed)
        if denied is not None:
            return denied
        try:
            guard_error = self._guard.check("migration.migrate", agent, confirmed)
        except MigrationError as exc:
            return self._error(exc, agent, "migration.migrate")
        if guard_error is not None:
            self._audit.log(AUDIT_COMMAND_DENIED, agent.agent_id, "migration.migrate",
                            agent.project_id, agent.campaign_id, guard_error.message)
            return guard_error
        self._audit.log(AUDIT_MIGRATION_STARTED, agent.agent_id, "migration.migrate",
                        agent.project_id, agent.campaign_id, "started")
        try:
            self._engine.migrate()
        except MigrationError as exc:
            self._audit.log(AUDIT_MIGRATION_FAILED, agent.agent_id, "migration.migrate",
                            agent.project_id, agent.campaign_id, str(exc))
            return self._error(exc, agent, "migration.migrate")
        self._audit.log(AUDIT_MIGRATION_COMPLETED, agent.agent_id, "migration.migrate",
                        agent.project_id, agent.campaign_id, "completed")
        return MigrationOperationResponse(operation="migrate", status="completed")

    def rollback(
        self, agent: AgentContext | None = None, confirmed: bool = False
    ) -> MigrationOperationResponse | MigrationErrorResponse:
        """migration.rollback -> MigrationOperationResponse.

        Опасная операция: permission (ADMIN) + MigrationSafetyGuard.
        """
        agent = agent or _DEFAULT_AGENT
        denied = self._authorize("migration.rollback", agent, confirmed)
        if denied is not None:
            return denied
        try:
            guard_error = self._guard.check("migration.rollback", agent, confirmed)
        except MigrationError as exc:
            return self._error(exc, agent, "migration.rollback")
        if guard_error is not None:
            self._audit.log(AUDIT_COMMAND_DENIED, agent.agent_id, "migration.rollback",
                            agent.project_id, agent.campaign_id, guard_error.message)
            return guard_error
        self._audit.log(AUDIT_MIGRATION_STARTED, agent.agent_id, "migration.rollback",
                        agent.project_id, agent.campaign_id, "started")
        try:
            self._engine.rollback()
        except MigrationError as exc:
            self._audit.log(AUDIT_MIGRATION_FAILED, agent.agent_id, "migration.rollback",
                            agent.project_id, agent.campaign_id, str(exc))
            return self._error(exc, agent, "migration.rollback")
        self._audit.log(AUDIT_MIGRATION_COMPLETED, agent.agent_id, "migration.rollback",
                        agent.project_id, agent.campaign_id, "completed")
        return MigrationOperationResponse(operation="rollback", status="rolled_back")

    def validate(
        self, agent: AgentContext | None = None
    ) -> MigrationOperationResponse | MigrationErrorResponse:
        """migration.validate -> MigrationOperationResponse (READ)."""
        agent = agent or _DEFAULT_AGENT
        denied = self._authorize("migration.validate", agent)
        if denied is not None:
            return denied
        try:
            self._engine.validate()
        except MigrationError as exc:
            return self._error(exc, agent, "migration.validate")
        return MigrationOperationResponse(operation="validate", status="passed")

    def history(
        self, agent: AgentContext | None = None
    ) -> MigrationHistoryResponse | MigrationErrorResponse:
        """migration.history -> MigrationHistoryResponse."""
        agent = agent or _DEFAULT_AGENT
        denied = self._authorize("migration.history", agent)
        if denied is not None:
            return denied
        try:
            records = self._engine.history()
        except MigrationError as exc:
            return self._error(exc, agent, "migration.history")
        return MigrationHistoryResponse(entries=[
            MigrationRecordResponse(
                migration_id=record.migration_id,
                timestamp=record.timestamp,
                agent=record.agent,
                from_version=record.from_version,
                to_version=record.to_version,
                status=record.status,
                duration_ms=record.duration_ms,
                rolled_back=record.rolled_back,
            )
            for record in records
        ])

    # ---- внутренние помощники (без бизнес-логики) ----

    def _error(
        self,
        exc: MigrationError,
        agent: AgentContext,
        command: str,
    ) -> MigrationErrorResponse:
        """Преобразование исключения в единый error response.

        Исходное сообщение сохраняется; traceback логируется
        (не скрывается внутри адаптера).
        """
        # traceback не скрывается: фиксируется через базовый логгер
        try:
            self._logger.logger.error(
                f"Hermes migration error: {exc}", exc_info=True)
        except Exception:
            self._logger.error(f"Hermes migration error: {exc}")
        error_type = MIGRATION_ERROR_MAPPING.get(type(exc), "migration_failed")
        return MigrationErrorResponse(
            error_type=error_type,
            message=str(exc),
            component="migration",
            recoverable=error_type == "migration_lock",
        )

    def _authorize(
        self,
        command: str,
        agent: AgentContext,
        confirmed: bool = False,
    ) -> MigrationErrorResponse | None:
        """Permission check + аудит (COMMAND_RECEIVED/ALLOWED/DENIED)."""
        self._audit.log(AUDIT_COMMAND_RECEIVED, agent.agent_id, command,
                        agent.project_id, agent.campaign_id, "")
        result = check_permission(command, agent, confirmed=confirmed)
        if not result.allowed:
            self._audit.log(AUDIT_COMMAND_DENIED, agent.agent_id, command,
                            agent.project_id, agent.campaign_id, result.reason)
            return MigrationErrorResponse(
                error_type="migration_failed",
                message=result.reason,
                component="security",
                recoverable=True,
            )
        self._audit.log(AUDIT_COMMAND_ALLOWED, agent.agent_id, command,
                        agent.project_id, agent.campaign_id, "allowed")
        return None

    @staticmethod
    def _parse_status(raw: str) -> tuple[str, int, int]:
        """Разбор "STATE; current=N; target=M" (устойчив к формату)."""
        state = "UNKNOWN"
        current = 0
        target = 0
        for part in raw.split(";"):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                key, _, value = part.partition("=")
                try:
                    number = int(value.strip())
                except ValueError:
                    continue
                if key.strip() == "current":
                    current = number
                elif key.strip() == "target":
                    target = number
            else:
                state = part
        return state, current, target
