"""HKOS Librarian Layer (DS-006)
==============================
Librarian — единственная точка принятия решений о жизненном цикле
Knowledge (регистрация, канонизация, объединение, конфликты, статусы,
confidence, история). Не выполняет Retrieval/Index/Snapshot/Context.
"""

from hkos.services.librarian.canonicalizer import Canonicalizer
from hkos.services.librarian.confidence_engine import ConfidenceEngine
from hkos.services.librarian.conflict_detector import (
    ConflictDetector,
    ConflictResult,
)
from hkos.services.librarian.exceptions import (
    KnowledgeNotFoundError,
    KnowledgeStatusError,
    LibrarianError,
)
from hkos.services.librarian.knowledge_classifier import KnowledgeClassifier
from hkos.services.librarian.knowledge_history import KnowledgeHistory
from hkos.services.librarian.knowledge_merger import KnowledgeMerger
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_CONFLICT,
    KNOWLEDGE_STATUS_NEW,
    KNOWLEDGE_STATUS_REJECTED,
    KNOWLEDGE_STATUS_SUPERSEDED,
    KNOWLEDGE_STATUS_VERIFIED,
    VALID_KNOWLEDGE_STATUSES,
    KnowledgeStatus,
)
from hkos.services.librarian.knowledge_status import (
    TRANSITIONS as KNOWLEDGE_TRANSITIONS,
)
from hkos.services.librarian.librarian import Librarian

__all__ = [
    "Librarian",
    "Canonicalizer",
    "ConflictDetector",
    "ConflictResult",
    "KnowledgeClassifier",
    "KnowledgeHistory",
    "KnowledgeMerger",
    "KnowledgeStatus",
    "ConfidenceEngine",
    "LibrarianError",
    "KnowledgeNotFoundError",
    "KnowledgeStatusError",
    "KNOWLEDGE_STATUS_NEW",
    "KNOWLEDGE_STATUS_VERIFIED",
    "KNOWLEDGE_STATUS_CANONICAL",
    "KNOWLEDGE_STATUS_SUPERSEDED",
    "KNOWLEDGE_STATUS_CONFLICT",
    "KNOWLEDGE_STATUS_REJECTED",
    "KNOWLEDGE_STATUS_ARCHIVED",
    "VALID_KNOWLEDGE_STATUSES",
    "KNOWLEDGE_TRANSITIONS",
]
