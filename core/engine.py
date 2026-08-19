"""HKOS Engine
============
Core engine that manages the HKOS lifecycle.
"""

import time
from typing import Any

from hkos.core.config import ConfigLoader
from hkos.core.health import HealthManager
from hkos.core.logger import HKOSLogger
from hkos.core.registry import Registry
from hkos.core.state import RuntimeState
from hkos.core.version import VersionManager


class HKOSEngine:
    """Core engine of the Hermes Knowledge OS.

    Manages the HKOS lifecycle: start, stop, health, and version.
    On DS-001, this is a minimal engine that provides the framework
    for future components.
    """

    def __init__(
        self,
        config: ConfigLoader,
        logger: HKOSLogger,
        registry: Registry,
        version: VersionManager,
        health: HealthManager,
    ) -> None:
        self._config: ConfigLoader = config
        self._logger: HKOSLogger = logger
        self._registry: Registry = registry
        self._version: VersionManager = version
        self._health: HealthManager = health
        self._state: RuntimeState = RuntimeState()
        self._start_time: float = 0.0

    def start(self) -> None:
        """Start the HKOS engine.

        Transitions the engine to running state.
        """
        self._start_time = time.time()
        self._state.transition_to('initialized')
        self._state.transition_to('running')
        self._logger.info("HKOS engine started")

    def stop(self) -> None:
        """Stop the HKOS engine gracefully."""
        self._logger.info("HKOS engine stopping...")
        self._state.transition_to('stopped')
        self._logger.info("HKOS engine stopped")

    def status(self) -> dict[str, Any]:
        """Return the current engine status."""
        return {
            "state": self._state.current(),
            "version": self._version.version_string,
            "uptime_seconds": time.time() - self._start_time if self._start_time > 0 else 0.0,
            "config_profile": self._config.profile,
        }

    def health(self) -> dict[str, Any]:
        """Return the full health report."""
        return self._health.report()

    def version(self) -> dict[str, Any]:
        """Return version information."""
        return self._version.dict()
