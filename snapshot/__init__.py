"""HKOS Snapshot Layer (DS-010)
===============================
Snapshot Engine — снимки инженерного состояния проекта (HKOS-10).

Использует: RepositoryManager (Builder/Validator), существующий
SnapshotLoader из Context Layer (разбор), порт SnapshotPersistence
(персистентность — вне слоя). Запрещены: Retrieval, Storage,
изменение сущностей Repository.
"""

from hkos.snapshot.exceptions import (
    SnapshotError,
    SnapshotNotFoundError,
    SnapshotValidationError,
)
from hkos.snapshot.snapshot_builder import SnapshotBuilder
from hkos.snapshot.snapshot_diff import DiffResult, SnapshotDiff
from hkos.snapshot.snapshot_engine import SnapshotEngine
from hkos.snapshot.snapshot_history import SnapshotHistory
from hkos.snapshot.snapshot_loader import SnapshotLoader, SnapshotPersistence
from hkos.snapshot.snapshot_manager import SnapshotManager
from hkos.snapshot.snapshot_serializer import SnapshotSerializer
from hkos.snapshot.snapshot_validator import SnapshotValidator

__all__ = [
    "SnapshotEngine",
    "SnapshotManager",
    "SnapshotBuilder",
    "SnapshotLoader",
    "SnapshotPersistence",
    "SnapshotDiff",
    "DiffResult",
    "SnapshotValidator",
    "SnapshotSerializer",
    "SnapshotHistory",
    "SnapshotError",
    "SnapshotNotFoundError",
    "SnapshotValidationError",
]
