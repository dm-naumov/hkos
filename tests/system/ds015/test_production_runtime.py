"""DS-015 ЭТАП 3: Production Runtime Validation.
================================================================
Запуск HKOS с config/hkos-production.yaml: init -> project -> campaign
-> knowledge -> retrieval -> context -> save -> snapshot -> reload.
"""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine


class TestProductionRuntime:
    """Полный производственный цикл с production-конфигом."""

    def _boot(self, tmp_path: Path):
        loader = ConfigLoader(profile="production")
        config = loader.load()
        assert loader.validate() is True
        engine = StorageEngine(
            root=str(tmp_path), config=config, logger=HKOSLogger(),
            version=VersionManager())
        engine.initialize()
        repos = RepositoryManager(engine)
        projects = ProjectManager(repos, HKOSLogger())
        campaigns = CampaignManager(repos, HKOSLogger())
        librarian = Librarian(repos, HKOSLogger())
        store = IndexStore(engine)
        index = IndexEngine(repos, store, HKOSLogger())
        qc = IndexQueryExecutor(store)
        retrieval = RetrievalEngine(repos, qc, config, HKOSLogger())
        return config, engine, repos, projects, campaigns, librarian, index, qc, retrieval

    def test_production_cycle(self, tmp_path: Path) -> None:
        (config, engine, repos, projects, campaigns, librarian,
         index, qc, retrieval) = self._boot(tmp_path)
        # конфигурация применяется
        operations = config.get("operations", {})
        assert operations.get("auto_snapshot") is True
        assert operations.get("auto_index") is True
        assert operations.get("retrieve_before_task") is True
        assert operations.get("save_after_task") is True
        assert config["logging"]["level"] == "INFO"
        # project -> campaign -> knowledge
        project = projects.create(name="Prod", tags=["production"])
        campaign = campaigns.create(project.id, goal="prod-task")
        knowledge = librarian.register(project.id, Knowledge(
            title="ProdFact udp", body="udp", tags=["udp"],
            source_campaign=campaign.id))
        # index auto update
        index.update(project.id, knowledge.id, "knowledge")
        assert int(index.statistics(project.id).get("knowledge", 0)) >= 1
        # retrieval
        result = retrieval.retrieve("ProdFact", project_id=project.id)
        assert len(result.items) >= 1
        # reload (повторная инициализация = та же память)
        engine.initialize()
        assert repos.knowledge.exists(project.id, knowledge.id)
        assert repos.knowledge.count(project.id) == 1
