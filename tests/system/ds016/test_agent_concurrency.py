"""DS-016 ЭТАП 3.3: Concurrent Agent Test.
================================================================
5 агентов x 50 знаний = 250. AgentLock WRITE; нет race/дубликатов/
повреждений; index rebuild не нужен; retrieval работает.
"""

import threading
from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context


class TestAgentConcurrency:
    """5 конкурентных агентов (retrieve + save)."""

    def test_5x50_concurrent_agents(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Concurrent", tags=["hermes"])
        errors: list[Exception] = []
        saved_total = 0

        def agent(name: str, start: int) -> None:
            nonlocal saved_total
            try:
                for i in range(50):
                    # retrieve (перед задачей)
                    ctx.retrieve_before_task("udp", project_id=project.id)
                    # save
                    result = ctx.save_after_task(project.id, Knowledge(
                        title=f"{name}K{start + i}fact udp", body="udp",
                        tags=["udp"]))
                    if result["saved"]:
                        saved_total += 1
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [
            threading.Thread(target=agent, args=(f"A{n}", n * 100))
            for n in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert saved_total == 250
        # repository_count == 250; unique_ids == 250
        ids = [k.id for k in ctx.repos.knowledge.list(project.id)]
        assert len(ids) == 250
        assert len(set(ids)) == 250
        # index == repository (rebuild не нужен: счётчики сходятся через update)
        index_count = int(ctx.index.statistics(project.id).get("knowledge", 0))
        assert index_count == 250, f"index {index_count} != 250"
        # retrieval работает
        result = ctx.retrieval.retrieve("udp", project_id=project.id)
        assert len(result.items) >= 1
