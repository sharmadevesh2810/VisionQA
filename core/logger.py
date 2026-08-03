"""
VisionQA Logger

A lightweight logger used across the VisionQA framework.

Features:
- Consistent console output
- Log levels
- Section headers
- Key-value formatting
- File logging

Future enhancements:
- Colored output
- Debug mode
- CI/CD integration
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TextIO

from core.constants import (
    ERROR,
    INFO,
    LINE_SEPARATOR,
    SUCCESS,
    WARNING,
)


class Logger:
    """VisionQA Logger."""

    _log_file: TextIO | None = None

    # ---------------------------------------------------------------------
    # File Logging
    # ---------------------------------------------------------------------

    @classmethod
    def initialize(
        cls,
        log_path: Path,
    ) -> None:
        """
        Initialize file logging.

        Parameters
        ----------
        log_path
            Path of run.log
        """

        cls._log_file = open(
            log_path,
            "w",
            encoding="utf-8",
        )

    @classmethod
    def close(cls) -> None:
        """Close the log file."""

        if cls._log_file:

            cls._log_file.close()
            cls._log_file = None

    # ---------------------------------------------------------------------
    # Public Logging
    # ---------------------------------------------------------------------

    @staticmethod
    def section(title: str) -> None:

        Logger._write("")
        Logger._write(LINE_SEPARATOR)
        Logger._write(title)
        Logger._write(LINE_SEPARATOR)

    @staticmethod
    def info(message: str) -> None:

        Logger._log(INFO, message)

    @staticmethod
    def success(message: str) -> None:

        Logger._log(SUCCESS, message)

    @staticmethod
    def warning(message: str) -> None:

        Logger._log(WARNING, message)

    @staticmethod
    def error(message: str) -> None:

        Logger._log(ERROR, message)

    @staticmethod
    def kv(
        key: str,
        value,
    ) -> None:

        Logger._write(
            f"{key:<20}: {value}"
        )

    @staticmethod
    def blank() -> None:

        Logger._write("")

    # ---------------------------------------------------------------------
    # Internal Helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _log(
        level: str,
        message: str,
    ) -> None:

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        Logger._write(
            f"[{timestamp}] [{level}] {message}"
        )

    @staticmethod
    def _write(
        message: str,
    ) -> None:
        """
        Write to console and run.log.
        """

        print(message)

        if Logger._log_file:

            Logger._log_file.write(
                message + "\n"
            )

            Logger._log_file.flush()