"""
Crawler

Responsible for:

- Iterating through the discovered navigation tree
- Navigating to every page
- Capturing screenshots
- Returning crawl results
"""

from __future__ import annotations

from playwright.sync_api import Page

from core.logger import Logger
from core.navigator import Navigator
from core.screenshot import ScreenshotEngine

MENU_EXPAND_WAIT = 800


class Crawler:
    """
    Crawls the complete application navigation.
    """

    def __init__(
        self,
        page: Page,
        environment: str,
        version: str,
    ):

        self.page = page

        self.navigator = Navigator(page)

        self.screenshot_engine = ScreenshotEngine(
            environment=environment,
            version=version,
        )

    def crawl(self, navigation_tree: list[dict]) -> list[dict]:
        """
        Crawl every menu and submenu.

        Parameters
        ----------
        navigation_tree
            Navigation discovered by Navigation.discover()

        Returns
        -------
        list
            Crawl results.
        """

        Logger.section("Crawler")

        results = []

        for menu_data in navigation_tree:

            menu_name = menu_data["name"]

            Logger.info(f"Menu : {menu_name}")

            #
            # Expand menu
            #

            try:

                menu_data["locator"].click()

                self.page.wait_for_timeout(
                    MENU_EXPAND_WAIT
                )

            except Exception as exc:

                Logger.error(
                    f"Unable to expand '{menu_name}'"
                )

                Logger.error(str(exc))

                continue

            #
            # Skip empty menu
            #

            if not menu_data["submenus"]:

                Logger.warning(
                    f"No submenus found under '{menu_name}'"
                )

                continue

            #
            # Crawl every submenu
            #

            for submenu_data in menu_data["submenus"]:

                submenu_name = submenu_data["name"]

                Logger.info(
                    f"  → {submenu_name}"
                )

                result = self.navigator.navigate(
                    submenu_data["locator"]
                )

                #
                # Capture screenshot only if navigation succeeded
                #

                if result["status"] == "SUCCESS":

                    target_page = (
                        result["page"]
                        if result["page"] is not None
                        else self.page
                    )

                    screenshot_path = self.screenshot_engine.capture(
                        page=target_page,
                        menu=menu_name,
                        submenu=submenu_name,
                    )

                    Logger.kv(
                        "Screenshot",
                        screenshot_path,
                    )

                else:

                    screenshot_path = None

                #
                # Store result
                #

                results.append(

                    {
                        "menu": menu_name,
                        "submenu": submenu_name,
                        "status": result["status"],
                        "navigation_type": result["type"],
                        "url": result["url"],
                        "title": result["title"],
                        "load_time": result["load_time"],
                        "error": result["error"],
                        "screenshot": (
                            str(screenshot_path)
                            if screenshot_path
                            else None
                        ),
                    }

                )

                #
                # Console output
                #

                if result["status"] == "SUCCESS":

                    Logger.success(

                        f"{result['type']} "

                        f"({result['load_time']} sec)"

                    )

                elif result["status"] == "NO_NAVIGATION":

                    Logger.warning(
                        "No navigation detected."
                    )

                else:

                    Logger.error(
                        "Navigation failed."
                    )

                    if result["error"]:

                        Logger.error(
                            result["error"]
                        )

                #
                # Close popup page
                #

                if result["type"] == "POPUP":

                    try:

                        result["page"].close()

                    except Exception:

                        pass

        Logger.section("Crawler Summary")

        Logger.kv(
            "Pages Crawled",
            len(results),
        )

        success = len(
            [
                r
                for r in results
                if r["status"] == "SUCCESS"
            ]
        )

        Logger.kv(
            "Successful",
            success,
        )

        Logger.kv(
            "Failed",
            len(results) - success,
        )

        return results