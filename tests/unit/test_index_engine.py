"""Unit tests for IndexEngine (DS-007 §6)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import (
    ENTITY_TYPE_KNOWLEDGE,
    IndexEngine,
    IndexStore,
)
from hkos.index.exceptions import IndexError, IndexNotFoundError
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.storage import StorageEngine


class TestIndexEngine:
    """Публичный API IndexEngine (ровно 8 методов + read-контракт)."""

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

    def test_build_creates_index_files(self, tmp_path: Path) -> None:
        engine, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        index.build(p.id)
        health = index.health(p.id)
        assert health["status"] == "PASS"
        index_files = health["index_files"]
        assert isinstance(index_files, dict)
        assert all(index_files.values())

    def test_statistics(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="A", tags=["x"]))
        repos.knowledge.save(Knowledge(project=p.id, title="B", tags=["x"]))
        index.build(p.id)
        stats = index.statistics(p.id)
        assert stats["knowledge"] == 2
        assert stats["projects"] == 1

    def test_statistics_not_built_raises(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt"))
        with pytest.raises(IndexNotFoundError):
            index.statistics(p.id)

    def test_update_after_entity_change(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k = repos.knowledge.save(Knowledge(project=p.id, title="A", tags=["old"]))
        index.build(p.id)
        k2 = repos.knowledge.load(p.id, k.id)
        k2.tags = ["new"]
        repos.knowledge.update(k2)
        index.update(p.id, k.id, ENTITY_TYPE_KNOWLEDGE)
        from hkos.index import TagIndex

        tags = TagIndex(index.store.read(p.id, "tags"))
        assert tags.get_by_tag("new")
        assert tags.get_by_tag("old") == []

    def test_remove(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k = repos.knowledge.save(Knowledge(project=p.id, title="A", tags=["x"]))
        index.build(p.id)
        index.remove(p.id, k.id, ENTITY_TYPE_KNOWLEDGE)
        stats = index.statistics(p.id)
        assert stats["knowledge"] == 0

    def test_rebuild(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="A", tags=["x"]))
        index.build(p.id)
        index.rebuild(p.id)
        assert index.validate(p.id).valid is True

    def test_optimize_preserves_validity(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="A", tags=["x"]))
        index.build(p.id)
        index.optimize(p.id)
        assert index.validate(p.id).valid is True

    def test_invalid_entity_type_raises(self, tmp_path: Path) -> None:
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt"))
        with pytest.raises(IndexError):
            index.update(p.id, "x", "bogus")

    def test_public_api_exact(self, tmp_path: Path) -> None:
        """Ровно 8 методов DS-007 + RelationshipReader (Freeze) + свойства."""
        _, _, index = self._ctx(tmp_path)
        api = {name for name in dir(index) if not name.startswith("_")}
        assert api == {
            "build", "rebuild", "update", "remove", "validate",
            "statistics", "optimize", "health",
            "relations_of_knowledge", "relations_of_project",
            "manager", "store",
        }
