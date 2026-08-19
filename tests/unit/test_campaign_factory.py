"""Unit tests for CampaignFactory (IP-005 Stage 2, DS-005 §7)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.models import CampaignStep
from hkos.services.campaign_factory import (
    CAMPAIGN_SCHEMA_VERSION,
    JOURNAL_EVENT_CREATED,
    CampaignFactory,
)
from hkos.services.campaign_state import CAMPAIGN_STATE_CREATED
from hkos.storage import StorageEngine


class TestCampaignFactory:
    """Test suite for CampaignFactory (creation only)."""

    def _factory(self, tmp_path: Path) -> tuple[CampaignFactory, CampaignRepository]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = CampaignRepository(engine, engine.json_store)
        return CampaignFactory(repo), repo

    def test_create_generates_uuid(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        campaign = factory.create(project_id="p1", goal="Goal")
        assert campaign.id
        assert len(campaign.id) == 36

    def test_create_sets_created_state(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        campaign = factory.create(project_id="p1", goal="Goal")
        assert campaign.status == CAMPAIGN_STATE_CREATED

    def test_create_sets_mandatory_fields(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        campaign = factory.create(project_id="p1", goal="Goal")
        assert campaign.project == "p1"
        assert campaign.goal == "Goal"
        assert campaign.schema_version == CAMPAIGN_SCHEMA_VERSION

    def test_create_initializes_journal(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        campaign = factory.create(project_id="p1", goal="Goal")
        assert len(campaign.journal) == 1
        assert campaign.journal[0].event == JOURNAL_EVENT_CREATED
        assert campaign.journal[0].campaign_id == campaign.id

    def test_create_assigns_step_uuids(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        campaign = factory.create(
            project_id="p1", goal="Goal",
            steps=[CampaignStep(title="A"), CampaignStep(title="B")],
        )
        assert len(campaign.steps) == 2
        assert all(step.id for step in campaign.steps)

    def test_create_persists_via_repository(self, tmp_path: Path) -> None:
        factory, repo = self._factory(tmp_path)
        campaign = factory.create(project_id="p1", goal="Goal")
        assert repo.exists("p1", campaign.id)
        loaded = repo.load("p1", campaign.id)
        assert loaded.id == campaign.id
        assert loaded.goal == "Goal"

    def test_no_factory_side_apis(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        assert not hasattr(factory, "open")
        assert not hasattr(factory, "archive")
        assert not hasattr(factory, "validate")
        assert not hasattr(factory, "calculate_progress")
        assert not hasattr(factory, "calculate")
