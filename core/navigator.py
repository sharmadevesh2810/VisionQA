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

from playwright.sync_api import (
    Page,
    TimeoutError,
)

from core.logger import Logger
from core.utils import (
    get_page_metadata,
    wait_for_internal_navigation,
    wait_for_popup,
)


class Navigator:
    """
    Handles application navigation.

    Supports:
    - Internal page navigation
    - Popup navigation
    """

    POPUP_TIMEOUT = 3000

    def __init__(self, page: Page):
        self.page = page

    def navigate(self, locator) -> dict:
        """
        Navigate using the supplied locator.

        Returns
        -------
        dict

        {
            "status": str,
            "type": str,
            "page": Page,
            "url": str,
            "title": str,
            "load_time": float,
            "error": str | None
        }
        """

        previous_url = self.page.url
        start = time.perf_counter()

        #
        # ------------------------------------------------------------------
        # Try Popup Navigation
        # ------------------------------------------------------------------
        #

        try:

            with self.page.expect_popup(
                timeout=self.POPUP_TIMEOUT
            ) as popup_info:

                locator.click()

            popup = popup_info.value

            wait_for_popup(popup)

            metadata = get_page_metadata(popup)

            load_time = round(
                time.perf_counter() - start,
                2,
            )

            Logger.info("Popup navigation detected.")

            return self._result(
                status="SUCCESS",
                navigation_type="POPUP",
                page=popup,
                url=metadata["url"],
                title=metadata["title"],
                load_time=load_time,
                error=None,
            )

        except TimeoutError:

            Logger.info(
                "Popup not detected. Trying internal navigation..."
            )

        except Exception as exc:

            return self._result(
                status="FAILED",
                navigation_type="POPUP",
                page=None,
                url=None,
                title=None,
                load_time=None,
                error=str(exc),
            )

        #
        # ------------------------------------------------------------------
        # Internal Navigation
        # ------------------------------------------------------------------
        #

        try:

            locator.click()

            navigated = wait_for_internal_navigation(
                self.page,
                previous_url,
            )

            metadata = get_page_metadata(self.page)

            load_time = round(
                time.perf_counter() - start,
                2,
            )

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

            Logger.warning("No navigation detected.")

            return self._result(
                status="NO_NAVIGATION",
                navigation_type="INTERNAL",
                page=self.page,
                url=metadata["url"],
                title=metadata["title"],
                load_time=None,
                error="URL did not change.",
            )

        except Exception as exc:

            Logger.error(str(exc))

            return self._result(
                status="FAILED",
                navigation_type="INTERNAL",
                page=self.page,
                url=None,
                title=None,
                load_time=None,
                error=str(exc),
            )

    # ----------------------------------------------------------------------
    # Helper
    # ----------------------------------------------------------------------

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
        """
        Build a standardized navigation result.
        """

        return {
            "status": status,
            "type": navigation_type,
            "page": page,
            "url": url,
            "title": title,
            "load_time": load_time,
            "error": error,
        }