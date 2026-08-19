"""HKOS Project Manager (DS-004 §5-6)
====================================
ProjectManager — сервис жизненного цикла проектов HKOS.

Единственная точка управления проектами. Работает ТОЛЬКО поверх
RepositoryManager.projects; прямой доступ к Storage Engine запрещён
(IP-004 §07).

Публичный API (ровно эти методы, без дополнительных):
    create, open, close, archive, delete, exists, info, list,
    rename, validate

Композиция (DI): фабрика — создание, валидатор — проверка,
машина состояний — переходы. Менеджер — оркестрация.
"""

from hkos.core.logger import HKOSLogger
from hkos.repository.exceptions import RepositoryNotFoundError
from hkos.repository.models import Project
from hkos.repository.project_repository import ProjectRepository
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.exceptions import (
    ProjectNameConflictError,
    ProjectNotFoundError,
    ProjectStateError,
)
from hkos.services.project_factory import ProjectFactory
from hkos.services.project_state import (
    PROJECT_STATE_ACTIVE,
    PROJECT_STATE_ARCHIVED,
    PROJECT_STATE_CREATED,
    PROJECT_STATE_DELETED,
    PROJECT_STATE_PAUSED,
    ProjectState,
)
from hkos.services.project_validator import (
    ProjectValidator,
    ValidationResult,
)

__all__ = ["ProjectManager"]


