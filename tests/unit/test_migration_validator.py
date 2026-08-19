"""Unit tests: MigrationValidator (DS-011 §13, IP-011 ЭТАП 4)."""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.migration.exceptions import MigrationValidationError
from hkos.migration.migration_validator import MigrationValidator
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine


class _MemorySnapshotPersistence:
    """In-memory порт SnapshotPersistence (для SnapshotEngine)."""

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


class TestMigrationValidator:
    """Оркестрационный валидатор: структура/версии/ссылки/индекс/Snapshot."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[
        StorageEngine, RepositoryManager, Librarian, IndexEngine,
        SnapshotEngine, _MemorySnapshotPersistence,
    ]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        persistence = _MemorySnapshotPersistence()
        qc = IndexQueryExecutor(IndexStore(engine))
        snap = SnapshotEngine(repos, persistence, HKOSLogger(),
                              index_provider=qc.snapshot)
        return engine, repos, lib, index, snap, persistence

    def _corpus(
        self, repos: RepositoryManager, lib: Librarian, index: IndexEngine
    ) -> str:
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        assert p is not None
        k = lib.register(p.id, Knowledge(title="UDP fix", body="udp", tags=["udp"]))
        lib.canonicalize(p.id, k.id)
        index.build(p.id)
        return p.id

    def _validator(
        self, repos: RepositoryManager, index: IndexEngine, snap: SnapshotEngine
    ) -> MigrationValidator:
        return MigrationValidator(repos, index, snap, lambda pid: [1], sample_size=100)

    def test_valid_state(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, persistence = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)
        snap.create(project, reason="post_migration")
        result = self._validator(repos, index, snap).validate(1)
        assert result.valid is True

    def test_invalid_envelope_version(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, persistence = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)
        snap.create(project, reason="post")
        validator = MigrationValidator(repos, index, snap, lambda pid: [1, 99])
        with pytest.raises(MigrationValidationError):
            validator.validate(1)

    def test_broken_reference(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, persistence = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)
        k = lib.register(project, Knowledge(
            title="Broken", body="b", tags=["b"],
            parent_ids=["00000000-0000-4000-8000-000000000000"],
        ))
        index.update(project, k.id, "knowledge")
        snap.create(project, reason="post")
        validator = self._validator(repos, index, snap)
        with pytest.raises(MigrationValidationError):
            validator.validate(1)

    def test_missing_snapshot_is_error(self, tmp_path: Path) -> None:
        """После миграции снимок обязан существовать (пересоздан)."""
        engine, repos, lib, index, snap, persistence = self._ctx(tmp_path)
        self._corpus(repos, lib, index)
        with pytest.raises(MigrationValidationError):
            self._validator(repos, index, snap).validate(1)

    def test_snapshot_counter_mismatch(self, tmp_path: Path) -> None:
        engine, repos, lib, index, snap, persistence = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)
        from hkos.kernel.snapshot_document import SnapshotDocument

        correct = snap.create(project, reason="post")
        # сохранить поверх снимок с неверной статистикой (тот же id)
        broken = SnapshotDocument(
            snapshot_id=correct.snapshot_id, project_id=project,
            statistics={"knowledge": 999},
        )
        persistence.save(project, broken.as_dict())
        validator = self._validator(repos, index, snap)
        with pytest.raises(MigrationValidationError) as exc:
            validator.validate(1)
        assert "counter" in str(exc.value)

    def test_classification_mismatch(self, tmp_path: Path) -> None:
        """Знание в неверной секции снимка -> ошибка классификации."""
        engine, repos, lib, index, snap, persistence = self._ctx(tmp_path)
        project = self._corpus(repos, lib, index)
        from hkos.kernel.snapshot_document import SnapshotDocument

        knowledge_id = repos.knowledge.list(project)[0].id
        broken = SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project,
            sections={"Open Questions": [{"id": knowledge_id, "title": "X"}]},
            statistics={"knowledge": repos.knowledge.count(project)},
        )
        persistence.save(project, broken.as_dict())
        validator = self._validator(repos, index, snap)
        with pytest.raises(MigrationValidationError) as exc:
            validator.validate(1)
        assert "classification mismatch" in str(exc.value)

    def test_validator_readonly(self) -> None:
        """Валидатор только проверяет (нет методов записи)."""
        api = {m for m in dir(MigrationValidator) if not m.startswith("_")}
        assert api <= {"validate"}
