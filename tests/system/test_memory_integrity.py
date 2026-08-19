"""System: Memory Integrity (DS-014 ЭТАП 5 §9).
================================================================
Migration v1->v2 -> Rollback -> Rebuild Index -> Regenerate Snapshot:
Knowledge before == Knowledge after (SSOT не теряет данные).
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
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestMemoryIntegrity:
    """Данные не теряются при миграции/rollback/rebuild/regenerate."""

    def test_knowledge_preserved_through_migration_cycle(
        self, tmp_path: Path
    ) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "MemIntegrity", tags=["system"])
        before_ids = []
        for i in range(50):
            knowledge = ctx.librarian.register(project.id, Knowledge(
                title=f"MI{i}fact udp", body="udp", tags=["udp"]))
            before_ids.append(knowledge.id)
        ctx.index.build(project.id)
        before_count = ctx.repos.knowledge.count(project.id)
        # Migration v1->v2
        versions: list[int] = [1]
        registry = MigrationRegistry()
        registry.register(MigrationStep("001_mig", 1, 2))
        executor = MigrationExecutor({
            "001_mig": lambda step: versions.__setitem__(0, 2)})
        backup = BackupManager(tmp_path, keep_n=3)
        rollback = RollbackManager(tmp_path)
        validator = MigrationValidator(ctx.repos, ctx.index, snapshots,
                                       lambda pid: versions)
        detector = SchemaDetector(registry, lambda pid: versions)
        manager = MigrationManager(detector, registry, executor, backup,
                                   rollback, validator, ctx.index, snapshots)
        api = MigrationEngine(manager, MigrationHistory(), ctx.repos, ctx.index,
                              snapshots, validator,
                              lock_path=tmp_path / "migration.lock")
        api.migrate()
        # Rollback
        api.rollback()
        # Rebuild Index + Regenerate Snapshot
        ctx.index.rebuild(project.id)
        snapshots.create(project.id, reason="integrity", force=True)
        # Knowledge before == after
        after_count = ctx.repos.knowledge.count(project.id)
        assert after_count == before_count == 50
        for knowledge_id in before_ids:
            assert ctx.repos.knowledge.exists(project.id, knowledge_id)
