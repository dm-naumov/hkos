"""Unit tests for VersionManager.
"""

import re

from hkos.core.version import VersionManager


class TestVersionManager:
    """Test suite for VersionManager."""

    def setup_method(self) -> None:
        self.vm = VersionManager()

    def test_version_info_major(self) -> None:
        assert self.vm.version.major == 1

    def test_version_info_minor(self) -> None:
        assert self.vm.version.minor == 0

    def test_version_info_patch(self) -> None:
        assert self.vm.version.patch == 0

    def test_version_string_non_empty(self) -> None:
        assert len(self.vm.version_string) > 0

    def test_version_string_format(self) -> None:
        # Release: "1.0.0"; development builds: "1.0.0-dev".
        assert re.fullmatch(r"\d+\.\d+\.\d+(-[A-Za-z0-9]+)?",
                            self.vm.version_string), self.vm.version_string

    def test_schema_version(self) -> None:
        assert len(self.vm.schema_version) > 0

    def test_build_version(self) -> None:
        # Release builds carry no suffix; development builds carry "dev".
        assert isinstance(self.vm.build_version, str)

    def test_dict_contains_all_keys(self) -> None:
        d = self.vm.dict()
        assert "version" in d
        assert "major" in d
        assert "minor" in d
        assert "patch" in d
        assert "build" in d
        assert "schema" in d

    def test_dict_values_match_properties(self) -> None:
        d = self.vm.dict()
        assert d["version"] == self.vm.version_string
        assert d["build"] == self.vm.build_version
        assert d["schema"] == self.vm.schema_version
