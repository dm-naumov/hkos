"""DS-015 Fixtures (ЭТАП 1): DS015TestContext.
================================================================
Композиция ВСЕХ публичных фасадов HKOS (только через публичные API).
Запрещено: прямой Repository/Index/Snapshot mutation.
"""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian import Librarian
from hkos.services.memory_service import MemoryService
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine

__all__ = ["DS015TestContext", "create_ds015_context"]


class DS015TestContext:
    """Полный тестовый контекст DS-015 (DI; без singleton)."""

    def __init__(self, root: Path) -> None:
        """Инициализация: все публичные фасады."""
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(root), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.project = ProjectManager(self.repos, HKOSLogger())
        self.campaign = CampaignManager(self.repos, HKOSLogger())
        self.librarian = Librarian(self.repos, HKOSLogger())
        self.store = IndexStore(self.engine)
        # DS-013: общий IndexCache (production-композиция; warm-путь)
        self.index_cache = IndexCache()
        self.index = IndexEngine(self.repos, self.store, HKOSLogger(),
                                 cache=self.index_cache)
        self.qc = IndexQueryExecutor(self.store, cache=self.index_cache)
        self.retrieval = RetrievalEngine(self.repos, self.qc, cfg, HKOSLogger())
        self.context = None  # ContextBuilder подключается в тестах (DI)
        self.snapshot = None  # SnapshotEngine подключается в тестах (DI)
        self.memory = MemoryService(
            self.project, self.campaign, self.retrieval, self.context,
            self.librarian, self.index, self.snapshot, HKOSLogger())
        self.performance = None  # подключается в test_performance_regression

    def project_ids(self) -> list[str]:
        return [p.id for p in self.project.list()]


def create_ds015_context(tmp_path: Path) -> DS015TestContext:
    """Создать контекст DS-015 (fixture)."""
    return DS015TestContext(tmp_path)
