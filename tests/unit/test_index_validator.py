"""Unit tests for IndexValidator (DS-007 §12)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexStore
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.storage import StorageEngine


class TestIndexValidator:
    """Валидация целостности индексов."""

    def _ctx(self, tmp_path: Path) -> tuple[StorageEngine, RepositoryManager, IndexEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        return engine, repos, index

    def test_valid_index_passes(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="TProxy", tags=["tproxy"]))
        index.build(p.id)
        result = index.validate(p.id)
        assert result.valid is True
        assert result.errors == []

    def test_missing_index_fails(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt"))
        result = index.validate(p.id)
        assert result.valid is False
        assert any("missing" in e.lower() for e in result.errors)

    def test_corrupted_statistics_fails(self, tmp_path: Path) -> None:
        engine, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="T", tags=["x"]))
        index.build(p.id)
        # Портим статистику напрямую через storage
        from hkos.storage.path_manager import PathManager

        path = PathManager.index_file(engine.root, p.id, "statistics")
        doc = engine.read_json(path)
        doc["data"]["statistics"]["knowledge"] = 999
        engine.write_json(path, doc)
        result = index.validate(p.id)
        assert result.valid is False
        assert any("statistics" in e.lower() for e in result.errors)

    def test_broken_link_detected(self, tmp_path: Path) -> None:
        engine, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="T", tags=["x"]))
        index.build(p.id)
        # Добавляем в keyword-индекс запись с несуществующим id
        from hkos.index import KeywordIndex

        kw = KeywordIndex(index.store.read(p.id, "keyword"))
        kw.add("ghost-id", "knowledge", p.id, "ghostword")
        from hkos.index.index_builder import _index_doc

        index.store.write(p.id, "keyword", _index_doc(kw.data()))
        result = index.validate(p.id)
        assert result.valid is False
        assert any("broken link" in e for e in result.errors)

    def test_no_duplicates_detected(self, tmp_path: Path) -> None:
        engine, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="T", tags=["x"]))
        index.build(p.id)
        from hkos.index import KeywordIndex

        kw = KeywordIndex(index.store.read(p.id, "keyword"))
        # Прямое дублирование записи
        for word, entries in kw.data()["postings"].items():
            if entries:
                entries.append(dict(entries[0]))
                break
        from hkos.index.index_builder import _index_doc

        index.store.write(p.id, "keyword", _index_doc(kw.data()))
        result = index.validate(p.id)
        assert result.valid is False
