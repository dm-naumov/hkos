"""HKOS Snapshot Validator (DS-010 §15, IP-010)
==============================================
Проверяет:
- отсутствие битых ссылок (каждый id в references существует в Repository);
- корректность UUID;
- соответствие Repository (счётчики статистики);
- полноту структуры (все секции DS-010 §8 присутствуют).
"""

import re

from hkos.index.validation import ValidationResult
from hkos.kernel.snapshot_document import SnapshotDocument
from hkos.repository.repository_manager import RepositoryManager

__all__ = ["SnapshotValidator"]

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_REQUIRED_SECTIONS: tuple[str, ...] = (
    "Project Metadata",
    "Architecture",
    "Canonical Knowledge",
    "Accepted Decisions",
    "Configurations",
    "Known Failures",
    "Known Limitations",
    "Artifacts",
    "Open Questions",
    "Statistics",
)


class SnapshotValidator:
    """Валидация Snapshot (чтение Repository допустимо: проверка ссылок)."""

    def __init__(self, repositories: RepositoryManager) -> None:
        """Инициализация валидатора.

        Args:
            repositories: RepositoryManager (проверка существования ссылок).

        """
        self._repositories = repositories

    def validate(self, snapshot: SnapshotDocument) -> ValidationResult:
        """Проверить Snapshot.

        Args:
            snapshot: SnapshotDocument.

        Returns:
            ValidationResult.

        """
        errors: list[str] = []
        warnings: list[str] = []

        # Полнота структуры
        if not snapshot.snapshot_id:
            errors.append("Snapshot id is empty")
        if not snapshot.project_id:
            errors.append("Project id is empty")
        for name in _REQUIRED_SECTIONS:
            if name == "Statistics":
                continue
            if name not in snapshot.sections:
                warnings.append(f"Missing section: {name}")
        if not snapshot.statistics:
            warnings.append("Statistics section is empty")

        # UUID корректность
        if snapshot.project_id and not _UUID.match(snapshot.project_id):
            warnings.append(f"Project id is not a UUID: {snapshot.project_id!r}")

        # Битые ссылки: каждый reference существует в Repository
        broken: list[str] = []
        for reference in snapshot.references:
            if not _UUID.match(reference):
                warnings.append(f"Reference is not a UUID: {reference!r}")
                continue
            if not self._exists(snapshot.project_id, reference):
                broken.append(reference)
        if broken:
            errors.append(f"Broken references: {broken[:10]}")

        # Соответствие Repository (счётчики)
        try:
            knowledge_count = self._repositories.knowledge.count(snapshot.project_id)
            if snapshot.statistics.get("knowledge", -1) != knowledge_count:
                warnings.append(
                    f"Statistics mismatch: knowledge "
                    f"{snapshot.statistics.get('knowledge')} != repository {knowledge_count}"
                )
        except Exception:  # noqa: BLE001 — проект может отсутствовать
            warnings.append("Repository check unavailable")

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def _exists(self, project: str, entity_id: str) -> bool:
        """Существует ли сущность в Repository (по типам)."""
        for repository in (
            self._repositories.knowledge,
            self._repositories.decisions,
            self._repositories.artifacts,
            self._repositories.campaigns,
        ):
            try:
                if repository.exists(project, entity_id):
                    return True
            except Exception:  # noqa: BLE001 — репозиторий может не найти
                continue
        try:
            return self._repositories.projects.exists(entity_id)
        except Exception:  # noqa: BLE001
            return False
