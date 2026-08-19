"""HKOS Index Validator (DS-007 §12)
==================================
Проверка целостности индексов проекта:

- соответствие Repository (индексированные сущности существуют);
- отсутствие битых ссылок (postings/relations ссылаются на индексированные id);
- отсутствие дубликатов;
- корректность UUID;
- корректность статистики (пересчёт из Entity Index).

Возвращает ValidationResult (валидатор НЕ изменяет индексы).
"""

import re
from typing import TypeAlias

from hkos.index.entity_index import EntityIndex
from hkos.index.index_store import IndexStore
from hkos.index.keyword_index import KeywordIndex
from hkos.index.relationship_index import RelationshipIndex
from hkos.index.statistics_index import StatisticsIndex
from hkos.index.tag_index import TagIndex
from hkos.index.validation import ValidationResult
from hkos.repository.artifact_repository import ArtifactRepository
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.decision_repository import DecisionRepository
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.project_repository import ProjectRepository
from hkos.repository.repository_manager import RepositoryManager

# Объединение типов репозиториев, доступных Index Layer через RepositoryManager.
EntityRepository: TypeAlias = (
    ProjectRepository
    | CampaignRepository
    | KnowledgeRepository
    | DecisionRepository
    | ArtifactRepository
)



__all__ = ["IndexValidator"]

# Канонический формат UUID: 8-4-4-4-12 hex.
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class IndexValidator:
    """Валидация индексов проекта (только чтение)."""

    def __init__(
        self, repositories: RepositoryManager, store: IndexStore
    ) -> None:
        """Инициализация валидатора.

        Args:
            repositories: RepositoryManager — проверка существования сущностей.
            store: IndexStore — чтение файлов индексов.

        """
        self._repositories = repositories
        self._store = store

    def _repository_for(self, entity_type: str) -> EntityRepository:
        """Репозиторий для типа сущности."""
        repositories: dict[str, EntityRepository] = {
            "campaign": self._repositories.campaigns,
            "knowledge": self._repositories.knowledge,
            "decision": self._repositories.decisions,
            "artifact": self._repositories.artifacts,
            "project": self._repositories.projects,
        }
        return repositories[entity_type]

    def validate(self, project: str) -> ValidationResult:
        """Проверить индексы проекта.

        Args:
            project: UUID проекта.

        Returns:
            ValidationResult с ошибками и предупреждениями.

        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Файлы существуют
        missing = [
            name
            for name in ("keyword", "tags", "entities", "relations", "statistics")
            if not self._store.exists(project, name)
        ]
        if missing:
            return ValidationResult(
                valid=False,
                errors=[f"Index files missing for project {project}: {missing}"],
            )

        keyword = KeywordIndex(self._store.read(project, "keyword"))
        tags = TagIndex(self._store.read(project, "tags"))
        entities = EntityIndex(self._store.read(project, "entities"))
        relations = RelationshipIndex(self._store.read(project, "relations"))
        statistics = StatisticsIndex(self._store.read(project, "statistics"))

        # 2. Entity Index: корректность UUID, отсутствие дубликатов
        indexed_ids = set(entities.ids())
        for entity_id in indexed_ids:
            if not UUID_PATTERN.match(entity_id):
                errors.append(f"Invalid UUID in entity index: {entity_id!r}")
        if len(indexed_ids) != len(entities.ids()):
            errors.append("Duplicate entity ids in entity index")

        # 3. Keyword Index: нет битых ссылок и дубликатов
        seen_entries: set[tuple[str, str]] = set()
        for word, entries in keyword.data().get("postings", {}).items():
            for entry in entries:
                entry_id = entry.get("id")
                if entry_id not in indexed_ids:
                    errors.append(
                        f"Keyword index broken link: word={word!r}, id={entry_id!r}"
                    )
                pair = (word, entry_id)
                if pair in seen_entries:
                    errors.append(f"Keyword index duplicate: word={word!r}, id={entry_id!r}")
                seen_entries.add(pair)

        # 4. Tag Index: нет битых ссылок и дубликатов
        seen_tags: set[tuple[str, str]] = set()
        for tag, entries in tags.data().get("tags", {}).items():
            for entry in entries:
                entry_id = entry.get("id")
                if entry_id not in indexed_ids:
                    errors.append(
                        f"Tag index broken link: tag={tag!r}, id={entry_id!r}"
                    )
                pair = (tag, entry_id)
                if pair in seen_tags:
                    errors.append(f"Tag index duplicate: tag={tag!r}, id={entry_id!r}")
                seen_tags.add(pair)

        # 5. Relationship Index: source/target существуют
        for records in relations.data().get("out", {}).values():
            for record in records:
                if record.get("source_id") not in indexed_ids:
                    errors.append(
                        f"Relation broken source: {record.get('source_id')!r}"
                    )
                if record.get("target_id") not in indexed_ids:
                    errors.append(
                        f"Relation broken target: {record.get('target_id')!r}"
                    )

        # 6. Statistics: пересчёт и сравнение
        recomputed = StatisticsIndex()
        recomputed.recompute(entities)
        recomputed.increment(
            "project", self._repositories.projects.count() - 1
        )
        for key, expected in recomputed.get().items():
            actual = statistics.get().get(key, 0)
            if actual != expected:
                errors.append(
                    f"Statistics mismatch: {key}: index={actual}, expected={expected}"
                )

        # 7. Соответствие Repository: индексированные сущности существуют
        for entity_id, record in entities.data().get("entities", {}).items():
            entity_type = record.get("type", "")
            if entity_type == "project":
                exists = self._repositories.projects.exists(entity_id)
            else:
                repository = self._repository_for(entity_type)
                exists = repository.exists(project, entity_id)
            if not exists:
                warnings.append(
                    f"Indexed entity missing in repository: "
                    f"{entity_type}:{entity_id}"
                )

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
