"""Unit tests for Bootstrap.
"""


from hkos.core.bootstrap import Bootstrap


class TestBootstrap:
    """Test suite for Bootstrap."""

    def test_bootstrap_development(self) -> None:
        boot = Bootstrap(profile="development")
        engine = boot.run()
        assert engine is not None

    def test_bootstrap_engine_can_start(self) -> None:
        boot = Bootstrap(profile="development")
        engine = boot.run()
        engine.start()
        assert engine.status()["state"] == "running"

    def test_bootstrap_engine_can_stop(self) -> None:
        boot = Bootstrap(profile="development")
        engine = boot.run()
        engine.start()
        engine.stop()
        assert engine.status()["state"] == "stopped"

    def test_bootstrap_registers_checks(self) -> None:
        boot = Bootstrap(profile="development")
        engine = boot.run()
        health = engine.health()
        assert len(health["checks"]) >= 3

    def test_bootstrap_version_available(self) -> None:
        boot = Bootstrap(profile="development")
        engine = boot.run()
        v = engine.version()
        assert v["major"] >= 1
