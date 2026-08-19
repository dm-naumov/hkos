"""Integration tests: Librarian (DS-006 §20, IP-006).

Сценарии:
1. Knowledge A -> Verified -> Canonical
2. Knowledge A + B -> Merge -> Canonical
3. Knowledge A + C (противоречит) -> Conflict
4. Knowledge -> Rejected -> History

Дополнительно: отсутствие прямого обращения к Storage Engine
(статический скан + блокировка прямых API).
"""

import json as json_mod
import os
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_CONFLICT,
    KNOWLEDGE_STATUS_REJECTED,
    KnowledgeStatus,
)
from hkos.services.librarian.librarian import Librarian
from hkos.storage import StorageEngine

FORBIDDEN_IN_LIBRARIAN = [
    "StorageEngine",
    "JSONStore",
    "FileStore",
    "AtomicWriter",
    "PathManager",
    "os.makedirs",
    "os.remove",
    "os.listdir",
    "import json",
    "from json",
    "import pathlib",
    "from pathlib",
]


class TestLibrarianIntegration:
    """Полные сценарии жизненного цикла Knowledge."""

    def _librarian(self, tmp_path: Path) -> tuple[Librarian, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return Librarian(RepositoryManager(engine), HKOSLogger()), engine

    def test_scenario1_verified_then_canonical(self, tmp_path: Path) -> None:
        lib, engine = self._librarian(tmp_path)
        a = lib.register("p1", Knowledge(title="TProxy UDP works", body="..."))
        assert engine.exists(f"projects/p1/knowledge/{a.id}.json")
        # канонизация включает верификацию: NEW -> VERIFIED -> CANONICAL
        canonical = lib.canonicalize("p1", a.id)
        assert canonical.status == KNOWLEDGE_STATUS_CANONICAL
        assert KnowledgeStatus.is_canonical(canonical)
        assert canonical.history[-1].event == "Canonicalized"

    def test_scenario2_merge_to_canonical(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        a = lib.register("p1", Knowledge(title="TProxy UDP works", body="from A"))
        b = lib.register("p1", Knowledge(title="tproxy udp works", body="from B"))
        merged = lib.merge("p1", a.id, b.id, reason="same observation")
        assert merged.status == KNOWLEDGE_STATUS_CANONICAL
        assert merged.parent_ids == [a.id, b.id]
        assert "merge_reason=same observation" in merged.history[0].details
        # Исходники остались нетронутыми (immutability)
        assert lib._load("p1", a.id).title == "TProxy UDP works"
        assert lib._load("p1", b.id).title == "tproxy udp works"

    def test_scenario3_conflict(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        lib.register("p1", Knowledge(title="TProxy UDP works", body=""))
        contradicting = lib.register(
            "p1", Knowledge(title="tproxy udp works", body="", kind="negative")
        )
        conflicting = lib.detect_conflicts("p1", contradicting.id)
        assert len(conflicting) >= 1
        status = lib._load("p1", contradicting.id)
        assert status.status == KNOWLEDGE_STATUS_CONFLICT
        assert status.history[-1].event == "Conflict detected"

    def test_scenario4_rejected_with_history(self, tmp_path: Path) -> None:
        lib, _ = self._librarian(tmp_path)
        k = lib.register("p1", Knowledge(title="Bad idea", body=""))
        rejected = lib.reject("p1", k.id)
        assert rejected.status == KNOWLEDGE_STATUS_REJECTED
        events = [e.event for e in lib.history("p1", k.id)]
        assert events == ["Created", "Rejected"]

    def test_no_forbidden_api_in_librarian_source(self) -> None:
        """Статическая проверка: Librarian не использует Storage/поиск."""
        lib_dir = os.path.join(os.path.dirname(__file__), "..", "..",
                               "services", "librarian")
        offenders = []
        for name in sorted(os.listdir(lib_dir)):
            if not name.endswith(".py"):
                continue
            source = open(os.path.join(lib_dir, name), encoding="utf-8").read()
            for pattern in FORBIDDEN_IN_LIBRARIAN:
                if pattern in source:
                    offenders.append(f"{name}: {pattern}")
        assert offenders == []

    def test_scenario_with_blocked_direct_api(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        lib, _ = self._librarian(tmp_path)

        def fail(*args: object, **kwargs: object) -> None:
            raise AssertionError("Direct filesystem access from Librarian!")

        monkeypatch.setattr(json_mod, "load", fail)
        monkeypatch.setattr(json_mod, "dump", fail)

        k = lib.register("p1", Knowledge(title="X", body=""))
        lib.canonicalize("p1", k.id)
        lib.archive("p1", k.id)
        assert lib.validate("p1", k.id).valid is True
