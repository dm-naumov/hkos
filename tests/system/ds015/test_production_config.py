"""DS-015 ЭТАП 2: Production Configuration.

Файл существует; YAML корректен; обязательные параметры и типы.
"""

from pathlib import Path

import yaml

CONFIG_PATH = Path("/home/dm/hkos/config/hkos-production.yaml")

REQUIRED = {
    "hkos.enabled": bool,
    "operations.auto_snapshot": bool,
    "operations.auto_index": bool,
    "operations.retrieve_before_task": bool,
    "operations.save_after_task": bool,
    "operations.context_profile": str,
    "performance.cache.enabled": bool,
    "performance.cache.ttl_seconds": (int, float),
    "logging.level": str,
    "backup.enabled": bool,
}


class TestProductionConfig:
    """Производственный конфиг: существование, YAML, параметры, типы."""

    def test_file_exists(self) -> None:
        assert CONFIG_PATH.exists(), "hkos-production.yaml missing"

    def test_valid_yaml(self) -> None:
        config = yaml.safe_load(CONFIG_PATH.read_text())
        assert isinstance(config, dict)
        assert "hkos" in config

    def test_required_parameters_present(self) -> None:
        config = yaml.safe_load(CONFIG_PATH.read_text())

        def get(path: str):
            value = config
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            return value

        for key in REQUIRED:
            assert get(key) is not None, f"missing {key}"

    def test_parameter_types(self) -> None:
        config = yaml.safe_load(CONFIG_PATH.read_text())

        def get(path: str):
            value = config
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            return value

        for key, expected_type in REQUIRED.items():
            value = get(key)
            assert isinstance(value, expected_type), (
                f"{key}: expected {expected_type}, got {type(value)}")

    def test_loader_accepts_production(self) -> None:
        from hkos.core.config import ConfigLoader

        loader = ConfigLoader(profile="production")
        loader.load()
        assert loader.validate() is True
