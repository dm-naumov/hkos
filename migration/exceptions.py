"""HKOS Migration Exceptions (DS-011 Rev.1.2)
=============================================
Иерархия ошибок Migration Engine.
"""

from hkos.core.exceptions import HKOSError

__all__ = [
    "MigrationError",
    "MigrationLockError",
    "MigrationNotFoundError",
    "MigrationValidationError",
    "BackupError",
    "RollbackError",
]


class MigrationError(HKOSError):
    """Базовая ошибка Migration Engine."""

    def __init__(self, message: str) -> None:
        super().__init__(message, component="migration")


class MigrationLockError(MigrationError):
    """Конкурентная миграция: замок занят (DS-011 §15a)."""


class MigrationNotFoundError(MigrationError):
    """Запрашиваемая миграция/резервная копия отсутствует."""


class MigrationValidationError(MigrationError):
    """Ошибка валидации после миграции (DS-011 §13)."""


class BackupError(MigrationError):
    """Ошибка создания/восстановления резервной копии (DS-011 §9)."""


class RollbackError(MigrationError):
    """Ошибка отката (DS-011 §10)."""
