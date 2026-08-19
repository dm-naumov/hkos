"""Integration tests for configuration loading.
"""

from hkos.core.config import ConfigLoader


class TestConfigurationLoading:
    """Test config loading in an integrated context."""

    def test_dev_config_loaded(self) -> None:
        loader = ConfigLoader(profile="development")
        config = loader.load()
        assert config.get("hkos", {}).get("version") is not None

    def test_prod_config_loaded(self) -> None:
        loader = ConfigLoader(profile="production")
        config = loader.load()
        assert config.get("hkos", {}).get("version") is not None

    def test_logging_config_present(self) -> None:
        loader = ConfigLoader(profile="development")
        config = loader.load()
        assert "logging" in config

    def test_health_config_present(self) -> None:
        loader = ConfigLoader(profile="development")
        config = loader.load()
        assert "health" in config

    def test_core_config_present(self) -> None:
        loader = ConfigLoader(profile="development")
        config = loader.load()
        assert "core" in config

    def test_config_validation(self) -> None:
        loader = ConfigLoader(profile="development")
        loader.load()
        assert loader.validate() is True
