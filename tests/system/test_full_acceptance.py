"""System: Full Acceptance (DS-014 ЭТАП 5 §2).
================================================================
Полный инженерный цикл: Project -> Campaign -> Agent Task -> Retrieval
-> Context -> LLM Mock -> Librarian -> Repository -> Index -> Snapshot
-> Next Campaign -> Memory Reuse.
"""

from pathlib import Path

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import (
    assert_index_matches_repository,
    assert_knowledge_exists,
    assert_retrievable,
    assert_snapshot_matches_repository,
)
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
    project_factory,
)


class TestFullAcceptance:
    """HKOS как единая система: полный цикл + переиспользование памяти."""

    def test_knowledge_flow(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "Acceptance", tags=["system"])
        campaign = ctx.campaigns.create(project.id, goal="agent-task-1")
        ctx.campaigns.open(project.id, campaign.id)
        ctx.campaigns.open(project.id, campaign.id)  # RUNNING
        # Agent Task -> Knowledge
        knowledge = ctx.librarian.register(project.id, Knowledge(
            title="AcceptanceFact udp", body="udp", tags=["udp"],
            source_campaign=campaign.id))
        # Repository
        assert_knowledge_exists(ctx, project.id, knowledge.id)
        # Index
        ctx.index.update(project.id, knowledge.id, "knowledge")
        assert_index_matches_repository(ctx, project.id)
        # Snapshot
        snapshots.create(project.id, reason="cycle-1")
        assert_snapshot_matches_repository(ctx, snapshots, project.id)
        # Retrieval
        assert_retrievable(ctx, project.id, "AcceptanceFact", "AcceptanceFact")

    def test_memory_reuse_next_campaign(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = project_factory(ctx, "MemoryReuse", tags=["system"])
        c1 = ctx.campaigns.create(project.id, goal="campaign-1")
        ctx.campaigns.open(project.id, c1.id)
        ctx.campaigns.open(project.id, c1.id)
        ctx.librarian.register(project.id, Knowledge(
            title="VlessDecision udp", body="use VLESS instead of WARP",
            tags=["udp", "vless"], category="DECISION", source_campaign=c1.id))
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="c1")
        ctx.campaigns.close(project.id, c1.id)
        # Next Campaign -> Memory Reuse
        c2 = ctx.campaigns.create(project.id, goal="campaign-2")
        ctx.campaigns.open(project.id, c2.id)
        ctx.campaigns.open(project.id, c2.id)
        result = ctx.retrieval.retrieve("VLESS", project_id=project.id)
        titles = [str(i.entity.title) for i in result.items]
        assert any("VlessDecision" in t for t in titles), "memory not reused"
