"""
Crawler

Responsible for:

- Iterating through the discovered navigation tree
- Navigating to every page
- Capturing screenshots
- Returning crawl results
"""

from __future__ import annotations

import time

from comparison.vod_ui_detector import VODUIDetector
from comparison.channel_ui_detector import ChannelUIDetector
from comparison.epg_ui_detector import EPGUIDetector
from comparison.entitlement_control_ui_detector import EntitlementControlUIDetector
from comparison.global_configuration_ui_detector import GlobalConfigurationUIDetector
from comparison.bouquet_management_ui_detector import BouquetManagementUIDetector
from comparison.channel_logo_ui_detector import ChannelLogoUIDetector
from comparison.channel_poster_ui_detector import ChannelPosterUIDetector
from comparison.guide_metadata_ui_detector import GuideMetadataUIDetector

from comparison.component_detector import ComponentDetector

from pathlib import Path

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
        snapshot_dir: Path,
    ):

        self.page = page

        self.navigator = Navigator(page)

        self.screenshot_engine = ScreenshotEngine(
            snapshot_dir=snapshot_dir,
        )
        self.component_detector = ComponentDetector()
        self.vod_ui_detector = VODUIDetector()
        self.channel_ui_detector = ChannelUIDetector()
        self.epg_ui_detector = EPGUIDetector()
        self.entitlement_control_ui_detector = EntitlementControlUIDetector()
        self.global_configuration_ui_detector = GlobalConfigurationUIDetector()
        self.bouquet_management_ui_detector = BouquetManagementUIDetector()
        self.channel_logo_ui_detector = ChannelLogoUIDetector()
        self.channel_poster_ui_detector = ChannelPosterUIDetector()
        self.guide_metadata_ui_detector = GuideMetadataUIDetector()

    def _close_vod_details_drawer(self) -> None:
        """Close the Angular Material VOD Details side drawer if it is open."""
        try:
            drawer = self.page.locator(
                "mat-sidenav.vod-detail-wrapper.mat-drawer-opened"
            )

            if not drawer.is_visible(timeout=1000):
                return

            Logger.info("Closing VOD Details side drawer before continuing.")

            # Angular Material drawers normally close on Escape.
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(500)

            if drawer.is_visible(timeout=1000):
                # Fallback: click the Material drawer backdrop.
                backdrop = self.page.locator(".mat-drawer-backdrop")
                if backdrop.is_visible(timeout=1000):
                    backdrop.click(position={"x": 5, "y": 5})
                    self.page.wait_for_timeout(500)

            if drawer.is_visible(timeout=1000):
                Logger.warning(
                    "VOD Details side drawer is still open after close attempt."
                )
            else:
                Logger.success("VOD Details side drawer closed.")

        except Exception as exc:
            # Do not fail the crawl if no drawer exists or the drawer has
            # already disappeared during navigation.
            Logger.debug(
                f"VOD Details drawer close check skipped: {exc}"
            )

    def crawl_vod_category(
        self,
        menu_name: str,
        category: str,
    ) -> list[dict]:
        """
        Deep-crawl one VOD category.

        Flow:
            VOD tab/category
              -> first content row
              -> View CTA
              -> Details
              -> complete Details screenshots
              -> static UI structure

        Content values are intentionally ignored by VODUIDetector.
        """

        results = []

        Logger.section(f"VOD → {category}")

        # A previous VOD View action opens Details in an Angular Material
        # side drawer. Close it before interacting with the next VOD tab.
        self._close_vod_details_drawer()

        # ----------------------------------------------------------
        # Wait for VOD listing
        # ----------------------------------------------------------

        try:
            self.page.wait_for_selector(
                "table",
                state="visible",
                timeout=30000,
            )
        except Exception as exc:
            Logger.error(f"VOD listing table did not load for {category}.")
            Logger.error(str(exc))
            return results

        # ----------------------------------------------------------
        # Open VOD category tab
        # ----------------------------------------------------------

        try:
            category_tab = (
                self.page
                .get_by_text(
                    category,
                    exact=True,
                )
                .first
            )

            category_tab.wait_for(
                state="visible",
                timeout=15000,
            )

            category_tab.click()
            self.page.wait_for_timeout(1500)

            Logger.success(f"{category} tab opened.")

        except Exception as exc:
            Logger.error(
                f"Unable to open VOD → {category}."
            )
            Logger.error(str(exc))
            return results

        # ----------------------------------------------------------
        # Wait for category table
        # ----------------------------------------------------------

        try:
            self.page.wait_for_selector(
                "table tbody tr",
                state="visible",
                timeout=30000,
            )
        except Exception as exc:
            Logger.error(
                f"{category} content table did not load."
            )
            Logger.error(str(exc))
            return results

        # ----------------------------------------------------------
        # Get first content row
        # ----------------------------------------------------------

        try:
            first_row = (
                self.page
                .locator("table tbody tr")
                .first
            )

            first_row.wait_for(
                state="visible",
                timeout=15000,
            )

            Logger.success(
                f"First {category} content found."
            )

        except Exception as exc:
            Logger.error(
                f"No {category} content row found."
            )
            Logger.error(str(exc))
            return results

        # ----------------------------------------------------------
        # Capture category listing
        # ----------------------------------------------------------

        listing_start = time.perf_counter()

        try:
            listing_screenshot = (
                self.screenshot_engine.capture(
                    page=self.page,
                    menu=menu_name,
                    submenu=f"VOD - {category}",
                )
            )

            listing_components = (
                self.component_detector.detect(
                    self.page
                )
            )

            listing_load_time = (
                time.perf_counter()
                - listing_start
            )

            results.append(
                {
                    "menu": menu_name,
                    "submenu": f"VOD - {category}",
                    "status": "SUCCESS",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": self.page.title(),
                    "load_time": listing_load_time,
                    "error": None,
                    "screenshot": str(listing_screenshot),
                    "screenshots": [
                        str(listing_screenshot)
                    ],
                    "components": listing_components,
                    "type": "VOD_LISTING",
                    "category": category,
                }
            )

        except Exception as exc:
            Logger.error(
                f"Unable to capture {category} listing."
            )
            Logger.error(str(exc))

        # ----------------------------------------------------------
        # Find View CTA
        # ----------------------------------------------------------

        try:
            Logger.info(
                f"Searching for View CTA in first {category} row..."
            )

            view_button = (
                first_row
                .locator("#viewIcon")
                .first
            )

            Logger.info(
                f"View CTA candidates found: "
                f"{view_button.count()}"
            )

            view_button.wait_for(
                state="visible",
                timeout=15000,
            )

            view_button.scroll_into_view_if_needed()
            view_button.click()

            Logger.success(
                f"Clicked View CTA for first {category} content."
            )

        except Exception as exc:
            Logger.error(
                f"Unable to open {category} Details via View CTA."
            )
            Logger.error(str(exc))
            return results

        # ----------------------------------------------------------
        # Wait for Details page
        # ----------------------------------------------------------

        try:
            self.page.wait_for_timeout(1000)

            self.page.wait_for_load_state(
                "domcontentloaded",
                timeout=30000,
            )

            # Details-only section. This prevents the listing DOM from
            # being inspected immediately after the View click.
            self.page.get_by_text(
                "Basic Metadata",
                exact=True,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            self.page.wait_for_timeout(1500)

        except Exception as exc:
            Logger.warning(
                f"{category} Details stabilization wait completed with warning."
            )
            Logger.warning(str(exc))

        # ----------------------------------------------------------
        # Capture COMPLETE Details page
        # ----------------------------------------------------------

        details_start = time.perf_counter()

        try:
            Logger.info(
                f"Capturing complete {category} Details page..."
            )

            details_screenshots = (
                self.screenshot_engine.capture_details(
                    page=self.page,
                    menu=menu_name,
                    submenu=f"VOD - {category} - Details",
                )
            )

            # Retain generic components for backward compatibility.
            # VOD comparison uses ui_structure below.
            details_components = (
                self.component_detector.detect(
                    self.page
                )
            )

            # Extract ONLY static UI/form structure.
            details_ui = (
                self.vod_ui_detector
                .detect_details(self.page)
            )

            Logger.info(
                f"========== {category.upper()} DETAILS STATIC UI =========="
            )

            for section, items in details_ui.items():
                Logger.info(
                    f"{section}: "
                    f"{len(items) if isinstance(items, list) else 0}"
                )

                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            label = (
                                item.get("text")
                                or item.get("placeholder")
                                or item.get("ariaLabel")
                                or item.get("name")
                                or item.get("role")
                                or ""
                            )
                            Logger.info(
                                f"  [{item.get('type', section)}] {label}"
                            )
                        else:
                            Logger.info(
                                f"  [{section}] {item}"
                            )

            Logger.info(
                f"========== END {category.upper()} DETAILS STATIC UI =========="
            )

            details_load_time = (
                time.perf_counter()
                - details_start
            )

            results.append(
                {
                    "menu": menu_name,
                    "submenu": f"VOD - {category} - Details",
                    "status": "SUCCESS",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": self.page.title(),
                    "load_time": details_load_time,
                    "error": None,
                    "type": "VOD_DETAILS",
                    "category": category,
                    "screenshots": [
                        str(path)
                        for path in details_screenshots
                    ],
                    "screenshot": (
                        str(details_screenshots[0])
                        if details_screenshots
                        else None
                    ),
                    "components": details_components,
                    "ui_structure": details_ui,
                }
            )

            Logger.success(
                f"{category} Details captured in "
                f"{len(details_screenshots)} screenshot(s)."
            )

        except Exception as exc:
            Logger.error(
                f"Unable to capture {category} Details."
            )
            Logger.error(str(exc))

            results.append(
                {
                    "menu": menu_name,
                    "submenu": f"VOD - {category} - Details",
                    "status": "FAIL",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": "",
                    "load_time": (
                        time.perf_counter()
                        - details_start
                    ),
                    "error": str(exc),
                    "type": "VOD_DETAILS",
                    "category": category,
                    "screenshots": [],
                    "screenshot": None,
                    "components": [],
                    "ui_structure": {},
                }
            )

        return results

    def _return_to_channel_landing(self) -> bool:
        """Return to the Channel landing page through the left navigation menu."""
        try:
            Logger.info("Returning to Channel landing page using the left menu...")

            # Channel Details is a dedicated route.  Do not use browser
            # reload/history or the Details back arrow here.  The required
            # application flow is to click Channel in the left navigation.
            channel_menu = self.page.get_by_text(
                "Channel",
                exact=True,
            ).first

            channel_menu.wait_for(state="visible", timeout=15000)
            channel_menu.scroll_into_view_if_needed()
            channel_menu.click()

            Logger.info("Channel left-menu CTA clicked.")

            self.page.wait_for_url(
                "**/content_management/channel",
                timeout=30000,
            )

            self.page.get_by_text(
                "Pay TV Channel",
                exact=False,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            self.page.locator(
                ".generic-child-tab"
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            self.page.wait_for_timeout(1000)
            Logger.success("Returned to Channel landing page.")
            return True

        except Exception as exc:
            Logger.error("Unable to return to Channel landing page using left menu.")
            Logger.error(str(exc))
            return False

    def crawl_channel(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """
        Deep-crawl all Channel tabs.

        Current Channel page contains three tabs:
            - Commercial TV
            - Commercial Radio
            - App Launch Point

        For every tab:
            tab -> first row -> View CTA (#viewIcon) -> Details capture

        Dynamic channel values are not used for comparison at this stage.
        """
        results = []
        Logger.section("Content Management -> Channel")

        # ----------------------------------------------------------
        # Discover all Channel tabs from the actual UI
        # ----------------------------------------------------------
        try:
            self.page.wait_for_timeout(1000)
            channel_tabs = self.page.locator(".generic-child-tab")
            tab_count = channel_tabs.count()

            discovered_tabs = []
            for index in range(tab_count):
                try:
                    tab_name = channel_tabs.nth(index).inner_text().strip()
                except Exception:
                    continue

                if tab_name and tab_name not in discovered_tabs:
                    discovered_tabs.append(tab_name)

            Logger.info(
                "Discovered Channel tabs: " + ", ".join(discovered_tabs)
            )

        except Exception as exc:
            Logger.error("Unable to discover Channel tabs.")
            Logger.error(str(exc))
            return results

        if not discovered_tabs:
            Logger.error("No Channel tabs were discovered.")
            return results

        # ----------------------------------------------------------
        # Crawl every Channel tab
        # ----------------------------------------------------------
        for tab_name in discovered_tabs:
            Logger.section(f"Channel -> {tab_name}")

            self.page.wait_for_timeout(500)

            # ------------------------------------------------------
            # Open tab
            # ------------------------------------------------------
            try:
                # Do not use get_by_text() here. After an Angular Material
                # details drawer is closed, the Channel tab DOM can be
                # recreated and the text locator may point at a stale/hidden
                # element. Re-query the actual Channel tab containers.
                channel_tabs = self.page.locator(".generic-child-tab")

                # capture_details() can leave the application's internal
                # scroll container at the bottom of the page.  In that state
                # the tab exists in the DOM but is temporarily outside the
                # viewport, so waiting for state="visible" before scrolling
                # causes a timeout. Re-query the tab, scroll it into view,
                # then click it.
                tab_index = discovered_tabs.index(tab_name)
                channel_tab = channel_tabs.nth(tab_index)

                channel_tab.wait_for(state="attached", timeout=15000)
                channel_tab.scroll_into_view_if_needed()
                channel_tab.wait_for(state="visible", timeout=15000)
                channel_tab.click()
                self.page.wait_for_timeout(1200)
                Logger.success(f"{tab_name} tab opened.")
            except Exception as exc:
                Logger.error(f"Unable to open Channel -> {tab_name}.")
                Logger.error(str(exc))
                continue

            # ------------------------------------------------------
            # Wait for listing row
            # ------------------------------------------------------
            try:
                self.page.wait_for_selector(
                    "table tbody tr",
                    state="visible",
                    timeout=30000,
                )
                first_row = self.page.locator("table tbody tr").first
                first_row.wait_for(state="visible", timeout=15000)
                Logger.success(f"First {tab_name} content found.")
            except Exception as exc:
                Logger.warning(
                    f"No listing data available for Channel -> {tab_name}."
                )
                Logger.warning(str(exc))

                # Still capture the page because the static UI can be
                # validated even when the backend has no rows.
                try:
                    listing_screenshot = self.screenshot_engine.capture(
                        page=self.page,
                        menu=menu_name,
                        submenu=f"Channel - {tab_name}",
                    )
                    listing_components = self.component_detector.detect(self.page)
                    listing_ui_structure = self.channel_ui_detector.detect_listing(self.page)
                    results.append({
                        "menu": menu_name,
                        "submenu": f"Channel - {tab_name}",
                        "status": "SUCCESS",
                        "navigation_type": "INTERNAL",
                        "url": self.page.url,
                        "title": self.page.title(),
                        "load_time": 0,
                        "error": None,
                        "screenshot": str(listing_screenshot),
                        "screenshots": [str(listing_screenshot)],
                        "components": listing_components,
                        "ui_structure": listing_ui_structure,
                        "type": "CHANNEL_LISTING",
                        "category": tab_name,
                    })
                    Logger.success(f"{tab_name} listing captured (no rows).")
                except Exception as capture_exc:
                    Logger.error(f"Unable to capture {tab_name} listing.")
                    Logger.error(str(capture_exc))
                continue

            # ------------------------------------------------------
            # Capture listing
            # ------------------------------------------------------
            listing_start = time.perf_counter()
            try:
                listing_screenshot = self.screenshot_engine.capture(
                    page=self.page,
                    menu=menu_name,
                    submenu=f"Channel - {tab_name}",
                )
                listing_components = self.component_detector.detect(self.page)
                listing_ui_structure = self.channel_ui_detector.detect_listing(self.page)

                results.append({
                    "menu": menu_name,
                    "submenu": f"Channel - {tab_name}",
                    "status": "SUCCESS",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": self.page.title(),
                    "load_time": time.perf_counter() - listing_start,
                    "error": None,
                    "screenshot": str(listing_screenshot),
                    "screenshots": [str(listing_screenshot)],
                    "components": listing_components,
                    "ui_structure": listing_ui_structure,
                    "type": "CHANNEL_LISTING",
                    "category": tab_name,
                })
                Logger.success(f"{tab_name} listing captured.")
            except Exception as exc:
                Logger.error(f"Unable to capture {tab_name} listing.")
                Logger.error(str(exc))

            # ------------------------------------------------------
            # Find View CTA in first row
            # ------------------------------------------------------
            try:
                Logger.info(
                    f"Searching for View CTA in first {tab_name} row..."
                )
                view_button = first_row.locator("#viewIcon").first
                Logger.info(
                    f"View CTA candidates found: {view_button.count()}"
                )
                view_button.wait_for(state="visible", timeout=15000)
                view_button.scroll_into_view_if_needed()
                view_button.click()
                Logger.success(
                    f"Clicked View CTA for first {tab_name} content."
                )
            except Exception as exc:
                Logger.error(
                    f"Unable to open {tab_name} Details via View CTA."
                )
                Logger.error(str(exc))
                continue

            # ------------------------------------------------------
            # Stabilize Details UI
            # ------------------------------------------------------
            try:
                self.page.wait_for_timeout(1500)
                self.page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=30000,
                )
                self.page.wait_for_timeout(1500)
            except Exception as exc:
                Logger.warning(
                    f"{tab_name} Details stabilization wait completed with warning."
                )
                Logger.warning(str(exc))

            # ------------------------------------------------------
            # Capture COMPLETE Details view
            # ------------------------------------------------------
            details_start = time.perf_counter()
            try:
                Logger.info(
                    f"Capturing complete Channel -> {tab_name} Details..."
                )
                details_screenshots = self.screenshot_engine.capture_details(
                    page=self.page,
                    menu=menu_name,
                    submenu=f"Channel - {tab_name} - Details",
                )
                details_components = self.component_detector.detect(self.page)
                details_ui_structure = self.channel_ui_detector.detect_details(self.page)

                results.append({
                    "menu": menu_name,
                    "submenu": f"Channel - {tab_name} - Details",
                    "status": "SUCCESS",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": self.page.title(),
                    "load_time": time.perf_counter() - details_start,
                    "error": None,
                    "type": "CHANNEL_DETAILS",
                    "category": tab_name,
                    "screenshots": [str(path) for path in details_screenshots],
                    "screenshot": (
                        str(details_screenshots[0])
                        if details_screenshots else None
                    ),
                    "components": details_components,
                    "ui_structure": details_ui_structure,
                })

                Logger.success(
                    f"{tab_name} Details captured in "
                    f"{len(details_screenshots)} screenshot(s)."
                )

                # Channel Details is a dedicated route.  Return to the
                # Channel landing page through the LEFT MENU, as the
                # application flow requires.  The next iteration will then
                # explicitly open its required Channel tab.
                if not self._return_to_channel_landing():
                    Logger.error(
                        f"Stopping Channel deep crawl after {tab_name}: "
                        "unable to return to Channel landing page."
                    )
                    break

            except Exception as exc:
                Logger.error(f"Unable to capture {tab_name} Details.")
                Logger.error(str(exc))
                results.append({
                    "menu": menu_name,
                    "submenu": f"Channel - {tab_name} - Details",
                    "status": "FAIL",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": "",
                    "load_time": time.perf_counter() - details_start,
                    "error": str(exc),
                    "type": "CHANNEL_DETAILS",
                    "category": tab_name,
                    "screenshots": [],
                    "screenshot": None,
                    "components": [],
                    "ui_structure": {},
                })

        return results

    def _epg_drawer(self):
        """Return the currently opened Angular Material drawer used by EPG."""
        candidates = self.page.locator(
            "mat-drawer.mat-drawer-opened, mat-sidenav.mat-drawer-opened"
        )
        count = candidates.count()
        if count == 0:
            raise RuntimeError("No open EPG details drawer found.")
        return candidates.nth(count - 1)

    def _close_epg_details_drawer(self) -> None:
        try:
            drawer = self.page.locator(
                "mat-drawer.mat-drawer-opened, mat-sidenav.mat-drawer-opened"
            ).last
            if not drawer.is_visible(timeout=1000):
                return
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(500)
            if drawer.is_visible(timeout=1000):
                backdrop = self.page.locator(".mat-drawer-backdrop")
                if backdrop.is_visible(timeout=1000):
                    backdrop.click(position={"x": 5, "y": 5})
                    self.page.wait_for_timeout(500)
        except Exception as exc:
            Logger.debug(f"EPG drawer close check skipped: {exc}")

    def _capture_epg_drawer(self, drawer, active_tab: str, menu_name: str, base_name: str) -> tuple[list[Path], dict]:
        """Capture the visible EPG drawer; Aggregated Data is captured through its internal scroll."""
        directory = self.screenshot_engine._prepare_directory(menu_name)
        screenshots: list[Path] = []

        # Find the drawer's actual scrollable content area. Prefer the deepest
        # element whose scrollHeight exceeds clientHeight.
        scroll_info = drawer.evaluate("""
        (root) => {
          const nodes = [root, ...root.querySelectorAll('*')];
          const candidates = nodes.filter(el => {
            const s = getComputedStyle(el);
            return (s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                   el.scrollHeight > el.clientHeight + 4;
          });
          const el = candidates.sort((a,b) => b.scrollHeight - a.scrollHeight)[0] || root;
          return {scrollHeight: el.scrollHeight, clientHeight: el.clientHeight};
        }
        """)
        total = int(scroll_info.get("scrollHeight", 0))
        viewport = int(scroll_info.get("clientHeight", 0))
        if active_tab != "Aggregated Data" or total <= viewport + 4:
            path = directory / self.screenshot_engine._sanitize(f"{base_name} - {active_tab}")
            path = path.with_suffix(".png")
            drawer.screenshot(path=str(path))
            screenshots.append(path)
        else:
            part = 1
            y = 0
            step = max(1, viewport - 80)
            while y < total:
                drawer.evaluate("""
                (root, target) => {
                  const nodes = [root, ...root.querySelectorAll('*')];
                  const candidates = nodes.filter(el => {
                    const s = getComputedStyle(el);
                    return (s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                           el.scrollHeight > el.clientHeight + 4;
                  });
                  const el = candidates.sort((a,b) => b.scrollHeight - a.scrollHeight)[0] || root;
                  el.scrollTop = target;
                }
                """, y)
                self.page.wait_for_timeout(250)
                path = directory / self.screenshot_engine._sanitize(f"{base_name} - {active_tab} - Part {part:02d}")
                path = path.with_suffix(".png")
                drawer.screenshot(path=str(path))
                screenshots.append(path)
                if y + viewport >= total:
                    break
                y += step
                part += 1

        structure = self.epg_ui_detector.detect_drawer(drawer, active_tab)
        return screenshots, structure

    def _return_to_entitlement_control_landing(self) -> bool:
        """Return from Offer Details to Entitlement Control via the left menu."""
        try:
            Logger.info("Returning to Entitlement Control using the left menu...")

            menu_item = self.page.get_by_text(
                "Entitlement Control",
                exact=True,
            ).first
            menu_item.scroll_into_view_if_needed()
            menu_item.wait_for(state="visible", timeout=15000)
            menu_item.click()
            self.page.wait_for_timeout(1200)

            self.page.wait_for_selector(
                "table",
                state="visible",
                timeout=30000,
            )
            Logger.success("Returned to Entitlement Control landing page.")
            return True

        except Exception as exc:
            Logger.error(
                "Unable to return to Entitlement Control landing page using left menu."
            )
            Logger.error(str(exc))
            return False

    def crawl_entitlement_control(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """
        Deep-crawl Entitlement Control.

        Current page contains two offer tabs:
            - Subscription
            - PPV

        For every tab:
            tab -> first row -> View CTA -> Offer Details

        Both listing and details capture:
            1. screenshots
            2. static UI structure
        """
        results = []
        Logger.section("Content Management -> Entitlement Control")

        # Discover the actual offer tabs from the UI.
        try:
            self.page.wait_for_timeout(1000)
            tab_locator = self.page.locator(".generic-child-tab")
            tab_count = tab_locator.count()
            discovered_tabs = []

            for index in range(tab_count):
                try:
                    tab_name = tab_locator.nth(index).inner_text().strip()
                except Exception:
                    continue
                if tab_name and tab_name not in discovered_tabs:
                    discovered_tabs.append(tab_name)

            # Fallback for builds where the child-tab class differs.
            if not discovered_tabs:
                for tab_name in ("Subscription", "PPV"):
                    try:
                        if self.page.get_by_text(tab_name, exact=True).first.is_visible(timeout=1000):
                            discovered_tabs.append(tab_name)
                    except Exception:
                        pass

            Logger.info(
                "Discovered Entitlement Control tabs: "
                + ", ".join(discovered_tabs)
            )
        except Exception as exc:
            Logger.error("Unable to discover Entitlement Control tabs.")
            Logger.error(str(exc))
            return results

        if not discovered_tabs:
            Logger.error("No Entitlement Control tabs were discovered.")
            return results

        for tab_name in discovered_tabs:
            Logger.section(f"Entitlement Control -> {tab_name}")

            # ------------------------------------------------------
            # Open tab
            # ------------------------------------------------------
            try:
                tabs = self.page.locator(".generic-child-tab")
                tab_index = discovered_tabs.index(tab_name)
                tab = tabs.nth(tab_index) if tabs.count() > tab_index else self.page.get_by_text(tab_name, exact=True).first
                tab.scroll_into_view_if_needed()
                tab.wait_for(state="visible", timeout=15000)
                tab.click()
                self.page.wait_for_timeout(1200)
                Logger.success(f"{tab_name} tab opened.")
            except Exception as exc:
                Logger.error(f"Unable to open Entitlement Control -> {tab_name}.")
                Logger.error(str(exc))
                continue

            # ------------------------------------------------------
            # Wait for first offer row
            # ------------------------------------------------------
            try:
                self.page.wait_for_selector(
                    "table tbody tr",
                    state="visible",
                    timeout=30000,
                )
                first_row = self.page.locator("table tbody tr").first
                first_row.wait_for(state="visible", timeout=15000)
                Logger.success(f"First {tab_name} offer found.")
            except Exception as exc:
                Logger.warning(
                    f"No listing data available for Entitlement Control -> {tab_name}."
                )
                Logger.warning(str(exc))
                try:
                    listing_screenshot = self.screenshot_engine.capture(
                        page=self.page,
                        menu=menu_name,
                        submenu=f"Entitlement Control - {tab_name}",
                    )
                    listing_components = self.component_detector.detect(self.page)
                    listing_ui = self.entitlement_control_ui_detector.detect_listing(self.page)
                    results.append({
                        "menu": menu_name,
                        "submenu": f"Entitlement Control - {tab_name}",
                        "status": "SUCCESS",
                        "navigation_type": "INTERNAL",
                        "url": self.page.url,
                        "title": self.page.title(),
                        "load_time": 0,
                        "error": None,
                        "screenshot": str(listing_screenshot),
                        "screenshots": [str(listing_screenshot)],
                        "components": listing_components,
                        "ui_structure": listing_ui,
                        "type": "ENTITLEMENT_CONTROL_LISTING",
                        "category": tab_name,
                    })
                    Logger.success(f"{tab_name} listing captured (no rows).")
                except Exception as capture_exc:
                    Logger.error(f"Unable to capture {tab_name} listing.")
                    Logger.error(str(capture_exc))
                continue

            # ------------------------------------------------------
            # Listing screenshot + UI structure
            # ------------------------------------------------------
            try:
                listing_start = time.perf_counter()
                listing_screenshot = self.screenshot_engine.capture(
                    page=self.page,
                    menu=menu_name,
                    submenu=f"Entitlement Control - {tab_name}",
                )
                listing_components = self.component_detector.detect(self.page)
                listing_ui = self.entitlement_control_ui_detector.detect_listing(self.page)

                results.append({
                    "menu": menu_name,
                    "submenu": f"Entitlement Control - {tab_name}",
                    "status": "SUCCESS",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": self.page.title(),
                    "load_time": time.perf_counter() - listing_start,
                    "error": None,
                    "screenshot": str(listing_screenshot),
                    "screenshots": [str(listing_screenshot)],
                    "components": listing_components,
                    "ui_structure": listing_ui,
                    "type": "ENTITLEMENT_CONTROL_LISTING",
                    "category": tab_name,
                })
                Logger.success(f"{tab_name} listing captured.")
            except Exception as exc:
                Logger.error(f"Unable to capture {tab_name} listing.")
                Logger.error(str(exc))

            # ------------------------------------------------------
            # Open first offer Details through View CTA
            # ------------------------------------------------------
            try:
                Logger.info(f"Searching for View CTA in first {tab_name} offer...")
                view_button = first_row.locator("#viewIcon").first
                if view_button.count() == 0:
                    view_button = first_row.locator(
                        "[id*='view' i], [aria-label*='View' i], [title*='View' i]"
                    ).first
                Logger.info(f"View CTA candidates found: {view_button.count()}")
                view_button.wait_for(state="visible", timeout=15000)
                view_button.scroll_into_view_if_needed()
                view_button.click()
                Logger.success(f"Clicked View CTA for first {tab_name} offer.")
                self.page.wait_for_timeout(1500)
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                self.page.wait_for_timeout(1000)
            except Exception as exc:
                Logger.error(f"Unable to open {tab_name} Offer Details via View CTA.")
                Logger.error(str(exc))
                continue

            # ------------------------------------------------------
            # Details screenshot(s) + UI structure
            # ------------------------------------------------------
            details_start = time.perf_counter()
            try:
                Logger.info(f"Capturing complete Entitlement Control -> {tab_name} Details...")
                details_screenshots = self.screenshot_engine.capture_details(
                    page=self.page,
                    menu=menu_name,
                    submenu=f"Entitlement Control - {tab_name} - Details",
                )
                details_components = self.component_detector.detect(self.page)
                details_ui = self.entitlement_control_ui_detector.detect_details(self.page)

                results.append({
                    "menu": menu_name,
                    "submenu": f"Entitlement Control - {tab_name} - Details",
                    "status": "SUCCESS",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": self.page.title(),
                    "load_time": time.perf_counter() - details_start,
                    "error": None,
                    "type": "ENTITLEMENT_CONTROL_DETAILS",
                    "category": tab_name,
                    "screenshots": [str(path) for path in details_screenshots],
                    "screenshot": str(details_screenshots[0]) if details_screenshots else None,
                    "components": details_components,
                    "ui_structure": details_ui,
                })

                Logger.success(
                    f"{tab_name} Offer Details captured in "
                    f"{len(details_screenshots)} screenshot(s)."
                )

                # Return exactly through the left menu before the next tab.
                if not self._return_to_entitlement_control_landing():
                    Logger.error(
                        f"Stopping Entitlement Control deep crawl after {tab_name}: "
                        "unable to return to landing page."
                    )
                    break

            except Exception as exc:
                Logger.error(f"Unable to capture {tab_name} Offer Details.")
                Logger.error(str(exc))
                results.append({
                    "menu": menu_name,
                    "submenu": f"Entitlement Control - {tab_name} - Details",
                    "status": "FAIL",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": "",
                    "load_time": time.perf_counter() - details_start,
                    "error": str(exc),
                    "type": "ENTITLEMENT_CONTROL_DETAILS",
                    "category": tab_name,
                    "screenshots": [],
                    "screenshot": None,
                    "components": [],
                    "ui_structure": {},
                })

        return results

    def crawl_epg(self, menu_name: str, submenu_name: str) -> list[dict]:
        """Deep-crawl EPG listing and first-event Details drawer tabs."""
        results = []
        Logger.section("Content Management -> EPG")

        self._close_epg_details_drawer()
        self.page.wait_for_selector("table", state="visible", timeout=30000)
        self.page.wait_for_selector("table tbody tr", state="visible", timeout=30000)
        first_row = self.page.locator("table tbody tr").first

        # Listing: screenshot + static UI structure.
        listing_screenshot = self.screenshot_engine.capture(
            page=self.page, menu=menu_name, submenu="EPG"
        )
        listing_components = self.component_detector.detect(self.page)
        listing_ui = self.epg_ui_detector.detect_listing(self.page)
        results.append({
            "menu": menu_name, "submenu": "EPG", "status": "SUCCESS",
            "navigation_type": "INTERNAL", "url": self.page.url,
            "title": self.page.title(), "load_time": 0, "error": None,
            "screenshot": str(listing_screenshot), "screenshots": [str(listing_screenshot)],
            "components": listing_components, "ui_structure": listing_ui,
            "type": "EPG_LISTING",
        })

        # Open the first event via the eye/View action.
        view = first_row.locator("#viewIcon").first
        if view.count() == 0:
            # Fallback for custom Angular icon markup.
            view = first_row.locator("[id*='view'], [aria-label*='View' i], [title*='View' i]").first
        view.wait_for(state="visible", timeout=15000)
        view.scroll_into_view_if_needed()
        view.click()
        self.page.get_by_text("Event Id:", exact=False).first.wait_for(state="visible", timeout=30000)
        self.page.wait_for_timeout(800)

        drawer = self._epg_drawer()
        for tab in ["Images", "Videos", "Aggregated Data"]:
            tab_locator = drawer.get_by_text(tab, exact=True).first
            tab_locator.wait_for(state="visible", timeout=15000)
            tab_locator.click()
            self.page.wait_for_timeout(500)
            drawer = self._epg_drawer()
            shots, ui = self._capture_epg_drawer(
                drawer, tab, menu_name, f"EPG - Event Details"
            )
            results.append({
                "menu": menu_name,
                "submenu": f"EPG - Event Details - {tab}",
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": self.page.title(),
                "load_time": 0,
                "error": None,
                "type": "EPG_EVENT_DETAILS",
                "tab": tab,
                "screenshots": [str(p) for p in shots],
                "screenshot": str(shots[0]) if shots else None,
                "components": self.component_detector.detect(self.page),
                "ui_structure": ui,
            })

        self._close_epg_details_drawer()
        return results

    def crawl_vod_series(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """Backward-compatible wrapper for the Series deep crawl."""
        return self.crawl_vod_category(
            menu_name=menu_name,
            category="Series",
        )

    def crawl_global_configuration(self, menu_name: str, submenu_name: str) -> list[dict]:
        """Capture Global Configuration screenshot and stable UI structure."""
        Logger.section("Content Management -> Global Configuration")

        # Wait for the four configuration cards visible on the landing page.
        for text in ["Watermarking", "SSAI", "CDN Auth Token", "Primary Origin"]:
            self.page.get_by_text(text, exact=True).first.wait_for(
                state="visible", timeout=30000
            )

        self.page.wait_for_timeout(500)

        screenshot = self.screenshot_engine.capture(
            page=self.page,
            menu=menu_name,
            submenu="Global Configuration",
        )
        ui_structure = self.global_configuration_ui_detector.detect(self.page)
        components = self.component_detector.detect(self.page)

        Logger.success("Global Configuration screenshot captured.")
        Logger.success("Global Configuration UI structure captured.")

        return [{
            "menu": menu_name,
            "submenu": "Global Configuration",
            "status": "SUCCESS",
            "navigation_type": "INTERNAL",
            "url": self.page.url,
            "title": self.page.title(),
            "load_time": 0,
            "error": None,
            "screenshot": str(screenshot),
            "screenshots": [str(screenshot)],
            "components": components,
            "ui_structure": ui_structure,
            "type": "GLOBAL_CONFIGURATION",
        }]


    def crawl_bouquet_management(self, menu_name: str, submenu_name: str) -> list[dict]:
        """Deep-crawl Bouquet Management: listing -> Add Bouquet Group -> Cancel."""
        results = []
        Logger.section("Content Management -> Bouquet Management")

        # Listing page
        self.page.get_by_text("Bouquet Management", exact=True).first.wait_for(
            state="visible", timeout=30000
        )
        self.page.wait_for_timeout(500)

        screenshot = self.screenshot_engine.capture(
            page=self.page, menu=menu_name, submenu="Bouquet Management"
        )
        ui_structure = self.bouquet_management_ui_detector.detect_listing(self.page)
        components = self.component_detector.detect(self.page)
        Logger.success("Bouquet Management listing screenshot captured.")
        Logger.success("Bouquet Management listing UI structure captured.")

        results.append({
            "menu": menu_name,
            "submenu": "Bouquet Management",
            "status": "SUCCESS",
            "navigation_type": "INTERNAL",
            "url": self.page.url,
            "title": self.page.title(),
            "load_time": 0,
            "error": None,
            "screenshot": str(screenshot),
            "screenshots": [str(screenshot)],
            "components": components,
            "ui_structure": ui_structure,
            "type": "BOUQUET_MANAGEMENT_LISTING",
        })

        # User-defined flow: click Add Bouquet Group, capture Create Group, then Cancel.
        Logger.info("Bouquet Management: clicking Add Bouquet Group...")
        # Use the actual DOM button rather than relying on ARIA role/name
        # resolution. The OPC button is rendered as a <button>, but Playwright
        # role matching can fail intermittently with the Angular wrapper.
        add_button = self.page.locator("button").filter(
            has_text="Add Bouquet Group"
        ).first

        try:
            add_button.wait_for(state="visible", timeout=10000)
        except Exception:
            # Fallback to the visible text if the button wrapper changes.
            add_button = self.page.get_by_text(
                "Add Bouquet Group", exact=True
            ).first
            add_button.wait_for(state="visible", timeout=20000)

        add_button.click()

        self.page.get_by_text("Create Group", exact=True).first.wait_for(
            state="visible", timeout=30000
        )
        self.page.wait_for_timeout(500)

        create_screenshot = self.screenshot_engine.capture(
            page=self.page, menu=menu_name, submenu="Bouquet Management - Create Group"
        )
        create_ui_structure = self.bouquet_management_ui_detector.detect_create_group(self.page)
        create_components = self.component_detector.detect(self.page)
        Logger.success("Bouquet Management Create Group screenshot captured.")
        Logger.success("Bouquet Management Create Group UI structure captured.")

        results.append({
            "menu": menu_name,
            "submenu": "Bouquet Management - Create Group",
            "status": "SUCCESS",
            "navigation_type": "INTERNAL",
            "url": self.page.url,
            "title": self.page.title(),
            "load_time": 0,
            "error": None,
            "screenshot": str(create_screenshot),
            "screenshots": [str(create_screenshot)],
            "components": create_components,
            "ui_structure": create_ui_structure,
            "type": "BOUQUET_MANAGEMENT_CREATE_GROUP",
        })

        Logger.info("Bouquet Management: clicking Cancel to return to landing page...")
        cancel_button = self.page.get_by_role("button", name="Cancel", exact=True)
        cancel_button.first.wait_for(state="visible", timeout=30000)
        cancel_button.first.click()

        self.page.get_by_text("Bouquet Management", exact=True).first.wait_for(
            state="visible", timeout=30000
        )
        Logger.success("Returned to Bouquet Management landing page after Cancel.")

        return results


    def crawl_channel_logo(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """
        Capture System Configuration -> Channel Logo.

        Captures both:
          - UI screenshot
          - static UI structure

        Does not click Reset, Publish, or Re-Publish.
        """
        results = []

        Logger.section("System Configuration -> Channel Logo")

        try:
            self.page.get_by_text(
                "Channel Logo Configuration",
                exact=True,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            self.page.wait_for_timeout(800)

            screenshot_path = self.screenshot_engine.capture(
                page=self.page,
                menu=menu_name,
                submenu=submenu_name,
            )

            ui_structure = self.channel_logo_ui_detector.detect(
                self.page
            )

            components = self.component_detector.detect(self.page)

            results.append({
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": self.page.title(),
                "load_time": 0,
                "error": None,
                "screenshot": str(screenshot_path),
                "screenshots": [str(screenshot_path)],
                "components": components,
                "ui_structure": ui_structure,
                "type": "CHANNEL_LOGO_CONFIGURATION",
            })

            Logger.success(
                "Channel Logo: screenshot + UI structure captured."
            )

        except Exception as exc:
            Logger.error("Channel Logo deep capture failed.")
            Logger.error(str(exc))

            results.append({
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "FAIL",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": "",
                "load_time": 0,
                "error": str(exc),
                "screenshot": None,
                "screenshots": [],
                "components": [],
                "ui_structure": {},
                "type": "CHANNEL_LOGO_CONFIGURATION",
            })

        return results

    def crawl_channel_poster(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """
        Capture System Configuration -> Channel Poster.

        This section captures both:
          1. UI screenshot
          2. static UI structure

        Runtime/configuration values are filtered by ChannelPosterUIDetector.
        No Reset/Publish/Re-Publish action is clicked.
        """
        results = []

        Logger.section("System Configuration -> Channel Poster")

        try:
            # Wait for the actual Channel Poster page to be ready.
            self.page.get_by_text(
                "Channel Poster Configuration",
                exact=True,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            self.page.wait_for_timeout(800)

            Logger.info("Channel Poster: capturing UI screenshot...")
            screenshot_path = self.screenshot_engine.capture(
                page=self.page,
                menu=menu_name,
                submenu=submenu_name,
            )

            Logger.info("Channel Poster: capturing static UI structure...")
            ui_structure = self.channel_poster_ui_detector.detect(self.page)

            components = self.component_detector.detect(self.page)

            results.append({
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": self.page.title(),
                "load_time": 0,
                "error": None,
                "screenshot": str(screenshot_path),
                "screenshots": [str(screenshot_path)],
                "components": components,
                "ui_structure": ui_structure,
                "type": "CHANNEL_POSTER_CONFIGURATION",
            })

            Logger.success(
                "Channel Poster: screenshot + UI structure captured."
            )

        except Exception as exc:
            Logger.error("Channel Poster deep capture failed.")
            Logger.error(str(exc))

            results.append({
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "FAIL",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": "",
                "load_time": 0,
                "error": str(exc),
                "screenshot": None,
                "screenshots": [],
                "components": [],
                "ui_structure": {},
                "type": "CHANNEL_POSTER_CONFIGURATION",
            })

        return results

    def crawl_guide_metadata(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """
        Capture System Configuration -> Guide Metadata.

        Captures:
          1. UI screenshot
          2. static UI structure

        No Reset, Publish, or Re-Publish action is performed.
        """
        results = []

        Logger.section("System Configuration -> Guide Metadata")

        try:
            self.page.get_by_text(
                "Guide Metadata Configuration",
                exact=True,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            self.page.wait_for_timeout(800)

            Logger.info("Guide Metadata: capturing UI screenshot...")
            screenshot_path = self.screenshot_engine.capture(
                page=self.page,
                menu=menu_name,
                submenu=submenu_name,
            )

            Logger.info("Guide Metadata: capturing static UI structure...")
            ui_structure = self.guide_metadata_ui_detector.detect(self.page)
            components = self.component_detector.detect(self.page)

            results.append({
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": self.page.title(),
                "load_time": 0,
                "error": None,
                "screenshot": str(screenshot_path),
                "screenshots": [str(screenshot_path)],
                "components": components,
                "ui_structure": ui_structure,
                "type": "GUIDE_METADATA_CONFIGURATION",
            })

            Logger.success(
                "Guide Metadata: screenshot + UI structure captured."
            )

        except Exception as exc:
            Logger.error("Guide Metadata deep capture failed.")
            Logger.error(str(exc))

            results.append({
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "FAIL",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": "",
                "load_time": 0,
                "error": str(exc),
                "screenshot": None,
                "screenshots": [],
                "components": [],
                "ui_structure": {},
                "type": "GUIDE_METADATA_CONFIGURATION",
            })

        return results

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

            # ------------------------------------------------------
            # Expand menu
            # ------------------------------------------------------

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

            # ------------------------------------------------------
            # Skip empty menu
            # ------------------------------------------------------

            if not menu_data["submenus"]:

                Logger.warning(
                    f"No submenus found under '{menu_name}'"
                )

                continue

            # ------------------------------------------------------
            # Crawl every submenu
            # ------------------------------------------------------

            for submenu_data in menu_data["submenus"]:

                submenu_name = submenu_data["name"]

                Logger.info(
                    f"  → {submenu_name}"
                )

                result = self.navigator.navigate(
                    submenu_data["locator"]
                )

                # --------------------------------------------------
                # Capture screenshot only if navigation succeeded
                # --------------------------------------------------

                if result["status"] == "SUCCESS":

                    Logger.info(
                        f"DEBUG: checking VOD hook -> "
                        f"menu={menu_name}, submenu={submenu_name}"
                    )

                    # --------------------------------------------------
                    # VOD gets the dedicated deep crawl.
                    # This prevents the generic capture() from being
                    # used for Series Details.
                    # --------------------------------------------------


                    if (
                        menu_name == "System Configuration"
                        and submenu_name == "Channel Logo"
                    ):
                        channel_logo_results = self.crawl_channel_logo(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(channel_logo_results)
                        continue

                    if (
                        menu_name == "System Configuration"
                        and submenu_name == "Channel Poster"
                    ):
                        channel_poster_results = self.crawl_channel_poster(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(channel_poster_results)
                        continue

                    if (
                        menu_name == "System Configuration"
                        and submenu_name == "Guide Metadata"
                    ):
                        guide_metadata_results = self.crawl_guide_metadata(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(guide_metadata_results)
                        continue

                    if (
                        menu_name == "Content Management"
                        and submenu_name == "EPG"
                    ):
                        epg_results = self.crawl_epg(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(epg_results)
                        continue

                    if (
                        menu_name == "Content Management"
                        and submenu_name == "Bouquet Management"
                    ):
                        bouquet_results = self.crawl_bouquet_management(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(bouquet_results)
                        continue

                    if (
                        menu_name == "Content Management"
                        and submenu_name == "Global Configuration"
                    ):
                        global_configuration_results = self.crawl_global_configuration(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(global_configuration_results)
                        continue

                    if (
                        menu_name == "Content Management"
                        and submenu_name == "Entitlement Control"
                    ):
                        entitlement_results = self.crawl_entitlement_control(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(entitlement_results)
                        continue

                    if (
                        menu_name == "Content Management"
                        and submenu_name == "Channel"
                    ):

                        channel_results = self.crawl_channel(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(channel_results)
                        continue

                    if (
                        menu_name == "Content Management"
                        and submenu_name == "VOD"
                    ):

                        # Discover all VOD category tabs from the actual UI.
                        # This keeps the VOD crawl complete when a new category
                        # is added without requiring a code change.
                        try:
                            self.page.wait_for_timeout(1000)

                            category_tabs = self.page.locator(
                                ".generic-child-tab"
                            )

                            discovered_categories = []
                            tab_count = category_tabs.count()

                            for index in range(tab_count):
                                try:
                                    category_name = (
                                        category_tabs.nth(index)
                                        .inner_text()
                                        .strip()
                                    )
                                except Exception:
                                    continue

                                if (
                                    category_name
                                    and category_name not in discovered_categories
                                ):
                                    discovered_categories.append(category_name)

                            Logger.info(
                                "Discovered VOD categories: "
                                + ", ".join(discovered_categories)
                            )

                            # Persist the runtime-discovered VOD categories
                            # into the navigation tree. NavigationManifest runs
                            # after the crawler, so this information can be
                            # written into navigation.json without requiring
                            # a separate manifest format or hardcoded list.
                            submenu_data["vod_categories"] = list(
                                discovered_categories
                            )
                            submenu_data["vod_deep_crawl"] = True

                            Logger.success(
                                f"VOD category manifest captured: "
                                f"{len(discovered_categories)} categories."
                            )

                        except Exception as exc:
                            Logger.error(
                                "Unable to discover VOD category tabs."
                            )
                            Logger.error(str(exc))
                            discovered_categories = []

                        # Series is already crawled first so the existing
                        # validated Series flow remains unchanged.
                        vod_categories = [
                            category
                            for category in discovered_categories
                            if category != "Series"
                        ]

                        for category in vod_categories:
                            try:
                                # Details is an Angular Material side drawer. Closing it
                                # reveals the same VOD listing underneath; Navigator.navigate()
                                # is not needed because the URL does not change.
                                self._close_vod_details_drawer()
                                self.page.wait_for_timeout(500)

                                self.page.wait_for_selector(
                                    "table",
                                    state="visible",
                                    timeout=15000,
                                )

                                Logger.info(
                                    f"VOD listing restored. Starting VOD → {category}."
                                )

                                category_results = self.crawl_vod_category(
                                    menu_name=menu_name,
                                    category=category,
                                )
                                results.extend(category_results)

                            except Exception as exc:
                                Logger.error(
                                    f"Unable to start VOD → {category}."
                                )
                                Logger.error(str(exc))
                                break

                        continue

                    target_page = (
                        result["page"]
                        if result["page"] is not None
                        else self.page
                    )

                    screenshot_path = (
                        self.screenshot_engine.capture(
                            page=target_page,
                            menu=menu_name,
                            submenu=submenu_name,
                        )
                    )

                    components = (
                        self.component_detector.detect(
                            target_page
                        )
                    )

                    Logger.kv(
                        "Screenshot",
                        screenshot_path,
                    )

                else:

                    screenshot_path = None
                    components = []

                # --------------------------------------------------
                # Store result
                # --------------------------------------------------

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
                        "components": components,
                    }
                )

                # --------------------------------------------------
                # Console output
                # --------------------------------------------------

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

                # --------------------------------------------------
                # Close popup page
                # --------------------------------------------------

                if result["type"] == "POPUP":

                    try:

                        result["page"].close()

                    except Exception:

                        pass

        Logger.section(
            "Crawler Summary"
        )

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