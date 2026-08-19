"""Unit tests: IndexCache + retrieval hot path (DS-013 ЭТАП 3)."""

import threading
import time
from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import (
    IndexCache,
    IndexEngine,
    IndexQueryExecutor,
    IndexStore,
)
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.storage import StorageEngine


class TestIndexCache:
    """Контракт кэша: get/set/invalidate/clear + fingerprint."""

    def test_miss_then_hit(self, tmp_path: Path) -> None:
        cache = IndexCache()
        assert cache.get("p1", ("fp",)) is None      # miss
        cache.set("p1", "value", ("fp",))
        assert cache.get("p1", ("fp",)) == "value"   # hit

    def test_fingerprint_mismatch_invalidates(self, tmp_path: Path) -> None:
        cache = IndexCache()
        cache.set("p1", "value", ("fp1",))
        assert cache.get("p1", ("fp2",)) is None     # внешнее изменение
        assert cache.size() == 0

    def test_invalidate(self, tmp_path: Path) -> None:
        cache = IndexCache()
        cache.set("p1", "v", ("fp",))
        cache.invalidate("p1")
        assert cache.get("p1", ("fp",)) is None

    def test_clear(self, tmp_path: Path) -> None:
        cache = IndexCache()
        cache.set("p1", "v", ("fp",))
        cache.set("p2", "v", ("fp",))
        cache.clear()
        assert cache.size() == 0

    def test_fifo_eviction(self, tmp_path: Path) -> None:
        cache = IndexCache(max_entries=2)
        cache.set("p1", "v", ("fp",))
        cache.set("p2", "v", ("fp",))
        cache.set("p3", "v", ("fp",))                # вытесняет p1
        assert cache.get("p1", ("fp",)) is None
        assert cache.get("p2", ("fp",)) == "v"

    def test_concurrent_reads(self, tmp_path: Path) -> None:
        cache = IndexCache()
        cache.set("p1", "shared", ("fp",))
        results: list[object] = []
        errors: list[Exception] = []

        def reader() -> None:
            try:
                for _ in range(50):
                    results.append(cache.get("p1", ("fp",)))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert all(r == "shared" for r in results)

    def test_concurrent_update_no_race(self, tmp_path: Path) -> None:
        cache = IndexCache()
        errors: list[Exception] = []

        def writer(prefix: str) -> None:
            try:
                for i in range(50):
                    cache.set(f"p{i}", f"{prefix}{i}", ("fp",))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(str(n),)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        # кэш целостен: любой get возвращает значение или None (не исключение)
        for i in range(50):
            value = cache.get(f"p{i}", ("fp",))
            assert value is None or str(value).endswith(str(i))


class _Harness:
    """Index + query executor + retrieval с ОБЩИМ кэшем."""

    def __init__(self, tmp_path: Path, use_cache: bool = True):
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.cache = IndexCache() if use_cache else None
        self.store = IndexStore(self.engine)
        self.index = IndexEngine(self.repos, self.store, HKOSLogger(),
                                 cache=self.cache)
        self.qc = IndexQueryExecutor(self.store, cache=self.cache)

    def corpus(self) -> str:
        p = self.repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert p is not None
        for i in range(20):
            self.repos.knowledge.save(Knowledge(
                project=p.id, title=f"K{i} udp", body=f"body {i}",
                tags=["udp"] if i % 2 == 0 else ["net"]))
        self.index.build(p.id)
        return p.id


