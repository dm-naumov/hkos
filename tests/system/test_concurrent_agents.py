"""System: параллельные агенты (DS-014 ЭТАП 4).
================================================================
Planner/Executor/Reviewer/Researcher на одном HKOS.

- Shared memory: Planner пишет -> Executor читает -> Reviewer валидирует;
- Concurrent writes: 2 Executor одновременно (AgentLock WRITE);
- Read concurrency: 10 Reviewer параллельно (AgentLock READ).
"""

import threading
from pathlib import Path

from hkos.integration.hermes.agent_lock import (
    LOCK_MODE_READ,
    LOCK_MODE_WRITE,
    AgentLock,
)
from hkos.repository.models import Knowledge
from tests.system.fixtures import create_system_context, project_factory


class TestConcurrentAgentsSystem:
    """Мультиагентная работа: общая память, записи, чтения."""

    def test_shared_memory_flow(self, tmp_path: Path) -> None:
        """Planner пишет -> Executor читает -> Reviewer валидирует."""
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "SharedMemory", tags=["system"])
        # Planner writes
        knowledge = ctx.librarian.register(project.id, Knowledge(
            title="PlannerFact udp", body="udp", tags=["udp"]))
        ctx.index.update(project.id, knowledge.id, "knowledge")
        # Executor reads
        result = ctx.retrieval.retrieve("PlannerFact", project_id=project.id)
        assert any("PlannerFact" in str(i.entity.title) for i in result.items)
        # Reviewer validates
        assert ctx.repos.knowledge.exists(project.id, knowledge.id)
        assert ctx.index.validate(project.id).valid is True

    def test_concurrent_writes_no_loss(self, tmp_path: Path) -> None:
        """2 Executor пишут одновременно; AgentLock WRITE; нет потерь."""
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "ConcurrentW", tags=["system"])
        lock = AgentLock()
        errors: list[Exception] = []
        written: list[str] = []

        def writer(name: str, start_id: int) -> None:
            try:
                lock.acquire(LOCK_MODE_WRITE)
                for i in range(20):
                    knowledge = ctx.librarian.register(project.id, Knowledge(
                        title=f"{name}K{start_id + i}fact udp", body="udp",
                        tags=["udp"]))
                    written.append(knowledge.id)
                lock.release(LOCK_MODE_WRITE)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=("E1", 0)),
            threading.Thread(target=writer, args=("E2", 100)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(written) == 40           # нет потери данных
        assert ctx.repos.knowledge.count(project.id) == 40  # Repository цел
        # integrity: индекс совпадает
        ctx.index.build(project.id)
        index_stats = ctx.index.statistics(project.id)
        assert int(index_stats.get("knowledge", 0)) == 40

    def test_read_concurrency(self, tmp_path: Path) -> None:
        """10 Reviewer параллельно читают; без блокировок; корректно."""
        ctx = create_system_context(tmp_path)
        project = project_factory(ctx, "ConcurrentR", tags=["system"])
        for i in range(50):
            knowledge = ctx.librarian.register(project.id, Knowledge(
                title=f"R{i}fact udp", body="udp", tags=["udp"]))
            ctx.index.update(project.id, knowledge.id, "knowledge")
        lock = AgentLock()
        results: list[int] = []
        errors: list[Exception] = []

        def reviewer() -> None:
            try:
                lock.acquire(LOCK_MODE_READ)
                result = ctx.retrieval.retrieve("udp", project_id=project.id)
                results.append(len(result.items))
                lock.release(LOCK_MODE_READ)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=reviewer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(results) == 10           # все прочитали
        assert all(count > 0 for count in results)  # корректные результаты
