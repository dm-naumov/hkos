"""Unit tests for Librarian (DS-006 §7, IP-006)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.exceptions import (
    KnowledgeNotFoundError,
    KnowledgeStatusError,
    LibrarianError,
)
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_CONFLICT,
    KNOWLEDGE_STATUS_NEW,
    KNOWLEDGE_STATUS_REJECTED,
    KNOWLEDGE_STATUS_VERIFIED,
)
from hkos.services.librarian.librarian import Librarian
from hkos.storage import StorageEngine


class TestLibrarian:
    """Test suite for Librarian lifecycle API."""

    def _librarian(self, tmp_path: Path) -> tuple[Librarian, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return Librarian(RepositoryManager(engine), HKOSLogger()), engine

    def test_register(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="TProxy UDP works", body="..."))
        assert k.status == KNOWLEDGE_STATUS_NEW
        assert k.id
        assert k.category  # классифицировано
        assert k.confidence == 50
        assert [e.event for e in k.history] == ["Created"]

    def test_register_explicit_category(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"), category="RULE")
        assert k.category == "RULE"

    def test_register_invalid_category_raises(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        with pytest.raises(LibrarianError):
            lib.register("p1", Knowledge(title="X"), category="BOGUS")

    def test_register_duplicate_id_raises(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        with pytest.raises(LibrarianError):
            lib.register("p1", Knowledge(id=k.id, title="X"))

    def test_update(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X", body="v1"))
        k2 = lib._load("p1", k.id)
        k2.body = "v2"
        k2.confirmations = 4
        updated = lib.update("p1", k2)
        assert updated.body == "v2"
        assert updated.id == k.id
        assert updated.confidence == 70  # 50 + 4*5
        assert updated.history[-1].event == "Updated"

    def test_update_missing_raises(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        with pytest.raises(KnowledgeNotFoundError):
            lib.update("p1", Knowledge(id="11111111-2222-3333-4444-555555555555", title="X"))

    def test_canonicalize_includes_verification(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        canonical = lib.canonicalize("p1", k.id)
        assert canonical.status == KNOWLEDGE_STATUS_CANONICAL
        assert canonical.history[-1].event == "Canonicalized"

    def test_canonicalize_from_rejected_forbidden(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        lib.reject("p1", k.id)
        with pytest.raises(KnowledgeStatusError):
            lib.canonicalize("p1", k.id)

    def test_category_immutable_after_canonicalization(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"), category="FACT")
        lib.canonicalize("p1", k.id)
        k2 = lib._load("p1", k.id)
        k2.category = "RULE"  # попытка смены
        updated = lib.update("p1", k2)
        assert updated.category == "FACT"

    def test_merge(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        a = lib.register("p1", Knowledge(title="TProxy UDP works", body="A"))
        b = lib.register("p1", Knowledge(title="TProxy UDP works", body="B"))
        merged = lib.merge("p1", a.id, b.id, reason="dup")
        assert merged.status == KNOWLEDGE_STATUS_CANONICAL
        assert merged.parent_ids == [a.id, b.id]
        assert merged.confidence > 0
        # Исходники не изменены
        assert lib._load("p1", a.id).status == KNOWLEDGE_STATUS_NEW

    def test_merge_missing_raises(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        with pytest.raises(KnowledgeNotFoundError):
            lib.merge("p1", "11111111-2222-3333-4444-555555555555",
                      "22222222-3333-4444-5555-666666666666")

    def test_archive_and_restore(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        assert lib.archive("p1", k.id).status == KNOWLEDGE_STATUS_ARCHIVED
        restored = lib.restore("p1", k.id)
        assert restored.status == KNOWLEDGE_STATUS_VERIFIED
        assert restored.history[-1].event == "Restored"

    def test_reject(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        assert lib.reject("p1", k.id).status == KNOWLEDGE_STATUS_REJECTED
        assert lib._load("p1", k.id).history[-1].event == "Rejected"

    def test_detect_conflicts_marks_conflict(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        lib.register("p1", Knowledge(title="X works", body=""))
        c = lib.register("p1", Knowledge(title="x works", body="", kind="negative"))
        conflicting = lib.detect_conflicts("p1", c.id)
        assert len(conflicting) >= 1
        assert lib._load("p1", c.id).status == KNOWLEDGE_STATUS_CONFLICT
        assert lib._load("p1", c.id).history[-1].event == "Conflict detected"

    def test_recalculate_confidence(self, tmp_path: Path) -> None:
        lib, engine = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        k2 = lib._load("p1", k.id)
        k2.confirmations = 5
        lib.update("p1", k2)  # confidence = 75
        # Имитация легаси-данных: устаревшее значение confidence на диске
        stale = lib._load("p1", k.id)
        stale.confidence = 10
        RepositoryManager(engine).knowledge.update(stale)
        recalculated = lib.recalculate_confidence("p1", k.id)
        assert recalculated.confidence == 75
        assert recalculated.history[-1].event == "Confidence changed"

    def test_history(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        lib.archive("p1", k.id)
        entries = lib.history("p1", k.id)
        assert [e.event for e in entries] == ["Created", "Archived"]

    def test_history_missing_raises(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        with pytest.raises(KnowledgeNotFoundError):
            lib.history("p1", "11111111-2222-3333-4444-555555555555")

    def test_validate(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="X"))
        assert lib.validate("p1", k.id).valid is True

    def test_validate_missing(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        result = lib.validate("p1", "11111111-2222-3333-4444-555555555555")
        assert result.valid is False

    def test_negative_knowledge_supported(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="TUN ломает DNS", kind="negative"))
        assert k.category == "FAILURE"
        assert k.status == KNOWLEDGE_STATUS_NEW

    def test_exactly_eleven_public_methods(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        api = {name for name in dir(lib) if not name.startswith("_")}
        assert api == {
            "register", "update", "canonicalize", "merge", "archive",
            "restore", "reject", "detect_conflicts",
            "recalculate_confidence", "history", "validate",
        }
