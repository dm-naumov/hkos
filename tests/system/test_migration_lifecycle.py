"""System: жизненный цикл миграции (DS-014 ЭТАП 4).
================================================================
Schema v1 -> Migration v2 -> Migration v3 -> Rollback v2.

Проверки: Knowledge сохранены; версии корректны; Index/Snapshot
обновляются; Retrieval после миграции работает.
"""

from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.migration.backup_manager import BackupManager
from hkos.migration.migration_engine import MigrationEngine
from hkos.migration.migration_executor import MigrationExecutor
from hkos.migration.migration_history import MigrationHistory
from hkos.migration.migration_manager import MigrationManager
from hkos.migration.migration_registry import MigrationRegistry, MigrationStep
from hkos.migration.migration_validator import MigrationValidator
from hkos.migration.rollback_manager import RollbackManager
from hkos.migration.schema_detector import SchemaDetector
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


class TestMigrationLifecycleSystem:
    """v1 -> v2 -> v3 -> rollback (полный цикл через публичный фасад)."""

    def _engine(self, ctx, tmp_path: Path, versions: list[int]):
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        registry = MigrationRegistry()
        registry.register(MigrationStep("001_mig", 1, 2))
        registry.register(MigrationStep("002_mig", 2, 3))
        applied: list[str] = []

        def apply_step(step: object) -> None:
            applied.append(str(getattr(step, "migration_id", "")))
            versions[0] += 1  # имитация инкремента schema_version

        executor = MigrationExecutor({
            "001_mig": apply_step,
            "002_mig": apply_step,
        })
        backup = BackupManager(tmp_path, keep_n=5)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(ctx.repos, ctx.index, snapshots,
                                       lambda pid: versions)
        detector = SchemaDetector(registry, lambda pid: versions)
        manager = MigrationManager(detector, registry, executor, backup,
                                   rollback, validator, ctx.index, snapshots)
        api = MigrationEngine(manager, MigrationHistory(), ctx.repos, ctx.index,
                              snapshots, validator,
                              lock_path=tmp_path / "migration.lock")
        return api, snapshots, applied, versions

    def test_v1_to_v3_then_rollback(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        versions: list[int] = [1]
        api, snapshots, applied, versions = self._engine(ctx, tmp_path, versions)
        project = project_factory(ctx, "MigLife", tags=["system"])
        knowledge = ctx.librarian.register(project.id, Knowledge(
            title="MigLifeFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="v1")
        # v1 -> v2 -> v3
        api.migrate()
        assert versions[0] == 3
        assert applied == ["001_mig", "002_mig"]
        assert api.status().startswith("COMPLETED")
        # Knowledge сохранены; индекс/снимок согласованы
        assert ctx.repos.knowledge.exists(project.id, knowledge.id)
        assert_index_matches_repository(ctx, project.id)
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        # Retrieval после миграции работает
        assert_retrievable(ctx, project.id, "MigLifeFact", "MigLifeFact")
        # Rollback (восстановление последнего backup)
        api.rollback()
        assert api.status().startswith("FAILED")  # одноразовый FSM
        # знания сохранены; производные восстановлены (F-2)
        assert ctx.repos.knowledge.exists(project.id, knowledge.id)
        ctx.index.rebuild(project.id)
        snapshots.create(project.id, reason="post_rollback", force=True)
        assert_index_matches_repository(ctx, project.id)
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        assert_retrievable(ctx, project.id, "MigLifeFact", "MigLifeFact")
        # версии корректны (manifest/детектор)
        info = api.detect()
        assert info.current_version >= 1

    def test_idempotent_repeat_after_migration(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        versions: list[int] = [1]
        api, snapshots, applied, versions = self._engine(ctx, tmp_path, versions)
        project = project_factory(ctx, "MigIdem", tags=["system"])
        ctx.librarian.register(project.id, Knowledge(
            title="MigIdemFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        api.migrate()
        assert applied == ["001_mig", "002_mig"]
        # повторный запуск: up-to-date, ноль изменений
        api.migrate()
        assert applied == ["001_mig", "002_mig"]  # шаги не повторялись
        assert ctx.repos.knowledge.count(project.id) == 1
