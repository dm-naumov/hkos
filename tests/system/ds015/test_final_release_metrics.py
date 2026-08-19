"""DS-015 ЭТАП 4: Final Release Metrics.
================================================================
Сбор финальных метрик для отчёта DS-015-stage4-performance.md:
производительность (SLA-таблица), память, стабильность, Hermes.
"""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from hkos.core.logger import HKOSLogger
from hkos.performance.integration import PerformanceIntegration
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence

# Report sink: override with HKOS_REPORT_DIR (e.g. the dev machine's review
# dir); default to a temp file so the test is portable.
REPORT = Path(os.environ.get(
    "HKOS_REPORT_DIR",
    os.path.join(tempfile.gettempdir(), "hkos-release-metrics.md")))


@pytest.mark.sla
class TestFinalReleaseMetrics:
    """Метрики релиза: таблица SLA + сводка (пишется в отчёт)."""

    def test_metrics_collected(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="Metrics", tags=["final"])
        for i in range(100):
            ctx.librarian.register(project.id, Knowledge(
                title=f"FM{i}fact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        snapshots.create(project.id, reason="final")
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)

        start = time.perf_counter()
        measured.retrieve("udp", project_id=project.id)
        retrieval_cold = (time.perf_counter() - start) * 1000
        for _ in range(5):
            measured.retrieve("udp", project_id=project.id)
        start = time.perf_counter()
        measured.retrieve("udp", project_id=project.id)
        retrieval_warm = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        snapshots.load(project.id)
        snapshot_load = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        ctx.librarian.register(project.id, Knowledge(
            title="SaveFinal udp", body="udp", tags=["udp"]))
        save = (time.perf_counter() - start) * 1000
        ratio = perf.cache.statistics().get("hit_ratio", 0)

        # Корректность значений (нет отрицательных/NaN)
        assert retrieval_cold >= 0 and retrieval_warm >= 0
        assert snapshot_load >= 0 and save >= 0
        assert isinstance(ratio, float) and 0 <= ratio <= 1

        # SLA-проверки
        assert retrieval_cold < 100, f"cold {retrieval_cold:.1f}"
        assert retrieval_warm < 10, f"warm {retrieval_warm:.1f}"
        assert snapshot_load < 50, f"snapshot {snapshot_load:.1f}"
        assert save < 150, f"save {save:.1f}"
        assert ratio > 0.8, f"hit ratio {ratio:.2f}"

        # Сводка в отчёт (append)
        summary = {
            "retrieval_cold_ms": round(retrieval_cold, 2),
            "retrieval_warm_ms": round(retrieval_warm, 3),
            "snapshot_load_ms": round(snapshot_load, 2),
            "save_ms": round(save, 2),
            "cache_hit_ratio": round(ratio, 3),
            "knowledge_count": ctx.repos.knowledge.count(project.id),
            "project_count": len(ctx.project.list()),
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        with REPORT.open("a", encoding="utf-8") as handle:
            handle.write("\n```json\n" + json.dumps(summary, indent=2) +
                         "\n```\n")
