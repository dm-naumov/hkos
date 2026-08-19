"""HKOS Index Updater (DS-007 §8-9, §14)
=====================================
Инкрементальное обновление индексов.

Алгоритм update(project, entity_id, entity_type):
1. Прочитать 5 файлов индексов (если отсутствуют — начать с пустых);
2. Удалить старые записи сущности (по внутренним картам индексов:
   entity_words / entity_tags / entity_relations / entities) — O(размер сущности);
3. Прочитать ОДНУ сущность через RepositoryManager (1 документ);
4. Добавить новые записи во все индексы;
5. Статистика — дельта (O(1));
6. Записать файлы индексов (до 5).

Свойства: не перечитывает весь Repository; не перестраивает индекс;
объём работы пропорционален размеру изменения (DS-007 §14).
"""

from typing import Any, TypeAlias

from hkos.index.entity_index import EntityIndex
from hkos.index.index_builder import _index_doc
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



__all__ = ["IndexUpdater"]


class IndexUpdater:
    """Инкрементальное обновление индексов (дельта-изменения)."""

    def __init__(
        self, repositories: RepositoryManager, store: IndexStore
    ) -> None:
        """Инициализация апдейтера.

        Args:
            repositories: RepositoryManager — чтение сущностей.
            store: IndexStore — персистентность файлов индексов.

        """
        self._repositories = repositories
        self._store = store

    def _load_indexes(
        self, project: str
    ) -> tuple[
        KeywordIndex, TagIndex, EntityIndex, RelationshipIndex, StatisticsIndex
    ]:
        """Загрузить все 5 индексов (пустые, если файлов нет)."""
        return (
            KeywordIndex(self._store.read(project, "keyword")),
            TagIndex(self._store.read(project, "tags")),
            EntityIndex(self._store.read(project, "entities")),
            RelationshipIndex(self._store.read(project, "relations")),
            StatisticsIndex(self._store.read(project, "statistics")),
        )

    def _load_entity(self, entity_type: str, project: str, entity_id: str) -> Any:
        """Прочитать ОДНУ сущность через RepositoryManager."""
        if entity_type == "project":
            return self._repositories.projects.load(entity_id)
        if entity_type == "campaign":
            return self._repositories.campaigns.load(project, entity_id)
        if entity_type == "knowledge":
            return self._repositories.knowledge.load(project, entity_id)
        if entity_type == "decision":
            return self._repositories.decisions.load(project, entity_id)
        return self._repositories.artifacts.load(project, entity_id)

    def _save(
        self,
        project: str,
        keyword: KeywordIndex,
        tags: TagIndex,
        entities: EntityIndex,
        relations: RelationshipIndex,
        statistics: StatisticsIndex,
    ) -> None:
        """Записать файлы индексов."""
        self._store.write(project, "keyword", _index_doc(keyword.data()))
        self._store.write(project, "tags", _index_doc(tags.data()))
        self._store.write(project, "entities", _index_doc(entities.data()))
        self._store.write(project, "relations", _index_doc(relations.data()))
        self._store.write(project, "statistics", _index_doc(statistics.data()))

    def update(
        self, project: str, entity_id: str, entity_type: str
    ) -> None:
        """Инкрементально обновить индексы для одной сущности.

        Args:
            project: UUID проекта.
            entity_id: UUID сущности.
            entity_type: project|campaign|knowledge|decision|artifact.

        """
        keyword, tags, entities, relations, statistics = self._load_indexes(
            project
        )
        old_record = entities.get(entity_id)

        # 1. Удалить старые записи (по внутренним картам, без чтения Repository)
        keyword.remove(entity_id)
        tags.remove(entity_id)
        if entity_type == "knowledge":
            relations.remove_relations(entity_id)
        entities.remove(entity_id)

        # 2. Прочитать сущность (1 документ)
        entity = self._load_entity(entity_type, project, entity_id)

        # 3. Добавить новые записи
        keyword.add(entity.id, entity_type, project, indexable_text(entity))
        tags.add(entity.id, entity_type, project, indexable_tags(entity))
        entities.upsert(entity, entity_type, project)
        if entity_type == "knowledge":
            relations.add_relations(entity.id, entity.relations)

        # 4. Статистика — дельта
        if old_record is not None:
            old_type = old_record["type"]
            if old_type != entity_type:
                statistics.increment(old_type, -1)
                statistics.increment(entity_type, 1)
        else:
            statistics.increment(entity_type, 1)

        self._save(project, keyword, tags, entities, relations, statistics)

    def remove(
        self, project: str, entity_id: str, entity_type: str
    ) -> None:
        """Удалить сущность из индексов (без чтения Repository).

        Args:
            project: UUID проекта.
            entity_id: UUID сущности.
            entity_type: project|campaign|knowledge|decision|artifact.

        """
        keyword, tags, entities, relations, statistics = self._load_indexes(
            project
        )
        old_record = entities.get(entity_id)

        keyword.remove(entity_id)
        tags.remove(entity_id)
        if entity_type == "knowledge":
            relations.remove_relations(entity_id)
        entities.remove(entity_id)
        if old_record is not None:
            statistics.increment(old_record["type"], -1)

        self._save(project, keyword, tags, entities, relations, statistics)
