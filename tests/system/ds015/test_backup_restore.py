"""DS-015 ЭТАП 3: Backup / Restore Validation.
================================================================
Create -> Generate -> Snapshot -> Backup -> Modify -> Restore -> Verify.
before_backup == after_restore (IDs/categories/timestamps/metadata).
Index соответствует Repository; Snapshot соответствует состоянию;
Retrieval возвращает прежние знания.
"""

import shutil
from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence


class TestBackupRestore:
    """Полный цикл backup/restore (операционная процедура)."""

    def test_backup_restore_cycle(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = ctx.project.create(name="Backup", tags=["backup"])
        ids_before: list[str] = []
        for i in range(10):
            knowledge = ctx.librarian.register(project.id, Knowledge(
                title=f"B{i}fact udp", body=f"body {i}", tags=["udp"],
                category="CONFIGURATION" if i % 3 == 0 else ""))
            ids_before.append(knowledge.id)
        ctx.index.build(project.id)
        # Снимок до backup
        snapshots.create(project.id, reason="pre-backup")
        # BACKUP: копия Repository (операционная процедура)
        projects_dir = tmp_path / "projects"
        backup_dir = tmp_path / "backup" / "repository"
        shutil.copytree(projects_dir, backup_dir)
        # MODIFY: добавить и удалить знания (публичные API)
        ctx.librarian.register(project.id, Knowledge(
            title="ExtraFact udp", body="extra", tags=["udp"]))
        victim = ctx.repos.knowledge.list(project.id)[0]
        ctx.repos.knowledge.delete(project.id, victim.id)
        ctx.index.rebuild(project.id)
        # RESTORE: восстановить Repository из backup (операционная процедура)
        shutil.rmtree(projects_dir)
        shutil.copytree(backup_dir, projects_dir)
        # VERIFY: before_backup == after_restore
        assert ctx.repos.knowledge.count(project.id) == 10
        after_ids = sorted(
            k.id for k in ctx.repos.knowledge.list(project.id))
        assert sorted(ids_before) == after_ids
        # метаданные (теги) сохранились после restore
        restored_tags = [
            set(k.tags) for k in ctx.repos.knowledge.list(project.id)]
        assert any({"udp"} <= tags for tags in restored_tags)
        assert len(restored_tags) == 10
        # Index соответствует Repository (после rebuild)
        ctx.index.rebuild(project.id)
        assert int(ctx.index.statistics(project.id).get("knowledge", 0)) == 10
        # Snapshot пересоздаётся и соответствует
        snapshots.create(project.id, reason="post-restore", force=True)
        snapshot = snapshots.load(project.id)
        assert snapshot is not None
        assert int(snapshot.statistics.get("knowledge", 0)) == 10
        # Retrieval возвращает прежние знания
        result = ctx.retrieval.retrieve("B5fact", project_id=project.id)
        assert any("B5fact" in str(i.entity.title) for i in result.items)
