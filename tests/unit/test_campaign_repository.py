"""Unit tests for CampaignRepository (DS-003 §8)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.exceptions import RepositoryNotFoundError
from hkos.repository.models import (
    CAMPAIGN_STATUS_ARCHIVED,
    CAMPAIGN_STATUS_CLOSED,
    Campaign,
)
from hkos.storage import StorageEngine


class TestCampaignRepository:
    """Test suite for CampaignRepository."""

    def _repo(self, tmp_path: Path) -> tuple[CampaignRepository, str]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = CampaignRepository(engine, engine.json_store)
        project = repo.storage.path_manager.project(engine.root, "proj-1")
        repo.storage.mkdir(project)
        return repo, "proj-1"

    def test_create_load_roundtrip(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        campaign = repo.create_campaign(Campaign(project=project, goal="TProxy"))
        loaded = repo.load_campaign(project, campaign.id)
        assert loaded.goal == "TProxy"
        assert loaded.id == campaign.id

    def test_uuid_stable_after_update(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        campaign = repo.create_campaign(Campaign(project=project, goal="A"))
        campaign.goal = "B"
        repo.update_campaign(campaign)
        loaded = repo.load_campaign(project, campaign.id)
        assert loaded.id == campaign.id
        assert loaded.goal == "B"

    def test_close_campaign(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        campaign = repo.create_campaign(Campaign(project=project, goal="A"))
        state = repo.close_campaign(project, campaign.id)
        assert state.status == CAMPAIGN_STATUS_CLOSED
        assert state.updated_at
        assert repo.load_campaign(project, campaign.id).status == CAMPAIGN_STATUS_CLOSED

    def test_archive_campaign(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        campaign = repo.create_campaign(Campaign(project=project, goal="A"))
        state = repo.archive_campaign(project, campaign.id)
        assert state.status == CAMPAIGN_STATUS_ARCHIVED

    def test_load_metadata(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        campaign = repo.create_campaign(Campaign(project=project, goal="A"))
        meta = repo.load_metadata(project, campaign.id)
        assert meta.version == 1
        assert meta.created_at
        assert meta.updated_at

    def test_list_and_count(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        repo.create_campaign(Campaign(project=project, goal="A"))
        repo.create_campaign(Campaign(project=project, goal="B"))
        assert repo.count(project) == 2
        assert sorted(c.goal for c in repo.list(project)) == ["A", "B"]

    def test_delete(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        campaign = repo.create_campaign(Campaign(project=project, goal="A"))
        repo.delete(project, campaign.id)
        assert not repo.exists(project, campaign.id)

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        with pytest.raises(RepositoryNotFoundError):
            repo.load_campaign(project, "absent")

    def test_relative_path_layout(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        campaign = repo.create_campaign(Campaign(project=project, goal="A"))
        relative = f"projects/{project}/campaigns/{campaign.id}/campaign.json"
        assert repo.storage.exists(relative)
