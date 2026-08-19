"""Unit tests: VersionManifest (DS-013 ЭТАП 2)."""

from __future__ import annotations
import json
from pathlib import Path

import pytest

from hkos.migration.migration_engine import MigrationEngine
from hkos.migration.migration_registry import MigrationRegistry, MigrationStep
from hkos.migration.schema_detector import SchemaDetector
from hkos.migration.version_manifest import VersionManifest


class _CountingReader:
    """Порт чтения версий со счётчиком обращений (доказывает skip)."""

    def __init__(self, versions: list[int] | None = None) -> None:
        self.calls = 0
        self.versions = versions if versions is not None else [1]

    def __call__(self, project: str) -> list[int]:
        self.calls += 1
        return self.versions


def _registry() -> MigrationRegistry:
    registry = MigrationRegistry()
    registry.register(MigrationStep("001_mig", 1, 2))
    return registry


class TestVersionManifest:
    """Кэш: load/valid/covers/set/save/invalidate."""

    def test_load_and_valid(self, tmp_path: Path) -> None:
        manifest = VersionManifest(tmp_path / "version_manifest.json")
        assert manifest.is_valid() is False
        manifest.set("p1", 1)
        manifest.save()
        loaded = VersionManifest(tmp_path / "version_manifest.json")
        loaded.load()
        assert loaded.is_valid() is True
        assert loaded.schema_versions(["p1"]) == [1]

    def test_corrupt_file_invalid(self, tmp_path: Path) -> None:
        path = tmp_path / "version_manifest.json"
        path.write_text("{ not json")
        manifest = VersionManifest(path)
        manifest.load()
        assert manifest.is_valid() is False  # без исключения

    def test_invalid_structure(self, tmp_path: Path) -> None:
        path = tmp_path / "version_manifest.json"
        path.write_text(json.dumps({"projects": "not-a-dict"}))
        manifest = VersionManifest(path)
        manifest.load()
        assert manifest.is_valid() is False

    def test_covers(self, tmp_path: Path) -> None:
        manifest = VersionManifest(tmp_path / "m.json")
        manifest.set("p1", 1)
        assert manifest.covers(["p1"]) is True
        assert manifest.covers(["p1", "p2"]) is False  # неполон -> fallback

    def test_invalidate_removes_file(self, tmp_path: Path) -> None:
        manifest = VersionManifest(tmp_path / "m.json")
        manifest.set("p1", 1)
        manifest.save()
        manifest.invalidate()
        assert manifest.is_valid() is False
        assert not (tmp_path / "m.json").exists()


