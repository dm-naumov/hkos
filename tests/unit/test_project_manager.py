"""Unit tests for ProjectManager (DS-004 §5-6, IP-004 этап 05)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.exceptions import (
    ProjectNameConflictError,
    ProjectNotFoundError,
    ProjectStateError,
)
from hkos.services.project_manager import ProjectManager
from hkos.services.project_state import (
    PROJECT_STATE_ACTIVE,
    PROJECT_STATE_ARCHIVED,
    PROJECT_STATE_CREATED,
    PROJECT_STATE_PAUSED,
)
from hkos.storage import StorageEngine


class TestProjectManager:
    """Test suite for ProjectManager lifecycle API."""

    def _manager(self, tmp_path: Path) -> tuple[ProjectManager, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return ProjectManager(RepositoryManager(engine), HKOSLogger()), engine

    def test_create(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt", owner="dm", tags=["net"])
        assert project.status == PROJECT_STATE_CREATED
        assert manager.exists(project.id)

    def test_create_duplicate_name_raises(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        manager.create(name="OpenWrt")
        with pytest.raises(ProjectNameConflictError):
            manager.create(name="OpenWrt")

    def test_open(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        opened = manager.open(project.id)
        assert opened.status == PROJECT_STATE_ACTIVE

    def test_open_archived_forbidden(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        manager.archive(project.id)
        with pytest.raises(ProjectStateError):
            manager.open(project.id)

    def test_close(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        manager.open(project.id)
        closed = manager.close(project.id)
        assert closed.status == PROJECT_STATE_PAUSED

    def test_close_created_forbidden(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        with pytest.raises(ProjectStateError):
            manager.close(project.id)

    def test_archive(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        archived = manager.archive(project.id)
        assert archived.status == PROJECT_STATE_ARCHIVED

    def test_delete(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        manager.delete(project.id)
        assert not manager.exists(project.id)

    def test_delete_missing_raises(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        with pytest.raises(ProjectNotFoundError):
            manager.delete("11111111-2222-3333-4444-555555555555")

    def test_exists(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        assert manager.exists(project.id)
        assert not manager.exists("11111111-2222-3333-4444-555555555555")

    def test_info(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt", description="Router", owner="dm")
        info = manager.info(project.id)
        assert info.name == "OpenWrt"
        assert info.owner == "dm"
        assert info.status == PROJECT_STATE_CREATED
        assert info.schema_version == "1.0"
        assert info.created_at
        assert info.as_dict()["name"] == "OpenWrt"

    def test_info_missing_raises(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        with pytest.raises(ProjectNotFoundError):
            manager.info("11111111-2222-3333-4444-555555555555")

    def test_list(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        manager.create(name="A")
        manager.create(name="B")
        names = sorted(info.name for info in manager.list())
        assert names == ["A", "B"]

    def test_rename(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        renamed = manager.rename(project.id, "OpenWrt 25.12")
        assert renamed.name == "OpenWrt 25.12"
        assert renamed.id == project.id

    def test_rename_duplicate_raises(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        a = manager.create(name="A")
        manager.create(name="B")
        with pytest.raises(ProjectNameConflictError):
            manager.rename(a.id, "B")

    def test_rename_archived_forbidden(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        manager.archive(project.id)
        with pytest.raises(ProjectStateError):
            manager.rename(project.id, "X")

    def test_validate(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        result = manager.validate(project.id)
        assert result.valid is True

    def test_validate_missing(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        result = manager.validate("11111111-2222-3333-4444-555555555555")
        assert result.valid is False

    def test_state_chain(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        project = manager.create(name="OpenWrt")
        manager.open(project.id)
        manager.close(project.id)
        manager.open(project.id)
        manager.archive(project.id)
        assert manager.info(project.id).status == PROJECT_STATE_ARCHIVED

    def test_exactly_ten_public_methods(self, tmp_path: Path) -> None:
        manager, _ = self._manager(tmp_path)
        api = {name for name in dir(manager) if not name.startswith("_")}
        assert api == {
            "create", "open", "close", "archive", "delete",
            "exists", "info", "list", "rename", "validate",
        }
