"""DS-006B §7, §10: Error model audit.

Ни одно RuntimeError/ValueError/Exception не выходит из публичных методов
Librarian наружу — только LibrarianError/KnowledgeStatusError/
KnowledgeNotFoundError или наследники HKOSError.
"""

from pathlib import Path
from typing import Callable

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.exceptions import HKOSError
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.exceptions import LibrarianError
from hkos.services.librarian.librarian import Librarian
from hkos.storage import StorageEngine

MISSING = "11111111-2222-3333-4444-555555555555"


class TestErrorModel:
    """Все исключения Librarian — наследники HKOSError."""

    def _librarian(self, tmp_path: Path) -> Librarian:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return Librarian(RepositoryManager(engine), HKOSLogger())

    def test_all_public_errors_are_hkos_errors(self, tmp_path: Path) -> None:
        lib = self._librarian(tmp_path)
        errors: list[BaseException] = []

        def capture(fn: Callable[[], object]) -> None:
            try:
                fn()
            except BaseException as e:  # noqa: BLE001 — аудит
                errors.append(e)

        capture(lambda: lib.update("p1", Knowledge(id=MISSING, title="X")))
        capture(lambda: lib.canonicalize("p1", MISSING))
        capture(lambda: lib.merge("p1", MISSING, MISSING))
        capture(lambda: lib.archive("p1", MISSING))
        capture(lambda: lib.restore("p1", MISSING))
        capture(lambda: lib.reject("p1", MISSING))
        capture(lambda: lib.detect_conflicts("p1", MISSING))
        capture(lambda: lib.recalculate_confidence("p1", MISSING))
        capture(lambda: lib.history("p1", MISSING))
        capture(lambda: lib.register("p1", Knowledge(title="X"), category="BOGUS"))

        assert len(errors) == 10
        for err in errors:
            assert isinstance(err, HKOSError), f"{type(err).__name__}: {err}"
            assert isinstance(err, LibrarianError), f"{type(err).__name__}: {err}"

    def test_no_runtime_error_escape(self, tmp_path: Path) -> None:
        lib = self._librarian(tmp_path)
        with pytest.raises(HKOSError):
            lib.reject("p1", MISSING)
