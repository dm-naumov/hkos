"""HKOS Query Contract Implementation (HKOS-INDEX-CONTRACT-001, FROZEN)
=========================================================================
Единый фасад чтения индексов — реализация Query Contract Q1–Q5.

Q1 Keyword Query      keyword_search(project, word) -> list[IndexEntry]
Q2 Tag Query          tag_search(project, tag) -> list[IndexEntry]
Q3 Entity Query       entity_get(project, entity_id) -> EntityRecord | None
Q4 Relationship Query relations_of_knowledge / relations_of_project
Q5 Statistics Query   statistics(project) -> dict[str, int]

Расположение: Index Layer (владеет IndexStore). Потребители (Retriever,
Graph, Semantic, Snapshot) зависят ТОЛЬКО от QueryContract-интерфейса
и никогда не касаются IndexStore/файлов индексов (контракт Section 2,
Section 10-11).

Новый модуль; публичные API DS-007 (IndexEngine и классы индексов)
не изменены.
"""

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from hkos.index.entity_index import EntityIndex
from hkos.index.index_cache import IndexCache
from hkos.index.index_store import IndexStore
from hkos.index.keyword_index import KeywordIndex
from hkos.index.relationship_index import RelationshipIndex
from hkos.index.statistics_index import StatisticsIndex
from hkos.index.tag_index import TagIndex
from hkos.repository.knowledge_relations import KnowledgeRelation

__all__ = [
    "IndexEntry",
    "EntityRecord",
    "QueryContract",
    "IndexSnapshot",
    "IndexQueryExecutor",
]


@dataclass
class IndexEntry:
    """Запись постинг-листа (Q1/Q2): ссылка на проиндексированную сущность."""

    id: str
    type: str
    project: str

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "IndexEntry":
        """Запись из словаря индекса."""
        return cls(
            id=str(data.get("id", "")),
            type=str(data.get("type", "")),
            project=str(data.get("project", "")),
        )


@dataclass
class EntityRecord:
    """Метаданные сущности из Entity Index (Q3)."""

    id: str
    project: str
    type: str
    title: str = ""
    status: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "EntityRecord":
        """Запись из словаря Entity Index."""
        tags = data.get("tags", [])
        return cls(
            id=str(data.get("id", "")),
            project=str(data.get("project", "")),
            type=str(data.get("type", "")),
            title=str(data.get("title", "")),
            status=str(data.get("status", "")),
            category=str(data.get("category", "")),
            tags=[str(t) for t in tags] if isinstance(tags, list) else [],
            updated_at=str(data.get("updated_at", "")),
        )