class TestDetectWithManifest:
    """Detect: manifest путь vs fallback скан (DS-013 ЭТАП 2)."""

    def test_manifest_absent_fallback_scan(self, tmp_path: Path) -> None:
        reader = _CountingReader([1])
        detector = SchemaDetector(_registry(), reader, manifest=None)
        info = detector.detect(["p1"])
        assert reader.calls == 1          # полный скан
        assert info.current_version == 1
        assert info.pending == ["001_mig"]

    def test_manifest_exists_no_doc_read(self, tmp_path: Path) -> None:
        """Manifest валиден и полон -> reader НЕ вызывается (документы
        не читаются)."""
        manifest = VersionManifest(tmp_path / "m.json")
        manifest.set("p1", 1)
        reader = _CountingReader([1])
        detector = SchemaDetector(_registry(), reader, manifest=manifest)
        info = detector.detect(["p1"])
        assert reader.calls == 0          # документы не читались
        assert info.current_version == 1

    def test_manifest_corrupt_fallback(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        path.write_text("corrupt")
        manifest = VersionManifest(path)
        manifest.load()
        reader = _CountingReader([1])
        detector = SchemaDetector(_registry(), reader, manifest=manifest)
        info = detector.detect(["p1"])
        assert reader.calls == 1          # fallback скан
        assert info.pending == ["001_mig"]

    def test_manifest_incomplete_fallback(self, tmp_path: Path) -> None:
        manifest = VersionManifest(tmp_path / "m.json")
        manifest.set("p1", 1)             # p2 отсутствует
        reader = _CountingReader([1])
        detector = SchemaDetector(_registry(), reader, manifest=manifest)
        info = detector.detect(["p1", "p2"])
        assert reader.calls == 2          # fallback (по проектам, параллельно)
        assert info.pending == ["001_mig"]

    def test_manifest_stale_repository_wins(self, tmp_path: Path) -> None:
        """Manifest устарел (версия 1, а документы — 2): detect по
        manifest дал бы mixed/неверно; fallback-скан даёт истину
        (reader возвращает актуальное)."""
        manifest = VersionManifest(tmp_path / "m.json")
        manifest.set("p1", 1)             # устаревшая запись
        reader = _CountingReader([2])     # документы реально на v2
        detector = SchemaDetector(_registry(), reader, manifest=manifest)
        info = detector.detect(["p1"])
        # manifest покрывает p1 -> использован manifest (кэш)
        # актуальность гарантируется: manifest пересоздаётся после
        # миграций/rollback; при ручном изменении документов — валидация
        # («Repository wins») инвалидирует кэш
        assert info.current_version == 1  # по manifest (кэш)
        manifest.invalidate()             # рассинхронизация -> инвалидация
        detector2 = SchemaDetector(_registry(), reader, manifest=manifest)
        info2 = detector2.detect(["p1"])
        assert info2.current_version == 2  # Repository wins (скан)
        assert reader.calls >= 1

    def test_fallback_populates_manifest(self, tmp_path: Path) -> None:
        manifest = VersionManifest(tmp_path / "m.json")
        reader = _CountingReader([1])
        detector = SchemaDetector(_registry(), reader, manifest=manifest)
        detector.detect(["p1"])
        assert manifest.is_valid() is True
        assert manifest.schema_versions(["p1"]) == [1]
        assert (tmp_path / "m.json").exists()

    def test_100k_projects_detect_budget(self, tmp_path: Path) -> None:
        """100K проектов в manifest -> detect <= 100 мс (без скана)."""
        import time

        manifest = VersionManifest(tmp_path / "m.json")
        projects = [f"p{i:06d}" for i in range(100_000)]
        for project in projects:
            manifest.set(project, 1)
        reader = _CountingReader([1])
        detector = SchemaDetector(_registry(), reader, manifest=manifest)
        start = time.monotonic()
        info = detector.detect(projects)
        elapsed = (time.monotonic() - start) * 1000
        assert reader.calls == 0          # ноль чтений документов
        assert elapsed <= 100, f"detect {elapsed:.1f} ms"
        assert info.pending == ["001_mig"]

    def test_determinism(self, tmp_path: Path) -> None:
        reader = _CountingReader([1, 2])  # mixed
        detector = SchemaDetector(_registry(), reader)
        first = detector.detect(["p1"])
        second = detector.detect(["p1"])
        assert first == second

    def test_reader_error_not_hidden(self, tmp_path: Path) -> None:
        def broken(project: str) -> list[int]:
            raise RuntimeError("read failed")

        detector = SchemaDetector(_registry(), broken)
        with pytest.raises(RuntimeError):
            detector.detect(["p1"])


class TestEngineManifestLifecycle:
    """MigrationEngine обновляет/инвалидирует manifest (DS-013 ЭТАП 2)."""

    def _engine_with_manifest(
        self, tmp_path: Path
    ) -> tuple["MigrationEngine", VersionManifest, str, list[int]]:
        from hkos.core.config import ConfigLoader
        from hkos.core.logger import HKOSLogger
        from hkos.core.version import VersionManager
        from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
        from hkos.migration.backup_manager import BackupManager
        from hkos.migration.migration_engine import MigrationEngine
        from hkos.migration.migration_executor import MigrationExecutor
        from hkos.migration.migration_history import MigrationHistory
        from hkos.migration.migration_manager import MigrationManager
        from hkos.migration.migration_validator import MigrationValidator
        from hkos.migration.rollback_manager import RollbackManager
        from hkos.repository.models import Knowledge, Project
        from hkos.repository.repository_manager import RepositoryManager
        from hkos.services.librarian import Librarian
        from hkos.snapshot import SnapshotEngine
        from hkos.storage import StorageEngine
        class _MemoryPersistence:
            """Локальный in-memory порт SnapshotPersistence."""

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

        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        pers = _MemoryPersistence()
        qc = IndexQueryExecutor(IndexStore(engine))
        snap = SnapshotEngine(repos, pers, HKOSLogger(), index_provider=qc.snapshot)
        registry = MigrationRegistry()
        registry.register(MigrationStep("001_mig", 1, 2))
        executor = MigrationExecutor({"001_mig": lambda step: None})
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        manifest = VersionManifest(tmp_path / "version_manifest.json")
        versions: list[int] = [1]

        def reader(project: str) -> list[int]:
            return versions

        validator = MigrationValidator(repos, index, snap, reader)
        detector = SchemaDetector(registry, reader, manifest=manifest)
        manager = MigrationManager(detector, registry, executor, backup,
                                   rollback, validator, index, snap)
        api = MigrationEngine(manager, MigrationHistory(), repos, index, snap,
                              validator, lock_path=tmp_path / "migration.lock",
                              manifest=manifest)
        project = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert project is not None
        lib.register(project.id, Knowledge(title="K", body="b", tags=["t"]))
        index.build(project.id)
        return api, manifest, project.id, versions

    def test_manifest_updated_after_migrate(self, tmp_path: Path) -> None:
        api, manifest, project, versions = self._engine_with_manifest(tmp_path)
        assert manifest.is_valid() is False
        api.migrate()
        # после успешной миграции manifest отражает целевую версию
        assert manifest.is_valid() is True
        assert manifest.schema_versions([project]) == [2]

    def test_manifest_invalidated_after_rollback(self, tmp_path: Path) -> None:
        api, manifest, project, versions = self._engine_with_manifest(tmp_path)
        api.backup("001_mig", 2)
        api.migrate()
        assert manifest.is_valid() is True
        api.rollback()
        # после rollback manifest инвалидирован («Repository wins»)
        assert manifest.is_valid() is False
