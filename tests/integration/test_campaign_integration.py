"""Integration tests: полный жизненный цикл Campaign (DS-005 §17, IP-005 §16).

Сценарий 1 (happy path):
    Create -> READY -> RUNNING -> PAUSED -> RUNNING -> WAITING_EXTERNAL
    -> RUNNING -> COMPLETED -> ARCHIVED
Сценарий 2 (failure path):
    RUNNING -> FAILED -> ARCHIVED

Дополнительно: корректность Journal/Statistics/Progress,
отсутствие обращения к Storage Engine (статический скан + блокировка).
"""

import json as json_mod
import os
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import CampaignStep
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.campaign_manager import CampaignManager
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
from hkos.storage import StorageEngine

FORBIDDEN_IN_CAMPAIGN_SERVICES = [
    "StorageEngine",
    "JSONStore",
    "FileStore",
    "AtomicWriter",
    "PathManager",
    "os.makedirs",
    "os.remove",
    "os.listdir",
    "import json",
    "from json",
    "import pathlib",
    "from pathlib",
]


class TestCampaignIntegration:
    """Полные сценарии жизненного цикла кампании."""

    def _manager(self, tmp_path: Path) -> tuple[CampaignManager, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return CampaignManager(RepositoryManager(engine), HKOSLogger()), engine

    def test_happy_path(self, tmp_path: Path) -> None:
        manager, engine = self._manager(tmp_path)
        campaign = manager.create(
            project_id="p1", goal="TProxy research",
            steps=[CampaignStep(title="A"), CampaignStep(title="B")],
        )
        assert campaign.status == CAMPAIGN_STATE_CREATED
        assert engine.exists(f"projects/p1/campaigns/{campaign.id}/campaign.json")

        # READY
        assert manager.open("p1", campaign.id).status == CAMPAIGN_STATE_READY
        # RUNNING
        assert manager.open("p1", campaign.id).status == CAMPAIGN_STATE_RUNNING
        # PAUSED
        assert manager.pause("p1", campaign.id).status == CAMPAIGN_STATE_PAUSED
        # RUNNING
        assert manager.resume("p1", campaign.id).status == CAMPAIGN_STATE_RUNNING
        # WAITING_EXTERNAL
        waiting = manager._wait_external("p1", campaign.id)
        assert waiting.status == CAMPAIGN_STATE_WAITING_EXTERNAL
        # RUNNING
        assert manager.resume("p1", campaign.id).status == CAMPAIGN_STATE_RUNNING
        # COMPLETED
        assert manager.close("p1", campaign.id).status == CAMPAIGN_STATE_COMPLETED
        # ARCHIVED
        assert manager.archive("p1", campaign.id).status == CAMPAIGN_STATE_ARCHIVED

        # Корректность Journal
        loaded = manager._load("p1", campaign.id)
        events = [e.event for e in loaded.journal]
        assert events[-1] == "Campaign Archived"
        assert len(events) == 9

        # Корректность Statistics и Progress
        stats = manager.statistics("p1", campaign.id)
        assert stats.total_steps == 2
        assert 0 <= manager.progress("p1", campaign.id) <= 100

    def test_failure_path(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = manager.create(project_id="p1", goal="Goal")
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)  # RUNNING
        assert manager._fail("p1", campaign.id).status == CAMPAIGN_STATE_FAILED
        assert manager.archive("p1", campaign.id).status == CAMPAIGN_STATE_ARCHIVED

    def test_progress_reflects_steps(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        campaign = manager.create(
            project_id="p1", goal="Goal",
            steps=[CampaignStep(title="A"), CampaignStep(title="B"), CampaignStep(title="C")],
        )
        assert manager.progress("p1", campaign.id) == 0
        loaded = manager._load("p1", campaign.id)
        for step in loaded.steps:
            manager._update_step("p1", campaign.id, step.id, "completed")
        assert manager.progress("p1", campaign.id) == 100

    def test_no_forbidden_api_in_campaign_services(self) -> None:
        """Статическая проверка: сервисный слой не использует Storage."""
        services_dir = os.path.join(os.path.dirname(__file__), "..", "..", "services")
        offenders = []
        for name in sorted(os.listdir(services_dir)):
            if not name.endswith(".py") or not name.startswith("campaign_"):
                continue
            source = open(os.path.join(services_dir, name), encoding="utf-8").read()
            for pattern in FORBIDDEN_IN_CAMPAIGN_SERVICES:
                if pattern in source:
                    offenders.append(f"{name}: {pattern}")
        assert offenders == []

    def test_scenario_with_blocked_direct_api(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        manager, _ = self._manager(tmp_path)

        def fail(*args: object, **kwargs: object) -> None:
            raise AssertionError("Direct filesystem access from services!")

        monkeypatch.setattr(json_mod, "load", fail)
        monkeypatch.setattr(json_mod, "dump", fail)

        campaign = manager.create(project_id="p1", goal="Goal")
        manager.open("p1", campaign.id)
        manager.open("p1", campaign.id)
        manager.pause("p1", campaign.id)
        manager.resume("p1", campaign.id)
        manager.close("p1", campaign.id)
        manager.archive("p1", campaign.id)
        assert manager.validate("p1", campaign.id).valid is True
