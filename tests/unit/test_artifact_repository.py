"""Unit tests for ArtifactRepository (DS-003 §11)."""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.artifact_repository import ArtifactRepository
from hkos.repository.models import (
    ARTIFACT_STATUS_ACTIVE,
    ARTIFACT_STATUS_ARCHIVED,
    Artifact,
)
from hkos.storage import StorageEngine


class TestArtifactRepository:
    """Test suite for ArtifactRepository."""

    def _repo(self, tmp_path: Path) -> tuple[ArtifactRepository, str]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = ArtifactRepository(engine, engine.json_store)
        repo.storage.mkdir(repo.storage.path_manager.project(engine.root, "proj-1"))
        return repo, "proj-1"

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        a = repo.save(Artifact(project=project, kind="report", path="/x.pdf"))
        loaded = repo.load(project, a.id)
        assert loaded.kind == "report"
        assert loaded.path == "/x.pdf"
        assert loaded.status == ARTIFACT_STATUS_ACTIVE

    def test_uuid_stable_after_update(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        a = repo.save(Artifact(project=project, kind="report"))
        original_id = a.id
        a.checksum = "abc123"
        repo.update(a)
        loaded = repo.load(project, original_id)
        assert loaded.id == original_id
        assert loaded.checksum == "abc123"

    def test_archive(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        a = repo.save(Artifact(project=project, kind="report"))
        repo.archive(project, a.id)
        assert repo.load(project, a.id).status == ARTIFACT_STATUS_ARCHIVED

    def test_list_and_count(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        repo.save(Artifact(project=project, kind="report"))
        repo.save(Artifact(project=project, kind="config"))
        assert repo.count(project) == 2
        assert sorted(a.kind for a in repo.list(project)) == ["config", "report"]
