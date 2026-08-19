"""DS-016 ЭТАП 3.7: Final Performance (Hermes overhead).
================================================================
startup / retrieval hook / context injection / save hook;
SLA: retrieval <100, context <200, save <150; warm через IndexCache.
"""

import time
from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context


class TestFinalPerformance:
    """Overhead интеграции Hermes + HKOS."""

    def test_overhead_sla(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        # startup
        start = time.perf_counter()
        ctx.hooks.startup()
        startup_ms = (time.perf_counter() - start) * 1000
        # корпус
        project = ctx.project.create(name="PerfH", tags=["hermes"])
        for i in range(300):
            result = ctx.save_after_task(project.id, Knowledge(
                title=f"PH{i}fact udp", body="udp", tags=["udp"]))
            assert result["saved"]
        # retrieval hook (cold)
        start = time.perf_counter()
        ctx.retrieve_before_task("udp", project_id=project.id)
        cold = (time.perf_counter() - start) * 1000
        assert cold < 100, f"retrieval hook {cold:.1f} ms"
        # retrieval hook (warm через IndexCache)
        start = time.perf_counter()
        ctx.retrieve_before_task("udp", project_id=project.id)
        warm = (time.perf_counter() - start) * 1000
        assert warm < 100, f"warm {warm:.1f} ms"
        # context injection (в bundle; отдельный замер)
        start = time.perf_counter()
        bundle = ctx.retrieve_before_task("udp", project_id=project.id)
        context_ms = (time.perf_counter() - start) * 1000
        assert bundle["context"] is not None
        assert context_ms < 200, f"context {context_ms:.1f} ms"
        # save hook
        start = time.perf_counter()
        ctx.save_after_task(project.id, Knowledge(
            title="SavePerfH udp", body="udp", tags=["udp"]))
        save_ms = (time.perf_counter() - start) * 1000
        assert save_ms < 150, f"save {save_ms:.1f} ms"
        print(f"\nHERMES OVERHEAD: startup {startup_ms:.1f} ms, "
              f"retrieval cold {cold:.1f} ms, warm {warm:.1f} ms, "
              f"context {context_ms:.1f} ms, save {save_ms:.1f} ms")
