"""
Screenshot Engine

Responsible for capturing screenshots of application pages.

Responsibilities:
- Wait until the page is stable
- Create snapshot directories
- Capture screenshots
- Sanitize filenames
"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Page

from core.constants import (
    SCREENSHOT_EXTENSION,
    SNAPSHOTS_DIR,
)
from core.logger import Logger


class ScreenshotEngine:
    """
    Screenshot Engine.

    Captures screenshots and stores them using the following structure:

    snapshots/
        <environment>/
            <version>/
                <menu>/
                    <submenu>.png
    """

    def __init__(
        self,
        environment: str,
        version: str,
        stabilization_time: int = 3000,
        full_page: bool = True,
    ):

        self.environment = self._sanitize(environment)
        self.version = self._sanitize(version)

        self.stabilization_time = stabilization_time
        self.full_page = full_page

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def capture(
        self,
        page: Page,
        menu: str,
        submenu: str,
    ) -> Path:
        """
        Capture a screenshot.

        Parameters
        ----------
        page
            Playwright page.

        menu
            Parent menu name.

        submenu
            Submenu name.

        Returns
        -------
        Path
            Path of the saved screenshot.
        """

        self._wait_until_stable(page)

        directory = self._prepare_directory(menu)

        filename = (
            self._sanitize(submenu)
            + SCREENSHOT_EXTENSION
        )

        screenshot_path = directory / filename

        page.screenshot(
            path=str(screenshot_path),
            full_page=self.full_page,
        )

        Logger.success(f"Screenshot saved -> {screenshot_path}")

        return screenshot_path

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _prepare_directory(
        self,
        menu: str,
    ) -> Path:

        directory = (
            SNAPSHOTS_DIR
            / self.environment
            / self.version
            / self._sanitize(menu)
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        return directory

    def _wait_until_stable(
        self,
        page: Page,
    ) -> None:
        """
        Wait until the page is stable before taking a screenshot.
        """

        try:
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=15000,
            )
        except Exception:
            pass

        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=15000,
            )
        except Exception:
            pass

        try:
            page.locator("body").wait_for(
                state="visible",
                timeout=10000,
            )
        except Exception:
            pass

        page.wait_for_timeout(
            self.stabilization_time
        )

    @staticmethod
    def _sanitize(name: str) -> str:
        """
        Make a string safe for use as a filename.
        """

        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        name = re.sub(r"\s+", " ", name)

        return name.strip()