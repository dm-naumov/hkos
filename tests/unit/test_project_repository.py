"""Unit tests for ProjectRepository (DS-003 §7)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.exceptions import RepositoryNotFoundError
from hkos.repository.models import PROJECT_STATUS_ACTIVE, Project
from hkos.repository.project_repository import ProjectRepository
from hkos.storage import StorageEngine


class TestProjectRepository:
    """Test suite for ProjectRepository CRUD."""

    def _repo(self, tmp_path: Path) -> ProjectRepository:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return ProjectRepository(engine, engine.json_store)

    def test_save_assigns_uuid(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        project = repo.save(Project(name="OpenWrt"))
        assert project.id
        assert repo.exists(project.id)

    def test_save_preserves_given_id(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        project = repo.save(Project(id="openwrt", name="OpenWrt"))
        assert project.id == "openwrt"
        assert repo.exists("openwrt")

    def test_load_roundtrip(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        saved = repo.save(Project(name="OpenWrt", description="Router OS", tags=["networking"]))
        loaded = repo.load(saved.id)
        assert loaded.name == "OpenWrt"
        assert loaded.description == "Router OS"
        assert loaded.tags == ["networking"]
        assert loaded.status == PROJECT_STATUS_ACTIVE

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        with pytest.raises(RepositoryNotFoundError):
            repo.load("missing-project")

    def test_update_preserves_uuid(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        saved = repo.save(Project(name="OpenWrt"))
        original_id = saved.id
        saved.name = "OpenWrt 25.12"
        repo.update(saved)
        loaded = repo.load(original_id)
        assert loaded.id == original_id
        assert loaded.name == "OpenWrt 25.12"

    def test_update_missing_raises(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        with pytest.raises(RepositoryNotFoundError):
            repo.update(Project(id="absent", name="X"))

    def test_delete_removes_project(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        saved = repo.save(Project(name="OpenWrt"))
        repo.delete(saved.id)
        assert not repo.exists(saved.id)

    def test_delete_missing_raises(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        with pytest.raises(RepositoryNotFoundError):
            repo.delete("absent")

    def test_list_and_count(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        repo.save(Project(name="A"))
        repo.save(Project(name="B"))
        assert repo.count() == 2
        assert sorted(p.name for p in repo.list()) == ["A", "B"]

    def test_repeat_save_preserves_data(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        saved = repo.save(Project(name="OpenWrt"))
        saved.name = "OpenWrt v2"
        repo.save(saved)  # повторное сохранение
        loaded = repo.load(saved.id)
        assert loaded.name == "OpenWrt v2"
        assert loaded.id == saved.id
