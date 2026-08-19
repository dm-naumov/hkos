"""Hermes Migration Commands (DS-012 ЭТАП 3)
==============================================
Декларативный командный слой: маршрутизация command -> tool.

- детерминированный; без состояния; без FSM; без истории; без retry;
- поток: input -> tool -> response;
- НЕ импортирует внутренние компоненты migration (только интеграционные
  schemas/tools).
"""

from collections.abc import Callable
from typing import Final

from hkos.integration.hermes.migration_tools import MigrationTools
from hkos.integration.hermes.schemas import MigrationErrorResponse
from hkos.integration.hermes.security import AgentContext

__all__ = ["MigrationCommandRegistry", "UNKNOWN_COMMAND_ERROR"]

UNKNOWN_COMMAND_ERROR: Final[str] = "unknown_command"

_DEFAULT_AGENT = AgentContext(agent_id="hermes")


class MigrationCommandRegistry:
    """Реестр Hermes-команд миграции (routing command -> tool).

    Команды детерминированы, без состояния, без FSM, без retry;
    поток: input -> tool -> response. Идентичность агента и подтверждение
    ADMIN-команд передаются в tool (safety boundary в tools).
    """

    def __init__(self, tools: MigrationTools) -> None:
        """Инициализация реестра (dependency injection tools).

        Args:
            tools: Адаптер MigrationTools (тонкий; без логики).

        """
        self._tools = tools
        self._commands: dict[str, Callable[..., object]] = {
            "migration.detect": tools.detect,
            "migration.status": tools.status,
            "migration.migrate": tools.migrate,
            "migration.rollback": tools.rollback,
            "migration.validate": tools.validate,
            "migration.history": tools.history,
        }

    def commands(self) -> list[str]:
        """Зарегистрированные команды (детерминированный порядок)."""
        return sorted(self._commands)

    def execute(
        self,
        command: str,
        agent: AgentContext | None = None,
        confirmed: bool = False,
    ) -> object:
        """Выполнить команду: input -> tool -> response.

        Args:
            command: Имя команды (например, "migration.status").
            agent: Идентичность агента (DS-012 §4).
            confirmed: Явное подтверждение ADMIN-команды.

        Returns:
            Response schema (или MigrationErrorResponse для неизвестной
            команды).

        """
        handler = self._commands.get(command)
        if handler is None:
            return MigrationErrorResponse(
                error_type=UNKNOWN_COMMAND_ERROR,
                message=f"Unknown command: {command!r}",
                component="hermes",
            )
        return handler(agent or _DEFAULT_AGENT, confirmed)
