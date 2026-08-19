"""DS-017: Production Hardening — regression suite.

================================================================
Campaign lifecycle consistency (get_or_create), Repository == Index ==
Snapshot (doctor), защита от duplicate campaigns, archive/retrieval,
snapshot restore. Все проверки — через публичные API.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.integration.hermes.agent_lock import AgentLock
from hkos.integration.hermes.doctor import HkosDoctor
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


class HardeningContext:
    """Production-подобный контекст (MemoryService + hooks + doctor)."""

    def __init__(self, tmp_path: Path) -> None:
        """Собрать production-подобный контекст (public API + doctor)."""
        self.config = ConfigLoader(profile="production")
        self.config.load()
        self.engine = StorageEngine(
            root=str(tmp_path), config=self.config, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.projects = ProjectManager(self.repos, HKOSLogger())
        self.campaigns = CampaignManager(self.repos, HKOSLogger())
        self.librarian = Librarian(self.repos, HKOSLogger())
        self.store = IndexStore(self.engine)
        self.index_cache = IndexCache()
        self.index = IndexEngine(self.repos, self.store, HKOSLogger(),
                                 cache=self.index_cache)
        self.qc = IndexQueryExecutor(self.store, cache=self.index_cache)
        self.retrieval = RetrievalEngine(self.repos, self.qc, self.config,
                                         HKOSLogger())
        self.snapshots = SnapshotEngine(
            self.repos, _MemoryPersistence(), HKOSLogger(),
            index_provider=self.qc.snapshot)
        self.context = ContextBuilder(
            self.config, HKOSLogger(),
            loader=SnapshotLoader(
                lambda pid: (self.snapshots.load(pid).as_dict()
                             if self.snapshots.load(pid) else None)))
        self.memory = MemoryService(
            self.projects, self.campaigns, self.retrieval, self.context,
            self.librarian, self.index, self.snapshots, HKOSLogger())
        self.lock = AgentLock()
        self.hooks = HermesProductionHooks(
            self.memory, self.librarian, self.index, self.snapshots,
            optimizer=PerformanceContextOptimizer("NORMAL"), lock=self.lock)
        self.doctor = HkosDoctor(
            self.repos, self.index, self.snapshots, self.store)


class TestCampaignCreationConsistency:
    """Test 1: create campaign -> Repository == Index == Snapshot."""

    def test_create_campaign_syncs_derived(self, tmp_path: Path) -> None:
        """Кампания через resolve_campaign синхронизирует Repository/Index/Snapshot."""
        ctx = HardeningContext(tmp_path)
        project = ctx.projects.create(name="P1")
        pid = project.id
        campaign = ctx.memory.resolve_campaign(pid, goal="goal-one")
        # Repository и Index синхронны сразу (фикс incident 001)
        assert len(ctx.repos.campaigns.list(pid)) == 1
        assert ctx.index.statistics(pid)["campaigns"] == 1
        # Snapshot отражает состояние после refresh
        ctx.snapshots.create(pid, reason="t1")
        report = ctx.doctor.check(pid)
        assert report.verdict == "PASS", report.summary()
        assert campaign.id is not None


class TestHundredRetrieveSingleCampaign:
    """Test 2: 100 retrieve_before_task -> одна логическая кампания."""

    def test_100_retrieve_creates_one_campaign(self, tmp_path: Path) -> None:
        """100 retrieve с одним goal создают одну логическую кампанию."""
        ctx = HardeningContext(tmp_path)
        project = ctx.projects.create(name="P2")
        pid = project.id
        for _ in range(100):
            ctx.hooks.retrieve_before_task(
                agent_id="a", query="udp fix",
                project_id=pid, goal="same-goal")
        campaigns = ctx.repos.campaigns.list(pid)
        assert len(campaigns) == 1, f"expected 1 campaign, got {len(campaigns)}"
        # и индекс согласован
        assert ctx.index.statistics(pid)["campaigns"] == 1


class TestConcurrentCampaignCreation:
    """Test 3: 5 агентов x 50 операций -> нет дублей кампании."""

    def test_concurrent_retrieve_no_duplicates(self, tmp_path: Path) -> None:
        """5 агентов x 50 операций: без дублей кампании (AgentLock WRITE)."""
        ctx = HardeningContext(tmp_path)
        project = ctx.projects.create(name="P3")
        pid = project.id

        def work(_: int) -> None:
            for _ in range(50):
                ctx.hooks.retrieve_before_task(
                    agent_id="agent", query="udp chatgpt",
                    project_id=pid, goal="concurrent-goal")

        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(work, range(5)))
        campaigns = ctx.repos.campaigns.list(pid)
        assert len(campaigns) == 1, (
            f"expected 1 campaign, got {len(campaigns)}")
        assert ctx.index.statistics(pid)["campaigns"] == 1


class TestArchiveCampaignNotUsed:
    """Test 4: archived campaign не используется retrieval'ом."""

    def test_archived_campaign_not_retrieved(self, tmp_path: Path) -> None:
        """Архивная кампания не попадает в retrieval-выдачу."""
        ctx = HardeningContext(tmp_path)
        project = ctx.projects.create(name="P4")
        pid = project.id
        campaign = ctx.memory.resolve_campaign(pid, goal="archive-me-goal")
        # FSM: CREATED -> READY -> RUNNING -> COMPLETED -> ARCHIVED
        ctx.campaigns.open(pid, campaign.id)
        ctx.campaigns.open(pid, campaign.id)
        ctx.campaigns.close(pid, campaign.id)
        ctx.campaigns.archive(pid, campaign.id)
        result = ctx.retrieval.retrieve("archive-me-goal", project_id=pid)
        entity_types = {type(i.entity).__name__ for i in result.items}
        assert "Campaign" not in entity_types, (
            f"campaign leaked into retrieval: {entity_types}")
        # консистентность сохранена (архивация не удаляет из repo/index)
        assert ctx.index.statistics(pid)["campaigns"] == 1
        ctx.snapshots.create(pid, reason="t4")
        assert ctx.doctor.check(pid).verdict == "PASS"


class TestSnapshotRestoreConsistency:
    """Test 5: snapshot -> мутация -> refresh -> doctor PASS."""

    def test_snapshot_refresh_restores_consistency(self, tmp_path: Path) -> None:
        """Stale-снапшот обнаруживается doctor; refresh восстанавливает PASS."""
        ctx = HardeningContext(tmp_path)
        project = ctx.projects.create(name="P5")
        pid = project.id
        ctx.memory.resolve_campaign(pid, goal="snap-goal")
        knowledge = ctx.librarian.register(pid, KnowledgeFactory.knowledge())
        ctx.index.update(pid, knowledge.id, "knowledge")
        ctx.snapshots.create(pid, reason="snap1")
        # мутация после снапшота -> doctor обнаруживает stale
        extra = ctx.librarian.register(pid, KnowledgeFactory.knowledge())
        ctx.index.update(pid, extra.id, "knowledge")
        report = ctx.doctor.check(pid)
        assert report.verdict == "FAIL", "doctor must detect stale snapshot"
        assert any("snapshot knowledge" in i.check and i.status == "FAIL"
                   for i in report.issues)
        # refresh -> консистентность восстановлена
        ctx.snapshots.create(pid, reason="snap2", force=True)
        assert ctx.doctor.check(pid).verdict == "PASS"


class KnowledgeFactory:
    """Минимальный источник знаний для тестов (без обхода Librarian)."""

    @staticmethod
    def knowledge():
        """Знание для тестов (через Librarian, без обхода)."""
        from hkos.repository.models import Knowledge
        return Knowledge(title="Kfact udp", body="udp", tags=["udp"])
