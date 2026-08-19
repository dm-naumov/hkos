"""Unit tests for CampaignManager (IP-005 Stage 7, DS-005 §5-6)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Campaign, CampaignStep
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.campaign_manager import (
    EVENT_ARCHIVED,
    EVENT_COMPLETED,
    EVENT_CREATED,
    EVENT_PAUSED,
    EVENT_READY,
    EVENT_RESUMED,
    EVENT_RUNNING,
    EVENT_WAITING_EXTERNAL,
    CampaignManager,
)
from hkos.services.campaign_state import (
    CAMPAIGN_STATE_ARCHIVED,
    CAMPAIGN_STATE_COMPLETED,
    CAMPAIGN_STATE_CREATED,
    CAMPAIGN_STATE_FAILED,
    CAMPAIGN_STATE_PAUSED,
    CAMPAIGN_STATE_READY,
    CAMPAIGN_STATE_RUNNING,
    CAMPAIGN_STATE_WAITING_EXTERNAL,
)
from hkos.services.campaign_statistics import STEP_STATUS_COMPLETED
from hkos.services.exceptions import (
    CampaignNotFoundError,
    CampaignStateError,
)
from hkos.storage import StorageEngine


class TestCampaignManager:
    """Test suite for CampaignManager lifecycle API."""

    def _manager(self, tmp_path: Path) -> tuple[CampaignManager, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return CampaignManager(RepositoryManager(engine), HKOSLogger()), engine

    def _create(
        self,
        manager: CampaignManager,
        project: str = "p1",
        steps: list[CampaignStep] | None = None,
    ) -> Campaign:
        return manager.create(project_id=project, goal="Goal", steps=steps)

    def test_create(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        assert campaign.status == CAMPAIGN_STATE_CREATED
        assert manager.status("p1", campaign.id).state == CAMPAIGN_STATE_CREATED

    def test_open_creds_to_ready_then_running(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        ready = manager.open("p1", campaign.id)
        assert ready.status == CAMPAIGN_STATE_READY
        running = manager.open("p1", campaign.id)
        assert running.status == CAMPAIGN_STATE_RUNNING

    def test_open_illegal_from_running(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        with pytest.raises(CampaignStateError):
            manager.open("p1", campaign.id)

    def test_pause_and_resume(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        assert manager.pause("p1", campaign.id).status == CAMPAIGN_STATE_PAUSED
        assert manager.resume("p1", campaign.id).status == CAMPAIGN_STATE_RUNNING

    def test_pause_illegal_from_created(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        with pytest.raises(CampaignStateError):
            manager.pause("p1", campaign.id)

    def test_resume_from_waiting_external(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        manager._wait_external("p1", campaign.id)
        assert manager.resume("p1", campaign.id).status == CAMPAIGN_STATE_RUNNING

    def test_close_completes(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        assert manager.close("p1", campaign.id).status == CAMPAIGN_STATE_COMPLETED

    def test_close_illegal_from_paused(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        manager.pause("p1", campaign.id)
        with pytest.raises(CampaignStateError):
            manager.close("p1", campaign.id)

    def test_archive_from_completed(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        manager.close("p1", campaign.id)
        assert manager.archive("p1", campaign.id).status == CAMPAIGN_STATE_ARCHIVED

    def test_archive_from_failed(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        manager._fail("p1", campaign.id)
        assert manager.archive("p1", campaign.id).status == CAMPAIGN_STATE_ARCHIVED

    def test_archive_illegal_from_running(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        with pytest.raises(CampaignStateError):
            manager.archive("p1", campaign.id)

    def test_fail_from_ready(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        assert manager._fail("p1", campaign.id).status == CAMPAIGN_STATE_FAILED

    def test_fail_illegal_from_created(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        with pytest.raises(CampaignStateError):
            manager._fail("p1", campaign.id)

    def test_wait_external_only_from_running(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        assert manager._wait_external("p1", campaign.id).status == CAMPAIGN_STATE_WAITING_EXTERNAL

    def test_delete(self, tmp_path: Path) -> None:
        manager, engine = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.delete("p1", campaign.id)
        assert not engine.exists(f"projects/p1/campaigns/{campaign.id}/campaign.json")
        with pytest.raises(CampaignNotFoundError):
            manager.status("p1", campaign.id)

    def test_delete_missing_raises(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        with pytest.raises(CampaignNotFoundError):
            manager.delete("p1", "11111111-2222-3333-4444-555555555555")

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        with pytest.raises(CampaignNotFoundError):
            manager.status("p1", "11111111-2222-3333-4444-555555555555")

    def test_status(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        status = manager.status("p1", campaign.id)
        assert status.campaign_id == campaign.id
        assert status.project == "p1"
        assert status.state == CAMPAIGN_STATE_CREATED
        assert status.as_dict()["state"] == CAMPAIGN_STATE_CREATED

    def test_progress_from_steps(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(
            manager,
            steps=[CampaignStep(title="A"), CampaignStep(title="B")],
        )
        assert manager.progress("p1", campaign.id) == 0
        loaded = manager._load("p1", campaign.id)
        step_id = loaded.steps[0].id
        manager._update_step("p1", campaign.id, step_id, STEP_STATUS_COMPLETED)
        assert manager.progress("p1", campaign.id) == 50

    def test_statistics(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(
            manager,
            steps=[CampaignStep(title="A"), CampaignStep(title="B")],
        )
        stats = manager.statistics("p1", campaign.id)
        assert stats.total_steps == 2
        assert stats.as_dict()["total_steps"] == 2

    def test_list(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        self._create(manager, project="p1")
        self._create(manager, project="p1")
        self._create(manager, project="p2")
        assert len(manager.list("p1")) == 2
        assert len(manager.list("p2")) == 1

    def test_validate(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        assert manager.validate("p1", campaign.id).valid is True

    def test_validate_missing(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        result = manager.validate("p1", "11111111-2222-3333-4444-555555555555")
        assert result.valid is False

    def test_journal_events_sequence(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        manager.pause("p1", campaign.id)
        manager.resume("p1", campaign.id)
        manager._wait_external("p1", campaign.id)
        manager.resume("p1", campaign.id)
        manager.close("p1", campaign.id)
        manager.archive("p1", campaign.id)
        loaded = manager._load("p1", campaign.id)
        events = [entry.event for entry in loaded.journal]
        assert events == [
            EVENT_CREATED, EVENT_READY, EVENT_RUNNING, EVENT_PAUSED,
            EVENT_RESUMED, EVENT_WAITING_EXTERNAL, EVENT_RESUMED,
            EVENT_COMPLETED, EVENT_ARCHIVED,
        ]

    def test_journal_append_only(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        first = manager._load("p1", campaign.id).journal
        manager.open("p1", campaign.id)
        loaded = manager._load("p1", campaign.id)
        assert len(loaded.journal) == len(first) + 1
        assert loaded.journal[0] == first[0]  # существующие записи не изменены

    def test_exactly_twelve_public_methods(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        api = {name for name in dir(manager) if not name.startswith("_")}
        assert api == {
            "create", "open", "pause", "resume", "close", "archive",
            "delete", "status", "progress", "statistics", "list", "validate",
        }

    def test_update_step_missing_raises(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = self._create(manager)
        with pytest.raises(CampaignNotFoundError):
            manager._update_step("p1", campaign.id, "missing-step", STEP_STATUS_COMPLETED)
