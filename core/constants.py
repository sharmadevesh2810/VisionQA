"""
VisionQA Framework Constants

This module contains immutable constants shared across the framework.

Only values that should never change at runtime belong here.
Configurable values (timeouts, delays, headless mode, etc.) belong in
config/settings.py.
"""

from pathlib import Path

# ==============================================================================
# Framework Information
# ==============================================================================

VISIONQA_NAME = "VisionQA"
VISIONQA_VERSION = "1.0.0"

# ==============================================================================
# Directory Structure
# ==============================================================================

SNAPSHOTS_DIR = Path("snapshots")
REPORTS_DIR = Path("reports")
TEMPLATES_DIR = Path("templates")
LOGS_DIR = Path("logs")

# ==============================================================================
# Standard Files
# ==============================================================================

METADATA_FILE = "metadata.json"
NAVIGATION_FILE = "navigation.json"
COMPARISON_FILE = "comparison.json"
REPORT_FILE = "report.html"
LOG_FILE = "visionqa.log"

# ==============================================================================
# Screenshot
# ==============================================================================

SCREENSHOT_EXTENSION = ".png"

# ==============================================================================
# Encoding
# ==============================================================================

DEFAULT_ENCODING = "utf-8"

# ==============================================================================
# Console Formatting
# ==============================================================================

LINE_WIDTH = 80
LINE_SEPARATOR = "=" * LINE_WIDTH

# ==============================================================================
# Generic Values
# ==============================================================================

UNKNOWN = "unknown"
SUCCESS = "SUCCESS"
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"