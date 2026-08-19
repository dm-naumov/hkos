"""HKOS — Hermes Knowledge OS
============================
Main entry point for the Hermes Knowledge Operating System.

Usage:
    from hkos import HKOS
    
    hkos = HKOS()
    hkos.start()
    print(hkos.status())
    hkos.stop()
"""

from typing import Any

from hkos.core.bootstrap import Bootstrap
from hkos.core.engine import HKOSEngine
from hkos.core.version import VersionManager


class HKOS:
    """Hermes Knowledge OS — main entry point.
    
    Provides the public API for HKOS lifecycle management.
    
    Usage:
        hkos = HKOS()
        hkos.start()
        hkos.status()
        hkos.health()
        hkos.version()
        hkos.stop()
    
    Limitations:
        On DS-001, HKOS has no storage, retrieval, or memory.
        It is a minimal framework ready for future components.
    """

    def __init__(self, profile: str = "development") -> None:
        self._profile: str = profile
        self._engine: HKOSEngine | None = None
        self._bootstrap: Bootstrap | None = None

    def start(self) -> None:
        """Initialize and start HKOS.
        
        Runs the full bootstrap sequence and transitions
        the engine to running state.
        """
        self._bootstrap = Bootstrap(profile=self._profile)
        self._engine = self._bootstrap.run()
        self._engine.start()

    def stop(self) -> None:
        """Stop HKOS gracefully."""
        if self._engine is not None:
            self._engine.stop()

    def status(self) -> dict[str, Any]:
        """Return engine status."""
        if self._engine is None:
            return {"state": "stopped", "error": "HKOS not started"}
        return self._engine.status()

    def health(self) -> dict[str, Any]:
        """Return full health report."""
        if self._engine is None:
            return {"overall": "FAIL", "error": "HKOS not started"}
        return self._engine.health()

    def version(self) -> dict[str, Any]:
        """Return version information."""
        if self._engine is not None:
            return self._engine.version()
        return VersionManager().dict()
