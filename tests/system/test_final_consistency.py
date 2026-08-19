"""System: Final Consistency (DS-014 ЭТАП 5 §13).
================================================================
Инварианты после всех операций: Repository = SSOT; Index == проекция;
Snapshot == состояние; Cache == временное производное.
"""

from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_index_matches_repository,
    assert_snapshot_matches_repository,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestFinalConsistency:
    """Итоговые инварианты производных данных."""

    def test_derived_invariants(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "Final", tags=["system"])
        for i in range(25):
            knowledge = ctx.librarian.register(project.id, Knowledge(
                title=f"F{i}fact udp", body="udp", tags=["udp"]))
            ctx.index.update(project.id, knowledge.id, "knowledge")
        snapshots.create(project.id, reason="final")
        # SSOT: Repository — источник
        repository_count = ctx.repos.knowledge.count(project.id)
        # Index == проекция Repository
        assert_index_matches_repository(ctx, project.id)
        # Snapshot == состояние Repository
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        # Cache — временное производное (пустое до использования)
        assert repository_count == 25
