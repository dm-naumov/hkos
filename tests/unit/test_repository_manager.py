"""Unit tests for RepositoryManager (DS-003 §5)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.artifact_repository import ArtifactRepository
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.decision_repository import DecisionRepository
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.project_repository import ProjectRepository
from hkos.repository.repository_manager import RepositoryManager
from hkos.storage import StorageEngine


class TestRepositoryManager:
    """Test suite for RepositoryManager facade."""

    def _manager(self, tmp_path: Path) -> tuple[RepositoryManager, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return RepositoryManager(engine), engine

    def test_returns_correct_instances(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        assert isinstance(manager.projects, ProjectRepository)
        assert isinstance(manager.campaigns, CampaignRepository)
        assert isinstance(manager.knowledge, KnowledgeRepository)
        assert isinstance(manager.decisions, DecisionRepository)
        assert isinstance(manager.artifacts, ArtifactRepository)

    def test_shared_storage(self, tmp_path: Path) -> None:
        manager, engine = self._manager(tmp_path)
        assert manager.storage is engine
        assert manager.projects.storage is engine
        assert manager.campaigns.storage is engine
        assert manager.knowledge.storage is engine
        assert manager.decisions.storage is engine
        assert manager.artifacts.storage is engine

    def test_repositories_share_json_store(self, tmp_path: Path) -> None:
        manager, engine = self._manager(tmp_path)
        assert manager.projects.storage.json_store is engine.json_store

    def test_full_manager_crud(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        from hkos.repository.models import Campaign, Knowledge, Project

        project = manager.projects.save(Project(name="OpenWrt"))
        campaign = manager.campaigns.create_campaign(
            Campaign(project=project.id, goal="Research")
        )
        knowledge = manager.knowledge.create(
            Knowledge(project=project.id, title="Fact", tags=["x"])
        )
        assert manager.projects.count() == 1
        assert manager.campaigns.count(project.id) == 1
        assert manager.knowledge.count(project.id) == 1
        assert manager.knowledge.search_by_tag(project.id, "x")[0].id == knowledge.id
        assert campaign.project == project.id
