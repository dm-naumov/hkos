"""Compatibility tests for the canonical Knowledge status vocabulary."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.exceptions import RepositoryError
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.models import (
    LEGACY_KNOWLEDGE_STATUS_MAP,
    VALID_KNOWLEDGE_STATUSES,
    Knowledge,
    normalize_knowledge_status,
)
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.ranking_engine import RankedCandidate
from hkos.services.librarian.knowledge_status import (
    VALID_KNOWLEDGE_STATUSES as LIBRARIAN_STATUSES,
)
from hkos.storage import StorageEngine
from hkos.storage.path_manager import PathManager

_EXPECTED_LEGACY_MAP = {
    "new": "NEW",
    "candidate": "NEW",
    "under_review": "NEW",
    "validated": "VERIFIED",
    "verified": "VERIFIED",
    "canonical": "CANONICAL",
    "superseded": "SUPERSEDED",
    "conflict": "CONFLICT",
    "rejected": "REJECTED",
    "archived": "ARCHIVED",
}


def _repo(tmp_path: Path) -> tuple[KnowledgeRepository, StorageEngine]:
    cfg = ConfigLoader(profile="development")
    cfg.load()
    engine = StorageEngine(
        root=str(tmp_path), config=cfg, logger=HKOSLogger(),
        version=VersionManager())
    engine.initialize()
    return KnowledgeRepository(engine, engine.json_store), engine


def _write_legacy(
    engine: StorageEngine, project: str, knowledge_id: str, status: str
) -> str:
    path = PathManager.knowledge_file(engine.root, project, knowledge_id)
    engine.mkdir(PathManager.knowledge(engine.root, project))
    doc = engine.json_store.create_envelope({
        "id": knowledge_id,
        "project": project,
        "title": knowledge_id,
        "status": status,
    }, "knowledge")
    engine.write_json(path, doc)
    return path


def test_repository_and_librarian_share_vocabulary() -> None:
    assert VALID_KNOWLEDGE_STATUSES is LIBRARIAN_STATUSES
    assert Knowledge().status == "NEW"


@pytest.mark.parametrize(
    ("legacy", "canonical"), sorted(_EXPECTED_LEGACY_MAP.items()))
def test_known_lowercase_statuses_normalize(
    legacy: str, canonical: str
) -> None:
    assert LEGACY_KNOWLEDGE_STATUS_MAP[legacy] == canonical
    assert normalize_knowledge_status(legacy) == canonical
    assert canonical in VALID_KNOWLEDGE_STATUSES


def test_legacy_read_is_lazy_and_next_write_is_canonical(
    tmp_path: Path
) -> None:
    repo, engine = _repo(tmp_path)
    path = _write_legacy(engine, "p", "legacy", "archived")

    loaded = repo.load("p", "legacy")

    assert loaded.status == "ARCHIVED"
    assert engine.read_json(path)["data"]["status"] == "archived"
    repo.update(loaded)
    assert engine.read_json(path)["data"]["status"] == "ARCHIVED"


def test_legacy_archived_cannot_bypass_filter(tmp_path: Path) -> None:
    repo, engine = _repo(tmp_path)
    _write_legacy(engine, "p", "legacy", "archived")
    loaded = repo.load("p", "legacy")
    ranked = RankedCandidate(
        entity=loaded, entity_type="knowledge", score=1.0,
        factors={}, sources=[])

    assert KnowledgeFilter.filter([ranked]) == []


def test_unknown_status_is_reportable_but_cannot_be_written(
    tmp_path: Path
) -> None:
    repo, _ = _repo(tmp_path)
    assert normalize_knowledge_status("limbo") == "limbo"
    with pytest.raises(RepositoryError, match="invalid Knowledge status"):
        repo.save(Knowledge(project="p", title="Invalid", status="limbo"))
