"""Hermes Knowledge OS (HKOS)
============================
An object-oriented file-based engineering knowledge database.

DS-001 (Sprint 1): Foundation
- HKOS as an importable module
- Bootstrap, Configuration, Logger, Registry
- Version and Health management
"""

from hkos.core.config import ConfigLoader
from hkos.core.exceptions import (
    ConfigurationError,
    HKOSError,
    InitializationError,
    RuntimeErrorHKOS,
    ValidationError,
)
from hkos.core.health import HealthManager
from hkos.core.hkos import HKOS
from hkos.core.logger import HKOSLogger
from hkos.core.registry import Registry
from hkos.core.version import VersionManager

__all__ = [
    "HKOS",
    "VersionManager",
    "ConfigLoader",
    "HealthManager",
    "Registry",
    "HKOSLogger",
    "HKOSError",
    "ConfigurationError",
    "InitializationError",
    "RuntimeErrorHKOS",
    "ValidationError",
]
