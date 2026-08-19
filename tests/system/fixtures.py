"""HKOS System Test Fixtures (DS-014 ЭТАП 1).
================================================================
Фабрики данных ЧЕРЕЗ публичные интерфейсы HKOS:

- ProjectManager.create/info/list (проекты);
- CampaignManager.create/open (кампании);
- Librarian.register (знания - НЕ в обход Librarian);
- IndexEngine.build/update (индекс - только через публичный API);
- SnapshotEngine.create/load (снимки);
- PerformanceIntegration (производительность).

ЗАПРЕЩЕНО: прямое изменение JSON Repository; запись напрямую в Index;
использование Snapshot как источника истины; обход Librarian.
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

__all__ = [
    "HkosSystemContext",
    "create_system_context",
    "project_factory",
    "campaign_factory",
    "knowledge_generator",
    "snapshot_generator",
    "multi_agent_fixture",
    "performance_fixture",
]


class HkosSystemContext:
    """Полная композиция HKOS для системных тестов (DI; без singleton)."""

    def __init__(self, root: Path) -> None:
        """Инициализация (root - рабочая область теста)."""
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(root), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.projects = ProjectManager(self.repos, HKOSLogger())
        self.campaigns = CampaignManager(self.repos, HKOSLogger())
        self.librarian = Librarian(self.repos, HKOSLogger())
        self.store = IndexStore(self.engine)
        self.index = IndexEngine(self.repos, self.store, HKOSLogger())
        self.qc = IndexQueryExecutor(self.store)
        self.retrieval = RetrievalEngine(self.repos, self.qc, cfg, HKOSLogger())

    def project_ids(self) -> list[str]:
        """UUID проектов (публичный API)."""
        return [p.id for p in self.projects.list()]


def create_system_context(tmp_path: Path) -> HkosSystemContext:
    """Создать контекст системного теста (fixture-фабрика)."""
    return HkosSystemContext(tmp_path)


def project_factory(ctx: HkosSystemContext, name: str, tags: list[str] | None = None):
    """Создать проект через ProjectManager (публичный API)."""
    return ctx.projects.create(name=name, tags=tags or [])


def campaign_factory(ctx: HkosSystemContext, project_id: str, goal: str):
    """Создать кампанию через CampaignManager (публичный API)."""
    campaign = ctx.campaigns.create(project_id=project_id, goal=goal)
    ctx.campaigns.open(project_id, campaign.id)   # CREATED -> READY
    ctx.campaigns.open(project_id, campaign.id)   # READY -> RUNNING
    return campaign


def knowledge_generator(
    ctx: HkosSystemContext, project_id: str, count: int, prefix: str = "K"
) -> list[str]:
    """Создать знания ЧЕРЕЗ Librarian.register (не в обход Librarian)."""
    ids: list[str] = []
    for i in range(count):
        knowledge = ctx.librarian.register(project_id, Knowledge(
            title=f"{prefix}{i} udp", body=f"body {i} udp routing",
            tags=["udp"] if i % 2 == 0 else ["net"]))
        ids.append(knowledge.id)
    return ids


def snapshot_generator(ctx: HkosSystemContext, project_id: str, reason: str = "test"):
    """Создать снимок через SnapshotEngine (публичный API)."""
    from hkos.snapshot import SnapshotEngine

    persistence = _MemoryPersistence()
    snapshots = SnapshotEngine(ctx.repos, persistence, HKOSLogger(),
                               index_provider=ctx.qc.snapshot)
    return snapshots, snapshots.create(project_id, reason=reason)


class _MemoryPersistence:
    """In-memory порт SnapshotPersistence (тестовый; публичный порт)."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, dict[str, object]]] = {}
        self._order: dict[str, list[str]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def latest(self, project: str) -> dict[str, object] | None:
        order = self._order.get(project, [])
        if not order:
            return None
        return self._docs.get(project, {}).get(order[-1])

    def version(self, project: str, version: str) -> dict[str, object] | None:
        return self._docs.get(project, {}).get(f"snapshot-{version}")

    def save(self, project: str, doc: dict[str, object]) -> str:
        snapshot_id = str(doc.get("snapshot_id", ""))
        self._docs.setdefault(project, {})[snapshot_id] = doc
        self._order.setdefault(project, []).append(snapshot_id)
        return snapshot_id

    def history(self, project: str) -> list[dict[str, object]]:
        return self._history.get(project, [])

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        self._history.setdefault(project, []).append(entry)


def multi_agent_fixture() -> list:
    """Три агента (Planner/Executor/Reviewer) с AgentContext."""
    from hkos.integration.hermes.security import AgentContext

    return [
        AgentContext(agent_id="planner", agent_type="planner"),
        AgentContext(agent_id="executor", agent_type="executor"),
        AgentContext(agent_id="reviewer", agent_type="reviewer"),
    ]


def performance_fixture(tmp_path: Path):
    """Performance Layer поверх контекста (DI; без singleton)."""
    from hkos.performance.integration import PerformanceIntegration

    ctx = create_system_context(tmp_path)
    perf = PerformanceIntegration()
    return ctx, perf
