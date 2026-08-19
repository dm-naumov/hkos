"""Unit tests for ConfigLoader.
"""

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.exceptions import ConfigurationError


class TestConfigLoader:
    """Test suite for ConfigLoader."""

    def test_development_profile(self) -> None:
        loader = ConfigLoader(profile="development")
        assert loader.profile == "development"

    def test_production_profile(self) -> None:
        loader = ConfigLoader(profile="production")
        assert loader.profile == "production"

    def test_load_development_config(self) -> None:
        loader = ConfigLoader(profile="development")
        config = loader.load()
        assert isinstance(config, dict)
        assert "hkos" in config
        assert "logging" in config
        assert "health" in config

    def test_loaded_flag_after_load(self) -> None:
        loader = ConfigLoader(profile="development")
        assert not loader.is_loaded
        loader.load()
        assert loader.is_loaded

    def test_validate_passes(self) -> None:
        loader = ConfigLoader(profile="development")
        loader.load()
        assert loader.validate() is True

    def test_validate_fails_without_load(self) -> None:
        loader = ConfigLoader(profile="development")
        with pytest.raises(ConfigurationError, match="not loaded"):
            loader.validate()

    def test_get_existing_key(self) -> None:
        loader = ConfigLoader(profile="development")
        loader.load()
        version = loader.get("hkos.version")
        assert version is not None

    def test_get_missing_key_returns_default(self) -> None:
        loader = ConfigLoader(profile="development")
        loader.load()
        value = loader.get("nonexistent.key", default="fallback")
        assert value == "fallback"

    def test_set_changes_value(self) -> None:
        loader = ConfigLoader(profile="development")
        loader.load()
        loader.set("test.key", 42)
        assert loader.get("test.key") == 42

    def test_reload_works(self) -> None:
        loader = ConfigLoader(profile="development")
        loader.load()
        loader.reload()
        assert loader.is_loaded

    def test_defaults_applied(self) -> None:
        loader = ConfigLoader(profile="development")
        config = loader.load()
        health = config.get("health", {})
        assert "check_interval_seconds" in health
        assert health["check_interval_seconds"] > 0
