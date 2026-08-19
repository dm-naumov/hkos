"""Unit tests for ProjectFactory (DS-004 §7, IP-004 этап 03)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.project_repository import ProjectRepository
from hkos.services.project_factory import PROJECT_SCHEMA_VERSION, ProjectFactory
from hkos.services.project_state import PROJECT_STATE_CREATED
from hkos.storage import StorageEngine


class TestProjectFactory:
    """Test suite for ProjectFactory (creation only)."""

    def _factory(self, tmp_path: Path) -> tuple[ProjectFactory, ProjectRepository]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = ProjectRepository(engine, engine.json_store)
        return ProjectFactory(repo), repo

    def test_create_generates_uuid(self, tmp_path: Path) -> None:
        factory, repo = self._factory(tmp_path)
        project = factory.create(name="OpenWrt")
        assert project.id
        assert len(project.id) == 36  # 8-4-4-4-12

    def test_create_sets_created_state(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        project = factory.create(name="OpenWrt")
        assert project.status == PROJECT_STATE_CREATED

    def test_create_sets_schema_version(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        project = factory.create(name="OpenWrt")
        assert project.schema_version == PROJECT_SCHEMA_VERSION

    def test_create_fills_mandatory_fields(self, tmp_path: Path) -> None:
        factory, _ = self._factory(tmp_path)
        project = factory.create(
            name="OpenWrt", description="Router", owner="dm", tags=["net"]
        )
        assert project.name == "OpenWrt"
        assert project.description == "Router"
        assert project.owner == "dm"
        assert project.tags == ["net"]

    def test_create_persists_via_repository(self, tmp_path: Path) -> None:
        factory, repo = self._factory(tmp_path)
        project = factory.create(name="OpenWrt")
        assert repo.exists(project.id)
        loaded = repo.load(project.id)
        assert loaded.id == project.id
        assert loaded.name == "OpenWrt"

    def test_create_does_not_change_state_on_reload(self, tmp_path: Path) -> None:
        factory, repo = self._factory(tmp_path)
        project = factory.create(name="OpenWrt")
        loaded = repo.load(project.id)
        assert loaded.status == PROJECT_STATE_CREATED

    def test_no_factory_side_apis(self, tmp_path: Path) -> None:
        """Фабрика содержит только create (нет open/archive/rename/validate)."""
        factory, _ = self._factory(tmp_path)
        assert not hasattr(factory, "open")
        assert not hasattr(factory, "archive")
        assert not hasattr(factory, "rename")
        assert not hasattr(factory, "validate")
