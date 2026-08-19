"""Unit tests for HealthManager.
"""

from hkos.core.constants import HEALTH_STATUS_FAIL, HEALTH_STATUS_PASS
from hkos.core.health import HealthManager


class TestHealthManager:
    """Test suite for HealthManager."""

    def setup_method(self) -> None:
        self.hm = HealthManager()

    def test_initial_no_checks(self) -> None:
        report = self.hm.summary()
        assert len(report.checks) == 0

    def test_register_check_ok(self) -> None:
        self.hm.register_check("test_component", ok=True)
        result = self.hm.check("test_component")
        assert result.status == HEALTH_STATUS_PASS
        assert result.component == "test_component"

    def test_register_check_fail(self) -> None:
        self.hm.register_check("test_component", ok=False)
        result = self.hm.check("test_component")
        assert result.status == HEALTH_STATUS_FAIL

    def test_check_unregistered(self) -> None:
        result = self.hm.check("unknown")
        assert result.status == HEALTH_STATUS_FAIL

    def test_summary_all_pass(self) -> None:
        self.hm.register_check("a", ok=True)
        self.hm.register_check("b", ok=True)
        report = self.hm.summary()
        assert report.overall == HEALTH_STATUS_PASS
        assert len(report.checks) == 2

    def test_summary_any_fail(self) -> None:
        self.hm.register_check("a", ok=True)
        self.hm.register_check("b", ok=False)
        report = self.hm.summary()
        assert report.overall == HEALTH_STATUS_FAIL

    def test_report_dict_format(self) -> None:
        self.hm.register_check("a", ok=True)
        report = self.hm.report()
        assert "overall" in report
        assert "checks" in report
        assert "version" in report
        assert "uptime_seconds" in report

    def test_uptime_increases(self) -> None:
        import time
        report1 = self.hm.summary()
        time.sleep(0.01)
        report2 = self.hm.summary()
        assert report2.uptime_seconds >= report1.uptime_seconds
