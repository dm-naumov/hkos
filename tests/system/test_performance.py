"""System: производительность (DS-014).

Бюджеты: retrieval <100 мс, context <200 мс, save <150 мс, profiler <2 мс,
metrics <1 мс, cache hit >80%.
Скелет ЭТАПА 1.
"""

from pathlib import Path


class TestSystemPerformance:
    """Системные бюджеты производительности."""

    def test_skeleton_smoke(self, tmp_path: Path) -> None:
        from tests.system.fixtures import performance_fixture

        ctx, perf = performance_fixture(tmp_path)
        assert ctx.engine is not None
        assert perf.cache is not None
