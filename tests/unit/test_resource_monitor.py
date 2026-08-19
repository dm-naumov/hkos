"""Unit tests: ResourceMonitor (DS-013 ЭТАП 4)."""

import time
from pathlib import Path

from hkos.performance.resource_monitor import ResourceMonitor


class TestResourceMonitor:
    """Read-only наблюдатель: RAM/CPU/размеры/кэш."""

    def test_snapshot_returns_data(self, tmp_path: Path) -> None:
        monitor = ResourceMonitor(tmp_path)
        snapshot = monitor.snapshot()
        assert "ram_mb" in snapshot
        assert "cpu_percent" in snapshot
        assert "repository_size_bytes" in snapshot
        assert "index_size_bytes" in snapshot
        assert "snapshot_size_bytes" in snapshot
        assert "cache_entries" in snapshot
        ram = snapshot["ram_mb"]
        assert isinstance(ram, (int, float)) and ram >= 0
        assert snapshot["repository_size_bytes"] == 0  # пустой корень

    def test_sizes_detected(self, tmp_path: Path) -> None:
        (tmp_path / "projects" / "p1" / "knowledge").mkdir(parents=True)
        (tmp_path / "projects" / "p1" / "knowledge" / "a.json").write_text("x" * 100)
        (tmp_path / "projects" / "p1" / "indexes").mkdir()
        (tmp_path / "projects" / "p1" / "indexes" / "i.idx").write_text("y" * 50)
        monitor = ResourceMonitor(tmp_path)
        snapshot = monitor.snapshot()
        assert snapshot["repository_size_bytes"] == 150
        assert snapshot["index_size_bytes"] == 50
        assert snapshot["snapshot_size_bytes"] == 0

    def test_cache_size_provider(self, tmp_path: Path) -> None:
        monitor = ResourceMonitor(tmp_path, cache_size_provider=lambda: 7)
        assert monitor.snapshot()["cache_entries"] == 7

    def test_read_only_no_mutation(self, tmp_path: Path) -> None:
        before = sorted(str(p) for p in tmp_path.rglob("*"))
        ResourceMonitor(tmp_path).snapshot()
        after = sorted(str(p) for p in tmp_path.rglob("*"))
        assert before == after  # ничего не создано/изменено

    def test_overhead_budget(self, tmp_path: Path) -> None:
        """resource monitor <= 10 ms (бюджет DS-013)."""
        monitor = ResourceMonitor(tmp_path)
        start = time.perf_counter()
        for _ in range(20):
            monitor.snapshot()
        elapsed = (time.perf_counter() - start) / 20 * 1000
        assert elapsed <= 10.0, f"resource monitor {elapsed:.3f} ms"
