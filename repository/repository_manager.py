"""HKOS Repository Manager (DS-003 §5)
====================================
Единственная точка получения репозиториев HKOS.

Другие компоненты HKOS не создают Repository самостоятельно —
только через RepositoryManager. Зависимости (StorageEngine, JSONStore)
внедряются извне; менеджер является композиционным корнем слоя.
"""

from hkos.repository.artifact_repository import ArtifactRepository
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.decision_repository import DecisionRepository
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.project_repository import ProjectRepository
from hkos.storage.storage_engine import StorageEngine

__all__ = ["RepositoryManager"]


class RepositoryManager:
    """Фасад доступа к репозиториям HKOS.

    Usage:
        manager = RepositoryManager(storage_engine)
        projects = manager.projects.list()
    """

    def __init__(self, storage: StorageEngine) -> None:
        """Инициализация менеджера с внедрённым StorageEngine.

        Args:
            storage: StorageEngine (Sprint 2) — единая точка доступа к ФС.

        """
        self._storage = storage
        json_store = storage.json_store
        self._projects: ProjectRepository = ProjectRepository(storage, json_store)
        self._campaigns: CampaignRepository = CampaignRepository(storage, json_store)
        self._knowledge: KnowledgeRepository = KnowledgeRepository(storage, json_store)
        self._decisions: DecisionRepository = DecisionRepository(storage, json_store)
        self._artifacts: ArtifactRepository = ArtifactRepository(storage, json_store)

    @property
    def storage(self) -> StorageEngine:
        """Внедрённый StorageEngine."""
        return self._storage

    @property
    def projects(self) -> ProjectRepository:
        """Репозиторий проектов."""
        return self._projects

    @property
    def campaigns(self) -> CampaignRepository:
        """Репозиторий кампаний."""
        return self._campaigns

    @property
    def knowledge(self) -> KnowledgeRepository:
        """Репозиторий знаний."""
        return self._knowledge

    @property
    def decisions(self) -> DecisionRepository:
        """Репозиторий решений."""
        return self._decisions

    @property
    def artifacts(self) -> ArtifactRepository:
        """Репозиторий артефактов."""
        return self._artifacts
