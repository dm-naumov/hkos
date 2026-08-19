"""HKOS Version Manager
=====================
Manages and returns version information for HKOS.
"""

from typing import Any

from hkos.core.constants import (
    SCHEMA_VERSION,
    VERSION_BUILD,
    VERSION_MAJOR,
    VERSION_MINOR,
    VERSION_PATCH,
    VERSION_STRING,
)
from hkos.core.types import VersionInfo


class VersionManager:
    """Manages HKOS version information.
    
    Provides access to the current HKOS version, schema version,
    and build version. All version data is read-only.
    """

    def __init__(self) -> None:
        self._major: int = VERSION_MAJOR
        self._minor: int = VERSION_MINOR
        self._patch: int = VERSION_PATCH
        self._build: str = VERSION_BUILD
        self._schema: str = SCHEMA_VERSION

    @property
    def version(self) -> VersionInfo:
        """Return the current HKOS version as a VersionInfo."""
        return VersionInfo(
            major=self._major,
            minor=self._minor,
            patch=self._patch,
            build=self._build,
        )

    @property
    def version_string(self) -> str:
        """Return the version string (e.g., '1.0.0-dev')."""
        return VERSION_STRING

    @property
    def schema_version(self) -> str:
        """Return the schema version."""
        return self._schema

    @property
    def build_version(self) -> str:
        """Return the build version string."""
        return self._build

    def dict(self) -> dict[str, Any]:
        """Return version info as a dictionary."""
        return {
            "version": self.version_string,
            "major": self._major,
            "minor": self._minor,
            "patch": self._patch,
            "build": self._build,
            "schema": self._schema,
        }