@runtime_checkable
class QueryContract(Protocol):
    """Query Contract Q1–Q5 (FROZEN, HKOS-INDEX-CONTRACT-001 Section 2).

    Потребители контракта НЕ зависят от формата хранения индекса
    (JSON/SQLite/иной движок) и от структуры файлов.
    """

    def keyword_search(
        self, project: str, word: str
    ) -> list[IndexEntry]:
        """Q1: сущности по точному токену (lower-case)."""
        ...

    def tag_search(self, project: str, tag: str) -> list[IndexEntry]:
        """Q2: сущности по тегу."""
        ...

    def entity_get(self, project: str, entity_id: str) -> EntityRecord | None:
        """Q3: метаданные сущности (или None)."""
        ...

    def relations_of_knowledge(
        self, project: str, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        """Q4: отношения Knowledge."""
        ...

    def relations_of_project(
        self, project: str
    ) -> list[KnowledgeRelation]:
        """Q4: все отношения проекта."""
        ...

    def statistics(self, project: str) -> dict[str, int]:
        """Q5: агрегированные счётчики проекта."""
        ...


class IndexSnapshot:
    """Снимок индексов проекта на один запрос (сессия чтения).

    Читает 5 файлов индексов ОДИН раз; все Q1–Q5 выполняются
    по in-memory данным. Гарантирует O(1) файловых чтений на
    запрос (производительность HKOS-INDEX-CONTRACT-001 §9).
    """

    def __init__(self, store: IndexStore, project: str) -> None:
        """Инициализация снимка (чтение 5 файлов индексов).

        Args:
            store: IndexStore.
            project: UUID проекта.

        """
        self._keyword = KeywordIndex(store.read(project, "keyword"))
        self._tags = TagIndex(store.read(project, "tags"))
        self._entities = EntityIndex(store.read(project, "entities"))
        self._relations = RelationshipIndex(store.read(project, "relations"))
        self._statistics = StatisticsIndex(store.read(project, "statistics"))

    def ids(self) -> list[str]:
        """Все id проиндексированных сущностей (in-memory, без I/O).

        Аддитивное расширение контракта (MINOR, HKOS-INDEX-CONTRACT-001
        §8): новый запрос не изменяет Q1–Q5. Используется Snapshot
        Builder для классификации (DS-010): перечисление id через индекс
        вместо Repository.list() (который загружает все документы).
        """
        return self._entities.ids()

    def keyword_search(self, word: str) -> list[IndexEntry]:
        """Q1: сущности по токену."""
        return [
            IndexEntry.from_dict(entry)
            for entry in self._keyword.search(word)
        ]

    def tag_search(self, tag: str) -> list[IndexEntry]:
        """Q2: сущности по тегу."""
        return [
            IndexEntry.from_dict(entry)
            for entry in self._tags.get_by_tag(tag)
        ]

    def entity_get(self, entity_id: str) -> EntityRecord | None:
        """Q3: метаданные сущности."""
        record = self._entities.get(entity_id)
        if record is None:
            return None
        return EntityRecord.from_dict(record)

    def relations_of_knowledge(
        self, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        """Q4: отношения Knowledge."""
        return self._relations.relations_of_knowledge(knowledge_id)

    def relations_of_project(self) -> list[KnowledgeRelation]:
        """Q4: все отношения проекта."""
        return self._relations.relations_of_project()

    def statistics(self) -> dict[str, int]:
        """Q5: агрегированные счётчики."""
        return self._statistics.get()


class IndexQueryExecutor:
    """Реализация Query Contract поверх IndexStore (Index Layer).

    DS-013 ЭТАП 3: при наличии IndexCache (внутренний кэш Index Layer)
    snapshot() использует РАЗОБРАННЫЙ снимок повторно; fingerprint
    (mtime/size файлов) обнаруживает внешние изменения. Поведение
    Q1-Q5 и детерминизм НЕ изменяются (кэш — только мемоизация).
    """

    def __init__(
        self, store: IndexStore, cache: "IndexCache | None" = None
    ) -> None:
        """Инициализация исполнителя запросов.

        Args:
            store: IndexStore — единственная точка доступа к файлам индексов.
            cache: Внутренний кэш Index Layer (опционально; DS-013).
                Должен быть тем же экземпляром, что и у IndexEngine
                (инвалидация при update/rebuild).

        """
        self._store = store
        self._cache = cache

    def snapshot(self, project: str) -> IndexSnapshot:
        """Снимок индексов проекта на один запрос (сессия чтения).

        С кэшем: повторные запросы без повторного parse файлов.
        """
        cache = self._cache
        if cache is None:
            return IndexSnapshot(self._store, project)
        fingerprint = self._store.fingerprint(project)
        cached = cache.get(project, fingerprint)
        if cached is not None:
            return cached  # type: ignore[return-value]  # object -> IndexSnapshot
        snapshot = IndexSnapshot(self._store, project)
        cache.set(project, snapshot, fingerprint)
        return snapshot

    # --- Q1 ---

    def keyword_search(
        self, project: str, word: str
    ) -> list[IndexEntry]:
        """Q1: сущности по точному токену."""
        keyword = KeywordIndex(self._store.read(project, "keyword"))
        return [
            IndexEntry.from_dict(entry)
            for entry in keyword.search(word)
        ]

    # --- Q2 ---

    def tag_search(self, project: str, tag: str) -> list[IndexEntry]:
        """Q2: сущности по тегу."""
        tags = TagIndex(self._store.read(project, "tags"))
        return [
            IndexEntry.from_dict(entry)
            for entry in tags.get_by_tag(tag)
        ]

    # --- Q3 ---

    def entity_get(self, project: str, entity_id: str) -> EntityRecord | None:
        """Q3: метаданные сущности."""
        entities = EntityIndex(self._store.read(project, "entities"))
        record = entities.get(entity_id)
        if record is None:
            return None
        return EntityRecord.from_dict(record)

    # --- Q4 ---

    def relations_of_knowledge(
        self, project: str, knowledge_id: str
    ) -> list[KnowledgeRelation]:
        """Q4: отношения Knowledge (единый READ-контракт)."""
        relations = RelationshipIndex(self._store.read(project, "relations"))
        return relations.relations_of_knowledge(knowledge_id)

    def relations_of_project(
        self, project: str
    ) -> list[KnowledgeRelation]:
        """Q4: все отношения проекта."""
        relations = RelationshipIndex(self._store.read(project, "relations"))
        return relations.relations_of_project()

    # --- Q5 ---

    def statistics(self, project: str) -> dict[str, int]:
        """Q5: агрегированные счётчики проекта."""
        statistics = StatisticsIndex(self._store.read(project, "statistics"))
        return statistics.get()
