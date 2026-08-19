"""HKOS Index Engine (DS-007 §4, §6)
================================
Публичный фасад Index Layer.

Публичный API (ровно эти методы): build, rebuild, update, remove,
validate, statistics, optimize, health + RelationshipReader
(relations_of_knowledge, relations_of_project — Architectural Freeze).

Расположение: индекс — компонент РЕПОЗИТОРНОГО уровня (слой между
repository и services). Сущности читаются ТОЛЬКО через RepositoryManager;
файлы индексов — через инжектированный IndexStore (единственная точка
storage-доступа в Index Layer). Dependency Rule не нарушается;
Retriever (DS-008) сможет использовать индекс без изменения Librarian.
"""

from hkos.core.logger import HKOSLogger
from hkos.index.index_cache import IndexCache
from hkos.index.index_manager import IndexManager
from hkos.index.index_store import IndexStore
from hkos.index.validation import ValidationResult
from hkos.repository.knowledge_relations import KnowledgeRelation
from hkos.repository.repository_manager import RepositoryManager

__all__ = ["IndexEngine"]

# Типы сущностей (repo _type_name).
ENTITY_TYPE_PROJECT: str = "project"
ENTITY_TYPE_CAMPAIGN: str = "campaign"
ENTITY_TYPE_KNOWLEDGE: str = "knowledge"
ENTITY_TYPE_DECISION: str = "decision"
ENTITY_TYPE_ARTIFACT: str = "artifact"

VALID_ENTITY_TYPES: frozenset[str] = frozenset({
    ENTITY_TYPE_PROJECT,
    ENTITY_TYPE_CAMPAIGN,
    ENTITY_TYPE_KNOWLEDGE,
    ENTITY_TYPE_DECISION,
    ENTITY_TYPE_ARTIFACT,
})


class IndexEngine:
    """Фасад Index Engine (единственная публичная точка Index Layer)."""

    def __init__(
        self,
        repositories: RepositoryManager,
        store: IndexStore,
        logger: HKOSLogger,
        manager: IndexManager | None = None,
        cache: "IndexCache | None" = None,
    ) -> None:
        """Инициализация Index Engine.

        Args:
            repositories: RepositoryManager — чтение сущностей.
            store: IndexStore — персистентность файлов индексов.
            logger: HKOSLogger — системное журналирование.
            manager: IndexManager; создаётся по умолчанию.
            cache: Внутренний кэш Index Layer (DS-013 ЭТАП 3);
                инвалидируется при update/rebuild/build/remove.

        """
        self._repositories = repositories
        self._store = store
        self._logger = logger
        self._cache = cache
        self._manager = manager if manager is not None else IndexManager(
            repositories, store
        )

    @property
    def manager(self) -> IndexManager:
        """Внутренний IndexManager."""
        return self._manager

    @property
    def store(self) -> IndexStore:
        """IndexStore (персистентность индексов)."""
        return self._store

    def _check_type(self, entity_type: str) -> None:
        """Проверить допустимость типа сущности."""
        if entity_type not in VALID_ENTITY_TYPES:
            from hkos.index.exceptions import IndexError

            raise IndexError(f"Invalid entity type: {entity_type!r}")

    def build(self, project: str) -> None:
        """Построить индексы проекта (полное построение)."""
        self._manager.build(project)
        if self._cache is not None:
            self._cache.invalidate(project)
        self._logger.info(f"Index Created: project={project}")

    def rebuild(self, project: str) -> None:
        """Полное перестроение индексов проекта."""
        self._manager.rebuild(project)
        if self._cache is not None:
            self._cache.invalidate(project)
        self._logger.info(f"Index Rebuilt: project={project}")

    def update(
        self, project: str, entity_id: str, entity_type: str
    ) -> None:
        """Инкрементальное обновление индексов для сущности."""
        self._check_type(entity_type)
        if self._cache is not None:
            self._cache.invalidate(project)
        self._manager.update(project, entity_id, entity_type)
        self._logger.info(
            f"Index Updated: project={project}, entity={entity_type}:{entity_id}"
        )

    def remove(
        self, project: str, entity_id: str, entity_type: str
    ) -> None:
        """Удалить сущность из индексов."""
        self._check_type(entity_type)
        if self._cache is not None:
            self._cache.invalidate(project)
        self._manager.remove(project, entity_id, entity_type)
        self._logger.info(
            f"Index Removed: project={project}, entity={entity_type}:{entity_id}"
        )

    def validate(self, project: str) -> ValidationResult:
        """Проверить целостность индексов проекта."""
        result = self._manager.validate(project)
        self._logger.info(
            f"Index Validated: project={project}, valid={result.valid}"
        )
        return result

    def statistics(self, project: str) -> dict[str, int]:
        """Агрегированная статистика проекта."""
        return self._manager.statistics(project)

    def optimize(self, project: str) -> None:
        """Оптимизировать индексы проекта."""
        self._manager.optimize(project)
        self._logger.info(f"Index Optimized: project={project}")

    def health(self, project: str) -> dict[str, object]:
        """Состояние индексов проекта."""
        return self._manager.health(project)

    # --- RelationshipReader (Architectural Freeze, условие 2) ---

    def relations_of_knowledge(
        self, project: str, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        """Все отношения Knowledge (единый READ-контракт)."""
        return self._manager.relations_of_knowledge(project, knowledge_id)

    def relations_of_project(self, project: str) -> list[KnowledgeRelation]:
        """Все отношения проекта (единый READ-контракт)."""
        return self._manager.relations_of_project(project)
