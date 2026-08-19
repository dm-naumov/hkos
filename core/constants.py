"""HKOS Constants
==============
Centralized constants for HKOS.
No magic strings in code — all constants must be defined here.
"""

# --- Version ---
VERSION_MAJOR: int = 1
VERSION_MINOR: int = 0
VERSION_PATCH: int = 0
VERSION_BUILD: str = ""  # empty = release build ("dev" during development)
VERSION_STRING: str = (
    f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
    if not VERSION_BUILD
    else f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}-{VERSION_BUILD}"
)
SCHEMA_VERSION: str = "1.0"

# --- Runtime states ---
STATE_STARTED: str = "started"
STATE_INITIALIZED: str = "initialized"
STATE_RUNNING: str = "running"
STATE_STOPPING: str = "stopping"
STATE_STOPPED: str = "stopped"
STATE_ERROR: str = "error"

# --- Names ---
PROJECT_NAME: str = "HKOS"
PROJECT_FULL_NAME: str = "Hermes Knowledge OS"
NAMESPACE: str = "hkos"

# --- Config ---
CONFIG_FILE_DEV: str = "config/hkos-development.yaml"
CONFIG_FILE_PROD: str = "config/hkos-production.yaml"
CONFIG_LOGGING_FILE: str = "config/logging.yaml"

# --- Logging ---
LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")

# --- Health ---
HEALTH_STATUS_PASS: str = "PASS"
HEALTH_STATUS_FAIL: str = "FAIL"
HEALTH_STATUS_WARN: str = "WARN"

# --- Defaults ---
DEFAULT_HEALTH_CHECK_INTERVAL: int = 60
DEFAULT_LOG_MAX_SIZE_MB: int = 10
DEFAULT_LOG_BACKUP_COUNT: int = 3
