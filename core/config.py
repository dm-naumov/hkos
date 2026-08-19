"""HKOS Configuration Loader
==========================
Loads and manages HKOS configuration from YAML files.
"""

import os
from typing import Any

import yaml

from hkos.core.constants import (
    CONFIG_FILE_DEV,
    CONFIG_FILE_PROD,
    DEFAULT_HEALTH_CHECK_INTERVAL,
    DEFAULT_LOG_BACKUP_COUNT,
    DEFAULT_LOG_MAX_SIZE_MB,
)
from hkos.core.exceptions import ConfigurationError


class ConfigLoader:
    """Configuration loader for HKOS.
    
    Loads configuration from YAML files with sensible defaults.
    Supports development and production config profiles.
    """

    def __init__(self, profile: str = "development") -> None:
        self._profile: str = profile
        self._config: dict[str, Any] = {}
        self._loaded: bool = False

    def load(self) -> dict[str, Any]:
        """Load configuration from the appropriate YAML file."""
        config_file = CONFIG_FILE_DEV if self._profile == "development" else CONFIG_FILE_PROD

        # Try absolute path first, then relative
        paths_to_try = [
            config_file,
            os.path.join(os.getcwd(), config_file),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", config_file),
        ]

        loaded = False
        for path in paths_to_try:
            normalized = os.path.normpath(path)
            if os.path.isfile(normalized):
                try:
                    with open(normalized, "r") as f:
                        self._config = yaml.safe_load(f) or {}
                    self._loaded = True
                    loaded = True
                    break
                except yaml.YAMLError as e:
                    raise ConfigurationError(f"Invalid YAML in {normalized}: {e}")
                except OSError as e:
                    raise ConfigurationError(f"Cannot read {normalized}: {e}")

        if not loaded:
            raise ConfigurationError(f"Configuration file not found for profile '{self._profile}'")

        self._apply_defaults()
        return self._config

    def reload(self) -> dict[str, Any]:
        """Reload configuration from disk."""
        self._loaded = False
        return self.load()

    def validate(self) -> bool:
        """Validate the loaded configuration.
        
        Returns:
            True if configuration passes all validation checks.
        
        Raises:
            ConfigurationError if validation fails.

        """
        if not self._loaded:
            raise ConfigurationError("Configuration not loaded. Call load() first.")

        # Validate required top-level keys
        if "hkos" not in self._config:
            raise ConfigurationError("Missing 'hkos' section in configuration.")

        hkos_section = self._config.get("hkos", {})
        if "version" not in hkos_section:
            raise ConfigurationError("Missing 'hkos.version' in configuration.")

        return True

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-separated key."""
        if not self._loaded:
            return default

        keys = key.split(".")
        value: Any = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value by dot-separated key.
        
        This modifies the in-memory config only. Persistent changes
        must be made through the config YAML file.
        """
        keys = key.split(".")
        target: dict[str, Any] = self._config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    def _apply_defaults(self) -> None:
        """Apply default values for missing configuration parameters."""
        health = self._config.setdefault("health", {})
        health.setdefault("check_interval_seconds", DEFAULT_HEALTH_CHECK_INTERVAL)
        health.setdefault("components", ["config", "logger", "registry"])

        logging_cfg = self._config.setdefault("logging", {})
        logging_cfg.setdefault("level", "DEBUG")
        logging_cfg.setdefault("max_size_mb", DEFAULT_LOG_MAX_SIZE_MB)
        logging_cfg.setdefault("backup_count", DEFAULT_LOG_BACKUP_COUNT)

        core = self._config.setdefault("core", {})
        bootstrap = core.setdefault("bootstrap", {})
        bootstrap.setdefault("auto_start", False)
        bootstrap.setdefault("health_check_on_start", True)

    @property
    def profile(self) -> str:
        """Return the current config profile name."""
        return self._profile

    @property
    def is_loaded(self) -> bool:
        """Return whether configuration has been loaded."""
        return self._loaded
