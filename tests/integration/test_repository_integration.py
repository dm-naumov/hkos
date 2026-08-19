"""Integration tests: полная цепочка Repository (DS-003 §18).

Project -> Campaign -> Knowledge -> Decision -> Artifact -> StorageEngine -> JSON
"""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import (
    CAMPAIGN_STATUS_CLOSED,
    KNOWLEDGE_STATUS_ARCHIVED,
    Artifact,
    Campaign,
    Decision,
    Knowledge,
    Project,
)
from hkos.repository.repository_manager import RepositoryManager
from hkos.storage import StorageEngine


class TestRepositoryIntegration:
    """Полный жизненный цикл объектного слоя."""

    def _manager(self, tmp_path: Path) -> tuple[RepositoryManager, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return RepositoryManager(engine), engine

    def test_full_chain(self, tmp_path: Path) -> None:
        manager, engine = self._manager(tmp_path)

        # Project
        project = manager.projects.save(
            Project(name="OpenWrt", description="Router OS")
        )
        assert manager.projects.load(project.id).name == "OpenWrt"

        # Campaign
        campaign = manager.campaigns.create_campaign(
            Campaign(project=project.id, goal="TProxy research")
        )
        state = manager.campaigns.close_campaign(project.id, campaign.id)
        assert state.status == CAMPAIGN_STATUS_CLOSED

        # Knowledge
        k = manager.knowledge.create(
            Knowledge(project=project.id, title="TProxy UDP", kind="fact", tags=["tproxy"])
        )
        manager.knowledge.archive(project.id, k.id)
        assert manager.knowledge.load(project.id, k.id).status == KNOWLEDGE_STATUS_ARCHIVED

        # Decision
        d = manager.decisions.append(
            Decision(project=project.id, campaign=campaign.id, decision="ACCEPT")
        )
        assert manager.decisions.latest(project.id).id == d.id

        # Artifact
        a = manager.artifacts.save(
            Artifact(project=project.id, kind="report", path="capture.pcap", campaign=campaign.id)
        )
        assert manager.artifacts.load(project.id, a.id).path == "capture.pcap"

        # Каждый уровень независим и лежит в правильном месте хранилища
        assert engine.exists(f"projects/{project.id}/project.json")
        assert engine.exists(f"projects/{project.id}/campaigns/{campaign.id}/campaign.json")
        assert engine.exists(f"projects/{project.id}/knowledge/{k.id}.json")
        assert engine.exists(f"projects/{project.id}/decisions/{d.id}.json")
        assert engine.exists(f"projects/{project.id}/artifacts/{a.id}.json")

    def test_json_documents_are_hkos_envelopes(self, tmp_path: Path) -> None:
        manager, engine = self._manager(tmp_path)
        project = manager.projects.save(Project(name="OpenWrt"))
        doc = engine.read_json(f"projects/{project.id}/project.json")
        assert doc["schema"] == "HKOS-1.0"
        assert doc["type"] == "project"
        assert doc["version"] == 1
        assert doc["data"]["name"] == "OpenWrt"

    def test_each_level_independent(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        p1 = manager.projects.save(Project(name="A"))
        p2 = manager.projects.save(Project(name="B"))
        manager.knowledge.create(Knowledge(project=p1.id, title="only-in-A"))
        assert manager.knowledge.count(p2.id) == 0
        assert manager.knowledge.count(p1.id) == 1
