"""Unit tests for HKOSEngine.
"""

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.engine import HKOSEngine
from hkos.core.health import HealthManager
from hkos.core.logger import HKOSLogger
from hkos.core.registry import Registry
from hkos.core.version import VersionManager


@pytest.fixture
def engine() -> HKOSEngine:
    """Create a configured engine for testing."""
    config = ConfigLoader(profile="development")
    config.load()
    logger = HKOSLogger()
    logger.initialize(level="ERROR", console=False)
    registry = Registry()
    version = VersionManager()
    health = HealthManager()
    return HKOSEngine(
        config=config,
        logger=logger,
        registry=registry,
        version=version,
        health=health,
    )


class TestHKOSEngine:
    """Test suite for HKOSEngine."""

    def test_start_changes_state(self, engine: HKOSEngine) -> None:
        assert engine.status()["state"] == "stopped"
        engine.start()
        assert engine.status()["state"] == "running"

    def test_stop_changes_state(self, engine: HKOSEngine) -> None:
        engine.start()
        engine.stop()
        assert engine.status()["state"] == "stopped"

    def test_version_returns_dict(self, engine: HKOSEngine) -> None:
        v = engine.version()
        assert isinstance(v, dict)
        assert "version" in v

    def test_health_returns_dict(self, engine: HKOSEngine) -> None:
        h = engine.health()
        assert isinstance(h, dict)
        assert "overall" in h

    def test_status_has_required_keys(self, engine: HKOSEngine) -> None:
        engine.start()
        s = engine.status()
        assert "state" in s
        assert "version" in s
        assert "uptime_seconds" in s
        assert "config_profile" in s

    def test_uptime_after_start(self, engine: HKOSEngine) -> None:
        import time
        engine.start()
        time.sleep(0.01)
        status = engine.status()
        assert status["uptime_seconds"] > 0
