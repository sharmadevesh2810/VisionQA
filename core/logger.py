"""
VisionQA Logger

A lightweight logger used across the VisionQA framework.

Features:
- Consistent console output
- Log levels
- Section headers
- Key-value formatting

Future enhancements:
- Colored output
- File logging
- Debug mode
- Timestamps
- CI/CD integration
"""

from datetime import datetime

from core.constants import (
    ERROR,
    INFO,
    LINE_SEPARATOR,
    SUCCESS,
    WARNING,
)


class Logger:
    """Simple console logger."""

    @staticmethod
    def section(title: str) -> None:
        """Print a section header."""

        print()
        print(LINE_SEPARATOR)
        print(title)
        print(LINE_SEPARATOR)

    @staticmethod
    def info(message: str) -> None:
        """Print an info message."""

        Logger._log(INFO, message)

    @staticmethod
    def success(message: str) -> None:
        """Print a success message."""

        Logger._log(SUCCESS, message)

    @staticmethod
    def warning(message: str) -> None:
        """Print a warning message."""

        Logger._log(WARNING, message)

    @staticmethod
    def error(message: str) -> None:
        """Print an error message."""

        Logger._log(ERROR, message)

    @staticmethod
    def kv(key: str, value) -> None:
        """Print a formatted key-value pair."""

        print(f"{key:<20}: {value}")

    @staticmethod
    def blank() -> None:
        """Print a blank line."""

        print()

    @staticmethod
    def _log(level: str, message: str) -> None:
        """
        Internal log formatter.

        Example:
        [INFO] Browser launched
        """

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")