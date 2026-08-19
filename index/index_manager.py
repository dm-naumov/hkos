"""HKOS Index Manager (DS-007 §4)
================================
Оркестрация индексов проекта: построение, обновление, валидация,
оптимизация, статистика, health.

IndexManager реализует RelationshipReader (Architectural Freeze,
условие 2) — единый контракт чтения отношений для Graph Index
и Retriever.
"""


from hkos.index.entity_index import EntityIndex
from hkos.index.exceptions import IndexNotFoundError
from hkos.index.index_builder import IndexBuilder, _index_doc
from hkos.index.index_store import IndexStore
from hkos.index.index_updater import IndexUpdater
from hkos.index.index_validator import IndexValidator
from hkos.index.keyword_index import KeywordIndex
from hkos.index.relationship_index import RelationshipIndex
from hkos.index.statistics_index import StatisticsIndex
from hkos.index.tag_index import TagIndex
from hkos.index.validation import ValidationResult
from hkos.repository.knowledge_relations import KnowledgeRelation
from hkos.repository.repository_manager import RepositoryManager

__all__ = ["IndexManager"]

# Имена файлов индексов (DS-007 §11).
_INDEX_FILES: tuple[str, ...] = (
    "keyword", "tags", "entities", "relations", "statistics",
)


class IndexManager:
    """Оркестратор индексов проекта (Builder + Updater + Validator)."""

    def __init__(
        self,
        repositories: RepositoryManager,
        store: IndexStore,
        builder: IndexBuilder | None = None,
        updater: IndexUpdater | None = None,
        validator: IndexValidator | None = None,
    ) -> None:
        """Инициализация менеджера.

        Args:
            repositories: RepositoryManager — чтение сущностей.
            store: IndexStore — персистентность индексов.
            builder/updater/validator: компоненты; создаются по умолчанию.

        """
        self._repositories = repositories
        self._store = store
        self._builder = builder if builder is not None else IndexBuilder(
            repositories, store
        )
        self._updater = updater if updater is not None else IndexUpdater(
            repositories, store
        )
        self._validator = (
            validator if validator is not None else IndexValidator(repositories, store)
        )

    @property
    def store(self) -> IndexStore:
        """Используемый IndexStore."""
        return self._store

    # --- Жизненный цикл индексов ---

    def build(self, project: str) -> None:
        """Полное построение индексов проекта."""
        self._builder.build(project)

    def rebuild(self, project: str) -> None:
        """Полное перестроение индексов проекта."""
        self._builder.rebuild(project)

    def update(self, project: str, entity_id: str, entity_type: str) -> None:
        """Инкрементальное обновление после изменения сущности."""
        self._updater.update(project, entity_id, entity_type)

    def remove(self, project: str, entity_id: str, entity_type: str) -> None:
        """Удаление сущности из индексов."""
        self._updater.remove(project, entity_id, entity_type)

    def validate(self, project: str) -> ValidationResult:
        """Проверить целостность индексов проекта."""
        return self._validator.validate(project)

    def optimize(self, project: str) -> None:
        """Оптимизация: дедупликация, удаление устаревшего, статистика.

        Не перестраивает из Repository — только уплотняет файлы индексов.
        """
        keyword = KeywordIndex(self._store.read(project, "keyword"))
        tags = TagIndex(self._store.read(project, "tags"))
        entities = EntityIndex(self._store.read(project, "entities"))
        relations = RelationshipIndex(self._store.read(project, "relations"))
        statistics = StatisticsIndex(self._store.read(project, "statistics"))

        records = entities.data()["entities"]

        # Keyword: пересборка postings из entity_words, без устаревших id
        deduped_keyword = KeywordIndex()
        for entity_id, words in keyword.data().get("entity_words", {}).items():
            record = records.get(entity_id)
            if record is None:
                continue  # устаревшая запись — отбрасывается
            deduped_keyword.add(
                entity_id, record["type"], record["project"], " ".join(words)
            )

        # Tags: пересборка из entity_tags, без устаревших id
        deduped_tags = TagIndex()
        for entity_id, entity_tags in tags.data().get("entity_tags", {}).items():
            record = records.get(entity_id)
            if record is None:
                continue
            deduped_tags.add(
                entity_id, record["type"], record["project"], entity_tags
            )

        # Статистика: пересчёт из Entity Index
        statistics.recompute(entities)

        self._store.write(project, "keyword", _index_doc(deduped_keyword.data()))
        self._store.write(project, "tags", _index_doc(deduped_tags.data()))
        self._store.write(project, "relations", _index_doc(relations.data()))
        self._store.write(project, "statistics", _index_doc(statistics.data()))

    def statistics(self, project: str) -> dict[str, int]:
        """Агрегированная статистика проекта (из statistics.idx).

        Raises:
            IndexNotFoundError: Если индекс не построен.

        """
        data = self._store.read(project, "statistics")
        if data is None:
            raise IndexNotFoundError(
                f"Statistics index not built for project {project}"
            )
        statistics = StatisticsIndex(data)
        return statistics.get()

    def health(self, project: str) -> dict[str, object]:
        """Состояние индексов проекта (без исключений)."""
        exists_map: dict[str, bool] = {
            name: self._store.exists(project, name) for name in _INDEX_FILES
        }
        status = "PASS" if all(exists_map.values()) else "FAIL"
        result: dict[str, object] = {
            "status": status,
            "project": project,
            "index_files": exists_map,
        }
        if all(exists_map.values()):
            entities = EntityIndex(self._store.read(project, "entities"))
            relations = RelationshipIndex(self._store.read(project, "relations"))
            result["entity_count"] = entities.count()
            result["edge_count"] = relations.edge_count()
        return result

    # --- RelationshipReader (Architectural Freeze, условие 2) ---

    def relations_of_knowledge(
        self, project: str, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        """Все отношения Knowledge (единый READ-контракт)."""
        relations = RelationshipIndex(self._store.read(project, "relations"))
        return relations.relations_of_knowledge(knowledge_id)

    def relations_of_project(self, project: str) -> list[KnowledgeRelation]:
        """Все отношения проекта (единый READ-контракт)."""
        relations = RelationshipIndex(self._store.read(project, "relations"))
        return relations.relations_of_project()
