"""DS-015 ЭТАП 4: Full Acceptance (полная цепочка).
================================================================
Project -> Campaign -> Knowledge -> Index -> Snapshot -> Retrieve ->
Context -> LLM Mock -> Save -> Index Update -> Snapshot Update ->
Close -> Reopen -> Reuse -> Backup -> Restore -> Migration Check ->
Rollback Check -> Final Retrieval.
"""

import shutil
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
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence


class TestFullAcceptance:
    """Полный жизненный цикл: данные сохранены; rollback не уничтожает память."""

    def test_full_lifecycle(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        # Project -> Campaign -> Knowledge
        project = ctx.project.create(name="Full", tags=["acceptance"])
        c1 = ctx.campaign.create(project.id, goal="task-1")
        ctx.campaign.open(project.id, c1.id)
        ctx.campaign.open(project.id, c1.id)
        knowledge = ctx.librarian.register(project.id, Knowledge(
            title="FullFact udp", body="udp", tags=["udp"],
            source_campaign=c1.id))
        ctx.librarian.canonicalize(project.id, knowledge.id)
        # Index -> Snapshot
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="v1")
        # Retrieve -> Context (LLM mock = результат) -> Save
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        assert len(result.items) >= 1
        saved = ctx.librarian.register(project.id, Knowledge(
            title="SavedFact udp", body="llm output", tags=["udp"]))
        ctx.librarian.canonicalize(project.id, saved.id)
        # Index Update -> Snapshot Update
        ctx.index.update(project.id, saved.id, "knowledge")
        snapshots.create(project.id, reason="v2", force=True)
        # Close -> Reopen -> Reuse
        ctx.campaign.close(project.id, c1.id)
        c2 = ctx.campaign.create(project.id, goal="task-2")
        ctx.campaign.open(project.id, c2.id)
        ctx.campaign.open(project.id, c2.id)
        reused = ctx.retrieval.retrieve("udp", project_id=project.id)
        assert len(reused.items) >= 2  # память переиспользуется
        # Backup (файловый) -> Restore
        backup_dir = tmp_path / "backup-repo"
        shutil.copytree(tmp_path / "projects", backup_dir)
        shutil.rmtree(tmp_path / "projects")
        shutil.copytree(backup_dir, tmp_path / "projects")
        assert ctx.repos.knowledge.count(project.id) == 2
        # Migration Check -> Rollback Check (память цела)
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
        api.rollback()
        # Final Retrieval: память не уничтожена rollback'ом
        ctx.index.rebuild(project.id)
        final = ctx.retrieval.retrieve("udp", project_id=project.id)
        titles = [str(i.entity.title) for i in final.items]
        assert any("FullFact" in t for t in titles)
        assert any("SavedFact" in t for t in titles)
        assert ctx.repos.knowledge.count(project.id) == 2