class TestRetrievalCache:
    """Retrieval hot path с кэшем: miss -> hit; инвалидация."""

    def test_first_miss_second_hit(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        assert h.cache is not None
        project = h.corpus()
        before = h.cache.size()
        first = h.qc.snapshot(project)
        assert h.cache.size() == before + 1            # miss -> set
        second = h.qc.snapshot(project)
        assert h.cache.size() == before + 1            # hit (без нового set)
        assert first.keyword_search("udp") == second.keyword_search("udp")
        # один и тот же разобранный объект (повторное использование)
        assert first is second

    def test_index_update_invalidates(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        assert h.cache is not None
        project = h.corpus()
        h.qc.snapshot(project)                         # cold
        assert h.cache.size() == 1
        k = self._save_one(h, project)
        assert k is not None
        h.index.update(project, str(getattr(k, "id", "")), "knowledge")
        assert h.cache.size() == 0                     # -> инвалидация

    def test_index_rebuild_invalidates(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        assert h.cache is not None
        project = h.corpus()
        h.qc.snapshot(project)
        assert h.cache.size() == 1
        h.index.rebuild(project)
        assert h.cache.size() == 0

    def test_external_file_change_invalidates(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        assert h.cache is not None
        project = h.corpus()
        h.qc.snapshot(project)
        assert h.cache.size() == 1
        # внешнее изменение файла индекса (mtime меняется)
        time.sleep(0.01)
        index_file = (tmp_path / "projects" / project / "indexes" / "entities.idx")
        assert index_file.exists()
        index_file.write_text(index_file.read_text() + "\n")
        time.sleep(0.01)
        again = h.qc.snapshot(project)
        # fingerprint не совпал -> перестройка (не ошибка)
        assert again is not None

    def test_empty_index_correct(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        p = h.repos.projects.save(Project(name="Empty", tags=[]))
        assert p is not None
        h.index.build(p.id)
        snapshot = h.qc.snapshot(p.id)
        # корректный пустой индекс: только сущность самого проекта
        assert snapshot.ids() == [p.id]

    def test_broken_index_error_not_hidden(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.corpus()
        # сломать файл индекса
        index_file = (tmp_path / "projects" / project / "indexes" / "entities.idx")
        index_file.write_text("{ broken json")
        from hkos.storage.exceptions import StorageSerializationError
        with pytest.raises(StorageSerializationError):
            h.qc.snapshot(project)

    def test_determinism(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.corpus()
        first = h.qc.snapshot(project).keyword_search("udp")
        second = h.qc.snapshot(project).keyword_search("udp")
        assert first == second

    def test_no_cache_unchanged(self, tmp_path: Path) -> None:
        """Без кэша поведение не изменяется (обратная совместимость)."""
        h = _Harness(tmp_path, use_cache=False)
        project = h.corpus()
        snapshot = h.qc.snapshot(project)
        assert snapshot.ids()
        assert h.cache is None

    @staticmethod
    def _save_one(h: _Harness, project: str) -> object:
        return h.repos.knowledge.save(Knowledge(
            project=project, title="new udp fact", body="b", tags=["udp"]))


class TestCachePerformance:
    """Cold vs warm: повторные запросы без повторного parse (DS-013 §5)."""

    def test_cold_vs_warm(self, tmp_path: Path) -> None:
        import time

        h = _Harness(tmp_path)
        p = h.repos.projects.save(Project(name="Big", tags=["bulk"]))
        assert p is not None
        for i in range(10_000):
            h.repos.knowledge.save(Knowledge(
                project=p.id, title=f"K{i} udp fact", body=f"body {i}",
                tags=["udp"] if i % 2 == 0 else ["net"]))
        h.index.build(p.id)

        # COLD: первый запрос (parse индекса)
        start = time.monotonic()
        cold_snapshot = h.qc.snapshot(p.id)
        cold_ms = (time.monotonic() - start) * 1000
        assert len(cold_snapshot.ids()) > 0

        # WARM: повторные запросы (кэш; без parse)
        start = time.monotonic()
        for _ in range(20):
            h.qc.snapshot(p.id)
        warm_ms = (time.monotonic() - start) / 20 * 1000

        print(f"\ncold={cold_ms:.2f} ms warm={warm_ms:.3f} ms "
              f"speedup={cold_ms / max(warm_ms, 0.001):.0f}x")
        # цель: минимум x3 ускорение warm
        assert cold_ms >= 3 * warm_ms, (
            f"warm {warm_ms:.3f} ms не в 3 раза быстрее cold {cold_ms:.2f} ms")
        # KPI: retrieval <= 100 ms (warm — тем более)
        assert warm_ms <= 100
