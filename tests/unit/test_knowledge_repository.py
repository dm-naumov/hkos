"""Unit tests for KnowledgeRepository (DS-003 §9)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.exceptions import RepositoryNotFoundError
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.models import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_NEW,
    Knowledge,
)
from hkos.storage import StorageEngine


class TestKnowledgeRepository:
    """Test suite for KnowledgeRepository."""

    def _repo(self, tmp_path: Path) -> tuple[KnowledgeRepository, str]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = KnowledgeRepository(engine, engine.json_store)
        repo.storage.mkdir(repo.storage.path_manager.project(engine.root, "proj-1"))
        return repo, "proj-1"

    def test_create_load_roundtrip(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="TProxy", body="UDP", tags=["tproxy"]))
        loaded = repo.load(project, k.id)
        assert loaded.title == "TProxy"
        assert loaded.body == "UDP"
        assert loaded.status == KNOWLEDGE_STATUS_NEW

    def test_uuid_stable_after_update(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="A"))
        original_id = k.id
        k.confidence = 95
        repo.update(k)
        loaded = repo.load(project, original_id)
        assert loaded.id == original_id
        assert loaded.confidence == 95

    def test_archive_sets_status(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="A"))
        repo.archive(project, k.id)
        assert repo.load(project, k.id).status == KNOWLEDGE_STATUS_ARCHIVED

    def test_search_by_tag(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        repo.create(Knowledge(project=project, title="A", tags=["tproxy", "udp"]))
        repo.create(Knowledge(project=project, title="B", tags=["tproxy"]))
        repo.create(Knowledge(project=project, title="C", tags=["dns"]))
        assert len(repo.search_by_tag(project, "tproxy")) == 2
        assert len(repo.search_by_tag(project, "dns")) == 1

    def test_search_by_type(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        repo.create(Knowledge(project=project, title="A", kind="fact"))
        repo.create(Knowledge(project=project, title="B", kind="negative"))
        assert len(repo.search_by_type(project, "negative")) == 1
        assert len(repo.search_by_type(project, "fact")) == 1

    def test_list_and_count(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        repo.create(Knowledge(project=project, title="A"))
        repo.create(Knowledge(project=project, title="B"))
        assert repo.count(project) == 2
        assert sorted(k.title for k in repo.list(project)) == ["A", "B"]

    def test_repeat_save_preserves_data(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="A"))
        k.title = "A2"
        repo.save(k)
        loaded = repo.load(project, k.id)
        assert loaded.title == "A2"
        assert loaded.id == k.id

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        with pytest.raises(RepositoryNotFoundError):
            repo.load(project, "absent")

    def test_delete(self, tmp_path: Path) -> None:
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="A"))
        repo.delete(project, k.id)
        assert not repo.exists(project, k.id)
