"""HKOS Project Factory (DS-004 §7)
==================================
ProjectFactory отвечает ТОЛЬКО за создание проекта:

- генерирует UUID (внутренний идентификатор, DS-004 §12);
- создаёт project.json (через ProjectRepository);
- устанавливает версию схемы;
- заполняет обязательные поля;
- устанавливает начальное состояние CREATED.

Фабрика НЕ содержит логики открытия, архивации, валидации,
переименования и не обращается к Storage Engine напрямую —
только через ProjectRepository (RepositoryManager.projects).
"""

import uuid

from hkos.repository.models import Project
from hkos.repository.project_repository import ProjectRepository
from hkos.services.project_state import (
    PROJECT_STATE_CREATED,
)

__all__ = ["ProjectFactory"]

# Версия схемы проекта (конверт HKOS-08: schema "HKOS-1.0").
PROJECT_SCHEMA_VERSION: str = "1.0"


class ProjectFactory:
    """Фабрика создания проектов (единственная обязанность — создание)."""

    def __init__(self, repository: ProjectRepository) -> None:
        """Инициализация фабрики.

        Args:
            repository: ProjectRepository из RepositoryManager.projects.
        """
        self._repository = repository

    def create(
        self,
        name: str,
        description: str = "",
        owner: str = "",
        tags: list[str] | None = None,
    ) -> Project:
        """Создать проект и сохранить его через репозиторий.

        Args:
            name: Человекочитаемое имя проекта (уникальность проверяет Manager).
            description: Описание проекта.
            owner: Владелец проекта (метаданные DS-004 §11).
            tags: Теги проекта.

        Returns:
            Сохранённый Project с назначенным UUID и состоянием CREATED.
        """
        project = Project(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            status=PROJECT_STATE_CREATED,
            tags=list(tags) if tags else [],
            owner=owner,
            schema_version=PROJECT_SCHEMA_VERSION,
        )
        return self._repository.save(project)
