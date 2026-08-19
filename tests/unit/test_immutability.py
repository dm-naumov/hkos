"""Immutability tests (IP-006 §19).

Проверяются архитектурные инварианты DS-006:
- Merge не изменяет исходные Knowledge;
- Canonicalizer не вызывает Repository;
- ConflictDetector не изменяет статус;
- Confidence не сохраняется вручную;
- History append-only;
- Repository — единственная точка записи.
"""

import inspect
from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.canonicalizer import Canonicalizer
from hkos.services.librarian.conflict_detector import ConflictDetector
from hkos.services.librarian.librarian import Librarian
from hkos.storage import StorageEngine


class TestImmutability:
    """Архитектурные инварианты Librarian (IP-006 §19)."""

    def _librarian(self, tmp_path: Path) -> Librarian:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return Librarian(RepositoryManager(engine), HKOSLogger())

    def test_merge_does_not_change_originals(self, tmp_path: Path) -> None:
        lib = self._librarian(tmp_path)
        a = lib.register("p1", Knowledge(title="TProxy UDP works", body="A"))
        b = lib.register("p1", Knowledge(title="TProxy UDP works", body="B"))
        a_snapshot = (a.title, a.body, a.status, a.confidence, len(a.history))
        b_snapshot = (b.title, b.body, b.status, b.confidence, len(b.history))
        lib.merge("p1", a.id, b.id, reason="dup")
        a_after = lib._load("p1", a.id)
        b_after = lib._load("p1", b.id)
        assert (a_after.title, a_after.body, a_after.status,
                a_after.confidence, len(a_after.history)) == a_snapshot
        assert (b_after.title, b_after.body, b_after.status,
                b_after.confidence, len(b_after.history)) == b_snapshot

    def test_canonicalizer_has_no_repository_dependency(self) -> None:
        source = inspect.getsource(Canonicalizer)
        assert "Repository" not in source
        assert "storage" not in source.lower()

    def test_conflict_detector_does_not_change_status(self, tmp_path: Path) -> None:
        lib = self._librarian(tmp_path)
        a = lib.register("p1", Knowledge(title="X works", body=""))
        lib.register("p1", Knowledge(title="x works", body="", kind="negative"))
        before = lib._load("p1", a.id).status
        lib.detect_conflicts("p1", a.id)
        # Статус A может стать CONFLICT (это делает Librarian, не Detector);
        # сам Detector статус не меняет:
        candidate = Knowledge(id="z", title="Y", status="NEW")
        others = [Knowledge(id="w", title="y", kind="negative")]
        ConflictDetector.detect(candidate, others)
        assert candidate.status == "NEW"
        assert before in ("NEW", "CONFLICT")

    def test_confidence_not_stored_manually(self) -> None:
        from hkos.services.librarian import confidence_engine

        source = inspect.getsource(confidence_engine)
        assert "confidence +=" not in source
        assert "knowledge.confidence +=" not in source

    def test_history_append_only(self, tmp_path: Path) -> None:
        lib = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="T", body=""))
        lib.archive("p1", k.id)
        loaded = lib._load("p1", k.id)
        first = loaded.history[0]
        first.event = "HACK"  # мутация в памяти не сохраняется на диск
        reloaded = lib._load("p1", k.id)
        assert reloaded.history[0].event == "Created"

    def test_librarian_source_uses_repository_only(self) -> None:
        """Librarian пишет только через RepositoryManager.knowledge."""
        source = inspect.getsource(Librarian)
        assert "StorageEngine" not in source
        assert "JSONStore" not in source
        assert "repositories.knowledge" in source
