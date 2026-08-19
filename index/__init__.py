"""HKOS Index Layer (DS-007)
==========================
Слой индексирования HKOS: Keyword/Tag/Entity/Relationship/Statistics
индексы. Расположен на репозиторном уровне (между repository и services);
сущности читаются через RepositoryManager, файлы индексов — через
IndexStore (инжектируется). Retriever (DS-008) будет читать индекс
напрямую, не нарушая слои и не изменяя Librarian.
"""

from hkos.index.entity_index import EntityIndex
from hkos.index.exceptions import (
    IndexCorruptedError,
    IndexError,
    IndexNotFoundError,
)
from hkos.index.index_builder import IndexBuilder
from hkos.index.index_cache import IndexCache
from hkos.index.index_engine import (
    ENTITY_TYPE_ARTIFACT,
    ENTITY_TYPE_CAMPAIGN,
    ENTITY_TYPE_DECISION,
    ENTITY_TYPE_KNOWLEDGE,
    ENTITY_TYPE_PROJECT,
    VALID_ENTITY_TYPES,
    IndexEngine,
)
from hkos.index.index_manager import IndexManager
from hkos.index.index_store import INDEX_NAMES, IndexStore
from hkos.index.index_updater import IndexUpdater
from hkos.index.index_validator import IndexValidator
from hkos.index.keyword_index import KeywordIndex
from hkos.index.query_contract import (
    EntityRecord,
    IndexEntry,
    IndexQueryExecutor,
    IndexSnapshot,
    QueryContract,
)
from hkos.index.relationship_index import (
    RelationshipIndex,
    RelationshipReader,
)
from hkos.index.statistics_index import StatisticsIndex
from hkos.index.tag_index import TagIndex
from hkos.index.validation import ValidationResult

__all__ = [
    "IndexEngine",
    "IndexManager",
    "IndexBuilder",
    "IndexUpdater",
    "IndexValidator",
    "IndexStore",
    "KeywordIndex",
    "QueryContract",
    "IndexQueryExecutor",
    "IndexCache",
    "IndexSnapshot",
    "IndexEntry",
    "EntityRecord",
    "TagIndex",
    "EntityIndex",
    "RelationshipIndex",
    "RelationshipReader",
    "StatisticsIndex",
    "ValidationResult",
    "IndexError",
    "IndexNotFoundError",
    "IndexCorruptedError",
    "INDEX_NAMES",
    "ENTITY_TYPE_PROJECT",
    "ENTITY_TYPE_CAMPAIGN",
    "ENTITY_TYPE_KNOWLEDGE",
    "ENTITY_TYPE_DECISION",
    "ENTITY_TYPE_ARTIFACT",
    "VALID_ENTITY_TYPES",
]
