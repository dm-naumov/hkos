"""Integration tests: Performance Integration (DS-013 ЭТАП 5 §10-11)."""

import time
from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.performance.integration import PerformanceIntegration
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.librarian import Librarian
from hkos.storage import StorageEngine


class _Harness:
    """Pipeline с Performance-обёртками (DI)."""

    def __init__(self, tmp_path: Path):
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.lib = Librarian(self.repos, HKOSLogger())
        self.store = IndexStore(self.engine)
        self.index = IndexEngine(self.repos, self.store, HKOSLogger())
        self.qc = IndexQueryExecutor(self.store)
        self.retrieval = RetrievalEngine(self.repos, self.qc, cfg, HKOSLogger())
        self.perf = PerformanceIntegration()
        self.measured_retrieval = self.perf.wrap_retrieval(
            self.retrieval, fingerprint=self.store.fingerprint)
        self.measured_save = self.perf.wrap_save(self.lib)
        self.measured_index = self.perf.wrap_index(self.index)

    def corpus(self, n: int = 50) -> str:
        p = self.repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert p is not None
        for i in range(n):
            self.repos.knowledge.save(Knowledge(
                project=p.id, title=f"K{i} udp fix", body=f"body {i} udp",
                tags=["udp"] if i % 2 == 0 else ["net"]))
        self.index.build(p.id)
        return p.id


class TestPerformanceScenarios:
    """Сценарии 1-5 (DS-013 ЭТАП 5 §10)."""

    def test_scenario_1_cold_retrieval(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.corpus()
        result = h.measured_retrieval.retrieve("udp", project_id=project)
        assert len(result.items) >= 1
        stats = h.perf.cache.statistics()
        misses = stats.get("misses", 0)
        assert isinstance(misses, int) and misses >= 1  # cold: miss

    def test_scenario_2_warm_retrieval(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.corpus()
        first = h.measured_retrieval.retrieve("udp", project_id=project)
        second = h.measured_retrieval.retrieve("udp", project_id=project)
        assert len(first.items) == len(second.items)
        stats = h.perf.cache.statistics()
        hits = stats.get("hits", 0)
        assert isinstance(hits, int) and hits >= 1  # warm: cache hit

    def test_scenario_3_context_compression(self, tmp_path: Path) -> None:
        """Large Context -> Compression -> Token reduction."""
        from hkos.context.models import ContextDocument, ContextItem
        from hkos.repository.models import Knowledge

        h = _Harness(tmp_path)
        items = [
            ContextItem(entity=Knowledge(title=f"Knowledge {i}", body="udp " * 20,
                                         tags=["udp"]),
                        entity_type="knowledge")
            for i in range(20)
        ]
        decision = Knowledge(title="Decision keep", body="decision",
                             tags=["d"], category="DECISION")
        items.append(ContextItem(entity=decision, entity_type="knowledge"))
        context = ContextDocument(items=items, project_id="p1")
        from hkos.performance.context_profiles import CompressedContext

        before = len(context.items)
        compressed = h.perf.optimizer.compress(context)
        assert isinstance(compressed, CompressedContext)
        after = compressed.item_count()
        # protected (DECISIONS) сохранено; NORMAL сжимает не-protected
        assert after < before
        decisions = compressed.sections.get("DECISIONS", [])
        assert any(
            str(getattr(getattr(i, "entity", i), "title", "")) == "Decision keep"
            for i in decisions
        )

    def test_scenario_4_repeated_query_no_repository(self, tmp_path: Path) -> None:
        """Repeated query: cache hit -> без обращения к Repository."""
        h = _Harness(tmp_path)
        project = h.corpus()
        first = h.measured_retrieval.retrieve("udp", project_id=project)
        second = h.measured_retrieval.retrieve("udp", project_id=project)
        stats = h.perf.cache.statistics()
        hits = stats.get("hits", 0)
        assert isinstance(hits, int) and hits >= 1
        # cache hit: второй запрос НЕ обращается к pipeline (Repository)
        assert len(first.items) == len(second.items)
        ratio = stats.get("hit_ratio", 0)
        assert isinstance(ratio, float) and ratio >= 0.4

    def test_scenario_5_performance_failure_continues(self, tmp_path: Path) -> None:
        """Сбой компонента -> warning -> pipeline продолжается."""
        h = _Harness(tmp_path)
        project = h.corpus()

        class BrokenRetrieval:
            def retrieve(self, query: str, **kwargs: object) -> object:
                raise RuntimeError("retrieval down")

        h.perf._cache.clear()
        broken_wrapped = h.perf.wrap_retrieval(BrokenRetrieval(), fingerprint=lambda p: "fp")
        try:
            broken_wrapped.retrieve("udp", project_id=project)
            raised = False
        except RuntimeError:
            raised = True
        # исключение НЕ скрывается (измерение не меняет поведение)
        assert raised is True
        # pipeline продолжает работать на исправном компоненте
        ok = h.measured_retrieval.retrieve("udp", project_id=project)
        assert len(ok.items) >= 1


class TestPerformanceValidation:
    """Бюджеты (DS-013 ЭТАП 5 §11)."""

    def test_retrieval_budget(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.corpus(200)
        start = time.perf_counter()
        h.retrieval.retrieve("udp", project_id=project)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 100, f"retrieval {elapsed:.1f} ms"

    def test_snapshot_load_budget(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.corpus(50)
        # save budget
        start = time.perf_counter()
        h.measured_save.register(project, Knowledge(
            title="new", body="b", tags=["t"]))
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 150, f"save {elapsed:.1f} ms"

    def test_profiler_overhead(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        start = time.perf_counter()
        for _ in range(50):
            with h.perf.manager.measure("op"):
                pass
        elapsed = (time.perf_counter() - start) / 50 * 1000
        assert elapsed < 2.0, f"profiler {elapsed:.3f} ms"

    def test_metrics_overhead(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        start = time.perf_counter()
        for _ in range(100):
            h.perf.manager._metrics.record("op", 1.0)
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed < 1.0, f"metrics {elapsed:.3f} ms"

    def test_cache_hit_ratio_above_80_percent(self, tmp_path: Path) -> None:
        """Повторные идентичные запросы: hit ratio > 80%."""
        h = _Harness(tmp_path)
        project = h.corpus(50)
        for _ in range(10):
            h.measured_retrieval.retrieve("udp", project_id=project)
        stats = h.perf.cache.statistics()
        ratio = stats.get("hit_ratio", 0)
        assert isinstance(ratio, float) and ratio >= 0.8
