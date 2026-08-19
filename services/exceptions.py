"""HKOS Services Exceptions (DS-004)
================================
Специализированные исключения сервисного слоя (Project Manager).
Наследуют HKOSError (Sprint 1). RuntimeError/Exception не используются.
"""

from hkos.core.exceptions import HKOSError

__all__ = [
    "ProjectError",
    "ProjectNotFoundError",
    "ProjectStateError",
    "ProjectNameConflictError",
    "CampaignError",
    "CampaignNotFoundError",
    "CampaignStateError",
]


class ProjectError(HKOSError):
    """Базовое исключение сервисного слоя Project Manager."""

    def __init__(self, message: str, component: str = "project") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class ProjectNotFoundError(ProjectError):
    """Проект не найден."""


class ProjectStateError(ProjectError):
    """Запрещённый переход состояния проекта."""


class ProjectNameConflictError(ProjectError):
    """Имя проекта уже занято (DS-004 §12: имя уникально)."""


class CampaignError(HKOSError):
    """Базовое исключение сервисного слоя Campaign Manager."""

    def __init__(self, message: str, component: str = "campaign") -> None:
        """Инициализация с указанием компонента-источника."""
        super().__init__(message, component=component)


class CampaignNotFoundError(CampaignError):
    """Кампания не найдена."""


class CampaignStateError(CampaignError):
    """Запрещённый переход состояния кампании."""
