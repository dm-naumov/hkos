"""HKOS Project Validator (DS-004 §8)
====================================
ProjectValidator проверяет проект и возвращает ValidationResult.

Проверки (только через ProjectRepository):
- существование проекта и его структуры;
- корректность Repository (документ загружается без ошибок);
- формат UUID;
- наличие обязательных полей;
- корректность версии схемы;
- допустимость состояния;
- целостность JSON (документ парсится репозиторием).

Валидатор НЕ бросает исключения по результатам проверки —
возвращает ValidationResult(valid, errors, warnings).
"""

import re

from hkos.repository.exceptions import (
    RepositoryNotFoundError,
    RepositoryParseError,
)
from hkos.repository.project_repository import ProjectRepository
from hkos.services.project_state import VALID_PROJECT_STATES

__all__ = ["ProjectValidator", "ValidationResult"]

# Канонический формат UUID: 8-4-4-4-12 hex.
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class ValidationResult:
    """Результат валидации проекта (DS-004 §8).

    NOTE (Audit Remediation DS-009A, задача 2): поведенчески идентичный
    ValidationResult существует в hkos/index/validation.py (DS-007).
    Консолидация в единый kernel-тип ОТЛОЖЕНА: объединение изменило бы
    идентичность публичных классов (isinstance-семантику между слоями)
    и потребовало бы модификации замороженных модулей — нарушение
    Architectural Freeze. Долг задокументирован (Managed Technical
    Debt, владелец: общий kernel-модуль / DS-011).
    """

    def __init__(
        self,
        valid: bool,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        """Инициализация результата.

        Args:
            valid: Прошёл ли проект проверку.
            errors: Критические проблемы.
            warnings: Некритические замечания.
        """
        self.valid = valid
        self.errors: list[str] = list(errors) if errors else []
        self.warnings: list[str] = list(warnings) if warnings else []

    def __bool__(self) -> bool:
        """Проект валиден."""
        return self.valid

    def as_dict(self) -> dict[str, object]:
        """Результат как словарь."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ProjectValidator:
    """Валидатор проектов (единственная обязанность — проверка)."""

    def __init__(self, repository: ProjectRepository) -> None:
        """Инициализация валидатора.

        Args:
            repository: ProjectRepository из RepositoryManager.projects.
        """
        self._repository = repository

    def validate(self, project_id: str) -> ValidationResult:
        """Проверить проект по id.

        Args:
            project_id: UUID проекта.

        Returns:
            ValidationResult с ошибками и предупреждениями.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not self._repository.exists(project_id):
            return ValidationResult(
                valid=False,
                errors=[f"Project not found: {project_id}"],
            )

        try:
            project = self._repository.load(project_id)
        except (RepositoryNotFoundError, RepositoryParseError) as e:
            return ValidationResult(
                valid=False,
                errors=[f"Repository error for {project_id}: {e}"],
            )

        if not UUID_PATTERN.match(project.id):
            errors.append(f"Invalid UUID: {project.id!r}")
        if not project.name:
            errors.append("Project name is empty (mandatory field)")
        if not project.schema_version:
            errors.append("Schema version is empty (mandatory field)")
        else:
            if not project.schema_version.startswith("1."):
                warnings.append(
                    f"Schema version {project.schema_version!r} is not in 1.x series"
                )
        if project.status.upper() not in VALID_PROJECT_STATES:
            errors.append(
                f"Invalid project state: {project.status!r}; "
                f"allowed: {sorted(VALID_PROJECT_STATES)}"
            )
        elif project.status != project.status.upper():
            warnings.append(
                f"Legacy lowercase project state: {project.status!r} "
                f"(DS-003); canonical: {project.status.upper()}"
            )
        if not project.created_at:
            warnings.append("created_at is missing in document envelope")

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
