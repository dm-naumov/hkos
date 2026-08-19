"""Integration tests: DS-011 Migration Engine (IP-011 ЭТАП 7).

11 сценариев: полный конвейер, rollback, идемпотентность, lock,
stale lock, ABORT, legacy, append-only history, keep-N, производные
после rollback, retrieval после rollback.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

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
from hkos.retrieval import RetrievalEngine, RetrievalItem
from hkos.services.librarian import Librarian
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine


class _Persistence:
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


class _Harness:
    """Композиция полного конвейера DS-011 для интеграционных сценариев."""

    def __init__(self, tmp_path: Path, versions: list[int] | None = None,
                 appliers: dict[str, Callable[[object], None]] | None = None):
        self.versions = versions if versions is not None else [1]
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.lib = Librarian(self.repos, HKOSLogger())
        self.index = IndexEngine(self.repos, IndexStore(self.engine), HKOSLogger())
        self.persistence = _Persistence()
        qc = IndexQueryExecutor(IndexStore(self.engine))
        self.snap = SnapshotEngine(self.repos, self.persistence, HKOSLogger(),
                                   index_provider=qc.snapshot)
        self.registry = MigrationRegistry()
        self.registry.register(MigrationStep("001_mig", 1, 2))
        self.applied: list[str] = []
        default_appliers: dict[str, Callable[[object], None]] = {
            "001_mig": lambda step: self.applied.append("001_mig"),
        }
        self.executor = MigrationExecutor(appliers or default_appliers)
        self.backup = BackupManager(tmp_path, keep_n=3)
        self.rollback = RollbackManager(tmp_path)
        self.validator = MigrationValidator(
            self.repos, self.index, self.snap, lambda pid: self.versions,
            sample_size=1000)
        self.detector = SchemaDetector(self.registry, lambda pid: self.versions)
        self.manager = MigrationManager(
            self.detector, self.registry, self.executor, self.backup,
            self.rollback, self.validator, self.index, self.snap)
        self.history = MigrationHistory()
        self.api = MigrationEngine(
            self.manager, self.history, self.repos, self.index, self.snap,
            self.validator, lock_path=tmp_path / "migration.lock")

    def corpus(self) -> str:
        p = self.repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert p is not None
        k = self.lib.register(p.id, Knowledge(
            title="UDP fix", body="udp", tags=["udp"], confirmations=8))
        self.lib.canonicalize(p.id, k.id)
        self.index.build(p.id)
        return p.id

    def query(self, project: str, query: str) -> list["RetrievalItem"]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        rv = RetrievalEngine(self.repos, IndexQueryExecutor(IndexStore(self.engine)),
                             cfg, HKOSLogger())
        result = rv.retrieve(query, project_id=project)
        return result.items


class TestMigrationIntegration:
    """Полные сценарии DS-011 §19 / IP-011 ЭТАП 7."""

    def test_scenario_1_full_pipeline(self, tmp_path: Path) -> None:
        """v1 -> Migrate -> v2 -> rebuild -> regenerate -> validate -> COMPLETED."""
        h = _Harness(tmp_path)
        project = h.corpus()
        h.api.migrate()
        assert h.api.status().startswith("COMPLETED")
        assert h.applied == ["001_mig"]
        assert h.api.history()[-1].status == "completed"
        # производные существуют
        assert h.index.validate(project).valid is True
        assert h.snap.load(project) is not None

    def test_scenario_2_error_rollback_restore(self, tmp_path: Path) -> None:
        """Ошибка apply -> Rollback -> Repository восстановлен."""
        def boom(step: object) -> None:
            raise RuntimeError("apply boom")

        h = _Harness(tmp_path, appliers={"001_mig": boom})
        project = h.corpus()
        knowledge_dir = tmp_path / "projects" / project / "knowledge"
        before = sorted(p.name for p in knowledge_dir.iterdir())
        with pytest.raises(MigrationError):
            h.api.migrate()
        assert h.api.status().startswith("FAILED")
        after = sorted(p.name for p in knowledge_dir.iterdir())
        assert before == after  # Repository полностью восстановлен
        # rollback события в журнале
        statuses = [r.status for r in h.api.history()]
        assert "rollback" in statuses
        assert "failed" in statuses

    def test_scenario_3_repeat_up_to_date(self, tmp_path: Path) -> None:
        """Повторный запуск: up-to-date, ноль изменений, ноль новых backup."""
        h = _Harness(tmp_path)
        h.corpus()
        h.api.migrate()
        backups = len(list((tmp_path / "backup").iterdir()))
        entries_before = len(h.api.history())
        h.versions[0] = 2  # после миграции версия 2
        h.api.migrate()
        assert h.api.status().startswith("COMPLETED")
        assert len(list((tmp_path / "backup").iterdir())) == backups
        assert len(h.api.history()) > entries_before  # append-only: факт запуска
        # шаг повторно не применялся
        assert h.applied == ["001_mig"]

    def test_scenario_4_concurrent_lock(self, tmp_path: Path) -> None:
        """Второй engine при активной миграции -> MigrationLockError."""
        h = _Harness(tmp_path)
        h.corpus()
        h.api.acquire_lock()
        # второй engine с ТЕМ ЖЕ lock-файлом -> MigrationLockError
        h2 = _Harness(tmp_path / "second")
        h2.api._lock_path = tmp_path / "migration.lock"
        with pytest.raises(MigrationLockError):
            h2.api.migrate()
        h.api.release_lock()
        # после снятия — доступен
        h2.api.detect()

    def test_scenario_5_stale_lock(self, tmp_path: Path) -> None:
        """Stale lock -> авто-снятие -> успешный запуск."""
        import json
        h = _Harness(tmp_path)
        h.corpus()
        lock = tmp_path / "migration.lock"
        lock.write_text(json.dumps({"timestamp": 0.0, "agent": "stale"}))
        h.api.migrate()
        assert h.api.status().startswith("COMPLETED")
        assert not lock.exists()

    def test_scenario_6_future_version_abort(self, tmp_path: Path) -> None:
        """Неизвестная будущая schema_version -> ABORT, без backup/rollback."""
        h = _Harness(tmp_path, versions=[99])
        h.corpus()
        with pytest.raises(MigrationError):
            h.api.migrate()
        assert not (tmp_path / "backup").exists()
        assert h.api.status().startswith("FAILED")

    def test_scenario_7_legacy_documents(self, tmp_path: Path) -> None:
        """Документы без version -> детектируются как v1 (legacy)."""
        h = _Harness(tmp_path, versions=[1])
        h.corpus()
        info = h.api.detect()
        assert info.current_version == 1
        assert info.pending == ["001_mig"]

    def test_scenario_8_append_only_history(self, tmp_path: Path) -> None:
        """Несколько applied/rollback/попыток — ничего не удаляется."""
        h = _Harness(tmp_path)
        h.corpus()
        h.api.migrate()          # applied
        h.versions[0] = 1        # «откат данных» имитация
        h.api.migrate()          # повторная попытка applied
        records = h.api.history()
        applied_count = sum(1 for r in records if r.status == "applied")
        assert applied_count >= 2  # два прогона — две записи applied
        # append-only: журнал ничего не удаляет
        assert not hasattr(MigrationHistory, "clear")
        assert not hasattr(MigrationHistory, "remove")

    def test_scenario_9_backup_keep_n(self, tmp_path: Path) -> None:
        """keep-N: старые удаляются, актуальные остаются."""
        h = _Harness(tmp_path)
        h.corpus()
        h.api.backup("001_mig", 2)
        h.api.backup("002_next", 3)
        h.api.backup("003_final", 4)
        h.api.backup("004_latest", 5)
        dirs = sorted(p.name for p in (tmp_path / "backup").iterdir())
        # keep-N=3: старейший удалён, актуальные остались
        assert dirs == ["002_next_3", "003_final_4", "004_latest_5"]
        assert "001_mig_2" not in dirs

    def test_scenario_10_rollback_no_stale_derivatives(self, tmp_path: Path) -> None:
        """После rollback индекс/снимок НЕ восстанавливаются, а пересоздаются."""
        h = _Harness(tmp_path)
        project = h.corpus()
        h.api.backup("001_mig", 2)
        h.api.rollback()
        assert h.index.validate(project).valid is True   # пересоздан
        assert h.snap.load(project) is not None          # пересоздан
        # событие rollback в журнале
        assert any(r.status == "rollback" for r in h.api.history())

    def test_scenario_11_retrieval_after_rollback(self, tmp_path: Path) -> None:
        """После rollback retrieval работает и совпадает со Snapshot."""
        h = _Harness(tmp_path)
        project = h.corpus()
        h.api.backup("001_mig", 2)
        h.api.rollback()
        items = h.query(project, "udp")
        assert len(items) >= 1  # поиск работает
        snapshot = h.snap.load(project)
        assert snapshot is not None
        # каноническое знание в снимке и в результатах поиска
        snapshot_titles: list[str] = []
        canonical = (snapshot.sections or {}).get("Canonical Knowledge", [])
        if isinstance(canonical, list):
            snapshot_titles = [
                str(entry.get("title", "")) for entry in canonical
                if isinstance(entry, dict)
            ]
        result_titles = [item.entity.title for item in items]
        assert any(t in snapshot_titles for t in result_titles if t)
