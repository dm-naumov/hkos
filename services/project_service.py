"""HKOS Project Service (DS-004 §4)
=================================
ProjectService — тонкий фасад над ProjectManager.

Намеренно НЕ содержит бизнес-логики: все вызовы делегируются
ProjectManager 1:1. Назначение — стабильная граница API для будущей
регистрации сервисов в Registry/DI (DS-012, Hermes Integration).

Решение по IP-004 этап 06: сервис не дублирует ProjectManager —
он является тонкой прокладкой без собственной логики.
"""

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Project
from hkos.services.project_manager import ProjectInfo, ProjectManager
from hkos.services.project_validator import ValidationResult

__all__ = ["ProjectService"]


class ProjectService:
    """Тонкий фасад сервисного слоя проектов (без логики)."""

    def __init__(self, manager: ProjectManager, logger: HKOSLogger) -> None:
        """Инициализация сервиса.

        Args:
            manager: ProjectManager (единственный источник операций).
            logger: HKOSLogger.
        """
        self._manager = manager
        self._logger = logger

    @property
    def manager(self) -> ProjectManager:
        """Внутренний ProjectManager."""
        return self._manager

    def create(
        self,
        name: str,
        description: str = "",
        owner: str = "",
        tags: list[str] | None = None,
    ) -> Project:
        """Создать проект (делегирование)."""
        return self._manager.create(
            name=name, description=description, owner=owner, tags=tags
        )

    def open(self, project_id: str) -> Project:
        """Открыть проект (делегирование)."""
        return self._manager.open(project_id)

    def close(self, project_id: str) -> Project:
        """Закрыть проект (делегирование)."""
        return self._manager.close(project_id)

    def archive(self, project_id: str) -> Project:
        """Архивировать проект (делегирование)."""
        return self._manager.archive(project_id)

    def delete(self, project_id: str) -> None:
        """Удалить проект (делегирование)."""
        self._manager.delete(project_id)

    def exists(self, project_id: str) -> bool:
        """Проверить существование (делегирование)."""
        return self._manager.exists(project_id)

    def info(self, project_id: str) -> ProjectInfo:
        """Информация о проекте (делегирование)."""
        return self._manager.info(project_id)

    def list(self) -> list[ProjectInfo]:
        """Список проектов (делегирование)."""
        return self._manager.list()

    def rename(self, project_id: str, new_name: str) -> Project:
        """Переименовать проект (делегирование)."""
        return self._manager.rename(project_id, new_name)

    def validate(self, project_id: str) -> ValidationResult:
        """Проверить проект (делегирование)."""
        return self._manager.validate(project_id)
