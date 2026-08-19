"""Post-Audit Refinement: идемпотентность жизненного цикла и валидация категорий."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.services.librarian.exceptions import LibrarianError
from hkos.storage import StorageEngine


class TestLifecycleIdempotency:
    """Повторные операции жизненного цикла (Post-Audit Refinement)."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[RepositoryManager, Librarian, str]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        return repos, lib, p.id

    def test_canonicalize_idempotent(self, tmp_path: Path) -> None:
        """Повторный canonicalize(canonical) — no-op, без исключения."""
        repos, lib, project = self._ctx(tmp_path)
        k = lib.register(project, Knowledge(title="UDP", body="udp", tags=["udp"]))
        first = lib.canonicalize(project, k.id)
        # Повторная канонизация не бросает и не меняет результат
        second = lib.canonicalize(project, k.id)
        assert first.id == second.id
        assert second.status == "CANONICAL"

    def test_merge_self_rejected(self, tmp_path: Path) -> None:
        """merge(a, a) — осмысленно невозможно (guard)."""
        repos, lib, project = self._ctx(tmp_path)
        k = lib.register(project, Knowledge(title="UDP", body="udp", tags=["udp"]))
        with pytest.raises(LibrarianError):
            lib.merge(project, k.id, k.id)

    def test_update_invalid_category_rejected(self, tmp_path: Path) -> None:
        """Замкнутый словарь категорий: недопустимая категория отклоняется."""
        repos, lib, project = self._ctx(tmp_path)
        k = lib.register(project, Knowledge(title="UDP", body="udp", tags=["udp"]))
        k.category = "BOGUS"
        with pytest.raises(LibrarianError):
            lib.update(project, k)

    def test_update_valid_category_accepted(self, tmp_path: Path) -> None:
        repos, lib, project = self._ctx(tmp_path)
        k = lib.register(project, Knowledge(title="UDP", body="udp", tags=["udp"]))
        k.category = "CONFIGURATION"
        updated = lib.update(project, k)
        assert updated.category == "CONFIGURATION"


class TestSnapshotDocumentOwnership:
    """SnapshotDocument живёт в kernel; context re-export сохраняет совместимость."""

    def test_kernel_identity(self) -> None:
        from hkos.context.snapshot_loader import SnapshotDocument as CtxDoc
        from hkos.kernel.snapshot_document import SnapshotDocument as KernelDoc

        assert CtxDoc is KernelDoc  # один и тот же тип (re-export)

    def test_roundtrip(self) -> None:
        from hkos.kernel.snapshot_document import SnapshotDocument

        doc = SnapshotDocument(snapshot_id="snapshot-00001", project_id="p1",
                               sections={"Canonical Knowledge": []})
        restored = SnapshotDocument.from_dict(doc.as_dict())
        assert restored.snapshot_id == "snapshot-00001"
        assert restored.sections == {"Canonical Knowledge": []}
