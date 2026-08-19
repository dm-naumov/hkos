"""HKOS Logger
============
Separate logging system for HKOS.
Uses its own namespace ('hkos') to avoid affecting Hermes logging.
"""

import logging
import logging.handlers
import os
import sys

from hkos.core.constants import NAMESPACE


class HKOSLogger:
    """Isolated logger for HKOS.
    
    Operates in its own namespace to avoid interfering with
    Hermes Agent's existing logging infrastructure.
    """

    def __init__(self, name: str = NAMESPACE) -> None:
        self._logger: logging.Logger = logging.getLogger(name)
        self._logger.propagate = False
        self._handlers_initialized: bool = False

    def initialize(
        self,
        level: str = "DEBUG",
        log_file: str | None = None,
        console: bool = True,
    ) -> None:
        """Initialize the logger with handlers.
        
        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR).
            log_file: Optional path to log file.
            console: Whether to add a console handler.

        """
        if self._handlers_initialized:
            return

        numeric_level = getattr(logging, level.upper(), logging.DEBUG)
        self._logger.setLevel(numeric_level)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

        if console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(numeric_level)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        if log_file:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except OSError:
                    pass  # Best effort — logging should not crash

            try:
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=3,
                )
                file_handler.setLevel(numeric_level)
                file_handler.setFormatter(formatter)
                self._logger.addHandler(file_handler)
            except OSError:
                pass  # Best effort

        self._handlers_initialized = True

    def debug(self, message: str) -> None:
        """Log a debug message."""
        self._logger.debug(message)

    def info(self, message: str) -> None:
        """Log an info message."""
        self._logger.info(message)

    def warning(self, message: str) -> None:
        """Log a warning message."""
        self._logger.warning(message)

    def error(self, message: str) -> None:
        """Log an error message."""
        self._logger.error(message)

    @property
    def logger(self) -> logging.Logger:
        """Return the underlying Python logger instance."""
        return self._logger

    @property
    def is_initialized(self) -> bool:
        """Return whether handlers have been initialized."""
        return self._handlers_initialized
