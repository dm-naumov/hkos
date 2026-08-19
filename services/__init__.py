"""HKOS Services Layer (DS-004)
===============================
Первый сервисный слой HKOS — Project Manager.

Project Manager — единственная точка управления жизненным циклом
инженерных проектов (создание, открытие, закрытие, архивация,
удаление, переименование, проверка). Работает поверх Repository
Layer (DS-003) и не обращается к Storage Engine напрямую.
"""

from hkos.services.campaign_factory import CampaignFactory
from hkos.services.campaign_manager import CampaignManager, CampaignStatus
from hkos.services.campaign_service import CampaignService
from hkos.services.campaign_state import (
    CAMPAIGN_STATE_ARCHIVED,
    CAMPAIGN_STATE_COMPLETED,
    CAMPAIGN_STATE_CREATED,
    CAMPAIGN_STATE_FAILED,
    CAMPAIGN_STATE_PAUSED,
    CAMPAIGN_STATE_READY,
    CAMPAIGN_STATE_RUNNING,
    CAMPAIGN_STATE_WAITING_EXTERNAL,
    VALID_CAMPAIGN_STATES,
    CampaignState,
)
from hkos.services.campaign_state import (
    TRANSITIONS as CAMPAIGN_TRANSITIONS,
)
from hkos.services.campaign_statistics import (
    CampaignStatistics,
    CampaignStatisticsResult,
)
from hkos.services.campaign_validator import CampaignValidator
from hkos.services.exceptions import (
    CampaignError,
    CampaignNotFoundError,
    CampaignStateError,
    ProjectError,
    ProjectNameConflictError,
    ProjectNotFoundError,
    ProjectStateError,
)
from hkos.services.librarian import Librarian
from hkos.services.project_factory import ProjectFactory
from hkos.services.project_manager import ProjectInfo, ProjectManager
from hkos.services.project_service import ProjectService
from hkos.services.project_state import (
    PROJECT_STATE_ACTIVE,
    PROJECT_STATE_ARCHIVED,
    PROJECT_STATE_CREATED,
    PROJECT_STATE_DELETED,
    PROJECT_STATE_PAUSED,
    TRANSITIONS,
    VALID_PROJECT_STATES,
    ProjectState,
)
from hkos.services.project_validator import (
    ProjectValidator,
    ValidationResult,
)

__all__ = [
    "Librarian",
    "CampaignManager",
    "CampaignService",
    "CampaignFactory",
    "CampaignValidator",
    "CampaignState",
    "CampaignStatus",
    "CampaignStatistics",
    "CampaignStatisticsResult",
    "CampaignError",
    "CampaignNotFoundError",
    "CampaignStateError",
    "CAMPAIGN_STATE_CREATED",
    "CAMPAIGN_STATE_READY",
    "CAMPAIGN_STATE_RUNNING",
    "CAMPAIGN_STATE_PAUSED",
    "CAMPAIGN_STATE_WAITING_EXTERNAL",
    "CAMPAIGN_STATE_FAILED",
    "CAMPAIGN_STATE_COMPLETED",
    "CAMPAIGN_STATE_ARCHIVED",
    "VALID_CAMPAIGN_STATES",
    "CAMPAIGN_TRANSITIONS",
    "ProjectManager",
    "ProjectService",
    "ProjectFactory",
    "ProjectValidator",
    "ProjectState",
    "ValidationResult",
    "ProjectInfo",
    "ProjectError",
    "ProjectNotFoundError",
    "ProjectStateError",
    "ProjectNameConflictError",
    "PROJECT_STATE_CREATED",
    "PROJECT_STATE_ACTIVE",
    "PROJECT_STATE_PAUSED",
    "PROJECT_STATE_ARCHIVED",
    "PROJECT_STATE_DELETED",
    "VALID_PROJECT_STATES",
    "TRANSITIONS",
]
