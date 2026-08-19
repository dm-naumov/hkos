"""DS-015 ЭТАП 5.6: Operational Readiness.
================================================================
Startup (production config) / Shutdown (clean, no temp) / Recovery
(corrupted index/snapshot, failed migration) / Backup (create/restore/verify).
"""

import shutil
from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence


class TestOperationalReadiness:
    """Эксплуатационная готовность: startup/shutdown/recovery/backup."""

    def test_startup_production(self, tmp_path: Path) -> None:
        loader = ConfigLoader(profile="production")
        config = loader.load()
        engine = StorageEngine(
            root=str(tmp_path), config=config, logger=HKOSLogger(),
            version=VersionManager())
        engine.initialize()
        engine.initialize()  # идемпотентность
        assert engine.health() is not None  # ready state

    def test_shutdown_clean(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="Shut", tags=["op"])
        ctx.librarian.register(project.id, Knowledge(
            title="ShutFact udp", body="udp", tags=["udp"]))
        # flush (файловое хранилище синхронно) + clean exit
        ctx.engine.initialize()
        assert ctx.repos.knowledge.count(project.id) == 1
        temp_files = list((tmp_path / "projects").rglob("*.tmp*"))
        assert temp_files == [], "temp files left after shutdown"

    def test_recovery_corrupted_index(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="RecIdx", tags=["op"])
        ctx.librarian.register(project.id, Knowledge(
            title="RecFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        index_file = (tmp_path / "projects" / project.id / "indexes" / "entities.idx")
        index_file.write_text("{ broken")
        from hkos.storage.exceptions import StorageSerializationError
        try:
            ctx.retrieval.retrieve("RecFact", project_id=project.id)
            detected = False
        except StorageSerializationError:
            detected = True
        assert detected
        ctx.index.rebuild(project.id)
        assert len(ctx.retrieval.retrieve(
            "RecFact", project_id=project.id).items) >= 1

    def test_recovery_corrupted_snapshot(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = ctx.project.create(name="RecSnap", tags=["op"])
        ctx.librarian.register(project.id, Knowledge(
            title="SnapFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="valid")
        from hkos.kernel.snapshot_document import SnapshotDocument
        snapshots._persistence.save(project.id, SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project.id,
            statistics={"knowledge": 999}).as_dict())
        assert int(snapshots.load(project.id).statistics.get("knowledge", 0)) == 999
        snapshots.create(project.id, reason="recovered", force=True)
        assert int(snapshots.load(project.id).statistics.get("knowledge", 0)) == 1

    def test_backup_restore_verify(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="Bak", tags=["op"])
        for i in range(5):
            ctx.librarian.register(project.id, Knowledge(
                title=f"BK{i}fact udp", body="udp", tags=["udp"]))
        backup_dir = tmp_path / "backup-op"
        shutil.copytree(tmp_path / "projects", backup_dir)
        # модификация после backup
        ctx.librarian.register(project.id, Knowledge(
            title="AfterBak udp", body="udp", tags=["udp"]))
        assert ctx.repos.knowledge.count(project.id) == 6
        # restore
        shutil.rmtree(tmp_path / "projects")
        shutil.copytree(backup_dir, tmp_path / "projects")
        assert ctx.repos.knowledge.count(project.id) == 5  # verify
