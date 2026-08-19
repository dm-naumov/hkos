"""DS-015 ЭТАП 5.4: Final Release Acceptance.
================================================================
New Project -> Campaigns -> Knowledge -> Index -> Snapshot -> Retrieval
-> Context -> Token Optimization -> Save -> Close -> Restart -> Reuse ->
Backup -> Restore -> Migration -> Rollback -> Final Retrieval.
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


class TestReleaseAcceptance:
    """Полный финальный сценарий (все подсистемы)."""

    def test_release_scenario(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = ctx.project.create(name="RC1", tags=["release"])
        c1 = ctx.campaign.create(project.id, goal="rc-task-1")
        ctx.campaign.open(project.id, c1.id)
        ctx.campaign.open(project.id, c1.id)
        # Register Knowledge (включая FAILURE)
        decision = ctx.librarian.register(project.id, Knowledge(
            title="DecisionRC udp", body="use VLESS", tags=["vless", "udp"],
            category="DECISION", source_campaign=c1.id))
        failure = ctx.librarian.register(project.id, Knowledge(
            title="FailureRC udp", body="cause: WARP\nrecommendations: VLESS",
            tags=["warp", "udp"], kind="negative", source_campaign=c1.id))
        for k in (decision, failure):
            ctx.librarian.canonicalize(project.id, k.id)
        # Index -> Snapshot
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="rc-v1")
        # Retrieval -> Context (LLM mock) -> Save
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        assert len(result.items) >= 2
        saved = ctx.librarian.register(project.id, Knowledge(
            title="SavedRC udp", body="llm", tags=["udp"]))
        ctx.librarian.canonicalize(project.id, saved.id)
        ctx.index.update(project.id, saved.id, "knowledge")
        snapshots.create(project.id, reason="rc-v2", force=True)
        ctx.campaign.close(project.id, c1.id)
        # Restart (re-init) -> Reuse Memory
        ctx.engine.initialize()
        c2 = ctx.campaign.create(project.id, goal="rc-task-2")
        ctx.campaign.open(project.id, c2.id)
        ctx.campaign.open(project.id, c2.id)
        reused = ctx.retrieval.retrieve("udp", project_id=project.id)
        assert len(reused.items) >= 2
        # Backup -> Restore
        backup_dir = tmp_path / "backup-rc"
        shutil.copytree(tmp_path / "projects", backup_dir)
        shutil.rmtree(tmp_path / "projects")
        shutil.copytree(backup_dir, tmp_path / "projects")
        assert ctx.repos.knowledge.count(project.id) == 3
        # Migration -> Rollback
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
        # Final Retrieval: память цела; FAILURE доступна
        ctx.index.rebuild(project.id)
        final = ctx.retrieval.retrieve("udp", project_id=project.id)
        titles = [str(i.entity.title) for i in final.items]
        assert any("DecisionRC" in t for t in titles)
        assert any("FailureRC" in t for t in titles)   # FAILURE доступна
        assert any("SavedRC" in t for t in titles)
        # Snapshot корректен; Index соответствует Repository
        snapshots.create(project.id, reason="rc-final", force=True)
        snapshot = snapshots.load(project.id)
        assert int(snapshot.statistics.get("knowledge", 0)) == 3
        assert int(ctx.index.statistics(project.id).get("knowledge", 0)) == 3
        assert ctx.repos.knowledge.count(project.id) == 3
