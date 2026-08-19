"""System: консистентность и восстановление Snapshot (DS-014 ЭТАП 3).
================================================================
create -> knowledge -> snapshot -> modify (Librarian) -> update snapshot
-> compare; recovery: valid -> corrupted -> detect -> restore ->
Repository цел; retrieval корректен.

Snapshot — производное (НЕ источник истины).
"""

from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_retrievable,
    assert_snapshot_matches_repository,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestSnapshotConsistencySystem:
    """Снимок отражает Repository; не содержит лишнего; восстанавливается."""

    def _ctx_with_snapshots(self, tmp_path: Path):
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        return ctx, snapshots

    def test_snapshot_reflects_repository(self, tmp_path: Path) -> None:
        ctx, snapshots = self._ctx_with_snapshots(tmp_path)
        project = project_factory(ctx, "SnapReflect", tags=["system"])
        k1 = ctx.librarian.register(project.id, Knowledge(
            title="FirstFact udp", body="udp", tags=["udp"]))
        snapshots.create(project.id, reason="v1")
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        # модификация через Librarian (публичный API)
        k1.title = "ModifiedFact udp"
        ctx.librarian.update(project.id, k1)
        ctx.index.update(project.id, k1.id, "knowledge")
        # снимок устарел (создан до модификации)
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        # обновление снимка -> актуальное состояние
        snapshots.create(project.id, reason="v2", force=True)
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        latest = snapshots.load(project.id)
        titles = [
            entry.get("title", "") for section in (latest.sections or {}).values()
            if isinstance(section, list)
            for entry in section if isinstance(entry, dict)
        ]
        assert any("ModifiedFact" in str(t) for t in titles), (
            "snapshot does not reflect modified knowledge")
        # снимок не содержит лишнего (счётчики по всем типам)
        assert_snapshot_matches_repository(ctx, snapshots, project.id)

    def test_snapshot_not_source_of_truth(self, tmp_path: Path) -> None:
        ctx, snapshots = self._ctx_with_snapshots(tmp_path)
        project = project_factory(ctx, "NotTruth", tags=["system"])
        ctx.librarian.register(project.id, Knowledge(
            title="TruthFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="v1")
        # ИСТИНА — Repository: новое знание видно через Retrieval
        # ДАЖЕ если снимок не обновлялся
        assert_retrievable(ctx, project.id, "TruthFact", "TruthFact")

    def test_snapshot_recovery(self, tmp_path: Path) -> None:
        """Corrupted snapshot -> обнаружение -> восстановление -> retrieval."""
        ctx, snapshots = self._ctx_with_snapshots(tmp_path)
        project = project_factory(ctx, "Recovery", tags=["system"])
        k1 = ctx.librarian.register(project.id, Knowledge(
            title="RecoveryFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        valid = snapshots.create(project.id, reason="valid")
        assert valid is not None
        # ПОВРЕЖДЕНИЕ снимка (битая структура в порте)
        from hkos.kernel.snapshot_document import SnapshotDocument
        broken = SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project.id,
            statistics={"knowledge": 999},
        )
        snapshots._persistence.save(project.id, broken.as_dict())
        # ошибка обнаруживается (счётчик не соответствует Repository)
        corrupted = snapshots.load(project.id)
        assert corrupted is not None
        corrupted_count = int(corrupted.statistics.get("knowledge", 0))
        assert corrupted_count != ctx.repos.knowledge.count(project.id)
        # Repository цел (SSOT не затронут)
        assert ctx.repos.knowledge.exists(project.id, k1.id)
        assert ctx.repos.knowledge.count(project.id) == 1
        # ВОССТАНОВЛЕНИЕ: пересоздание снимка из Repository
        recovered = snapshots.create(project.id, reason="recovered", force=True)
        assert recovered is not None
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        # retrieval после восстановления корректен
        assert_retrievable(ctx, project.id, "RecoveryFact", "RecoveryFact")
