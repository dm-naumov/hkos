"""HKOS Exceptions
===============
Custom exception hierarchy for HKOS.
"""


class HKOSError(Exception):
    """Base exception for all HKOS errors."""

    def __init__(self, message: str, component: str | None = None) -> None:
        self.component = component
        super().__init__(message)


class ConfigurationError(HKOSError):
    """Raised when configuration loading or validation fails."""

    def __init__(self, message: str, param: str | None = None) -> None:
        self.param = param
        super().__init__(message, component="config")


class InitializationError(HKOSError):
    """Raised when HKOS initialization fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, component="bootstrap")


class RuntimeErrorHKOS(HKOSError):
    """Raised when a runtime operation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, component="runtime")


class ValidationError(HKOSError):
    """Raised when data validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        self.field = field
        super().__init__(message, component="validation")
