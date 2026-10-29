"""
Navigator

Responsible for navigating to application pages.

Supports:
- Internal Angular navigation
- Popup navigation

Returns a standardized navigation result dictionary.
"""

from __future__ import annotations

import time

from playwright.sync_api import Page, TimeoutError

from core.logger import Logger
from core.utils import (
    get_page_metadata,
    wait_for_internal_navigation,
    wait_for_popup,
)


class Navigator:
    """Handles popup and internal application navigation."""

    POPUP_TIMEOUT = 3000

    def __init__(self, page: Page):
        self.page = page

    def navigate(self, locator) -> dict:
        previous_url = self.page.url
        start = time.perf_counter()

        # First try popup navigation. Do not treat a popup timeout as a click
        # failure; it usually means this control navigates in the same page.
        try:
            with self.page.expect_popup(timeout=self.POPUP_TIMEOUT) as popup_info:
                locator.click(timeout=10000)
            popup = popup_info.value
            wait_for_popup(popup)
            metadata = get_page_metadata(popup)
            return self._result(
                status="SUCCESS",
                navigation_type="POPUP",
                page=popup,
                url=metadata["url"],
                title=metadata["title"],
                load_time=round(time.perf_counter() - start, 2),
                error=None,
            )

        except TimeoutError:
            Logger.info("Popup not detected. Trying internal navigation...")

        except Exception as exc:
            # A click may itself time out or fail. Do not silently retry it as
            # an internal navigation, which could cause a duplicate action.
            return self._result(
                status="FAILED",
                navigation_type="POPUP",
                page=None,
                url=None,
                title=None,
                load_time=round(time.perf_counter() - start, 2),
                error=str(exc),
            )

        # If the popup did not open, the first click may still have navigated
        # internally. Check before clicking again to avoid double-clicking.
        if self.page.url != previous_url:
            navigated = True
        else:
            try:
                navigated = wait_for_internal_navigation(
                    self.page,
                    previous_url,
                    timeout=15000,
                )
            except Exception as exc:
                Logger.warning(f"Internal navigation wait failed: {exc}")
                navigated = self.page.url != previous_url

        # The original click might have caused a client-side route change
        # shortly after the popup timeout. Only click again if URL is still
        # unchanged, and then wait once more.
        if not navigated and self.page.url == previous_url:
            try:
                locator.click(timeout=10000)
                navigated = wait_for_internal_navigation(
                    self.page,
                    previous_url,
                    timeout=15000,
                )
            except Exception as exc:
                Logger.warning(f"Internal navigation retry failed: {exc}")
                navigated = self.page.url != previous_url

        metadata = get_page_metadata(self.page)
        load_time = round(time.perf_counter() - start, 2)

        if navigated:
            Logger.info("Internal navigation successful.")
            return self._result(
                status="SUCCESS",
                navigation_type="INTERNAL",
                page=self.page,
                url=metadata["url"],
                title=metadata["title"],
                load_time=load_time,
                error=None,
            )

        Logger.warning(
            f"No navigation detected after bounded wait. "
            f"URL remains: {metadata['url']}"
        )
        return self._result(
            status="NO_NAVIGATION",
            navigation_type="INTERNAL",
            page=self.page,
            url=metadata["url"],
            title=metadata["title"],
            load_time=load_time,
            error="URL did not change within the navigation timeout.",
        )

    @staticmethod
    def _result(
        status: str,
        navigation_type: str,
        page: Page | None,
        url: str | None,
        title: str | None,
        load_time: float | None,
        error: str | None,
    ) -> dict:
        return {
            "status": status,
            "type": navigation_type,
            "page": page,
            "url": url,
            "title": title,
            "load_time": load_time,
            "error": error,
        }
