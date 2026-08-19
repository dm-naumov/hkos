"""Integration tests for HKOS startup sequence.
"""

from hkos import HKOS


class TestHKOSStartup:
    """Test the full HKOS lifecycle."""

    def test_hkos_importable(self) -> None:
        from hkos import HKOS
        assert HKOS is not None

    def test_hkos_start_and_stop(self) -> None:
        hkos = HKOS()
        hkos.start()
        assert hkos.status()["state"] == "running"
        hkos.stop()
        assert hkos.status()["state"] == "stopped"

    def test_hkos_health_after_start(self) -> None:
        hkos = HKOS()
        hkos.start()
        health = hkos.health()
        assert health["overall"] in ("PASS", "FAIL")
        assert len(health["checks"]) >= 3
        hkos.stop()

    def test_hkos_version_after_start(self) -> None:
        hkos = HKOS()
        hkos.start()
        version = hkos.version()
        assert version["version"].startswith("1.")
        hkos.stop()

    def test_hkos_status_before_start(self) -> None:
        hkos = HKOS()
        status = hkos.status()
        assert status["state"] == "stopped"

    def test_hkos_double_start(self) -> None:
        hkos = HKOS()
        hkos.start()
        hkos.stop()
        hkos.start()
        assert hkos.status()["state"] == "running"
        hkos.stop()

    def test_hkos_version_without_start(self) -> None:
        hkos = HKOS()
        v = hkos.version()
        assert "version" in v