class ProjectInfo:
    """Информация о проекте (метаданные DS-004 §11)."""

    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        created_at: str,
        updated_at: str,
        status: str,
        schema_version: str,
        owner: str,
        tags: list[str],
        statistics: dict[str, object],
    ) -> None:
        """Инициализация информации о проекте."""
        self.id = id
        self.name = name
        self.description = description
        self.created_at = created_at
        self.updated_at = updated_at
        self.status = status
        self.schema_version = schema_version
        self.owner = owner
        self.tags = list(tags)
        self.statistics = dict(statistics)

    @classmethod
    def from_project(cls, project: Project) -> "ProjectInfo":
        """Собрать ProjectInfo из сущности Project."""
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
            status=project.status,
            schema_version=project.schema_version,
            owner=project.owner,
            tags=project.tags,
            statistics=project.statistics,
        )

    def as_dict(self) -> dict[str, object]:
        """Информация как словарь."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "schema_version": self.schema_version,
            "owner": self.owner,
            "tags": self.tags,
            "statistics": self.statistics,
        }


class ProjectManager:
    """Оркестрация жизненного цикла проектов.

    Состояния (DS-004 §9): CREATED -> ACTIVE -> PAUSED <-> ACTIVE,
    CREATED/ACTIVE/PAUSED -> ARCHIVED -> DELETED (терминальное).
    """

    # Операции, допускающие переименование (политика менеджера).
    _RENAMEABLE_STATES: frozenset[str] = frozenset({
        PROJECT_STATE_CREATED,
        PROJECT_STATE_ACTIVE,
        PROJECT_STATE_PAUSED,
    })

    def __init__(
        self,
        repositories: RepositoryManager,
        logger: HKOSLogger,
        factory: ProjectFactory | None = None,
        validator: ProjectValidator | None = None,
    ) -> None:
        """Инициализация Project Manager.

        Args:
            repositories: RepositoryManager (Sprint 3) — доступ через .projects.
            logger: HKOSLogger (Sprint 1) — журналирование операций.
            factory: ProjectFactory; создаётся по умолчанию (DI-конвенция).
            validator: ProjectValidator; создаётся по умолчанию.
        """
        self._repositories = repositories
        self._projects: ProjectRepository = repositories.projects
        self._logger = logger
        self._factory = factory if factory is not None else ProjectFactory(
            self._projects
        )
        self._validator = (
            validator if validator is not None else ProjectValidator(self._projects)
        )

    def _load(self, project_id: str) -> Project:
        """Загрузить проект или поднять ProjectNotFoundError."""
        try:
            return self._projects.load(project_id)
        except RepositoryNotFoundError as e:
            raise ProjectNotFoundError(
                f"Project not found: {project_id}"
            ) from e

    def _save(self, project: Project) -> Project:
        """Сохранить проект."""
        return self._projects.update(project)

    def _transition(self, project: Project, target: str) -> Project:
        """Применить переход состояния и сохранить проект."""
        state = ProjectState(project.status)
        state.transition_to(target)
        project.status = state.current
        return self._save(project)

    def _check_name_free(self, name: str, exclude_id: str = "") -> None:
        """Проверить уникальность имени (DS-004 §12)."""
        for other in self._projects.list():
            if other.id != exclude_id and other.name == name:
                raise ProjectNameConflictError(
                    f"Project name already in use: {name!r}"
                )

    def create(
        self,
        name: str,
        description: str = "",
        owner: str = "",
        tags: list[str] | None = None,
    ) -> Project:
        """Создать проект (CREATED).

        Raises:
            ProjectNameConflictError: Если имя занято.
        """
        self._check_name_free(name)
        project = self._factory.create(
            name=name, description=description, owner=owner, tags=tags
        )
        self._logger.info(f"Project Created: {project.id} ({project.name})")
        return project

    def open(self, project_id: str) -> Project:
        """Открыть проект (CREATED/PAUSED -> ACTIVE)."""
        project = self._load(project_id)
        project = self._transition(project, PROJECT_STATE_ACTIVE)
        self._logger.info(f"Project Opened: {project_id}")
        return project

    def close(self, project_id: str) -> Project:
        """Закрыть проект (ACTIVE -> PAUSED)."""
        project = self._load(project_id)
        project = self._transition(project, PROJECT_STATE_PAUSED)
        self._logger.info(f"Project Closed: {project_id}")
        return project

    def archive(self, project_id: str) -> Project:
        """Архивировать проект (CREATED/ACTIVE/PAUSED -> ARCHIVED)."""
        project = self._load(project_id)
        project = self._transition(project, PROJECT_STATE_ARCHIVED)
        self._logger.info(f"Project Archived: {project_id}")
        return project

    def delete(self, project_id: str) -> None:
        """Удалить проект (любое состояние -> DELETED, документ удаляется).

        Raises:
            ProjectNotFoundError: Если проект отсутствует.
        """
        project = self._load(project_id)
        state = ProjectState(project.status)
        state.transition_to(PROJECT_STATE_DELETED)
        self._projects.delete(project_id)
        self._logger.info(f"Project Deleted: {project_id}")

    def exists(self, project_id: str) -> bool:
        """Проверить существование проекта."""
        return self._projects.exists(project_id)

    def info(self, project_id: str) -> ProjectInfo:
        """Информация о проекте (метаданные DS-004 §11)."""
        return ProjectInfo.from_project(self._load(project_id))

    def list(self) -> list[ProjectInfo]:
        """Список всех проектов (информация, не сущности)."""
        return [
            ProjectInfo.from_project(project) for project in self._projects.list()
        ]

    def rename(self, project_id: str, new_name: str) -> Project:
        """Переименовать проект (CREATED/ACTIVE/PAUSED).

        Raises:
            ProjectNameConflictError: Если имя занято другим проектом.
            ProjectStateError: Если проект в ARCHIVED/DELETED.
        """
        project = self._load(project_id)
        if project.status not in self._RENAMEABLE_STATES:
            state = ProjectState(project.status)
            raise ProjectStateError(
                f"Rename is not allowed in state {state.current}"
            )
        self._check_name_free(new_name, exclude_id=project_id)
        project.name = new_name
        saved = self._save(project)
        self._logger.info(f"Project Renamed: {project_id} -> {new_name}")
        return saved

    def validate(self, project_id: str) -> ValidationResult:
        """Проверить проект (DS-004 §8).

        Returns:
            ValidationResult (валидатор не бросает по результатам проверки).
        """
        result = self._validator.validate(project_id)
        if not result.valid:
            self._logger.warning(
                f"Validation Failed: {project_id}: {result.errors}"
            )
        return result
