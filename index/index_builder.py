"""HKOS Index Builder (DS-007 §10, §14)
==================================
Полное построение/перестроение индексов проекта.

build(): O(N) чтений (все сущности проекта через RepositoryManager)
+ O(total tokens) записей; пишет 5 файлов индексов.
Используется при build()/rebuild()/миграции/массовом импорте.
"""

from typing import Any, TypeAlias

from hkos.index.entity_index import EntityIndex
from hkos.index.index_store import IndexStore
from hkos.index.keyword_index import KeywordIndex, indexable_text
from hkos.index.relationship_index import RelationshipIndex
from hkos.index.statistics_index import StatisticsIndex
from hkos.index.tag_index import TagIndex, indexable_tags
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



__all__ = ["IndexBuilder", "_index_doc"]


def _index_doc(data: dict[str, Any]) -> dict[str, Any]:
    """Обернуть данные индекса в документ файла индекса (JSON)."""
    return {
        "schema": "HKOS-1.0",
        "type": "index",
        "version": 1,
        "data": data,
    }


# Типы сущностей, индексируемые per-project (repo _type_name).
_ENTITY_TYPES: tuple[str, ...] = (
    "campaign",
    "knowledge",
    "decision",
    "artifact",
)


class IndexBuilder:
    """Построение полного набора индексов проекта."""

    def __init__(
        self, repositories: RepositoryManager, store: IndexStore
    ) -> None:
        """Инициализация строителя.

        Args:
            repositories: RepositoryManager — чтение сущностей.
            store: IndexStore — персистентность файлов индексов.

        """
        self._repositories = repositories
        self._store = store

    @staticmethod
    def _index_entity(
        entity: Any,
        entity_type: str,
        project: str,
        keyword: KeywordIndex,
        tags: TagIndex,
        entities: EntityIndex,
        relations: RelationshipIndex,
    ) -> None:
        """Добавить сущность во все индексы."""
        keyword.add(
            entity.id, entity_type, project, indexable_text(entity)
        )
        tags.add(
            entity.id, entity_type, project, indexable_tags(entity)
        )
        entities.upsert(entity, entity_type, project)
        if entity_type == "knowledge":
            relations.add_relations(entity.id, entity.relations)

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

    def build(self, project: str) -> None:
        """Построить индексы проекта (полная перестройка).

        Args:
            project: UUID проекта.

        """
        keyword = KeywordIndex()
        tags = TagIndex()
        entities = EntityIndex()
        relations = RelationshipIndex()
        statistics = StatisticsIndex()

        # Сам проект
        project_entity = self._repositories.projects.load(project)
        self._index_entity(project_entity, "project", project,
                           keyword, tags, entities, relations)

        # Сущности проекта
        for entity_type in _ENTITY_TYPES:
            repository = self._repository_for(entity_type)
            for entity in repository.list(project):
                self._index_entity(entity, entity_type, project,
                                   keyword, tags, entities, relations)

        # Статистика: пересчёт из Entity Index; projects — глобальный счётчик
        statistics.recompute(entities)
        statistics.increment(
            "project", self._repositories.projects.count() - 1
        )

        self._save(project, keyword, tags, entities, relations, statistics)

    def rebuild(self, project: str) -> None:
        """Полное перестроение (удаляет старые файлы и строит заново)."""
        for index_name in ("keyword", "tags", "entities", "relations", "statistics"):
            self._store.delete(project, index_name)
        self.build(project)

    def _save(
        self,
        project: str,
        keyword: KeywordIndex,
        tags: TagIndex,
        entities: EntityIndex,
        relations: RelationshipIndex,
        statistics: StatisticsIndex,
    ) -> None:
        """Записать 5 файлов индексов."""
        self._store.write(project, "keyword", _index_doc(keyword.data()))
        self._store.write(project, "tags", _index_doc(tags.data()))
        self._store.write(project, "entities", _index_doc(entities.data()))
        self._store.write(project, "relations", _index_doc(relations.data()))
        self._store.write(project, "statistics", _index_doc(statistics.data()))
