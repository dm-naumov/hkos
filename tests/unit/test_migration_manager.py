"""Unit tests: MigrationManager (DS-011 §15, IP-011 ЭТАП 5)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.migration.backup_manager import BackupManager
from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_executor import MigrationExecutor
from hkos.migration.migration_manager import MigrationManager
from hkos.migration.migration_registry import MigrationRegistry, MigrationStep
from hkos.migration.migration_validator import MigrationValidator
from hkos.migration.rollback_manager import RollbackManager
from hkos.migration.schema_detector import SchemaDetector
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine


class _MemoryPersistence:
    """In-memory порт SnapshotPersistence."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, dict[str, object]]] = {}
        self._order: dict[str, list[str]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def latest(self, project: str) -> dict[str, object] | None:
        order = self._order.get(project, [])
        if not order:
            return None
        return self._docs.get(project, {}).get(order[-1])

    def version(self, project: str, version: str) -> dict[str, object] | None:
        return self._docs.get(project, {}).get(f"snapshot-{version}")

    def save(self, project: str, doc: dict[str, object]) -> str:
        snapshot_id = str(doc.get("snapshot_id", ""))
        self._docs.setdefault(project, {})[snapshot_id] = doc
        self._order.setdefault(project, []).append(snapshot_id)
        return snapshot_id

    def history(self, project: str) -> list[dict[str, object]]:
        return self._history.get(project, [])

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        self._history.setdefault(project, []).append(entry)


class TestMigrationManager:
    """FSM: DETECT->BACKUP->MIGRATING->REBUILD->REGENERATE->VALIDATE->COMPLETED."""

    def _ctx(
        self, tmp_path: Path,
        appliers: dict[str, Callable[[object], None]] | None = None,
    ) -> tuple[StorageEngine, RepositoryManager, Librarian, IndexEngine,
               SnapshotEngine, MigrationManager, list[str]]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        persistence = _MemoryPersistence()
        qc = IndexQueryExecutor(IndexStore(engine))
        snap = SnapshotEngine(repos, persistence, HKOSLogger(), index_provider=qc.snapshot)
        registry = MigrationRegistry()
        registry.register(MigrationStep("001_mig", 1, 2))
        applied: list[str] = []
        default_appliers: dict[str, Callable[[object], None]] = {
            "001_mig": lambda step: applied.append(
                str(getattr(step, "migration_id", "")),
            ),
        }
        appliers = appliers or default_appliers
        executor = MigrationExecutor(appliers)
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(repos, index, snap, lambda pid: [1], sample_size=100)
        detector = SchemaDetector(registry, lambda pid: [1])
        manager = MigrationManager(detector, registry, executor, backup, rollback,
                                   validator, index, snap)
        return engine, repos, lib, index, snap, manager, applied

    def _corpus(
        self, repos: RepositoryManager, lib: Librarian, index: IndexEngine
    ) -> str:
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert p is not None
        lib.register(p.id, Knowledge(title="UDP fix", body="udp", tags=["udp"]))
        index.build(p.id)
        return p.id

    def test_happy_path_fsm(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, applied = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)
        manager.migrate([project])
        assert applied == ["001_mig"]
        assert manager.status() == "COMPLETED"
        assert (tmp_path / "backup" / "001_mig_2").is_dir()
        # после миграции: индекс пересоздан, снимок пересоздан
        assert snap.load(project) is not None

    def test_order_matches_fsm(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        order: list[str] = []
        engine, repos, lib, index, snap, manager, applied = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)

        def record_apply(step: object) -> None:
            order.append("apply")
            applied.append("x")

        def record_rebuild(project_id: str) -> None:
            order.append("rebuild")
            index._manager.rebuild(project_id)

        def record_create(
            project_id: str, campaign_id: str = "", author: str = "",
            reason: str = "manual", comment: str = "", branch: str = "main",
            force: bool = False,
        ) -> object:
            order.append("regenerate")
            return snap._manager.create(
                project_id, campaign_id, author, reason, comment, branch, force,
            )

        monkeypatch.setattr(manager._executor, "apply", record_apply)
        monkeypatch.setattr(index, "rebuild", record_rebuild)
        monkeypatch.setattr(snap, "create", record_create)
        manager.migrate([project])
        assert order == ["apply", "rebuild", "regenerate"]

    def test_error_before_backup_no_rollback(self, tmp_path: Path) -> None:
        """Ошибка DETECT -> FAILED без rollback."""
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager())
        engine.initialize()
        repos = RepositoryManager(engine)
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        pers = _MemoryPersistence()
        qc = IndexQueryExecutor(IndexStore(engine))
        snap = SnapshotEngine(repos, pers, HKOSLogger(), index_provider=qc.snapshot)
        registry = MigrationRegistry()
        registry.register(MigrationStep("001_mig", 1, 2))
        # детектор бросает (неизвестная будущая версия)
        detector = SchemaDetector(registry, lambda pid: [99])
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(repos, index, snap, lambda pid: [1])
        manager = MigrationManager(detector, registry, MigrationExecutor({}), backup,
                                   rollback, validator, index, snap)
        lib = Librarian(repos, HKOSLogger())
        project = self._corpus(repos, lib, index)
        with pytest.raises(MigrationError):
            manager.migrate([project])
        assert manager.status() == "FAILED"
        assert not (tmp_path / "backup").exists()  # rollback не вызывался

    def test_error_after_backup_triggers_rollback(self, tmp_path: Path) -> None:
        """Ошибка в MIGRATING -> ROLLBACK -> FAILED."""
        def boom(step: object) -> None:
            raise RuntimeError("step failed")

        engine, repos, lib, index, snap, manager, applied = self._ctx(
            tmp_path, appliers={"001_mig": boom})
        project = self._corpus(repos, lib, index)
        with pytest.raises(MigrationError):
            manager.migrate([project])
        assert manager.status() == "FAILED"
        # backup существует; rollback восстановил Repository (индекс удалён)
        assert (tmp_path / "backup" / "001_mig_2").is_dir()
        assert not (tmp_path / "projects" / project / "indexes").exists()

    def test_idempotent_repeat(self, tmp_path: Path) -> None:
        """Повторный запуск на той же версии -> up-to-date, ноль изменений."""
        # версии отражают миграцию: после apply version становится 2
        versions: list[int] = [1]

        def _bump(step: object) -> None:
            versions[0] = 2  # имитация инкремента schema_version шагом

        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager())
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        pers = _MemoryPersistence()
        qc = IndexQueryExecutor(IndexStore(engine))
        snap = SnapshotEngine(repos, pers, HKOSLogger(), index_provider=qc.snapshot)
        registry = MigrationRegistry()
        registry.register(MigrationStep("001_mig", 1, 2))
        executor = MigrationExecutor({"001_mig": _bump})
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(repos, index, snap, lambda pid: versions,
                                       sample_size=100)
        detector = SchemaDetector(registry, lambda pid: versions)
        manager = MigrationManager(detector, registry, executor, backup, rollback,
                                   validator, index, snap)
        project = self._corpus(repos, lib, index)
        manager.migrate([project])
        backups_after_first = len(list((tmp_path / "backup").iterdir()))
        manager.migrate([project])  # повторный: detect -> pending пуст (v=2)
        assert manager.status() == "COMPLETED"
        assert versions == [2]
        assert len(list((tmp_path / "backup").iterdir())) == backups_after_first

    def test_rollback_explicit(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, applied = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        manager.backup("001_mig", 2)
        manager.rollback()
        assert manager.status() == "FAILED"

    def test_status_initial_idle(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, applied = self._ctx(tmp_path)
        assert manager.status() == "IDLE"
