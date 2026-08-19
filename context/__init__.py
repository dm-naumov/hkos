"""HKOS Context Layer (DS-009)
===========================
Context Builder — формирование оптимального инженерного контекста
из RetrievalResult (минимальный по объёму, максимальный по полезности).

Использует: RetrievalResult (DS-008), SnapshotLoader (read-only),
Query Contract. Запрещены: StorageEngine/IndexStore/JSON/поиск.
"""

from hkos.context.context_builder import (
    PROFILE_FULL,
    PROFILE_LARGE,
    PROFILE_MEDIUM,
    PROFILE_SMALL,
    VALID_PROFILES,
    ContextBuilder,
)
from hkos.context.context_manager import ContextManager
from hkos.context.context_optimizer import ContextOptimizer
from hkos.context.context_serializer import ContextSerializer
from hkos.context.context_statistics import ContextStatistics
from hkos.context.context_validator import ContextValidator
from hkos.context.exceptions import ContextError, ContextValidationError
from hkos.context.models import (
    ContextDocument,
    ContextExplanation,
    ContextItem,
)
from hkos.context.snapshot_loader import (
    SnapshotDocument,
    SnapshotLoader,
    SnapshotReader,
)
from hkos.context.token_estimator import TokenEstimate, TokenEstimator

__all__ = [
    "ContextBuilder",
    "ContextManager",
    "ContextOptimizer",
    "ContextSerializer",
    "ContextValidator",
    "ContextStatistics",
    "TokenEstimator",
    "TokenEstimate",
    "SnapshotLoader",
    "SnapshotReader",
    "SnapshotDocument",
    "ContextDocument",
    "ContextItem",
    "ContextExplanation",
    "ContextError",
    "ContextValidationError",
    "PROFILE_SMALL",
    "PROFILE_MEDIUM",
    "PROFILE_LARGE",
    "PROFILE_FULL",
    "VALID_PROFILES",
]
