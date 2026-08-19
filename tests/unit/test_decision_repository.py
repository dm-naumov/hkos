"""Unit tests for DecisionRepository (DS-003 §10)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.decision_repository import DecisionRepository
from hkos.repository.exceptions import (
    RepositoryError,
    RepositoryNotFoundError,
)
from hkos.repository.models import DECISION_ACCEPT, Decision
from hkos.storage import StorageEngine


class TestDecisionRepository:
    """Test suite for DecisionRepository (append-only)."""

    def _repo(self, tmp_path: Path) -> tuple[DecisionRepository, str]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = DecisionRepository(engine, engine.json_store)
        repo.storage.mkdir(repo.storage.path_manager.project(engine.root, "proj-1"))
        return repo, "proj-1"

    def test_append_load_roundtrip(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        d = repo.append(Decision(project=project, decision="ACCEPT", reason="works"))
        loaded = repo.load(project, d.id)
        assert loaded.decision == DECISION_ACCEPT
        assert loaded.reason == "works"

    def test_history(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        repo.append(Decision(project=project, decision="ACCEPT"))
        repo.append(Decision(project=project, decision="REJECT"))
        history = repo.history(project)
        assert len(history.entries) == 2

    def test_latest(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        repo.append(Decision(project=project, decision="ACCEPT"))
        repo.append(Decision(project=project, decision="REJECT"))
        assert repo.latest(project).decision == "REJECT"

    def test_latest_empty_raises(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        with pytest.raises(RepositoryNotFoundError):
            repo.latest(project)

    def test_delete_forbidden(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        d = repo.append(Decision(project=project, decision="ACCEPT"))
        with pytest.raises(RepositoryError):
            repo.delete(project, d.id)

    def test_uuid_stable_after_update(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        d = repo.append(Decision(project=project, decision="ACCEPT"))
        original_id = d.id
        d.reason = "updated"
        repo.update(d)
        loaded = repo.load(project, original_id)
        assert loaded.id == original_id
        assert loaded.reason == "updated"
