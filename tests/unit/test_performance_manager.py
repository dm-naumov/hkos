"""Unit tests: PerformanceManager (DS-013 ЭТАП 4)."""

import time
from pathlib import Path

from hkos.performance.metrics_engine import MetricsEngine
from hkos.performance.performance_manager import (
    EVENT_METRIC_RECORDED,
    EVENT_PROFILING_FINISHED,
    EVENT_PROFILING_STARTED,
    PerformanceLogger,
    PerformanceManager,
)
from hkos.performance.resource_monitor import ResourceMonitor


class TestPerformanceManager:
    """Фасад: start/stop/statistics/profile/health/reset."""

    def test_start_stop_log_events(self, tmp_path: Path) -> None:
        log = PerformanceLogger(tmp_path / "performance.log")
        manager = PerformanceManager(logger=log)
        manager.start()
        manager.stop()
        content = (tmp_path / "performance.log").read_text()
        assert EVENT_PROFILING_STARTED in content
        assert EVENT_PROFILING_FINISHED in content

    def test_measure_records_metric_and_log(self, tmp_path: Path) -> None:
        log = PerformanceLogger(tmp_path / "performance.log")
        metrics = MetricsEngine()
        manager = PerformanceManager(metrics=metrics, logger=log)
        with manager.measure("retrieval", project_id="p1"):
            time.sleep(0.005)
        assert metrics.statistics("retrieval")[0].count == 1
        content = (tmp_path / "performance.log").read_text()
        assert EVENT_METRIC_RECORDED in content

    def test_disabled_measure_noop(self, tmp_path: Path) -> None:
        metrics = MetricsEngine()
        manager = PerformanceManager(metrics=metrics)
        manager.stop()
        with manager.measure("op"):
            pass
        assert metrics.entries() == []  # no-op при disabled

    def test_profile_alias(self, tmp_path: Path) -> None:
        metrics = MetricsEngine()
        manager = PerformanceManager(metrics=metrics)
        with manager.profile("ranking"):
            pass
        assert metrics.statistics("ranking")[0].count == 1

    def test_statistics(self, tmp_path: Path) -> None:
        manager = PerformanceManager()
        with manager.measure("retrieval"):
            time.sleep(0.01)
        stats = manager.statistics()
        metrics = stats.get("metrics")
        assert isinstance(metrics, list) and metrics
        assert metrics[0].operation == "retrieval"
        latency = stats.get("latency")
        assert isinstance(latency, dict)
        assert "p50" in latency

    def test_reset(self, tmp_path: Path) -> None:
        manager = PerformanceManager()
        with manager.measure("op"):
            pass
        manager.reset()
        assert manager.statistics()["metrics"] == []

    def test_health(self, tmp_path: Path) -> None:
        manager = PerformanceManager(resource=ResourceMonitor(tmp_path))
        health = manager.health()
        assert health["enabled"] is True
        assert "resources" in health
        log_path = health.get("log_path")
        assert isinstance(log_path, str) and log_path.endswith("performance.log")

    def test_resource_warning_logged(self, tmp_path: Path) -> None:
        log = PerformanceLogger(tmp_path / "performance.log")
        manager = PerformanceManager(logger=log)
        manager.resource_warning("RAM high")
        assert "RESOURCE_WARNING" in (tmp_path / "performance.log").read_text()

    def test_no_forbidden_imports(self) -> None:
        """Performance Layer не импортирует бизнес-слои."""
        import inspect

        for module_name in (
            "hkos.performance.performance_manager",
            "hkos.performance.metrics_engine",
            "hkos.performance.profiler",
            "hkos.performance.latency_tracker",
            "hkos.performance.resource_monitor",
        ):
            module = __import__(module_name, fromlist=["x"])
            source = inspect.getsource(module)
            for forbidden in ("repository", "retrieval", "context", "snapshot",
                              "migration", "services.librarian"):
                assert f"hkos.{forbidden}" not in source, (
                    f"{module_name}: {forbidden}")
