"""Unit tests for ProjectValidator (DS-004 §8, IP-004 этап 04)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Project
from hkos.repository.project_repository import ProjectRepository
from hkos.services.project_validator import ProjectValidator
from hkos.storage import StorageEngine


class TestProjectValidator:
    """Test suite for ProjectValidator."""

    def _ctx(self, tmp_path: Path) -> tuple[ProjectValidator, ProjectRepository]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = ProjectRepository(engine, engine.json_store)
        return ProjectValidator(repo), repo

    def test_valid_project_passes(self, tmp_path: Path) -> None:
        validator, repo = self._ctx(tmp_path)
        project = repo.save(Project(id="11111111-2222-3333-4444-555555555555", name="OpenWrt"))
        result = validator.validate(project.id)
        assert result.valid is True
        assert result.errors == []
        assert result.as_dict()["valid"] is True

    def test_missing_project_fails(self, tmp_path: Path) -> None:
        validator, _ = self._ctx(tmp_path)
        result = validator.validate("11111111-2222-3333-4444-555555555555")
        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_invalid_uuid_fails(self, tmp_path: Path) -> None:
        validator, repo = self._ctx(tmp_path)
        project = repo.save(Project(id="not-a-uuid", name="X"))
        result = validator.validate(project.id)
        assert result.valid is False
        assert any("UUID" in e for e in result.errors)

    def test_empty_name_fails(self, tmp_path: Path) -> None:
        validator, repo = self._ctx(tmp_path)
        project = repo.save(Project(id="11111111-2222-3333-4444-555555555555", name=""))
        result = validator.validate(project.id)
        assert result.valid is False
        assert any("name" in e.lower() for e in result.errors)

    def test_invalid_state_fails(self, tmp_path: Path) -> None:
        validator, repo = self._ctx(tmp_path)
        project = repo.save(
            Project(id="11111111-2222-3333-4444-555555555555",
                    name="X", status="LIMBO")
        )
        result = validator.validate(project.id)
        assert result.valid is False
        assert any("state" in e for e in result.errors)

    def test_no_runtime_error_on_missing(self, tmp_path: Path) -> None:
        validator, _ = self._ctx(tmp_path)
        result = validator.validate("11111111-2222-3333-4444-555555555555")
        assert isinstance(result.valid, bool)

    def test_bool_conversion(self, tmp_path: Path) -> None:
        validator, repo = self._ctx(tmp_path)
        project = repo.save(Project(id="11111111-2222-3333-4444-555555555555", name="X"))
        assert validator.validate(project.id)
