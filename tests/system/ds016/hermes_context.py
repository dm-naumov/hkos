"""DS-016: Hermes Runtime Context (ЭТАП 1).
================================================================
Модель Agent Runtime с HKOS-интеграцией: startup (production config +
initialize), retrieve-before-task hook, save-after-task hook.

Hermes работает ТОЛЬКО через публичные API HKOS (MemoryService/
Librarian/RetrievalEngine); HKOS — единственный SSOT; отдельной памяти
Hermes НЕТ.
"""

from pathlib import Path

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.integration.hermes.agent_lock import AgentLock
from hkos.integration.hermes.hooks import HermesProductionHooks
from hkos.performance.context_profiles import PerformanceContextOptimizer
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian import Librarian
from hkos.services.memory_service import MemoryService
from hkos.services.project_manager import ProjectManager
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine
from tests.system.fixtures import _MemoryPersistence

__all__ = ["HermesRuntimeContext", "create_hermes_context"]


class HermesRuntimeContext:
    """Agent Runtime: Hermes + HKOS (интеграция через публичные API)."""

    def __init__(self, root: Path) -> None:
        """Startup hook: production config + initialize (без изменения
        CLI-сценария Hermes).
        """
        self.config = ConfigLoader(profile="production")
        self.config.load()
        self.engine = StorageEngine(
            root=str(root), config=self.config, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()          # memory backend ready
        self.repos = RepositoryManager(self.engine)
        self.project = ProjectManager(self.repos, HKOSLogger())
        self.campaign = CampaignManager(self.repos, HKOSLogger())
        self.librarian = Librarian(self.repos, HKOSLogger())
        self.store = IndexStore(self.engine)
        self.index_cache = IndexCache()   # DS-013: warm-путь retrieval
        self.index = IndexEngine(self.repos, self.store, HKOSLogger(),
                                 cache=self.index_cache)
        self.qc = IndexQueryExecutor(self.store, cache=self.index_cache)
        self.retrieval = RetrievalEngine(self.repos, self.qc, self.config,
                                         HKOSLogger())
        # Snapshot + Context (реальные компоненты; ЭТАП 2)
        self.snapshots = SnapshotEngine(
            self.repos, _MemoryPersistence(), HKOSLogger(),
            index_provider=self.qc.snapshot)
        self.context = ContextBuilder(
            self.config, HKOSLogger(),
            loader=SnapshotLoader(lambda pid: self._load_snapshot(pid)))
        self.memory = MemoryService(
            self.project, self.campaign, self.retrieval, self.context,
            self.librarian, self.index, self.snapshots, HKOSLogger())
        # Production hooks (DS-016 ЭТАП 2)
        self.lock = AgentLock()
        self.hooks = HermesProductionHooks(
            self.memory, self.librarian, self.index, self.snapshots,
            optimizer=PerformanceContextOptimizer("NORMAL"), lock=self.lock)

    def _load_snapshot(self, project_id: str):
        snapshot = self.snapshots.load(project_id)
        return snapshot.as_dict() if snapshot is not None else None

    def retrieve_before_task(self, query: str, project_id: str,
                            campaign_id: str = "", agent_id: str = "hermes"):
        """Retrieval hook: перед задачей (через HermesProductionHooks)."""
        return self.hooks.retrieve_before_task(
            agent_id, query, project_id=project_id, campaign_id=campaign_id)

    def save_after_task(self, project_id: str, knowledge,
                        agent_id: str = "hermes"):
        """Save hook: после задачи (Librarian через hooks; canonicalize)."""
        return self.hooks.save_after_task(
            agent_id, project_id, knowledge=[knowledge])


def create_hermes_context(tmp_path: Path) -> HermesRuntimeContext:
    """Создать контекст Hermes Runtime (fixture)."""
    return HermesRuntimeContext(tmp_path)
