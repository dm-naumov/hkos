"""System: восстановление после сбоев (DS-014 ЭТАП 4).
================================================================
A) Index corruption   B) Snapshot corruption   C) Repository failure
D) Migration failure -> rollback.

Проверки: ошибки обнаруживаются; Repository (SSOT) цел; производные
восстанавливаются; Retrieval корректен; Fallback работает.
"""

import time
from pathlib import Path

import pytest

from hkos.core.logger import HKOSLogger
from hkos.integration.hermes.fallback import FallbackPolicy
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_index_matches_repository,
    assert_retrievable,
    assert_snapshot_matches_repository,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestFailureRecoverySystem:
    """Сценарии A-D: обнаружение, изоляция SSOT, восстановление."""

    def test_scenario_a_index_corruption(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "IndexCorrupt", tags=["system"])
        ctx.librarian.register(project.id, Knowledge(
            title="IndexCorruptFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        assert_retrievable(ctx, project.id, "IndexCorruptFact", "IndexCorruptFact")
        # ПОВРЕЖДЕНИЕ индекса (битый файл)
        index_file = (tmp_path / "projects" / project.id / "indexes" / "entities.idx")
        index_file.write_text("{ broken json")
        # ошибка обнаруживается (не скрывается)
        from hkos.storage.exceptions import StorageSerializationError
        with pytest.raises(StorageSerializationError):
            ctx.retrieval.retrieve("IndexCorruptFact", project_id=project.id)
        # Repository цел (SSOT)
        assert ctx.repos.knowledge.count(project.id) == 1
        # rebuild восстанавливает Index
        ctx.index.rebuild(project.id)
        assert_index_matches_repository(ctx, project.id)
        assert_retrievable(ctx, project.id, "IndexCorruptFact", "IndexCorruptFact")

    def test_scenario_b_snapshot_corruption(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "SnapCorrupt", tags=["system"])
        ctx.librarian.register(project.id, Knowledge(
            title="SnapCorruptFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="valid")
        # ПОВРЕЖДЕНИЕ снимка
        from hkos.kernel.snapshot_document import SnapshotDocument
        broken = SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project.id,
            statistics={"knowledge": 999},
        )
        snapshots._persistence.save(project.id, broken.as_dict())
        # corruption detected (счётчик не сходится)
        corrupted = snapshots.load(project.id)
        assert int(corrupted.statistics.get("knowledge", 0)) == 999
        # Repository не изменён
        assert ctx.repos.knowledge.count(project.id) == 1
        # Snapshot regenerated
        snapshots.create(project.id, reason="recovered", force=True)
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        # Retrieval корректен
        assert_retrievable(ctx, project.id, "SnapCorruptFact", "SnapCorruptFact")

    def test_scenario_c_repository_failure_fallback(self, tmp_path: Path) -> None:
        """Ошибки storage не скрываются; Fallback работает; знания не теряются."""
        ctx = create_system_context(tmp_path)
        policy = FallbackPolicy()
        project = project_factory(ctx, "RepoFail", tags=["system"])
        knowledge = Knowledge(title="RepoFailFact udp", body="udp", tags=["udp"])
        # недоступность Librarian (имитация) -> pending queue
        ctx.librarian.register(project.id, knowledge)
        saved = ctx.repos.knowledge.count(project.id)
        assert saved == 1
        # ошибка чтения не скрывается (битый файл знания)
        knowledge_dir = tmp_path / "projects" / project.id / "knowledge"
        first_file = next(f for f in knowledge_dir.iterdir() if f.suffix == ".json")
        first_file.write_text("{ broken")
        from hkos.storage.exceptions import StorageSerializationError
        with pytest.raises(StorageSerializationError):
            ctx.repos.knowledge.list(project.id)
        # Fallback: знание НЕ теряется (очередь)
        policy.librarian_unavailable(knowledge)
        assert policy.pending_count() == 1

    def test_scenario_d_migration_failure_rollback(self, tmp_path: Path) -> None:
        """Migration с принудительной ошибкой -> rollback; знания сохраняются."""
        from hkos.migration.backup_manager import BackupManager
        from hkos.migration.exceptions import MigrationError
        from hkos.migration.migration_engine import MigrationEngine
        from hkos.migration.migration_executor import MigrationExecutor
        from hkos.migration.migration_history import MigrationHistory
        from hkos.migration.migration_manager import MigrationManager
        from hkos.migration.migration_registry import MigrationRegistry, MigrationStep
        from hkos.migration.migration_validator import MigrationValidator
        from hkos.migration.rollback_manager import RollbackManager
        from hkos.migration.schema_detector import SchemaDetector
        from hkos.snapshot import SnapshotEngine

        ctx = create_system_context(tmp_path)

        def boom(step: object) -> None:
            raise RuntimeError("forced migration failure")

        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        registry = MigrationRegistry()
        registry.register(MigrationStep("001_mig", 1, 2))
        executor = MigrationExecutor({"001_mig": boom})
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(ctx.repos, ctx.index, snapshots,
                                       lambda pid: [1])
        detector = SchemaDetector(registry, lambda pid: [1])
        manager = MigrationManager(detector, registry, executor, backup,
                                   rollback, validator, ctx.index, snapshots)
        api = MigrationEngine(manager, MigrationHistory(), ctx.repos, ctx.index,
                              snapshots, validator,
                              lock_path=tmp_path / "migration.lock")
        project = project_factory(ctx, "MigFail", tags=["system"])
        knowledge = ctx.librarian.register(project.id, Knowledge(
            title="MigFailFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        # migration с принудительной ошибкой -> rollback (FSM)
        start = time.perf_counter()
        with pytest.raises(MigrationError):
            api.migrate()
        rollback_time = (time.perf_counter() - start) * 1000
        # состояние возвращено; Knowledge сохранено (SSOT)
        assert ctx.repos.knowledge.exists(project.id, knowledge.id)
        assert ctx.repos.knowledge.count(project.id) == 1
        # Index/Snapshot восстановлены (rollback lifecycle F-2)
        ctx.index.rebuild(project.id)
        assert_index_matches_repository(ctx, project.id)
        assert_retrievable(ctx, project.id, "MigFailFact", "MigFailFact")
        # бюджет rollback
        assert rollback_time < 10_000, f"rollback {rollback_time:.0f} ms"
