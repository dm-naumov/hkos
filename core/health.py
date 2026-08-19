"""HKOS Health Manager
====================
Provides health checking for HKOS subsystems.
"""

import time
from typing import Any

from hkos.core.constants import HEALTH_STATUS_FAIL, HEALTH_STATUS_PASS, HEALTH_STATUS_WARN
from hkos.core.types import HealthReport, HealthStatus


class HealthManager:
    """Health check manager for HKOS.
    
    Performs health checks on registered HKOS subsystems.
    On DS-001, checks: config, logger, registry.
    """

    def __init__(self) -> None:
        self._start_time: float = time.time()
        self._checks: dict[str, bool] = {}

    def register_check(self, name: str, ok: bool = True) -> None:
        """Register or update a health check result."""
        self._checks[name] = ok

    def check(self, name: str) -> HealthStatus:
        """Run a specific health check by name."""
        ok = self._checks.get(name, False)
        status = HEALTH_STATUS_PASS if ok else HEALTH_STATUS_FAIL
        return HealthStatus(
            component=name,
            status=status,
            message=f"{name} is {'available' if ok else 'unavailable'}",
            details={"registered": name in self._checks},
        )

    def summary(self) -> HealthReport:
        """Return a complete health report for all registered checks."""
        uptime = time.time() - self._start_time
        results = []
        overall_failures = 0
        overall_warnings = 0

        for name in self._checks:
            result = self.check(name)
            results.append(result)
            if result.status == HEALTH_STATUS_FAIL:
                overall_failures += 1
            elif result.status == HEALTH_STATUS_WARN:
                overall_warnings += 1

        if overall_failures > 0:
            overall = HEALTH_STATUS_FAIL
        elif overall_warnings > 0:
            overall = HEALTH_STATUS_WARN
        else:
            overall = HEALTH_STATUS_PASS

        from hkos.core.constants import VERSION_STRING
        return HealthReport(
            overall=overall,
            checks=results,
            version=VERSION_STRING,
            uptime_seconds=uptime,
        )

    def report(self) -> dict[str, Any]:
        """Return health report as a dictionary (for API/CLI output)."""
        return self.summary().dict()
