"""
Navigation Manifest

Responsible for writing the discovered application navigation
to a JSON manifest.

The manifest acts as the table of contents for a snapshot and
is later used by the comparison engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.constants import (
    DEFAULT_ENCODING,
    NAVIGATION_FILE,
)
from core.logger import Logger


class NavigationManifest:
    """
    Writes the discovered navigation to navigation.json.
    """

    def __init__(self, snapshot_dir: Path):
        self.snapshot_dir = snapshot_dir

    @property
    def manifest_path(self) -> Path:
        return self.snapshot_dir / NAVIGATION_FILE

    def write(self, pages: list[dict[str, Any]]) -> Path:
        """
        Write navigation manifest.

        Parameters
        ----------
        pages
            List of discovered pages from the crawler.

        Returns
        -------
        Path
            Path to navigation.json
        """

        self.snapshot_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest = {
            "total_pages": len(pages),
            "pages": pages,
        }

        with open(
            self.manifest_path,
            "w",
            encoding=DEFAULT_ENCODING,
        ) as fp:
            json.dump(
                manifest,
                fp,
                indent=4,
                ensure_ascii=False,
            )

        Logger.section("Navigation Manifest")
        Logger.kv("Pages", len(pages))
        Logger.kv("Manifest", self.manifest_path)
        Logger.success("navigation.json created successfully.")

        return self.manifest_path