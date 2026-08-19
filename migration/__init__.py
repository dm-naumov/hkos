"""HKOS Migration Engine (DS-011 Rev.1.2)
=========================================
Слой обслуживания: эволюция схемы хранения без потери инженерной памяти.
Порядок: Repository -> Index -> Snapshot (SSOT; производные пересоздаются).
"""

from hkos.migration.backup_manager import BackupManager
from hkos.migration.exceptions import (
    BackupError,
    MigrationError,
    MigrationLockError,
    MigrationNotFoundError,
    MigrationValidationError,
    RollbackError,
)
from hkos.migration.migration_engine import MigrationEngine
from hkos.migration.migration_executor import MigrationExecutor
from hkos.migration.migration_history import MigrationHistory, MigrationRecord
from hkos.migration.migration_manager import MigrationManager
from hkos.migration.migration_registry import MigrationRegistry, MigrationStep
from hkos.migration.migration_validator import MigrationValidator
from hkos.migration.rollback_manager import RollbackManager
from hkos.migration.schema_detector import SchemaDetector, SchemaInfo
from hkos.migration.version_manifest import VersionManifest

__all__ = [
    "MigrationEngine",
    "MigrationManager",
    "MigrationRegistry",
    "MigrationStep",
    "MigrationExecutor",
    "MigrationValidator",
    "MigrationHistory",
    "MigrationRecord",
    "BackupManager",
    "RollbackManager",
    "SchemaDetector",
    "SchemaInfo",
    "VersionManifest",
    "MigrationError",
    "MigrationLockError",
    "MigrationNotFoundError",
    "MigrationValidationError",
    "BackupError",
    "RollbackError",
]
