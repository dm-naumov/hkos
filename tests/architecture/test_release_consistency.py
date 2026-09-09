"""Architecture gate for release-version and active-document consistency."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

from hkos.core import constants
from hkos.core.version import VersionManager

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _version() -> str:
    """Return the canonical release version from the repository root."""
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _assert_equal(source: str, actual: object, expected: str) -> None:
    """Report a release-source mismatch with actionable values."""
    assert str(actual) == expected, (
        f"{source} is out of sync: expected {expected!r}, got {actual!r}")


class TestReleaseVersionConsistency:
    """All active release metadata follows the root VERSION file."""

    def test_version_is_semver(self) -> None:
        version = _version()
        assert SEMVER.fullmatch(version), (
            f"VERSION must be MAJOR.MINOR.PATCH SemVer, got {version!r}")

    def test_file_metadata_matches_version(self) -> None:
        expected = _version()
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
        manifest = json.loads((ROOT / "manifest.json").read_text())
        release_manifest = json.loads(
            (ROOT / "release" / "VERSION_MANIFEST.json").read_text())

        sources = {
            "release/VERSION": (
                ROOT / "release" / "VERSION").read_text().strip(),
            "pyproject.toml project.version": pyproject["project"]["version"],
            "manifest.json version": manifest["version"],
            "release/VERSION_MANIFEST.json version": release_manifest["version"],
            "release/VERSION_MANIFEST.json production_config_version":
                release_manifest["production_config_version"],
        }
        for source, actual in sources.items():
            _assert_equal(source, actual, expected)

    def test_config_versions_match_version(self) -> None:
        expected = _version()
        for relative in (
            "config/hkos-development.yaml",
            "config/hkos-production.yaml",
        ):
            config = yaml.safe_load((ROOT / relative).read_text())
            _assert_equal(f"{relative} hkos.version",
                          config["hkos"]["version"], expected)

    def test_runtime_version_matches_version(self) -> None:
        expected = _version()
        major, minor, patch = (int(part) for part in expected.split("."))
        runtime_sources = {
            "core.constants.VERSION_MAJOR": constants.VERSION_MAJOR,
            "core.constants.VERSION_MINOR": constants.VERSION_MINOR,
            "core.constants.VERSION_PATCH": constants.VERSION_PATCH,
        }
        expected_parts = {
            "core.constants.VERSION_MAJOR": major,
            "core.constants.VERSION_MINOR": minor,
            "core.constants.VERSION_PATCH": patch,
        }
        for source, actual in runtime_sources.items():
            assert actual == expected_parts[source], (
                f"{source} is out of sync: expected "
                f"{expected_parts[source]!r}, got {actual!r}")
        _assert_equal("core.constants.VERSION_STRING",
                      constants.VERSION_STRING, expected)
        _assert_equal("VersionManager.version_string",
                      VersionManager().version_string, expected)


class TestActiveReleaseDocumentation:
    """Current docs distinguish canonical storage from derived indexes."""

    def test_current_release_is_documented(self) -> None:
        expected = _version()
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert f"**v{expected}**" in roadmap, (
            f"ROADMAP current release does not contain v{expected}")
        assert "v1.2 (released)" in readme, (
            "README must list v1.2 as released")

    def test_sqlite_is_documented_as_derived_index(self) -> None:
        active_paths = (
            ROOT / "README.md",
            ROOT / "ROADMAP.md",
            ROOT / "docs" / "architecture.md",
            ROOT / "docs" / "performance-guide.md",
        )
        active = "\n".join(
            path.read_text(encoding="utf-8") for path in active_paths)
        lowered = active.lower()
        assert "sqlite storage backend" not in lowered, (
            "active docs call SQLite a storage backend; it is an index backend")
        assert "sqlite index" in lowered, (
            "active docs must describe the released SQLite index backend")
        assert "repository" in lowered and "ssot" in lowered, (
            "active docs must preserve the Repository as SSOT")
        assert "rebuildable projection" in lowered, (
            "active docs must describe indexes as rebuildable projections")

    def test_semantic_retrieval_remains_future_and_optional(self) -> None:
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8").lower()
        assert "optional semantic retrieval" in roadmap
        assert "candidate-provider extension point" in roadmap
        assert "later" in roadmap
