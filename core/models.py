"""
VisionQA Data Models

This module contains the data models shared across the VisionQA framework.

The purpose of these models is to avoid passing dictionaries throughout the
framework and provide strongly-typed objects between components.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page


# ==============================================================================
# Snapshot Metadata
# ==============================================================================

@dataclass(slots=True)
class SnapshotMetadata:
    """
    Represents the metadata associated with a snapshot.
    """

    environment: str
    version: str
    tenant: str
    url: str
    captured_at: str
    visionqa_version: str


# ==============================================================================
# Snapshot Context
# ==============================================================================

@dataclass(slots=True)
class SnapshotContext:
    """
    Shared information required while generating a snapshot.

    This object is created once and shared between the crawler,
    screenshot engine, metadata manager, etc.
    """

    environment: str
    version: str
    tenant: str
    snapshot_dir: Path


# ==============================================================================
# Navigation Result
# ==============================================================================

@dataclass(slots=True)
class NavigationResult:
    """
    Represents the outcome of navigating to a page.
    """

    menu: str
    submenu: str

    status: str
    navigation_type: str

    url: str
    title: str

    load_time: Optional[float]

    error: Optional[str]

    page: Optional[Page]


# ==============================================================================
# Crawl Result
# ==============================================================================

@dataclass(slots=True)
class CrawlResult:
    """
    Represents the result of an entire crawl.
    """

    total_pages: int
    successful_pages: int
    failed_pages: int

    navigation_results: list[NavigationResult]


# ==============================================================================
# Screenshot Result
# ==============================================================================

@dataclass(slots=True)
class ScreenshotResult:
    """
    Represents a captured screenshot.
    """

    menu: str
    submenu: str

    screenshot_path: Path

    success: bool

    error: Optional[str] = None