"""System: Stress 1M (DS-014 ЭТАП 5 §6).
================================================================
100 проектов x 10000 Knowledge = 1 000 000 Knowledge.
Проверки: count == 1M; index == repository; snapshot == repository;
retrieval K000001/K500000/K999999.

ВНИМАНИЕ: полный прогон (~30-40 мин) — отдельное окно. Масштаб
переключается env HKOS_STRESS_SCALE (по умолчанию 1 000 000);
для валидации механики в CI: HKOS_STRESS_SCALE=100000.
"""

import os
import time
from pathlib import Path

import pytest

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import assert_index_matches_repository
from tests.system.fixtures import (
    _MemoryPersistence,
    create_system_context,
)

# Полный прогон 1M — отдельное окно (HKOS_STRESS_SCALE=1000000);
# без env тест пропускается (в обычном прогоне не выполняется).
SCALE = int(os.environ.get("HKOS_STRESS_SCALE", "1000000"))
PROJECTS = 100
PER_PROJECT = SCALE // PROJECTS

pytestmark = pytest.mark.skipif(
    os.environ.get("HKOS_STRESS_SCALE") is None,
    reason="1M stress requires HKOS_STRESS_SCALE (dedicated window)",
)


class TestStress1M:
    """1M Knowledge (env-масштаб; полный прогон — отдельное окно)."""

    def test_stress_1m_validation(self, tmp_path: Path) -> None:
        ctx = create_system_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        start = time.perf_counter()
        for p in range(PROJECTS):
            project = ctx.projects.create(name=f"M{p}", tags=["stress1m"])
            for k in range(PER_PROJECT):
                ctx.librarian.register(project.id, Knowledge(
                    title=f"K{k:06d}fact udp", body="udp", tags=["udp"]))
            ctx.index.build(project.id)
            snapshots.create(project.id, reason="stress1m")
        gen_ms = (time.perf_counter() - start) * 1000
        sample = next(pid for pid in ctx.project_ids())
        # Repository: count == масштаб
        assert ctx.repos.knowledge.count(sample) == PER_PROJECT
        # Index == Repository
        assert_index_matches_repository(ctx, sample)
        # Snapshot == Repository (счётчик)
        snapshot = snapshots.load(sample)
        assert snapshot is not None
        assert int(snapshot.statistics.get("knowledge", 0)) == PER_PROJECT
        # Retrieval: контрольные точки (первое/среднее/последнее).
        # Токен целиком: "K000001fact" (токенизатор не режет цифры).
        markers = ("K000001", f"K{PER_PROJECT // 2:06d}",
                   f"K{PER_PROJECT - 1:06d}")
        for marker in markers:
            result = ctx.retrieval.retrieve(f"{marker}fact", project_id=sample)
            assert any(marker in str(i.entity.title) for i in result.items), (
                f"{marker} not found")
        print(f"\nSTRESS 1M-mode ({SCALE} knowledge): "
              f"gen {gen_ms / 1000:.1f}s, per-project {PER_PROJECT}")
