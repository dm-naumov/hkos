"""Unit tests: MigrationEngine (DS-011 §6/§15a, IP-011 ЭТАП 6)."""

from pathlib import Path

import pytest
from pytest import MonkeyPatch

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.migration.backup_manager import BackupManager
from hkos.migration.exceptions import MigrationError, MigrationLockError
from hkos.migration.migration_engine import MigrationEngine
from hkos.migration.migration_executor import MigrationExecutor
from hkos.migration.migration_history import MigrationHistory
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


class TestMigrationEngine:
    """Тонкий фасад: lock, history, rollback lifecycle, делегирование."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[StorageEngine, RepositoryManager, Librarian, IndexEngine,
               SnapshotEngine, MigrationManager, MigrationHistory,
               MigrationEngine]:
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
        executor = MigrationExecutor({
            "001_mig": lambda step: None,
        })
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(repos, index, snap, lambda pid: [1])
        detector = SchemaDetector(registry, lambda pid: [1])
        manager = MigrationManager(detector, registry, executor, backup, rollback,
                                   validator, index, snap)
        history = MigrationHistory()
        engine_api = MigrationEngine(
            manager, history, repos, index, snap, validator,
            lock_path=tmp_path / "migration.lock",
        )
        return engine, repos, lib, index, snap, manager, history, engine_api

    def _corpus(
        self, repos: RepositoryManager, lib: Librarian, index: IndexEngine
    ) -> str:
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert p is not None
        lib.register(p.id, Knowledge(title="UDP fix", body="udp", tags=["udp"]))
        index.build(p.id)
        return p.id

    def test_manager_delegation(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        """Engine делегирует manager; FSM не дублируется."""
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        called: list[str] = []
        original_migrate = manager.migrate

        def spy(project_ids: list[str]) -> None:
            called.append("manager.migrate")
            original_migrate(project_ids)

        monkeypatch.setattr(manager, "migrate", spy)
        api.migrate()
        assert called == ["manager.migrate"]
        assert api.status().startswith("COMPLETED")

    def test_lock_active_blocks(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        api.acquire_lock()
        with pytest.raises(MigrationLockError):
            api.detect()
        api.release_lock()

    def test_stale_lock_auto_release(self, tmp_path: Path) -> None:
        """Stale замок (>30 мин) авто-снимается при входе в migrate()."""
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        api.acquire_lock()
        # состарить замок
        import json
        (tmp_path / "migration.lock").write_text(
            json.dumps({"timestamp": 0.0, "agent": "stale"}))
        api.migrate()  # stale -> авто-снятие -> миграция проходит
        assert api.status().startswith("COMPLETED")
        assert not (tmp_path / "migration.lock").exists()

    def test_lock_released_after_migrate(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        api.migrate()
        assert not (tmp_path / "migration.lock").exists()
        # повторная миграция возможна (замок снят)
        api.detect()

    def test_history_append(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        api.migrate()
        statuses = [record.status for record in api.history()]
        assert "started" in statuses
        assert "backup_created" in statuses
        assert "applied" in statuses
        assert "completed" in statuses

    def test_history_no_dedup(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        api.migrate()
        counts: dict[str, int] = {}
        for record in api.history():
            counts[record.status] = counts.get(record.status, 0) + 1
        assert counts.get("started") == 1
        assert counts.get("completed") == 1

    def test_rollback_lifecycle(self, tmp_path: Path) -> None:
        """F-2: rollback -> restore + rebuild индексов + regenerate снимков
        + validate (производные существуют после отката)."""
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)
        api.backup("001_mig", 2)
        api.rollback()
        # индексы пересозданы (не удалены)
        assert (tmp_path / "projects" / project / "indexes").is_dir()
        # снимки пересозданы
        assert snap.load(project) is not None
        # событие rollback в журнале
        assert any(r.status == "rollback" for r in api.history())

    def test_status_composition(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, manager, history, api = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        status = api.status()
        assert "IDLE" in status
        assert "current=1" in status
        assert "target=1" in status

    def test_migrate_failure_journaling(self, tmp_path: Path) -> None:
        """Ошибка миграции -> rollback + failed в журнале."""
        def boom(step: object) -> None:
            raise RuntimeError("step boom")

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
        executor = MigrationExecutor({"001_mig": boom})
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(repos, index, snap, lambda pid: [1])
        detector = SchemaDetector(registry, lambda pid: [1])
        manager = MigrationManager(detector, registry, executor, backup, rollback,
                                   validator, index, snap)
        history = MigrationHistory()
        api = MigrationEngine(manager, history, repos, index, snap, validator,
                              lock_path=tmp_path / "migration.lock")
        self._corpus(repos, lib, index)
        with pytest.raises(MigrationError):
            api.migrate()
        statuses = [r.status for r in api.history()]
        assert "started" in statuses
        assert "failed" in statuses
        # после отката производные пересозданы быть не могут (rollback —
        # физический; rebuild — только в engine.rollback()); состояние FAILED
        assert api.status().startswith("FAILED")
        assert not (tmp_path / "migration.lock").exists()
