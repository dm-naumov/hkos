"""HKOS Repository Layer (DS-003)
===============================
Слой объектного доступа к инженерной памяти HKOS.

Repository — адаптер между Storage Engine (Sprint 2) и будущими
сервисами HKOS. Не содержит бизнес-логики: только сохраняет
и извлекает объекты (Project, Campaign, Knowledge, Decision, Artifact).

Единственная точка получения репозиториев — RepositoryManager.
"""

from hkos.repository.artifact_repository import ArtifactRepository
from hkos.repository.base_repository import BaseRepository
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.decision_repository import DecisionRepository
from hkos.repository.exceptions import (
    RepositoryError,
    RepositoryNotFoundError,
    RepositoryParseError,
)
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.models import (
    ARTIFACT_STATUS_ACTIVE,
    CAMPAIGN_STATUS_ACTIVE,
    DECISION_ACCEPT,
    KNOWLEDGE_STATUS_NEW,
    PROJECT_STATUS_ACTIVE,
    Artifact,
    Campaign,
    CampaignMetadata,
    CampaignState,
    Decision,
    DecisionHistory,
    Knowledge,
    Project,
)
from hkos.repository.project_repository import ProjectRepository
from hkos.repository.repository_manager import RepositoryManager

__all__ = [
    "RepositoryManager",
    "BaseRepository",
    "ProjectRepository",
    "CampaignRepository",
    "KnowledgeRepository",
    "DecisionRepository",
    "ArtifactRepository",
    "Project",
    "Campaign",
    "Knowledge",
    "Decision",
    "Artifact",
    "CampaignState",
    "CampaignMetadata",
    "DecisionHistory",
    "RepositoryError",
    "RepositoryNotFoundError",
    "RepositoryParseError",
    "PROJECT_STATUS_ACTIVE",
    "CAMPAIGN_STATUS_ACTIVE",
    "KNOWLEDGE_STATUS_NEW",
    "ARTIFACT_STATUS_ACTIVE",
    "DECISION_ACCEPT",
]
