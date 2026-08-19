"""Unit tests for CampaignValidator (IP-005 Stage 3, DS-005 §9)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.models import Campaign, CampaignStep, JournalEntry
from hkos.services.campaign_validator import CampaignValidator
from hkos.storage import StorageEngine

UUID = "11111111-2222-3333-4444-555555555555"


class TestCampaignValidator:
    """Test suite for CampaignValidator."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[CampaignValidator, CampaignRepository, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = CampaignRepository(engine, engine.json_store)
        return CampaignValidator(repo), repo, engine

    def _valid_campaign(self) -> Campaign:
        return Campaign(
            id=UUID, project="p1", goal="Goal", status="CREATED",
            steps=[CampaignStep(id="s1", title="A")],
            journal=[JournalEntry(timestamp="t", campaign_id=UUID, event="Campaign Created")],
        )

    def test_valid_campaign_passes(self, tmp_path: Path) -> None:
        validator, repo, _ = self._ctx(tmp_path)
        repo.save(self._valid_campaign())
        result = validator.validate("p1", UUID)
        assert result.valid is True
        assert result.errors == []

    def test_missing_campaign_fails(self, tmp_path: Path) -> None:
        validator, _, _ = self._ctx(tmp_path)
        result = validator.validate("p1", UUID)
        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_invalid_uuid_fails(self, tmp_path: Path) -> None:
        validator, repo, _ = self._ctx(tmp_path)
        campaign = self._valid_campaign()
        campaign.id = "not-a-uuid"
        repo.save(campaign)
        result = validator.validate("p1", "not-a-uuid")
        assert result.valid is False
        assert any("UUID" in e for e in result.errors)

    def test_wrong_project_not_found(self, tmp_path: Path) -> None:
        """Адресация кампании = (project, id): чужой проект -> not found."""
        validator, repo, _ = self._ctx(tmp_path)
        repo.save(self._valid_campaign())
        result = validator.validate("other-project", UUID)
        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_project_mismatch_fails(self, tmp_path: Path) -> None:
        """Несогласованный документ: data.project != каталог проекта."""
        validator, repo, engine = self._ctx(tmp_path)
        campaign = self._valid_campaign()
        campaign.project = "p2"
        repo.save(campaign)
        source = engine.read_json(f"projects/p2/campaigns/{UUID}/campaign.json")
        engine.mkdir(f"projects/p1/campaigns/{UUID}")
        engine.write_json(f"projects/p1/campaigns/{UUID}/campaign.json", source)
        result = validator.validate("p1", UUID)
        assert result.valid is False
        assert any("does not match" in e for e in result.errors)

    def test_empty_goal_fails(self, tmp_path: Path) -> None:
        validator, repo, _ = self._ctx(tmp_path)
        campaign = self._valid_campaign()
        campaign.goal = ""
        repo.save(campaign)
        result = validator.validate("p1", UUID)
        assert result.valid is False
        assert any("goal" in e.lower() for e in result.errors)

    def test_invalid_state_fails(self, tmp_path: Path) -> None:
        validator, repo, _ = self._ctx(tmp_path)
        campaign = self._valid_campaign()
        campaign.status = "LIMBO"
        repo.save(campaign)
        result = validator.validate("p1", UUID)
        assert result.valid is False
        assert any("state" in e for e in result.errors)

    def test_legacy_lowercase_state_invalid(self, tmp_path: Path) -> None:
        """Легаси-статусы DS-003 не маппятся на состояния DS-005."""
        validator, repo, _ = self._ctx(tmp_path)
        campaign = self._valid_campaign()
        campaign.status = "active"  # DS-003 legacy, нет в VALID_CAMPAIGN_STATES
        repo.save(campaign)
        result = validator.validate("p1", UUID)
        assert result.valid is False
        assert any("state" in e for e in result.errors)

    def test_empty_step_id_fails(self, tmp_path: Path) -> None:
        validator, repo, _ = self._ctx(tmp_path)
        campaign = self._valid_campaign()
        campaign.steps = [CampaignStep(id="", title="X")]
        repo.save(campaign)
        result = validator.validate("p1", UUID)
        assert result.valid is False
        assert any("step" in e.lower() for e in result.errors)

    def test_empty_journal_warns(self, tmp_path: Path) -> None:
        validator, repo, _ = self._ctx(tmp_path)
        campaign = self._valid_campaign()
        campaign.journal = []
        repo.save(campaign)
        result = validator.validate("p1", UUID)
        assert result.valid is True
        assert any("journal" in w.lower() for w in result.warnings)

    def test_no_runtime_error_on_missing(self, tmp_path: Path) -> None:
        validator, _, _ = self._ctx(tmp_path)
        result = validator.validate("p1", UUID)
        assert isinstance(result.valid, bool)

    def test_bool_conversion(self, tmp_path: Path) -> None:
        validator, repo, _ = self._ctx(tmp_path)
        repo.save(self._valid_campaign())
        assert validator.validate("p1", UUID)
