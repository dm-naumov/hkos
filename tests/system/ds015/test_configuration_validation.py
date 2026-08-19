"""DS-015 ЭТАП 2: Configuration Validation.

Invalid config отклоняется; missing required fields отклоняются;
production config принимается.
"""

from pathlib import Path

import pytest
import yaml

from hkos.core.config import ConfigLoader
from hkos.core.exceptions import ConfigurationError


def _write_config(tmp: Path, data: dict) -> Path:
    path = tmp / "config" / "hkos-production.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(data))
    return path


class TestConfigurationValidation:
    """Валидация конфигурации (профиль production)."""

    def test_production_config_accepted(self) -> None:
        loader = ConfigLoader(profile="production")
        loader.load()
        assert loader.validate() is True

    def test_invalid_yaml_rejected(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        path = tmp_path / "config" / "hkos-production.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("{ broken yaml: [")
        monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
        with pytest.raises(ConfigurationError):
            ConfigLoader(profile="production").load()

    def test_missing_hkos_section_rejected(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        _write_config(tmp_path, {"operations": {}})
        monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
        loader = ConfigLoader(profile="production")
        loader.load()
        with pytest.raises(ConfigurationError):
            loader.validate()

    def test_missing_version_rejected(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        _write_config(tmp_path, {"hkos": {"enabled": True}})
        monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
        loader = ConfigLoader(profile="production")
        loader.load()
        with pytest.raises(ConfigurationError):
            loader.validate()
