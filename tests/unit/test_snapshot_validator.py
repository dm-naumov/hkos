"""Unit tests for SnapshotValidator (DS-010 §15)."""

from pathlib import Path

from hkos.context.snapshot_loader import SnapshotDocument
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.snapshot.snapshot_validator import SnapshotValidator
from hkos.storage import StorageEngine


class TestSnapshotValidator:
    """Валидация: ссылки, UUID, структура, соответствие Repository."""

    def _repos(self, tmp_path: Path) -> tuple[RepositoryManager, str]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="UDP", body="udp", tags=["udp"]))
        return repos, p.id

    def test_valid_snapshot(self, tmp_path: Path) -> None:
        repos, project_id = self._repos(tmp_path)
        snapshot = SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project_id,
            statistics={"knowledge": 1},
        )
        result = SnapshotValidator(repos).validate(snapshot)
        assert result.valid is True

    def test_broken_reference(self, tmp_path: Path) -> None:
        repos, project_id = self._repos(tmp_path)
        snapshot = SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project_id,
            references=["99999999-9999-4999-8999-999999999999"],
        )
        result = SnapshotValidator(repos).validate(snapshot)
        assert result.valid is False
        assert any("Broken" in e for e in result.errors)

    def test_valid_reference(self, tmp_path: Path) -> None:
        repos, project_id = self._repos(tmp_path)
        k_id = repos.knowledge.list(project_id)[0].id
        snapshot = SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project_id,
            references=[k_id],
        )
        result = SnapshotValidator(repos).validate(snapshot)
        assert result.valid is True

    def test_empty_id(self, tmp_path: Path) -> None:
        repos, project_id = self._repos(tmp_path)
        snapshot = SnapshotDocument(project_id=project_id)
        result = SnapshotValidator(repos).validate(snapshot)
        assert result.valid is False
        assert any("id is empty" in e for e in result.errors)

    def test_statistics_mismatch_warns(self, tmp_path: Path) -> None:
        repos, project_id = self._repos(tmp_path)
        snapshot = SnapshotDocument(
            snapshot_id="snapshot-1", project_id=project_id,
            statistics={"knowledge": 999},
        )
        result = SnapshotValidator(repos).validate(snapshot)
        assert any("mismatch" in w for w in result.warnings)
