"""HKOS Types
==========
Common type definitions used across HKOS modules.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VersionInfo:
    """HKOS version information."""

    major: int
    minor: int
    patch: int
    build: str

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}-{self.build}"

    def dict(self) -> dict[str, Any]:
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "build": self.build,
        }


@dataclass
class HealthStatus:
    """Health check result for a component."""

    component: str
    status: str  # PASS | FAIL | WARN
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class HealthReport:
    """Complete health report for the HKOS system."""

    overall: str  # PASS | FAIL | WARN
    checks: list[HealthStatus] = field(default_factory=list)
    version: str = ""
    uptime_seconds: float = 0.0

    def dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "checks": [c.dict() for c in self.checks],
        }


@dataclass
class RuntimeStateValue:
    """Immutable runtime state descriptor."""

    name: str
    description: str
