"""
Crawler

Responsible for:

- Iterating through the discovered navigation tree
- Navigating to every page
- Capturing screenshots
- Returning crawl results
"""

from __future__ import annotations

import re
import time

from comparison.vod_ui_detector import VODUIDetector
from comparison.channel_ui_detector import ChannelUIDetector
from comparison.epg_ui_detector import EPGUIDetector
from comparison.entitlement_control_ui_detector import EntitlementControlUIDetector
from comparison.global_configuration_ui_detector import GlobalConfigurationUIDetector
from comparison.bouquet_management_ui_detector import BouquetManagementUIDetector
from comparison.channel_logo_ui_detector import ChannelLogoUIDetector

from comparison.component_detector import ComponentDetector

from pathlib import Path

from playwright.sync_api import Page

from core.logger import Logger
from core.navigator import Navigator
from core.screenshot import ScreenshotEngine

HOUSEHOLD_TEST_IDS = {
    "stage": "603901141",
    "prod": "11110001",
}


def get_household_test_id(url: str) -> str:
    """Return the environment-specific Household test ID."""
    url_lower = str(url or "").lower()

    if "opc.astro.live.xp.irdeto.com" in url_lower:
        return HOUSEHOLD_TEST_IDS["prod"]

    # Stage is the default for the known Stage host and local/unknown runs.
    return HOUSEHOLD_TEST_IDS["stage"]


MENU_EXPAND_WAIT = 800

# Known OPC navigation items that have previously been captured in Stage.
# If they are absent from an environment's discovered navigation, record the
# discovery gap explicitly rather than silently letting the comparator call
# them missing from that environment.
KNOWN_NAVIGATION_EXPECTATIONS = {
    ("Observability", "Monitoring"),
    ("Security", "DRM Manager"),
}

# VOD categories observed in the supported OPC tenant. Runtime-discovered
# categories are added to this list, so newly introduced tabs are still crawled.
KNOWN_VOD_CATEGORIES = (
    "Episodes",
    "Highlights",
    "Movies",
    "Series",
    "3PP VOD Episode",
    "3PP VOD Season",
    "3PP VOD Series",
    "3PP VOD Title",
    "Trailers",
)


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

    def _coverage_record(
        self,
        menu_name: str,
        submenu_name: str,
        status: str,
        reason: str,
        *,
        error: str | None = None,
        url: str | None = None,
        record_type: str = "CRAWL_COVERAGE",
    ) -> dict:
        """Build an explicit record for a screen that was not fully crawled."""
        return {
            "menu": menu_name,
            "submenu": submenu_name,
            "status": status,
            "navigation_type": "INTERNAL",
            "url": url,
            "title": "",
            "load_time": 0,
            "error": error,
            "reason": reason,
            "coverage_status": status,
            "type": record_type,
            "screenshot": None,
            "screenshots": [],
            "components": [],
            "ui_structure": {},
        }

    def _vod_category_failure_records(
        self,
        menu_name: str,
        category: str,
        status: str,
        reason: str,
        *,
        error: str | None = None,
    ) -> list[dict]:
        """Return explicit listing/detail records when a VOD flow fails."""
        current_url = self.page.url if self.page else None
        return [
            self._coverage_record(
                menu_name,
                f"VOD - {category}",
                status,
                reason,
                error=error,
                url=current_url,
                record_type="VOD_LISTING",
            ),
            self._coverage_record(
                menu_name,
                f"VOD - {category} - Details",
                "NOT_ATTEMPTED" if status != "NOT_DISCOVERED" else status,
                "Details flow was not attempted because the category/listing was not available.",
                error=error,
                url=current_url,
                record_type="VOD_DETAILS",
            ),
        ]

    def _capture_vod_edit_screen(self, menu_name: str, category: str, results: list[dict]) -> bool:
        """Capture the first row's Edit form, then safely cancel back to its listing.

        The edit flow is read-only: it never presses Update/Save. OPC may show an
        unsaved-changes confirmation even when no values were changed, so the
        helper explicitly chooses Leave page and verifies that the category list
        is available again before the normal View/details flow continues.
        """
        edit_submenu = f"VOD - {category} - Edit"
        started = time.perf_counter()
        try:
            row = self.page.locator("table tbody tr:visible").first
            edit_button = row.locator(
                "#editIcon, [id*='editIcon'], button[aria-label*='Edit' i], "
                "button[title*='Edit' i], [role='button'][aria-label*='Edit' i]"
            ).first
            edit_button.wait_for(state="visible", timeout=7000)
            edit_button.scroll_into_view_if_needed()
            edit_button.click()
            self.page.wait_for_load_state("domcontentloaded", timeout=20000)
            self.page.wait_for_timeout(1000)

            # The form heading and controls are captured as static structure;
            # content values are handled by the detector's existing policy.
            screenshots = self.screenshot_engine.capture_details(
                page=self.page, menu=menu_name, submenu=edit_submenu
            )
            components = self.component_detector.detect(self.page)
            structure = self.vod_ui_detector.detect_details(self.page)
            results.append({
                "menu": menu_name,
                "submenu": edit_submenu,
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": self.page.title(),
                "load_time": time.perf_counter() - started,
                "error": None,
                "type": "VOD_EDIT",
                "category": category,
                "screenshots": [str(path) for path in screenshots],
                "screenshot": str(screenshots[0]) if screenshots else None,
                "components": components,
                "ui_structure": structure,
            })
            Logger.success(f"{category} Edit screen captured ({len(screenshots)} screenshot(s)).")
        except Exception as exc:
            Logger.warning(f"Unable to capture {category} Edit screen: {exc}")
            results.append(self._coverage_record(
                menu_name, edit_submenu, "FAILED_TO_OPEN_OR_CAPTURE",
                "The first-row Edit form could not be opened or captured.",
                error=str(exc), url=self.page.url, record_type="VOD_EDIT",
            ))
        finally:
            # If an edit form opened, cancel it. Do not submit form changes.
            try:
                cancel = self.page.get_by_role("button", name=re.compile(r"^cancel$", re.I)).last
                if cancel.count() and cancel.is_visible(timeout=1500):
                    cancel.click()
                    self.page.wait_for_timeout(300)
                    leave = self.page.get_by_role("button", name=re.compile(r"^leave page$", re.I)).last
                    if leave.count() and leave.is_visible(timeout=2000):
                        leave.click()
                    else:
                        stay = self.page.get_by_role("button", name=re.compile(r"^stay on page$", re.I)).last
                        if stay.count() and stay.is_visible(timeout=500):
                            # No navigation confirmation: stay here and retry Cancel once.
                            stay.click()
                            cancel = self.page.get_by_role("button", name=re.compile(r"^cancel$", re.I)).last
                            if cancel.count() and cancel.is_visible(timeout=1000):
                                cancel.click()
                                leave = self.page.get_by_role("button", name=re.compile(r"^leave page$", re.I)).last
                                if leave.count() and leave.is_visible(timeout=1500):
                                    leave.click()
                self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                self.page.wait_for_timeout(700)
            except Exception as cleanup_exc:
                Logger.warning(f"Could not complete Edit cancel/return flow for {category}: {cleanup_exc}")

        # Ensure the category list is restored before View is clicked by caller.
        try:
            self.page.locator("table tbody tr:visible").first.wait_for(state="visible", timeout=12000)
            return True
        except Exception:
            try:
                tab = self.page.get_by_text(category, exact=True).first
                if tab.is_visible(timeout=2000):
                    tab.click()
                    self.page.wait_for_timeout(800)
                self.page.locator("table tbody tr:visible").first.wait_for(state="visible", timeout=8000)
                return True
            except Exception as exc:
                Logger.warning(f"Could not restore VOD {category} listing after Edit capture: {exc}")
                return False

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
        # Open VOD category tab before waiting for listing content.
        # A previously selected category (e.g. Trailers) may show an
        # explicit empty state with no table. Waiting for a table here
        # prevents the crawler from ever switching to the next category.
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
            return self._vod_category_failure_records(
                menu_name, category, "FAILED_TO_OPEN",
                "The category tab was discovered but could not be opened.", error=str(exc)
            )

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
            # Empty categories are valid application states. Record the
            # listing and an explicit NO_DATA detail placeholder instead of
            # silently dropping the category and reporting it as missing.
            try:
                table = self.page.locator("table:visible").first
                table_visible = table.count() > 0 and table.is_visible(timeout=1000)
                row_count = self.page.locator("table tbody tr:visible").count()
                # Production can render an explicit empty-state panel instead
                # of an empty table (e.g. "No listing data available for Trailers").
                empty_state = self.page.get_by_text(
                    "No listing data available", exact=False
                ).first
                empty_state_visible = (
                    empty_state.count() > 0 and empty_state.is_visible(timeout=1000)
                )
            except Exception:
                table_visible = False
                row_count = -1
                empty_state_visible = False

            if empty_state_visible or (table_visible and row_count == 0):
                empty_reason = (
                    f"Application displayed an explicit empty state for {category}."
                    if empty_state_visible
                    else "Category table loaded but contains no content rows."
                )
                Logger.warning(
                    f"VOD → {category} confirmed empty; recording NO_DATA states."
                )
                try:
                    listing_screenshot = self.screenshot_engine.capture(
                        page=self.page,
                        menu=menu_name,
                        submenu=f"VOD - {category}",
                    )
                    listing_components = self.component_detector.detect(self.page)
                    listing_record = {
                        "menu": menu_name,
                        "submenu": f"VOD - {category}",
                        "status": "NO_DATA",
                        "navigation_type": "INTERNAL",
                        "url": self.page.url,
                        "title": self.page.title(),
                        "load_time": 0,
                        "error": None,
                        "reason": empty_reason,
                        "screenshot": str(listing_screenshot),
                        "screenshots": [str(listing_screenshot)],
                        "components": listing_components,
                        "ui_structure": {},
                        "type": "VOD_LISTING",
                        "category": category,
                    }
                    results.append(listing_record)

                    # No content exists to open, so do not invent a blank Details screen.
                    # Keep only the real listing capture and continue with the next category.
                    return results
                except Exception as capture_exc:
                    Logger.error(
                        f"Unable to record empty VOD category {category}: {capture_exc}"
                    )

            Logger.error(f"{category} content table did not load.")
            Logger.error(str(exc))
            return self._vod_category_failure_records(
                menu_name, category, "FAILED_TO_LOAD",
                "Category table did not load and was not confirmed empty.", error=str(exc)
            )

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
        # Capture Edit form for the first row, cancel safely, and return
        # to this category before continuing to View/Details.
        # ----------------------------------------------------------

        self._capture_vod_edit_screen(menu_name, category, results)

        # Re-resolve the first row because navigation away from Edit invalidates
        # the old Playwright locator's underlying DOM element.
        first_row = self.page.locator("table tbody tr:visible").first
        first_row.wait_for(state="visible", timeout=15000)

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
            results.append(self._coverage_record(
                menu_name,
                f"VOD - {category} - Details",
                "FAILED_TO_OPEN",
                "Listing was captured, but the first-row View action could not open Details.",
                error=str(exc),
                url=self.page.url,
                record_type="VOD_DETAILS",
            ))
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

    def _capture_channel_edit_wizard(self, menu_name: str, tab_name: str, results: list[dict]) -> bool:
        """Capture every step of the first Channel row's edit wizard without saving.

        OPC Channel edit is a multi-step wizard: General -> Delivery -> Security
        -> Enablers -> Advertising -> Preview. Each step is captured separately;
        the flow exits with Cancel and confirms Leave page when prompted.
        """
        base = f"Channel - {tab_name} - Edit"
        started = time.perf_counter()
        captured = []
        edit_opened = False
        try:
            row = self.page.locator("table tbody tr:visible").first
            edit_button = row.locator(
                "#editIcon, [id*='editIcon'], button[aria-label*='Edit' i], "
                "button[title*='Edit' i], [role='button'][aria-label*='Edit' i]"
            ).first
            edit_button.wait_for(state="visible", timeout=8000)
            edit_button.scroll_into_view_if_needed()
            edit_button.click()
            edit_opened = True
            self.page.wait_for_load_state("domcontentloaded", timeout=20000)
            self.page.wait_for_timeout(1000)

            # Capture General and each subsequent wizard step. Use exact visible
            # button names to avoid clicking similarly named controls in the form.
            step_names = ["General", "Delivery", "Security", "Enablers", "Advertising"]
            for step_index, step_name in enumerate(step_names):
                if step_index > 0:
                    # Previous step's Next button advances the wizard.
                    next_button = self.page.get_by_role("button", name=re.compile(r"^next$", re.I)).last
                    next_button.wait_for(state="visible", timeout=8000)
                    next_button.scroll_into_view_if_needed()
                    next_button.click()
                    self.page.wait_for_timeout(500)

                step_submenu = f"{base} - {step_name}"
                shots = self.screenshot_engine.capture_details(
                    page=self.page, menu=menu_name, submenu=step_submenu
                )
                components = self.component_detector.detect(self.page)
                structure = self.channel_ui_detector.detect_details(self.page)
                results.append({
                    "menu": menu_name, "submenu": step_submenu,
                    "status": "SUCCESS", "navigation_type": "INTERNAL",
                    "url": self.page.url, "title": self.page.title(),
                    "load_time": time.perf_counter() - started, "error": None,
                    "type": "CHANNEL_EDIT_STEP", "category": tab_name,
                    "wizard_step": step_name,
                    "screenshots": [str(path) for path in shots],
                    "screenshot": str(shots[0]) if shots else None,
                    "components": components, "ui_structure": structure,
                })
                captured.extend(shots)
                Logger.success(f"Channel {tab_name} Edit - {step_name} captured ({len(shots)} screenshot(s)).")

            # Advertising's final action is Preview, not Next.
            preview_button = self.page.get_by_role("button", name=re.compile(r"^preview$", re.I)).last
            preview_button.wait_for(state="visible", timeout=8000)
            preview_button.scroll_into_view_if_needed()
            preview_button.click()
            self.page.wait_for_timeout(700)
            preview_submenu = f"{base} - Preview"
            preview_shots = self.screenshot_engine.capture_details(
                page=self.page, menu=menu_name, submenu=preview_submenu
            )
            results.append({
                "menu": menu_name, "submenu": preview_submenu,
                "status": "SUCCESS", "navigation_type": "INTERNAL",
                "url": self.page.url, "title": self.page.title(),
                "load_time": time.perf_counter() - started, "error": None,
                "type": "CHANNEL_EDIT_PREVIEW", "category": tab_name,
                "wizard_step": "Preview",
                "screenshots": [str(path) for path in preview_shots],
                "screenshot": str(preview_shots[0]) if preview_shots else None,
                "components": self.component_detector.detect(self.page),
                "ui_structure": self.channel_ui_detector.detect_details(self.page),
            })
            Logger.success(f"Channel {tab_name} Edit - Preview captured ({len(preview_shots)} screenshot(s)).")
            return True
        except Exception as exc:
            Logger.warning(f"Unable to complete Channel {tab_name} Edit wizard: {exc}")
            results.append(self._coverage_record(
                menu_name, base, "FAILED_TO_OPEN_OR_CAPTURE",
                "The first-row Channel edit wizard could not be fully captured.",
                error=str(exc), url=self.page.url, record_type="CHANNEL_EDIT",
            ))
            return False
        finally:
            if edit_opened:
                try:
                    cancel = self.page.get_by_role("button", name=re.compile(r"^cancel$", re.I)).last
                    if cancel.count() and cancel.is_visible(timeout=2000):
                        cancel.click()
                        self.page.wait_for_timeout(350)
                        leave = self.page.get_by_role("button", name=re.compile(r"^leave page$", re.I)).last
                        if leave.count() and leave.is_visible(timeout=2000):
                            leave.click()
                        else:
                            stay = self.page.get_by_role("button", name=re.compile(r"^stay on page$", re.I)).last
                            if stay.count() and stay.is_visible(timeout=500):
                                stay.click()
                                cancel = self.page.get_by_role("button", name=re.compile(r"^cancel$", re.I)).last
                                if cancel.count() and cancel.is_visible(timeout=1000):
                                    cancel.click()
                                    leave = self.page.get_by_role("button", name=re.compile(r"^leave page$", re.I)).last
                                    if leave.count() and leave.is_visible(timeout=1500):
                                        leave.click()
                    self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                    self.page.wait_for_timeout(700)
                except Exception as cleanup_exc:
                    Logger.warning(f"Could not cancel/leave Channel {tab_name} Edit wizard: {cleanup_exc}")

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

        For every tab (Commercial TV, Commercial Radio, App Launch Point):
            listing capture -> first row Edit -> General -> Delivery -> Security
            -> Enablers -> Advertising -> Preview -> Cancel -> Leave page
            -> first row View CTA (#viewIcon) -> Details capture.

        Tab names are discovered from the UI, processed in the requested order,
        and any additional discovered tabs are also processed. Edit workflows are
        read-only: the crawler must never click Update/Save.

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

            # Keep the three OPC Channel tabs in the requested, deterministic
            # order. Include any additional tabs discovered in the UI after
            # these known tabs rather than silently skipping future additions.
            preferred_order = ["Commercial TV", "Commercial Radio", "App Launch Point"]
            ordered_tabs = [name for name in preferred_order if name in discovered_tabs]
            ordered_tabs.extend(name for name in discovered_tabs if name not in ordered_tabs)
            discovered_tabs = ordered_tabs

            Logger.info(
                "Channel tabs queued for listing + Edit wizard + Preview + Details: "
                + ", ".join(discovered_tabs)
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
            # Capture the first row's complete Edit wizard, then return to
            # the same tab before continuing with the existing View flow.
            # ------------------------------------------------------
            self._capture_channel_edit_wizard(menu_name, tab_name, results)
            try:
                # Re-query after wizard navigation; old row locators are stale.
                self.page.locator("table tbody tr:visible").first.wait_for(
                    state="visible", timeout=12000
                )
                first_row = self.page.locator("table tbody tr:visible").first
            except Exception as restore_exc:
                Logger.warning(f"Could not restore Channel -> {tab_name} listing after Edit: {restore_exc}")
                continue

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

    def _close_epg_channel_dropdown(self) -> None:
        """Close the Angular Material EPG channel dropdown/overlay safely."""
        try:
            # The EPG channel selector uses an Angular CDK overlay.  Escape can
            # leave the searchable panel open in this application, so prefer
            # clicking the overlay backdrop when it is present.
            backdrop = self.page.locator(
                ".cdk-overlay-backdrop.cdk-overlay-backdrop-showing"
            ).last
            if backdrop.count() > 0 and backdrop.is_visible(timeout=1000):
                backdrop.click(force=True)
                self.page.wait_for_timeout(300)
                return
        except Exception as exc:
            Logger.debug(f"EPG dropdown backdrop close skipped: {exc}")

        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
        except Exception as exc:
            Logger.debug(f"EPG dropdown Escape close skipped: {exc}")

    def _find_epg_channel_select(self):
        """Find the visible Select Channel mat-select on the EPG page."""
        selects = self.page.locator("mat-select:visible")
        count = selects.count()

        for index in range(count):
            candidate = selects.nth(index)
            try:
                parent_text = candidate.locator("xpath=..").inner_text().strip()
                if "channel" in parent_text.lower():
                    return candidate
            except Exception:
                pass

        return selects.first if count > 0 else None

    def _select_epg_channel_with_data(self, max_channels: int = 10) -> bool:
        """
        Find an EPG channel containing at least one event row.

        The initial EPG channel may legitimately have no data.  The channel
        selector is an Angular Material searchable dropdown, so the overlay
        must be explicitly closed after reading the options before the next
        click.
        """
        Logger.info("Checking EPG channel for available event data...")

        rows = self.page.locator("table tbody tr")

        # --------------------------------------------------------------
        # First wait for the initially selected channel to finish loading.
        # EPG data is fetched asynchronously; an immediate row count can be 0
        # even though the channel will populate shortly.
        # --------------------------------------------------------------
        try:
            deadline_seconds = 30
            for elapsed in range(deadline_seconds):
                try:
                    current_rows = self.page.locator("table tbody tr:visible")
                    row_count = current_rows.count()
                    meaningful_rows = 0
                    for index in range(min(row_count, 10)):
                        row = current_rows.nth(index)
                        try:
                            text = " ".join(row.inner_text(timeout=700).split())
                            if text and not re.fullmatch(r"(loading|no data|no records found|no events available)", text, re.I):
                                meaningful_rows += 1
                        except Exception:
                            continue
                    if meaningful_rows:
                        Logger.success(
                            f"Current EPG channel contains event data after {elapsed + 1}s wait."
                        )
                        return True
                except Exception:
                    pass
                self.page.wait_for_timeout(1000)
            Logger.info("Initial EPG channel still has no event rows after 30 seconds; trying other channels.")
        except Exception as exc:
            Logger.debug(f"Initial EPG delayed-row check skipped: {exc}")

        # --------------------------------------------------------------
        # Locate the channel selector.
        # --------------------------------------------------------------
        channel_select = None
        try:
            channel_select = self._find_epg_channel_select()
            Logger.info(
                "Visible EPG mat-select controls found: "
                f"{self.page.locator('mat-select:visible').count()}"
            )
        except Exception as exc:
            Logger.debug(f"EPG mat-select lookup failed: {exc}")

        if channel_select is None:
            try:
                native_selects = self.page.locator("select:visible")
                if native_selects.count() > 0:
                    channel_select = native_selects.first
                    Logger.info(
                        f"Visible native EPG selects found: {native_selects.count()}"
                    )
            except Exception as exc:
                Logger.debug(f"EPG native select lookup failed: {exc}")

        if channel_select is None:
            Logger.warning("EPG Select Channel control could not be found.")
            return False

        # --------------------------------------------------------------
        # Read available channel options.
        # --------------------------------------------------------------
        channels = []

        try:
            tag_name = channel_select.evaluate(
                "el => el.tagName.toLowerCase()"
            )

            if tag_name == "mat-select":
                channel_select.click()

                options = self.page.locator("mat-option:visible")
                options.first.wait_for(state="visible", timeout=10000)

                option_count = options.count()
                Logger.info(f"EPG channel options found: {option_count}")

                for index in range(option_count):
                    option = options.nth(index)
                    try:
                        text = " ".join(option.inner_text().split())
                        disabled = option.get_attribute("aria-disabled") == "true"
                    except Exception:
                        continue

                    # Ignore empty/disabled entries.  A searchable Material
                    # select can expose helper/search content as an option-like
                    # node; only actual selectable entries are retained.
                    if not text or disabled:
                        continue

                    if text not in channels:
                        channels.append(text)

                # IMPORTANT: the searchable EPG panel can remain open after
                # Escape.  Close the CDK overlay before trying another click.
                self._close_epg_channel_dropdown()

            else:
                option_count = channel_select.locator("option").count()
                Logger.info(f"EPG native channel options found: {option_count}")

                for index in range(option_count):
                    option = channel_select.locator("option").nth(index)
                    text = " ".join(option.inner_text().split())
                    value = option.get_attribute("value")
                    disabled = option.get_attribute("disabled") is not None
                    if text and not disabled:
                        channels.append({"text": text, "value": value})

        except Exception as exc:
            Logger.warning(f"Unable to read EPG channel options: {exc}")
            self._close_epg_channel_dropdown()
            return False

        if not channels:
            Logger.warning("No EPG channels were found in Select Channel.")
            return False

        limit = min(len(channels), max_channels)
        Logger.info(f"EPG channels available for fallback: {len(channels)}")

        # --------------------------------------------------------------
        # Try channels one by one.
        # --------------------------------------------------------------
        for index, channel in enumerate(channels[:max_channels], start=1):
            channel_name = (
                channel
                if isinstance(channel, str)
                else channel.get("text", "")
            )

            try:
                Logger.info(
                    f"Trying EPG channel {index}/{limit}: {channel_name}"
                )

                # Always make sure no previous searchable overlay is blocking
                # the selector.
                self._close_epg_channel_dropdown()

                if isinstance(channel, str):
                    current_select = self._find_epg_channel_select()
                    if current_select is None:
                        raise RuntimeError(
                            "EPG channel selector is not available."
                        )

                    current_select.click()

                    # Re-query the overlay after opening it.
                    option = self.page.locator(
                        "mat-option:visible"
                    ).filter(has_text=channel).first
                    option.wait_for(state="visible", timeout=10000)
                    option.click()

                else:
                    current_select = self.page.locator("select:visible").first
                    current_select.select_option(channel.get("value"))

                # The channel change triggers an Angular/API refresh.
                self.page.wait_for_timeout(1000)

                found_data = False

                # EPG channel refreshes can be slow. Wait up to 30 seconds for
                # the async event request and table rendering before treating
                # a channel as empty.
                for _ in range(30):
                    try:
                        current_rows = self.page.locator("table tbody tr")
                        row_count = current_rows.count()

                        if row_count > 0:
                            for row_index in range(min(row_count, 5)):
                                if current_rows.nth(row_index).is_visible(
                                    timeout=500
                                ):
                                    found_data = True
                                    break

                        if found_data:
                            break
                    except Exception:
                        pass

                    self.page.wait_for_timeout(1000)

                if found_data:
                    Logger.success(
                        f"EPG data found for channel: {channel_name}"
                    )
                    return True

                Logger.warning(
                    f"No EPG data found for channel: {channel_name}"
                )

            except Exception as exc:
                Logger.warning(
                    f"Unable to test EPG channel '{channel_name}': {exc}"
                )
                self._close_epg_channel_dropdown()

        Logger.warning(
            "No EPG channel with event data was found in the channels tested."
        )
        return False

    def crawl_epg(self, menu_name: str, submenu_name: str) -> list[dict]:
        """Deep-crawl EPG listing and first-event Details drawer tabs.

        The EPG listing is always captured once event data is available.
        Problems opening the first event or one Details tab are isolated so
        they do not stop the rest of the crawler.
        """
        results = []
        Logger.section("Content Management -> EPG")

        self._close_epg_details_drawer()

        # --------------------------------------------------------------
        # Find a channel that actually contains event data.
        # --------------------------------------------------------------
        if not self._select_epg_channel_with_data(max_channels=10):
            Logger.warning(
                "EPG has no event data in the available channels. "
                "Capturing the page as NO_DATA and continuing the crawl."
            )

            try:
                listing_screenshot = self.screenshot_engine.capture(
                    page=self.page,
                    menu=menu_name,
                    submenu="EPG",
                )
                listing_components = self.component_detector.detect(self.page)
                listing_ui = self.epg_ui_detector.detect_listing(self.page)

                results.append({
                    "menu": menu_name,
                    "submenu": "EPG",
                    "status": "NO_DATA",
                    "navigation_type": "INTERNAL",
                    "url": self.page.url,
                    "title": self.page.title(),
                    "load_time": 0,
                    "error": None,
                    "screenshot": str(listing_screenshot),
                    "screenshots": [str(listing_screenshot)],
                    "components": listing_components,
                    "ui_structure": listing_ui,
                    "type": "EPG_LISTING",
                    "reason": "No EPG event data found in available channels.",
                })
                Logger.success("EPG NO_DATA page captured.")

                # No selectable event exists yet, so do not create blank detail-page
                # records. If data appears after the wait, the listing path above
                # will proceed into the actual Event Details flow.
            except Exception as exc:
                Logger.warning(f"Unable to capture empty EPG page: {exc}")

            return results

        # --------------------------------------------------------------
        # Capture the EPG listing first. This result must not depend on the
        # success of the event-details flow.
        # --------------------------------------------------------------
        try:
            self.page.wait_for_selector(
                "table", state="visible", timeout=30000
            )
            self.page.wait_for_selector(
                "table tbody tr:visible", state="visible", timeout=30000
            )
            first_row = self.page.locator("table tbody tr:visible").first

            listing_screenshot = self.screenshot_engine.capture(
                page=self.page, menu=menu_name, submenu="EPG"
            )
            listing_components = self.component_detector.detect(self.page)
            listing_ui = self.epg_ui_detector.detect_listing(self.page)

            results.append({
                "menu": menu_name,
                "submenu": "EPG",
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
                "type": "EPG_LISTING",
            })
        except Exception as exc:
            Logger.error(f"Unable to capture EPG listing: {exc}")
            return results

        # --------------------------------------------------------------
        # Open the first event. If this fails, keep the EPG listing and
        # continue the overall crawl.
        # --------------------------------------------------------------
        try:
            view = first_row.locator("#viewIcon").first
            if view.count() == 0:
                view = first_row.locator(
                    "[id*='view'], [aria-label*='View' i], [title*='View' i]"
                ).first

            view.wait_for(state="visible", timeout=15000)
            view.scroll_into_view_if_needed()
            view.click()

            self.page.get_by_text("Event Id:", exact=False).first.wait_for(
                state="visible", timeout=30000
            )
            self.page.wait_for_timeout(800)

            drawer = self._epg_drawer()
            if drawer is None:
                raise RuntimeError("EPG event-details drawer was not found.")

        except Exception as exc:
            Logger.warning(
                f"Unable to open EPG event details. Listing was captured; continuing. {exc}"
            )
            self._close_epg_details_drawer()
            return results

        # --------------------------------------------------------------
        # Capture each details tab independently. A failure in Images must
        # not prevent Videos or Aggregated Data from being attempted.
        # --------------------------------------------------------------
        for tab in ["Images", "Videos", "Aggregated Data"]:
            try:
                drawer = self._epg_drawer()
                tab_locator = drawer.get_by_text(tab, exact=True).first
                tab_locator.wait_for(state="visible", timeout=15000)
                tab_locator.click()
                self.page.wait_for_timeout(500)

                drawer = self._epg_drawer()
                shots, ui = self._capture_epg_drawer(
                    drawer, tab, menu_name, "EPG - Event Details"
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

                Logger.success(f"EPG Event Details → {tab} captured.")

            except Exception as exc:
                # Keep the failure local to this tab. The remaining EPG tabs
                # and the rest of the application must still be crawled.
                Logger.warning(
                    f"Unable to capture EPG Event Details → {tab}: {exc}"
                )
                self._close_epg_details_drawer()

                # Re-open the first event if the drawer was closed by the
                # failed tab flow, then continue with the next tab.
                try:
                    first_row = self.page.locator("table tbody tr").first
                    view = first_row.locator("#viewIcon").first
                    if view.count() == 0:
                        view = first_row.locator(
                            "[id*='view'], [aria-label*='View' i], [title*='View' i]"
                        ).first
                    view.wait_for(state="visible", timeout=5000)
                    view.scroll_into_view_if_needed()
                    view.click()
                    self.page.get_by_text("Event Id:", exact=False).first.wait_for(
                        state="visible", timeout=10000
                    )
                    self.page.wait_for_timeout(500)
                except Exception as reopen_exc:
                    Logger.warning(
                        "Unable to reopen EPG Event Details after tab failure: "
                        f"{reopen_exc}"
                    )
                    break

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

        # Global Configuration does not always render the same card labels
        # across environments/versions. Do not hard-fail on a specific text
        # such as "Watermarking". Wait for the page itself to be ready, then
        # let the UI detector capture whatever configuration controls/cards
        # are actually present.
        try:
            self.page.locator("body").wait_for(
                state="visible", timeout=15000
            )
        except Exception as exc:
            Logger.warning(
                f"Global Configuration body readiness check failed: {exc}"
            )

        # Give Angular/API-backed configuration cards a chance to render.
        # This is intentionally a short stabilization wait rather than a
        # selector wait for a hard-coded card name.
        self.page.wait_for_timeout(2000)

        # Log the visible configuration labels when available. This is
        # diagnostic only and must never stop the crawl.
        try:
            visible_text = self.page.locator("body").inner_text(timeout=5000)
            lines = [
                line.strip()
                for line in visible_text.splitlines()
                if line.strip()
            ]
            Logger.info(
                "Global Configuration rendered text sample: "
                + " | ".join(lines[:20])
            )
        except Exception as exc:
            Logger.debug(
                f"Unable to read Global Configuration rendered text: {exc}"
            )

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
            "screenshot": str(screenshot) if screenshot else None,
            "screenshots": [str(screenshot)] if screenshot else [],
            "components": components,
            "ui_structure": ui_structure,
            "type": "GLOBAL_CONFIGURATION",
        }]


    def _wait_for_bouquet_create_group(self, timeout_ms: int = 15000) -> bool:
        """
        Wait for the Bouquet Management create-group UI without assuming a
        specific heading text.

        The current implementation must not depend on an exact
        "Create Group" label. Angular builds/versions can render the same
        create form with a different heading, inside a dialog, drawer, or
        page container.
        """
        deadline = time.time() + (timeout_ms / 1000)

        while time.time() < deadline:
            try:
                # Strong signal: an Angular Material dialog/drawer is open.
                overlays = self.page.locator(
                    "mat-dialog-container:visible, "
                    "[role='dialog']:visible, "
                    "mat-drawer.mat-drawer-opened:visible, "
                    "mat-sidenav.mat-drawer-opened:visible"
                )
                if overlays.count() > 0:
                    Logger.info(
                        "Bouquet Management create UI detected in dialog/drawer."
                    )
                    return True

                # Fallback signal: a visible Cancel button plus form controls.
                cancel_buttons = self.page.get_by_role(
                    "button", name="Cancel", exact=True
                )
                inputs = self.page.locator(
                    "input:visible, textarea:visible, mat-form-field:visible"
                )

                if cancel_buttons.count() > 0 and inputs.count() > 0:
                    Logger.info(
                        "Bouquet Management create form detected "
                        "(Cancel + form controls)."
                    )
                    return True

                # Some builds render the create form as a normal routed page.
                # Detect a meaningful create/add heading without requiring one
                # exact string.
                headings = self.page.locator(
                    "h1:visible, h2:visible, h3:visible, "
                    "[role='heading']:visible"
                )
                heading_count = headings.count()
                for index in range(min(heading_count, 20)):
                    try:
                        heading = " ".join(
                            headings.nth(index).inner_text().split()
                        ).lower()
                    except Exception:
                        continue

                    if (
                        "create" in heading
                        and ("group" in heading or "bouquet" in heading)
                    ):
                        Logger.info(
                            f"Bouquet Management create heading detected: "
                            f"{heading}"
                        )
                        return True

            except Exception:
                pass

            self.page.wait_for_timeout(300)

        return False


    def crawl_bouquet_management(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """
        Deep-crawl Bouquet Management.

        Flow:
            listing
              -> Add Bouquet Group
              -> capture the actual create-group UI
              -> Cancel
              -> return to listing

        Important:
        Do not require an exact "Create Group" heading. The create UI can be
        rendered differently across application versions/environments.
        A failure in this deep flow must not terminate the complete crawler.
        """
        results = []
        Logger.section("Content Management -> Bouquet Management")

        # --------------------------------------------------------------
        # Listing page
        # --------------------------------------------------------------
        try:
            self.page.get_by_text(
                "Bouquet Management",
                exact=True,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )
            self.page.wait_for_timeout(500)

            screenshot = self.screenshot_engine.capture(
                page=self.page,
                menu=menu_name,
                submenu="Bouquet Management",
            )
            ui_structure = self.bouquet_management_ui_detector.detect_listing(
                self.page
            )
            components = self.component_detector.detect(self.page)

            Logger.success(
                "Bouquet Management listing screenshot captured."
            )
            Logger.success(
                "Bouquet Management listing UI structure captured."
            )

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

        except Exception as exc:
            Logger.error(
                "Unable to capture Bouquet Management listing."
            )
            Logger.error(str(exc))
            return results

        # --------------------------------------------------------------
        # Add Bouquet Group
        # --------------------------------------------------------------
        Logger.info(
            "Bouquet Management: clicking Add Bouquet Group..."
        )

        try:
            add_button = self.page.locator("button").filter(
                has_text="Add Bouquet Group"
            ).first

            if add_button.count() == 0:
                add_button = self.page.get_by_text(
                    "Add Bouquet Group",
                    exact=True,
                ).first

            add_button.wait_for(
                state="visible",
                timeout=15000,
            )
            add_button.scroll_into_view_if_needed()
            add_button.click()

            Logger.success(
                "Bouquet Management: Add Bouquet Group clicked."
            )

        except Exception as exc:
            Logger.error(
                "Unable to click Add Bouquet Group."
            )
            Logger.error(str(exc))
            return results

        # --------------------------------------------------------------
        # Wait for actual create UI
        # --------------------------------------------------------------
        create_ready = self._wait_for_bouquet_create_group(
            timeout_ms=15000
        )

        if not create_ready:
            Logger.error(
                "Bouquet Management: create-group UI did not appear "
                "after clicking Add Bouquet Group."
            )

            # Diagnostic only. Never let this screen stop the full crawl.
            try:
                visible_text = self.page.locator("body").inner_text(
                    timeout=3000
                )
                lines = [
                    line.strip()
                    for line in visible_text.splitlines()
                    if line.strip()
                ]
                Logger.info(
                    "Bouquet create UI rendered text sample: "
                    + " | ".join(lines[:30])
                )
            except Exception as diagnostic_exc:
                Logger.debug(
                    f"Unable to read Bouquet create UI text: {diagnostic_exc}"
                )

            return results

        self.page.wait_for_timeout(500)

        # --------------------------------------------------------------
        # Capture create-group UI
        # --------------------------------------------------------------
        try:
            create_screenshot = self.screenshot_engine.capture(
                page=self.page,
                menu=menu_name,
                submenu="Bouquet Management - Create Group",
            )
            create_ui_structure = (
                self.bouquet_management_ui_detector.detect_create_group(
                    self.page
                )
            )
            create_components = self.component_detector.detect(self.page)

            Logger.success(
                "Bouquet Management Create Group screenshot captured."
            )
            Logger.success(
                "Bouquet Management Create Group UI structure captured."
            )

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

        except Exception as exc:
            Logger.error(
                "Unable to capture Bouquet Management Create Group UI."
            )
            Logger.error(str(exc))
            results.append({
                "menu": menu_name,
                "submenu": "Bouquet Management - Create Group",
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
                "type": "BOUQUET_MANAGEMENT_CREATE_GROUP",
            })

        # --------------------------------------------------------------
        # Cancel and return to landing page
        # --------------------------------------------------------------
        Logger.info(
            "Bouquet Management: clicking Cancel to return to landing page..."
        )

        try:
            cancel_button = self.page.get_by_role(
                "button",
                name="Cancel",
                exact=True,
            ).first

            if cancel_button.count() == 0:
                cancel_button = self.page.get_by_text(
                    "Cancel",
                    exact=True,
                ).first

            cancel_button.wait_for(
                state="visible",
                timeout=15000,
            )
            cancel_button.click()

            self.page.get_by_text(
                "Bouquet Management",
                exact=True,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            Logger.success(
                "Returned to Bouquet Management landing page after Cancel."
            )

        except Exception as exc:
            Logger.warning(
                "Bouquet Management: unable to confirm return to landing page."
            )
            Logger.warning(str(exc))

        return results


    def _capture_system_configuration_screen(
        self,
        menu_name: str,
        submenu_name: str,
        screen_type: str,
    ) -> dict:
        """Capture a System Configuration screen with static UI structure.

        The System Configuration pages are simple routed forms/tables.  They
        already navigate successfully, but the generic crawler only records
        components.  This helper records the stable UI contract as well, while
        deliberately excluding input values, table row data, and select options.
        """
        self.page.locator("body").wait_for(state="visible", timeout=15000)
        self.page.wait_for_timeout(1000)

        # Use the existing screenshot engine; do not change its behavior.
        screenshot = self.screenshot_engine.capture(
            page=self.page,
            menu=menu_name,
            submenu=submenu_name,
        )

        ui_structure = self.page.evaluate("""
        () => {
            const clean = value => (value || "").replace(/\\s+/g, " ").trim();
            const uniqueStrings = values => [...new Set(values.filter(Boolean))];

            const structure = {
                headings: [],
                labels: [],
                inputs: [],
                selects: [],
                checkboxes: [],
                radio_buttons: [],
                buttons: [],
                tabs: [],
                tables: [],
                links: []
            };

            document.querySelectorAll(
                "h1,h2,h3,h4,h5,h6,[role='heading']"
            ).forEach(el => {
                const text = clean(el.innerText || el.textContent);
                if (text) structure.headings.push({type: "heading", text});
            });

            document.querySelectorAll("label").forEach(el => {
                const text = clean(el.innerText || el.textContent);
                if (text) structure.labels.push({type: "label", text});
            });

            document.querySelectorAll("input,textarea").forEach(el => {
                const type = (el.getAttribute("type") ||
                    (el.tagName.toLowerCase() === "textarea" ? "textarea" : "text"))
                    .toLowerCase();

                const item = {
                    type: el.tagName.toLowerCase() === "textarea" ? "textarea" : "input",
                    input_type: type,
                    placeholder: el.getAttribute("placeholder") || "",
                    aria_label: el.getAttribute("aria-label") || ""
                };

                if (type === "checkbox") {
                    structure.checkboxes.push(item);
                } else if (type === "radio") {
                    structure.radio_buttons.push(item);
                } else {
                    structure.inputs.push(item);
                }
            });

            document.querySelectorAll("select,mat-select,[role='combobox']").forEach(el => {
                structure.selects.push({
                    type: el.tagName.toLowerCase(),
                    aria_label: el.getAttribute("aria-label") || "",
                    role: el.getAttribute("role") || ""
                });
            });

            document.querySelectorAll("button,[role='button']").forEach(el => {
                const text = clean(
                    el.innerText ||
                    el.textContent ||
                    el.getAttribute("aria-label") ||
                    el.getAttribute("title")
                );
                if (text) structure.buttons.push({type: "button", text});
            });

            document.querySelectorAll("[role='tab'],mat-tab").forEach(el => {
                const text = clean(el.innerText || el.textContent);
                if (text) structure.tabs.push({type: "tab", text});
            });

            document.querySelectorAll("table").forEach(table => {
                const columns = [];
                table.querySelectorAll("thead th, thead td, tr:first-child th, tr:first-child td")
                    .forEach(cell => {
                        const text = clean(cell.innerText || cell.textContent);
                        if (text && !columns.includes(text)) columns.push(text);
                    });
                structure.tables.push({type: "table", columns});
            });

            document.querySelectorAll("a").forEach(el => {
                const text = clean(el.innerText || el.textContent);
                if (text) structure.links.push({type: "link", text});
            });

            // Deduplicate each collection while preserving order.
            for (const key of Object.keys(structure)) {
                const seen = new Set();
                structure[key] = structure[key].filter(item => {
                    const value = JSON.stringify(item);
                    if (seen.has(value)) return false;
                    seen.add(value);
                    return true;
                });
            }

            return structure;
        }
        """)

        components = self.component_detector.detect(self.page)

        return {
            "menu": menu_name,
            "submenu": submenu_name,
            "status": "SUCCESS",
            "navigation_type": "INTERNAL",
            "url": self.page.url,
            "title": self.page.title(),
            "load_time": 0,
            "error": None,
            "screenshot": str(screenshot) if screenshot else None,
            "screenshots": [str(screenshot)] if screenshot else [],
            "components": components,
            "ui_structure": ui_structure,
            "type": screen_type,
        }


    def crawl_device_propagator(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """
        Deep-crawl System Configuration -> Device Propagator.

        Flow:
          Device Propagator listing
              -> capture listing
              -> first row View/eye CTA
              -> ZIP Details
              -> capture details
              -> Back
              -> verify Device Propagator listing is restored

        The existing ScreenshotEngine is used unchanged.
        """
        results = []

        Logger.section("System Configuration -> Device Propagator")

        # --------------------------------------------------------------
        # Capture the Device Propagator listing first.
        # --------------------------------------------------------------
        try:
            listing = self._capture_system_configuration_screen(
                menu_name=menu_name,
                submenu_name=submenu_name,
                screen_type="DEVICE_PROPAGATOR",
            )
            results.append(listing)
            Logger.success("Device Propagator listing captured.")
        except Exception as exc:
            Logger.error("Unable to capture Device Propagator listing.")
            Logger.error(str(exc))
            return results

        # --------------------------------------------------------------
        # Open the first ZIP record through its eye/View action.
        # --------------------------------------------------------------
        try:
            rows = self.page.locator("table tbody tr")
            if rows.count() == 0:
                rows = self.page.locator("tbody tr")

            if rows.count() == 0:
                Logger.warning(
                    "NO_DATA: No Device Propagator table row available."
                )
                return results

            row = rows.first

            # The UI uses an eye icon for the row action. Keep the selector
            # flexible because the icon may be exposed through id, aria-label,
            # title, or a nested Material icon.
            view = row.locator(
                "#viewIcon, "
                "[id*='view' i], "
                "[aria-label*='view' i], "
                "[title*='view' i]"
            ).first

            if view.count() == 0:
                view = row.locator(
                    "button:has(mat-icon), "
                    "[role='button']:has(mat-icon)"
                ).first

            if view.count() == 0:
                Logger.warning(
                    "NO_DATA: Device Propagator View/eye CTA not found."
                )
                return results

            view.wait_for(state="visible", timeout=15000)
            view.scroll_into_view_if_needed()
            view.click(timeout=5000)

            # Verify that the details state actually loaded before capturing.
            self.page.get_by_text(
                "ZIP Details",
                exact=True,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )
            self.page.wait_for_timeout(800)

            Logger.success(
                "Device Propagator first ZIP Details screen opened."
            )

        except Exception as exc:
            Logger.warning(
                "Unable to open Device Propagator ZIP Details."
            )
            Logger.warning(str(exc))
            return results

        # --------------------------------------------------------------
        # Capture ZIP Details.
        # --------------------------------------------------------------
        try:
            # Use capture_details so this remains compatible with the
            # existing long-screen/part-splitting behavior without changing
            # ScreenshotEngine itself.
            screenshots = self.screenshot_engine.capture_details(
                page=self.page,
                menu=menu_name,
                submenu=f"{submenu_name} - Details",
            )
            screenshot = screenshots[0] if screenshots else None

            components = self.component_detector.detect(self.page)

            # Device Propagator ZIP Details is a card-based Angular page.
            # Its static field names are rendered as div/span text rather than
            # semantic <label> elements, so the generic detector only sees
            # the Service Status heading. Capture the actual static field names
            # from the rendered page while excluding dynamic values.
            ui_structure = self.page.evaluate("""
            () => {
                const clean = value => (value || "").replace(/\\s+/g, " ").trim();
                const visible = el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
                };

                const structure = {
                    headings: [],
                    labels: [],
                    inputs: [],
                    selects: [],
                    checkboxes: [],
                    radio_buttons: [],
                    buttons: [],
                    tabs: [],
                    tables: [],
                    links: []
                };

                const addUnique = (bucket, item) => {
                    if (!structure[bucket].some(x => JSON.stringify(x) === JSON.stringify(item))) {
                        structure[bucket].push(item);
                    }
                };

                // Attach stable human-readable context to form controls so a
                // comparison can identify the field/section, not only its tag.
                const controlContext = el => {
                    const label = clean(el.getAttribute("aria-label") || el.getAttribute("placeholder") ||
                        (el.labels ? Array.from(el.labels).map(x => clean(x.innerText || x.textContent)).filter(Boolean).join(" / ") : "") ||
                        (el.closest("mat-form-field,.mat-mdc-form-field")?.querySelector("mat-label,.mdc-floating-label")?.textContent || ""));
                    const section = el.closest("mat-card,mat-expansion-panel,fieldset,section,form,.card,.panel") ;
                    let sectionName = "";
                    if (section) {
                        const heading = section.querySelector("h1,h2,h3,h4,h5,h6,[role='heading'],legend,mat-panel-title");
                        sectionName = clean(heading?.innerText || heading?.textContent || "");
                    }
                    return {label: label.slice(0, 100), section: sectionName.slice(0, 100)};
                };

                document.querySelectorAll("h1,h2,h3,h4,h5,h6,[role='heading']").forEach(el => {
                    if (!visible(el)) return;
                    const text = clean(el.innerText || el.textContent);
                    if (text) addUnique("headings", {type: "heading", text});
                });

                // ZIP Details is rendered as non-semantic header text.
                document.querySelectorAll("body *").forEach(el => {
                    if (!visible(el)) return;
                    const text = clean(el.innerText || el.textContent);
                    if (text === "ZIP Details") addUnique("headings", {type: "heading", text});
                });

                const staticLabels = [
                    "Upload ID", "SCPC File Name", "MAP File Name", "Uploaded By",
                    "Status", "Total Devices", "Device Chipset Type",
                    "Start Date & Time", "Completed Date & Time",
                    "SCPC Files Upload", "KMS MAP Upload", "KMS SCD Upload",
                    "KMS OSC Upload", "KMS IID Upload", "Account Manager Import",
                    "Operator IEP Upload"
                ];

                for (const label of staticLabels) {
                    const found = Array.from(document.querySelectorAll("body *"))
                        .some(el => visible(el) && clean(el.innerText || el.textContent) === label);
                    if (found) addUnique("labels", {type: "label", text: label});
                }

                document.querySelectorAll("label").forEach(el => {
                    if (!visible(el)) return;
                    const text = clean(el.innerText || el.textContent);
                    if (text) addUnique("labels", {type: "label", text});
                });

                document.querySelectorAll("input,textarea").forEach(el => {
                    if (!visible(el)) return;
                    const type = (el.getAttribute("type") ||
                        (el.tagName.toLowerCase() === "textarea" ? "textarea" : "text")).toLowerCase();
                    const item = {
                        type: el.tagName.toLowerCase() === "textarea" ? "textarea" : "input",
                        input_type: type,
                        placeholder: el.getAttribute("placeholder") || "",
                        aria_label: el.getAttribute("aria-label") || "",
                        ...controlContext(el)
                    };
                    if (type === "checkbox") addUnique("checkboxes", item);
                    else if (type === "radio") addUnique("radio_buttons", item);
                    else addUnique("inputs", item);
                });

                document.querySelectorAll("select,mat-select,[role='combobox']").forEach(el => {
                    if (!visible(el)) return;
                    addUnique("selects", {
                        type: el.tagName.toLowerCase(),
                        aria_label: el.getAttribute("aria-label") || "",
                        role: el.getAttribute("role") || "",
                        ...controlContext(el)
                    });
                });

                document.querySelectorAll("button,[role='button']").forEach(el => {
                    if (!visible(el)) return;
                    const text = clean(el.innerText || el.textContent ||
                        el.getAttribute("aria-label") || el.getAttribute("title"));
                    if (text) addUnique("buttons", {type: "button", text});
                });

                document.querySelectorAll("[role='tab'],mat-tab").forEach(el => {
                    if (!visible(el)) return;
                    const text = clean(el.innerText || el.textContent);
                    if (text) addUnique("tabs", {type: "tab", text});
                });

                document.querySelectorAll("table").forEach(table => {
                    if (!visible(table)) return;
                    const columns = [];
                    table.querySelectorAll("thead th, thead td, tr:first-child th, tr:first-child td").forEach(cell => {
                        const text = clean(cell.innerText || cell.textContent);
                        if (text && !columns.includes(text)) columns.push(text);
                    });
                    addUnique("tables", {type: "table", columns});
                });

                document.querySelectorAll("a").forEach(el => {
                    if (!visible(el)) return;
                    const text = clean(el.innerText || el.textContent);
                    if (text) addUnique("links", {type: "link", text});
                });

                return structure;
            }
            """)

            results.append({
                "menu": menu_name,
                "submenu": f"{submenu_name} - Details",
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": self.page.title(),
                "load_time": 0,
                "error": None,
                "screenshot": str(screenshot) if screenshot else None,
                "screenshots": [str(path) for path in screenshots],
                "components": components,
                "ui_structure": ui_structure,
                "type": "DEVICE_PROPAGATOR_DETAILS",
            })

            Logger.success(
                "Device Propagator ZIP Details screenshot + UI structure captured."
            )

        except Exception as exc:
            Logger.error(
                "Unable to capture Device Propagator ZIP Details."
            )
            Logger.error(str(exc))

        # --------------------------------------------------------------
        # Return to Device Propagator listing.
        # --------------------------------------------------------------
        try:
            back = self.page.get_by_role(
                "button",
                name=re.compile(r"back", re.I),
            ).first

            if back.count() == 0:
                back = self.page.locator(
                    "button:has(mat-icon), "
                    "[role='button']:has(mat-icon)"
                ).filter(
                    has=self.page.locator("mat-icon")
                ).first

            if back.count() > 0 and back.is_visible(timeout=1000):
                back.click(timeout=5000)
            else:
                self.page.go_back()

            self.page.get_by_text(
                "Device Propagator",
                exact=False,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )
            self.page.wait_for_timeout(700)

            Logger.success(
                "Returned to Device Propagator listing after ZIP Details."
            )

        except Exception as exc:
            Logger.warning(
                "Unable to confirm return to Device Propagator listing."
            )
            Logger.warning(str(exc))

        return results


    def _cohort_ui_structure(self) -> dict:
        """Collect stable UI structure for Cohort Management screens."""
        return self.page.evaluate("""
        () => {
            const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
            const unique = values => [...new Set(values.filter(Boolean))];
            const textOf = el => clean(
                el.getAttribute('aria-label') ||
                el.getAttribute('mattooltip') ||
                el.getAttribute('title') ||
                el.innerText || el.textContent
            );
            const structure = {
                headings: [], labels: [], buttons: [], tabs: [],
                inputs: [], links: [], table_headers: [],
                sections: [], cards: []
            };
            document.querySelectorAll('h1,h2,h3,h4,[role="heading"]').forEach(el => {
                const value = textOf(el);
                if (value) structure.headings.push(value);
            });
            document.querySelectorAll('label,mat-label,.mat-mdc-form-field label').forEach(el => {
                const value = textOf(el);
                if (value) structure.labels.push(value);
            });
            document.querySelectorAll('button,[role="button"]').forEach(el => {
                const value = textOf(el);
                if (value) structure.buttons.push(value);
            });
            document.querySelectorAll('[role="tab"],mat-tab-label,.generic-child-tab').forEach(el => {
                const value = textOf(el);
                if (value) structure.tabs.push(value);
            });
            document.querySelectorAll('input,textarea,select,[role="combobox"]').forEach(el => {
                const value = clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('type'));
                if (value) structure.inputs.push(value);
            });
            document.querySelectorAll('a[href]').forEach(el => {
                const value = textOf(el);
                if (value) structure.links.push(value);
            });
            document.querySelectorAll('table thead th,[role="columnheader"]').forEach(el => {
                const value = textOf(el);
                if (value) structure.table_headers.push(value);
            });
            document.querySelectorAll('mat-expansion-panel-header,[role="region"] h1,[role="region"] h2,[role="region"] h3').forEach(el => {
                const value = textOf(el);
                if (value) structure.sections.push(value);
            });
            document.querySelectorAll('mat-card,.mat-mdc-card,[class*="device-family"],[class*="config-card"]').forEach(el => {
                const value = textOf(el.querySelector('h1,h2,h3,h4,[class*="title"]') || el);
                if (value) structure.cards.push(value);
            });
            for (const key of Object.keys(structure)) structure[key] = unique(structure[key]);
            return structure;
        }
        """)

    def crawl_device_configuration(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """Demo-safe Device Configuration handling: capture the initial listing only.

        Do not change filters, open View/Edit, or interact with configuration rows.
        """
        results = []
        menu_name = "Community Management"
        submenu_name = "Device Configuration"
        Logger.section("Community Management -> Device Configuration")
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        try:
            self.page.wait_for_timeout(800)
            screenshot = self.screenshot_engine.capture(
                page=self.page,
                menu=menu_name,
                submenu=f"{submenu_name} - Listing",
            )
            results.append({
                "menu": menu_name,
                "submenu": f"{submenu_name} - Listing",
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": self.page.title(),
                "screen_name": f"{submenu_name} - Listing",
                "load_time": 0,
                "error": None,
                "type": "DEVICE_CONFIGURATION_LISTING",
                "screenshot": str(screenshot),
                "screenshots": [str(screenshot)],
                "components": self.component_detector.detect(self.page),
                "ui_structure": {},
            })
            Logger.success("Device Configuration initial listing screenshot captured; skipped filters, View, and Edit.")
        except Exception as exc:
            Logger.error(f"Device Configuration initial listing screenshot failed: {exc}")
            results.append(self._coverage_record(
                menu_name,
                f"{submenu_name} - Listing",
                "FAILED_TO_CAPTURE",
                "Initial listing screenshot failed.",
                error=str(exc),
                url=self.page.url,
                record_type="DEVICE_CONFIGURATION_LISTING",
            ))
        return results

    def crawl_software_configurations(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """Capture Software Configurations listing and one View details screen.

        Read-only: opens the first configuration using its View action.
        """
        results = []
        screen_type = "SOFTWARE_CONFIGURATIONS"
        Logger.section("Community Management -> Software Configurations")

        def capture_record(title: str, screenshots: list):
            return {
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "SUCCESS",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": title,
                "screen_name": title,
                "load_time": 0,
                "error": None,
                "screenshot": str(screenshots[0]) if screenshots else None,
                "screenshots": [str(path) for path in screenshots],
                "components": self.component_detector.detect(self.page),
                "ui_structure": self._cohort_ui_structure(),
                "type": screen_type,
            }

        try:
            self.page.locator("body").wait_for(state="visible", timeout=20000)
            self.page.get_by_text("Software Configurations", exact=False).first.wait_for(
                state="visible", timeout=20000
            )
            self.page.wait_for_timeout(600)

            listing_shot = self.screenshot_engine.capture(
                page=self.page, menu=menu_name, submenu=submenu_name
            )
            listing = capture_record("Software Configurations - Listing", [listing_shot])
            listing["submenu"] = f"{submenu_name} - Listing"
            results.append(listing)
            Logger.success("Software Configurations listing screenshot + UI structure captured.")

            # Ensure at least one row is available. The page may append more
            # records through Load More, but one representative detail is enough.
            rows = None
            for selector in (
                "table tbody tr:visible",
                "mat-row:visible, .mat-mdc-row:visible",
                "[role='row']:visible",
            ):
                candidate_rows = self.page.locator(selector)
                if candidate_rows.count():
                    rows = candidate_rows
                    break

            if rows is None or rows.count() == 0:
                Logger.warning("Software Configurations listing captured, but no visible row was found.")
                return results

            row = rows.first
            view = row.locator(
                "button[aria-label*='view' i], [role='button'][aria-label*='view' i], "
                "button[title*='view' i], button[mattooltip*='view' i], "
                "button:has(mat-icon:text-is('visibility')), "
                "button:has(mat-icon:text-is('remove_red_eye')), "
                "button:has(svg[aria-label*='view' i]), button:has(svg[aria-label*='eye' i])"
            ).first
            if view.count() == 0:
                actions = row.locator(
                    "button:visible, [role='button']:visible, a[role='button']:visible"
                )
                if not actions.count():
                    Logger.warning("No View action found for the first software configuration.")
                    return results
                # The screenshot shows View (eye) as the first row action,
                # followed by Clone and Delete.
                view = actions.first

            previous_url = self.page.url
            previous_body = self.page.locator("body").inner_text(timeout=5000)
            view.click(timeout=8000)
            self.page.wait_for_timeout(700)

            try:
                self.page.get_by_text("Software Configurations Details", exact=False).first.wait_for(
                    state="visible", timeout=12000
                )
            except Exception:
                current_body = self.page.locator("body").inner_text(timeout=5000)
                if self.page.url == previous_url and current_body == previous_body:
                    raise RuntimeError("View action did not open Software Configurations Details.")

            self.page.wait_for_timeout(400)
            detail_shots = self.screenshot_engine.capture_details(
                page=self.page,
                menu=menu_name,
                submenu=f"{submenu_name} - Details",
            )
            detail = capture_record("Software Configurations - Details", detail_shots)
            detail["submenu"] = f"{submenu_name} - Details"
            results.append(detail)
            Logger.success("Software Configurations details screenshot + UI structure captured.")

            back = self.page.locator(
                "button[aria-label*='back' i], button[title*='back' i], "
                "[role='button'][aria-label*='back' i]"
            ).first
            if back.count() and back.is_visible():
                back.click(timeout=5000)
            else:
                self.page.go_back()
            self.page.get_by_text("Software Configurations", exact=False).first.wait_for(
                state="visible", timeout=15000
            )
            Logger.success("Returned to Software Configurations listing.")

        except Exception as exc:
            Logger.error("Software Configurations crawl failed.")
            Logger.error(str(exc))
            results.append({
                "menu": menu_name,
                "submenu": submenu_name,
                "status": "FAIL",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": "Software Configurations crawl failure",
                "load_time": 0,
                "error": str(exc),
                "screenshot": None,
                "screenshots": [],
                "components": [],
                "ui_structure": {},
                "type": screen_type,
            })
        return results

    def crawl_experience_management(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """Capture Experience Management listing and one representative View details page.

        Read-only: opens the first experience using its View action; it does not
        clone, edit, publish, or delete experiences.
        """
        results = []
        screen_type = "EXPERIENCE_MANAGEMENT"
        Logger.section("Community Management -> Experience Management")

        def capture_record(title: str, screenshots: list):
            return {
                "menu": menu_name, "submenu": submenu_name, "status": "SUCCESS",
                "navigation_type": "INTERNAL", "url": self.page.url,
                "title": title, "screen_name": title, "load_time": 0, "error": None,
                "screenshot": str(screenshots[0]) if screenshots else None,
                "screenshots": [str(path) for path in screenshots],
                "components": self.component_detector.detect(self.page),
                "ui_structure": self._cohort_ui_structure(), "type": screen_type,
            }

        try:
            self.page.locator("body").wait_for(state="visible", timeout=20000)
            self.page.get_by_text("Experience Management", exact=False).first.wait_for(
                state="visible", timeout=20000
            )
            self.page.wait_for_timeout(600)
            listing_shot = self.screenshot_engine.capture(
                page=self.page, menu=menu_name, submenu=submenu_name
            )
            listing = capture_record("Experience Management - Listing", [listing_shot])
            listing["submenu"] = f"{submenu_name} - Listing"
            results.append(listing)
            Logger.success("Experience Management listing screenshot + UI structure captured.")

            # Capture one representative detail layout rather than every record.
            row = None
            for selector in ("table tbody tr:visible", "mat-row:visible, .mat-mdc-row:visible", "[role='row']:visible"):
                rows = self.page.locator(selector)
                if rows.count():
                    row = rows.first
                    break
            if row is None:
                Logger.warning("Experience listing captured, but no visible experience row was found.")
                return results

            view = row.locator(
                "button[aria-label*='view' i], [role='button'][aria-label*='view' i], "
                "button[title*='view' i], button[mattooltip*='view' i], "
                "button:has(mat-icon:text-is('visibility')), "
                "button:has(mat-icon:text-is('remove_red_eye')), "
                "button:has(svg[aria-label*='view' i]), button:has(svg[aria-label*='eye' i])"
            ).first
            if view.count() == 0:
                actions = row.locator("button:visible, [role='button']:visible, a[role='button']:visible")
                if not actions.count():
                    Logger.warning("No View action found for the first experience; details not opened.")
                    return results
                # Eye/View is first in the row, ahead of Edit, Clone, and Delete.
                view = actions.first

            old_url = self.page.url
            view.click(timeout=8000)
            self.page.wait_for_timeout(700)
            try:
                self.page.get_by_text("Experience Details", exact=True).wait_for(
                    state="visible", timeout=15000
                )
            except Exception:
                if self.page.url == old_url:
                    raise RuntimeError("View action did not open Experience Details.")

            self.page.wait_for_timeout(400)
            detail_shots = self.screenshot_engine.capture_details(
                page=self.page, menu=menu_name, submenu=f"{submenu_name} - Details"
            )
            detail = capture_record("Experience Management - Experience Details", detail_shots)
            detail["submenu"] = f"{submenu_name} - Experience Details"
            results.append(detail)
            Logger.success("Experience Details screenshot + UI structure captured separately.")

            back = self.page.locator("button[aria-label*='back' i], button[title*='back' i]").first
            if back.count() and back.is_visible(timeout=1000):
                back.click(timeout=5000)
            else:
                self.page.go_back()
            self.page.get_by_text("Experience Management", exact=False).first.wait_for(
                state="visible", timeout=15000
            )
            Logger.success("Returned to Experience Management listing.")

        except Exception as exc:
            Logger.error("Experience Management deep crawl failed.")
            Logger.error(str(exc))
            results.append({
                "menu": menu_name, "submenu": submenu_name, "status": "FAIL",
                "navigation_type": "INTERNAL", "url": self.page.url,
                "title": "Experience Management crawl failure", "load_time": 0,
                "error": str(exc), "screenshot": None, "screenshots": [],
                "components": [], "ui_structure": {}, "type": screen_type,
            })
        return results

    def crawl_cohort_management(
        self,
        menu_name: str,
        submenu_name: str,
    ) -> list[dict]:
        """Capture the listing and the topmost cohort's View/Edit screens for demo.

        Cohort selection is data-driven: use the first visible cohort row, regardless of its name.
        Edit is read-only: capture the form, then Cancel; never Save/Update.
        """
        results = []
        screen_type = "COHORT_MANAGEMENT"
        Logger.section("Community Management -> Cohort Management")

        host = (self.page.url or "").lower()
        if "opc.astro.stage.xp.irdeto.com" in host:
            environment = "stage"
        elif "opc.astro.live.xp.irdeto.com" in host:
            environment = "production"
        else:
            environment = "unknown"
        required_cohort = None

        def capture_record(name: str, screenshot_paths: list, kind: str,
                           status: str = "SUCCESS", error=None, cohort_name=None):
            return {
                "menu": menu_name,
                "submenu": f"{submenu_name} - {name}",
                "status": status,
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": name,
                "screen_name": name,
                "load_time": 0,
                "error": error,
                "screenshot": str(screenshot_paths[0]) if screenshot_paths else None,
                "screenshots": [str(path) for path in screenshot_paths],
                "components": self.component_detector.detect(self.page),
                "ui_structure": self._cohort_ui_structure(),
                "type": kind,
                "environment": environment,
                **({"cohort_name": cohort_name} if cohort_name else {}),
            }

        def find_rows():
            for selector in ("table tbody tr:visible", "mat-row:visible, .mat-mdc-row:visible", "[role='row']:visible"):
                loc = self.page.locator(selector)
                if loc.count():
                    return loc
            return self.page.locator("__visionqa_no_cohort_rows__")

        def row_name(row) -> str:
            try:
                return " ".join(row.locator("td, [role='cell']").first.inner_text(timeout=1500).split())
            except Exception:
                return ""

        def action(row, name: str):
            for selector in (
                f"#{name}Icon", f"[id*='{name}Icon' i]",
                f"button[aria-label*='{name}' i]", f"button[title*='{name}' i]",
                f"button[mattooltip*='{name}' i]", f"[role='button'][aria-label*='{name}' i]",
            ):
                loc = row.locator(selector).first
                try:
                    if loc.count() and loc.is_visible():
                        return loc
                except Exception:
                    pass
            icon_names = {"view": ("visibility", "remove_red_eye"), "edit": ("edit", "create")}
            for icon_name in icon_names.get(name.lower(), ()):
                loc = row.locator(f"button:has(mat-icon:text-is('{icon_name}'))").first
                if loc.count() and loc.is_visible():
                    return loc
            return None

        def cancel_edit_safely():
            try:
                cancel = self.page.get_by_role("button", name=re.compile(r"^\s*cancel\s*$", re.I)).last
                if cancel.count() and cancel.is_visible(timeout=1200):
                    cancel.click(timeout=4000)
                    self.page.wait_for_timeout(300)
                    leave = self.page.get_by_role("button", name=re.compile(r"^\s*leave page\s*$", re.I)).last
                    if leave.count() and leave.is_visible(timeout=1000):
                        leave.click(timeout=3000)
                    else:
                        stay = self.page.get_by_role("button", name=re.compile(r"^\s*stay on page\s*$", re.I)).last
                        if stay.count() and stay.is_visible(timeout=500):
                            stay.click(timeout=2000)
                            cancel = self.page.get_by_role("button", name=re.compile(r"^\s*cancel\s*$", re.I)).last
                            if cancel.count() and cancel.is_visible(timeout=1000):
                                cancel.click(timeout=3000)
                                leave = self.page.get_by_role("button", name=re.compile(r"^\s*leave page\s*$", re.I)).last
                                if leave.count() and leave.is_visible(timeout=1000):
                                    leave.click(timeout=3000)
                self.page.wait_for_timeout(500)
            except Exception as exc:
                Logger.warning(f"Could not safely exit Cohort Edit form: {exc}")

        try:
            self.page.locator("body").wait_for(state="visible", timeout=20000)
            self.page.get_by_text("Cohort Management", exact=False).first.wait_for(state="visible", timeout=20000)
            self.page.wait_for_timeout(700)
            listing_screenshot = self.screenshot_engine.capture(
                page=self.page, menu=menu_name, submenu=f"{submenu_name} - Listing"
            )
            results.append(capture_record("Cohort Management - Listing", [listing_screenshot], "COHORT_MANAGEMENT_LISTING"))
            Logger.success(f"Cohort Management listing captured for {environment}.")

            # DEMO MODE: select the topmost visible cohort, without a hard-coded cohort name.
            rows = find_rows()
            if rows.count() == 0:
                self.page.wait_for_timeout(1000)
                rows = find_rows()
            if rows.count() == 0:
                raise RuntimeError("No cohort rows are visible in the Cohort Management listing.")
            target_row = rows.nth(0)
            required_cohort = row_name(target_row).strip()
            if not required_cohort:
                raise RuntimeError("The topmost cohort row is visible but its name could not be read.")
            Logger.info(f"Demo mode: targeting topmost cohort row '{required_cohort}'.")

            # View fixed cohort.
            view = action(target_row, "view")
            if view is None:
                raise RuntimeError(f"No View action found for required cohort '{required_cohort}'.")
            listing_url = self.page.url
            old_body = self.page.locator("body").inner_text(timeout=5000)
            view.click(timeout=8000)
            self.page.wait_for_timeout(800)
            try:
                self.page.wait_for_function(
                    "([u,t]) => location.href !== u || (document.body && document.body.innerText !== t)",
                    arg=[listing_url, old_body], timeout=12000,
                )
            except Exception:
                pass
            if self.page.url == listing_url and self.page.locator("body").inner_text(timeout=5000) == old_body:
                raise RuntimeError(f"View did not open details for '{required_cohort}'.")
            view_shots = self.screenshot_engine.capture_details(
                page=self.page, menu=menu_name,
                submenu=f"{submenu_name} - {required_cohort} - View",
            )
            view_record = capture_record(
                f"Cohort Management - {required_cohort} - View", view_shots,
                "COHORT_MANAGEMENT_VIEW", cohort_name=required_cohort,
            )
            # Stable cross-environment identity: the topmost cohort is captured on each environment.
            view_record["submenu"] = f"{submenu_name} - Selected Cohort - View"
            view_record["screen_name"] = "Cohort Management - Selected Cohort - View"
            view_record["comparison_key"] = "cohort_management:selected_cohort:view"
            results.append(view_record)
            Logger.success(f"Captured View for topmost {environment} cohort '{required_cohort}'.")

            # Return to listing; route-based detail pages can use browser history.
            try:
                drawer = self.page.locator("mat-sidenav.mat-drawer-opened, mat-drawer.mat-drawer-opened").last
                if drawer.count() and drawer.is_visible(timeout=500):
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(300)
            except Exception:
                pass
            if self.page.url != listing_url:
                self.page.go_back()
                self.page.wait_for_timeout(700)
            self.page.get_by_text("Cohort Management", exact=False).first.wait_for(state="visible", timeout=15000)

            # Re-find exact row after route/list re-render.
            rows = find_rows()
            target_row = None
            for i in range(rows.count()):
                row = rows.nth(i)
                if row_name(row).casefold() == required_cohort.casefold():
                    target_row = row
                    break
            if target_row is None:
                raise RuntimeError(f"Could not re-find '{required_cohort}' for Edit capture.")

            edit = action(target_row, "edit")
            if edit is None:
                raise RuntimeError(f"No Edit action found for required cohort '{required_cohort}'.")
            edit.click(timeout=8000)
            self.page.wait_for_timeout(700)
            edit_shots = self.screenshot_engine.capture_details(
                page=self.page, menu=menu_name,
                submenu=f"{submenu_name} - {required_cohort} - Edit",
            )
            edit_record = capture_record(
                f"Cohort Management - {required_cohort} - Edit", edit_shots,
                "COHORT_MANAGEMENT_EDIT", cohort_name=required_cohort,
            )
            edit_record["submenu"] = f"{submenu_name} - Selected Cohort - Edit"
            edit_record["screen_name"] = "Cohort Management - Selected Cohort - Edit"
            edit_record["comparison_key"] = "cohort_management:selected_cohort:edit"
            results.append(edit_record)
            Logger.success(f"Captured Edit form for topmost {environment} cohort '{required_cohort}' (no save).")
            cancel_edit_safely()

        except Exception as exc:
            Logger.error(f"Cohort Management crawl failed for {environment}: {exc}")
            results.append({
                "menu": menu_name,
                "submenu": f"{submenu_name} - {required_cohort or 'Required Cohort'}",
                "status": "FAILED_TO_OPEN_OR_CAPTURE",
                "navigation_type": "INTERNAL",
                "url": self.page.url,
                "title": f"Cohort Management - {required_cohort or 'Required Cohort'}",
                "screen_name": "Cohort Management - Required Cohort - Capture Failure",
                "comparison_key": "cohort_management:selected_cohort:capture_failure",
                "load_time": 0,
                "error": str(exc),
                "screenshot": None,
                "screenshots": [],
                "components": [],
                "ui_structure": {},
                "type": screen_type,
                "environment": environment,
                "cohort_name": required_cohort,
            })
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


    def _capture_household_profile_screen(
        self,
        menu_name: str,
        submenu_name: str,
        screen_type: str,
    ) -> dict:
        """Capture Household Profile screenshot + static UI structure."""
        # Use the existing ScreenshotEngine detail capture for Household screens.
        # It automatically keeps short screens as a single viewport screenshot
        # and splits long screens into readable viewport-sized parts.
        screenshots = self.screenshot_engine.capture_details(
            page=self.page,
            menu=menu_name,
            submenu=submenu_name,
        )

        screenshot = screenshots[0] if screenshots else None

        components = self.component_detector.detect(self.page)

        ui_structure = self.page.evaluate("""
        () => {
            const clean = value =>
                (value || "").replace(/\\s+/g, " ").trim();

            const structure = {
                headings: [],
                labels: [],
                buttons: [],
                tabs: [],
                inputs: [],
                links: []
            };

            document.querySelectorAll(
                "h1,h2,h3,h4,[role='heading']"
            ).forEach(el => {
                const text = clean(el.innerText);
                if (text) structure.headings.push(text);
            });

            document.querySelectorAll("label").forEach(el => {
                const text = clean(el.innerText);
                if (text) structure.labels.push(text);
            });

            document.querySelectorAll(
                "button,[role='button']"
            ).forEach(el => {
                const text = clean(
                    el.innerText ||
                    el.getAttribute("aria-label") ||
                    el.getAttribute("title")
                );
                if (text) structure.buttons.push(text);
            });

            document.querySelectorAll(
                "[role='tab'],mat-tab"
            ).forEach(el => {
                const text = clean(el.innerText);
                if (text) structure.tabs.push(text);
            });

            document.querySelectorAll(
                "input,textarea,select"
            ).forEach(el => {
                structure.inputs.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute("type") || "",
                    name: el.getAttribute("name") || "",
                    placeholder: el.getAttribute("placeholder") || ""
                });
            });

            document.querySelectorAll("a").forEach(el => {
                const text = clean(el.innerText);
                if (text) structure.links.push(text);
            });

            for (const key of Object.keys(structure)) {
                structure[key] = [...new Set(
                    structure[key].map(item =>
                        typeof item === "string"
                            ? item
                            : JSON.stringify(item)
                    )
                )].map(item => {
                    try {
                        return JSON.parse(item);
                    } catch {
                        return item;
                    }
                });
            }

            return structure;
        }
        """)

        return {
            "menu": menu_name,
            "submenu": submenu_name,
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
            "type": screen_type,
        }

    def _open_first_household_profile(self, profile_type: str) -> bool:
        """Open the View/Details action for a row whose profile type is Adult or Kids.

        Do not click the bare text: it can match a tab, filter, or page label and
        leave the listing open, which previously caused duplicate screenshots.
        """
        Logger.info(f"Searching for first available {profile_type} profile row...")

        try:
            rows = self.page.locator("table tbody tr:visible")
            if rows.count() == 0:
                rows = self.page.locator("tbody tr:visible")

            for index in range(rows.count()):
                row = rows.nth(index)
                try:
                    row_text = " ".join(row.inner_text().split())
                    if profile_type.casefold() not in row_text.casefold():
                        continue

                    view = row.locator("#viewIcon").first
                    if view.count() == 0:
                        view = row.locator(
                            "[id*='view' i], [aria-label*='View' i], "
                            "[title*='View' i], button:has-text('View')"
                        ).first

                    if view.count() == 0:
                        Logger.debug(
                            f"{profile_type} row {index + 1} has no View action."
                        )
                        continue

                    view.wait_for(state="visible", timeout=5000)
                    view.scroll_into_view_if_needed()
                    view.click()
                    self.page.wait_for_timeout(800)

                    # Require evidence that the listing was left before reporting
                    # a successful details navigation.
                    if self.page.locator("table tbody tr:visible").count() > 0:
                        # Some OPC details render in a drawer over the listing.
                        drawer = self.page.locator(
                            "mat-sidenav.mat-drawer-opened, "
                            "mat-drawer.mat-drawer-opened, "
                            "[role='dialog']:visible"
                        )
                        if drawer.count() == 0:
                            Logger.warning(
                                f"{profile_type} View action did not open a visible details panel."
                            )
                            return False

                    Logger.success(f"Opened {profile_type} profile Details.")
                    return True
                except Exception as exc:
                    Logger.debug(
                        f"Unable to open {profile_type} row {index + 1}: {exc}"
                    )

            Logger.warning(f"NO_DATA: No viewable {profile_type} profile row found.")
            return False
        except Exception as exc:
            Logger.warning(f"NO_DATA: Unable to locate {profile_type} profile row: {exc}")
            return False

    def crawl_household(self, menu_name: str, submenu_name: str) -> list[dict]:
        """Deep-crawl Household Manager -> Household, tab by tab."""
        results = []

        Logger.section("Household Manager -> Household")

        # Use the correct test Household ID for the current environment.
        # Stage: 603901141 | Production: 11110001
        household_test_id = get_household_test_id(self.page.url)
        Logger.info(
            f"Using Household test ID {household_test_id} for {self.page.url}"
        )

        try:
            search_input = self.page.locator("input[placeholder='Search ID']").first
            search_input.wait_for(state="visible", timeout=15000)
            search_input.fill(household_test_id)

            search_button = self.page.get_by_role("button", name="Search", exact=True).first
            search_button.wait_for(state="visible", timeout=15000)
            search_button.click()
            Logger.success(f"Household ID {household_test_id} submitted.")

            self.page.get_by_text(
                f"Household Manager ({household_test_id})", exact=False
            ).first.wait_for(state="visible", timeout=30000)
            self.page.wait_for_timeout(1000)
        except Exception as exc:
            Logger.error("Unable to open Household Overview.")
            Logger.error(str(exc))
            return results

        def capture(name: str, screen_type: str) -> None:
            try:
                record = self._capture_household_profile_screen(
                    menu_name=menu_name,
                    submenu_name=name,
                    screen_type=screen_type,
                )
                results.append(record)
                Logger.success(f"{name} captured.")
            except Exception as exc:
                Logger.error(f"Unable to capture {name}.")
                Logger.error(str(exc))

        def click_tab(name: str, nested: bool = False) -> bool:
            """Click a Household tab and verify that the requested tab became active."""
            try:
                if nested:
                    groups = self.page.locator("mat-tab-group")
                    if groups.count() > 0:
                        group = groups.last
                        candidates = group.get_by_role("tab", name=name, exact=True)
                        if candidates.count() == 0:
                            candidates = group.get_by_text(name, exact=True)
                    else:
                        candidates = self.page.get_by_role("tab", name=name, exact=True)
                else:
                    candidates = self.page.get_by_role("tab", name=name, exact=True)
                    if candidates.count() == 0:
                        candidates = self.page.get_by_text(name, exact=True)

                for i in range(candidates.count()):
                    el = candidates.nth(i)
                    if not el.is_visible(timeout=1000):
                        continue

                    el.scroll_into_view_if_needed()
                    el.click(timeout=5000)
                    self.page.wait_for_timeout(500)

                    # Verify the clicked tab is actually selected. This prevents
                    # capturing the previous screen when Angular navigation is slow.
                    selected = self.page.locator(
                        "[role='tab'][aria-selected='true']"
                    ).filter(has_text=name)
                    if selected.count() > 0 and selected.first.is_visible(timeout=3000):
                        self.page.wait_for_timeout(700)
                        return True

                    # Angular Material may not expose aria-selected on the tab.
                    # Fall back to checking the visible tab text/style state.
                    if el.is_visible(timeout=1000):
                        self.page.wait_for_timeout(700)
                        return True

            except Exception as exc:
                Logger.warning(f"Unable to open {name} tab: {exc}")
            return False

        def click_back(label: str) -> bool:
            try:
                candidates = self.page.get_by_role("button", name=label, exact=True)
                if candidates.count() == 0:
                    candidates = self.page.get_by_text(label, exact=True)
                for i in range(candidates.count()):
                    el = candidates.nth(i)
                    if el.is_visible(timeout=1000):
                        el.scroll_into_view_if_needed()
                        el.click()
                        self.page.wait_for_timeout(900)
                        return True
            except Exception as exc:
                Logger.warning(f"Unable to click {label}: {exc}")
            return False

        def click_first_view(device_family: str | None = None) -> bool:
            """Open the first View row, optionally restricted to a device family."""
            try:
                rows = self.page.locator("table tbody tr:visible")
                if rows.count() == 0:
                    rows = self.page.locator("tbody tr:visible")
                if rows.count() == 0:
                    Logger.warning("NO_DATA: No table row available for View CTA.")
                    return False

                row = None
                if device_family:
                    # Resolve the Device Family column by its header instead of
                    # assuming a fixed column index across UI revisions.
                    headers = self.page.locator(
                        "table thead th, table thead [role='columnheader'], [role='columnheader']"
                    )
                    family_column = None
                    for index in range(headers.count()):
                        if headers.nth(index).inner_text().strip().casefold() == "device family":
                            family_column = index
                            break

                    for index in range(rows.count()):
                        candidate = rows.nth(index)
                        cells = candidate.locator("td, [role='cell']")
                        if family_column is not None and cells.count() > family_column:
                            family_value = cells.nth(family_column).inner_text().strip()
                        else:
                            # Fallback for tables where header/cell roles differ.
                            family_value = candidate.inner_text()
                        if family_value.casefold() == device_family.casefold() or (
                            family_column is None and device_family.casefold() in family_value.casefold()
                        ):
                            row = candidate
                            break

                    if row is None:
                        Logger.warning(
                            f"NO_DATA: No Household device row found for Device Family '{device_family}'."
                        )
                        return False
                    Logger.info(f"Selecting Household device with Device Family: {device_family}")
                else:
                    row = rows.first

                view = row.locator("#viewIcon").first
                if view.count() == 0:
                    view = row.locator(
                        "[id*='view' i], [aria-label*='View' i], [title*='View' i]"
                    ).first
                if view.count() == 0:
                    Logger.warning("NO_DATA: View CTA not found in selected row.")
                    return False
                view.wait_for(state="visible", timeout=15000)
                view.scroll_into_view_if_needed()
                view.click()
                self.page.wait_for_timeout(1200)
                return True
            except Exception as exc:
                Logger.warning(f"Unable to click View CTA: {exc}")
                return False

        # Overview must be captured before any child tab.
        capture("Household - Overview", "HOUSEHOLD_OVERVIEW")

        # Household tab.
        if click_tab("Household"):
            capture("Household - Household", "HOUSEHOLD_DETAILS")

        # Device tab.
        if click_tab("Device"):
            # Capture the Device listing itself as well as the selected device
            # Details screen. The listing is a distinct UI screen and must not
            # be omitted just because comparison focuses on one device family.
            capture("Household - Device", "HOUSEHOLD_DEVICE_LISTING")
            if click_first_view(device_family="Ultra Box v2"):
                capture("Household - Device - Ultra Box v2 Details", "HOUSEHOLD_DEVICE_DETAILS")
                click_back("Device List")

        # Profile tab: one Adult and one Kids, returning through Profile List CTA.
        if click_tab("Profile"):
            capture("Household - Profile", "HOUSEHOLD_PROFILE_LISTING")
            if self._open_first_household_profile("Adult"):
                capture("Household - Profile - Adult Details", "HOUSEHOLD_ADULT_PROFILE_DETAILS")
                click_back("Profile List")
                self.page.wait_for_timeout(700)
            if self._open_first_household_profile("Kids"):
                capture("Household - Profile - Kids Details", "HOUSEHOLD_KIDS_PROFILE_DETAILS")
                click_back("Profile List")

        # Entitlement tab: listing only.
        if click_tab("Entitlement"):
            capture("Household - Entitlement", "HOUSEHOLD_ENTITLEMENT_LISTING")

        # Rentals: listing -> first View -> details -> Rentals List.
        if click_tab("Rentals"):
            capture("Household - Rentals", "HOUSEHOLD_RENTALS_LISTING")
            if click_first_view():
                capture("Household - Rentals - Details", "HOUSEHOLD_RENTAL_DETAILS")
                click_back("Rentals List")

        # Recordings: listing -> first View -> details -> Recording List.
        if click_tab("Recordings"):
            capture("Household - Recordings", "HOUSEHOLD_RECORDINGS_LISTING")
            if click_first_view():
                capture("Household - Recordings - Details", "HOUSEHOLD_RECORDING_DETAILS")
                click_back("Recording List")

        # Sessions: select only an Ultra Box v2 session for comparison.
        # Do not capture the unfiltered listing because it contains multiple
        # device families and would introduce unrelated environment differences.
        if click_tab("Sessions"):
            if click_first_view(device_family="Ultra Box v2"):
                capture("Household - Sessions - Ultra Box v2 Details", "HOUSEHOLD_SESSION_DETAILS")

                for nested_tab, screen_type in (
                    ("Configuration", "HOUSEHOLD_SESSION_CONFIGURATION"),
                    ("Entitlement", "HOUSEHOLD_SESSION_ENTITLEMENT"),
                    ("Generator", "HOUSEHOLD_SESSION_GENERATOR"),
                ):
                    if not click_tab(nested_tab, nested=True):
                        continue

                    # Only expand accordion headers belonging to the Session Details
                    # content. Never click generic aria-expanded controls because they
                    # can include unrelated navigation/menu elements.
                    try:
                        panels = self.page.locator(
                            "mat-tab-body.mat-tab-body-active mat-expansion-panel"
                        )
                        if panels.count() == 0:
                            panels = self.page.locator(
                                "mat-tab-body-active mat-expansion-panel"
                            )

                        for i in range(panels.count()):
                            panel = panels.nth(i)
                            header = panel.locator(
                                "mat-expansion-panel-header[aria-expanded='false']"
                            ).first
                            if header.count() and header.is_visible(timeout=1000):
                                header.scroll_into_view_if_needed()
                                header.click(timeout=5000)
                                self.page.wait_for_timeout(300)
                    except Exception as exc:
                        Logger.debug(
                            f"Accordion expansion skipped for {nested_tab}: {exc}"
                        )

                    capture(
                        f"Household - Sessions - {nested_tab}",
                        screen_type,
                    )

                click_back("Session List")

        Logger.success("Household Manager -> Household deep crawl completed.")
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
                for failed_submenu in menu_data.get("submenus", []):
                    failed_name = str(failed_submenu.get("name", "Unknown submenu"))
                    results.append(self._coverage_record(
                        menu_name,
                        failed_name,
                        "FAILED_TO_EXPAND_MENU",
                        "Menu could not be expanded; submenu crawl was not attempted.",
                        error=str(exc),
                        url=self.page.url,
                    ))
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
                        and submenu_name == "Device Propagator"
                    ):
                        device_propagator_results = self.crawl_device_propagator(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(device_propagator_results)
                        continue

                    if (
                        menu_name == "System Configuration"
                        and submenu_name in {
                            "Packager Detail Configuration",
                            "Channel Poster",
                            "Guide Metadata",
                            "Device Lookup",
                        }
                    ):
                        system_config_types = {
                            "Packager Detail Configuration": "PACKAGER_DETAIL_CONFIGURATION",
                            "Channel Poster": "CHANNEL_POSTER",
                            "Guide Metadata": "GUIDE_METADATA",
                            "Device Propagator": "DEVICE_PROPAGATOR",
                            "Device Lookup": "DEVICE_LOOKUP",
                        }
                        system_config_result = self._capture_system_configuration_screen(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                            screen_type=system_config_types[submenu_name],
                        )
                        results.append(system_config_result)
                        Logger.success(
                            f"{submenu_name}: screenshot + UI structure captured."
                        )
                        continue

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
                            submenu_data["vod_categories_discovered"] = list(
                                discovered_categories
                            )
                            expected_categories = list(dict.fromkeys(
                                [*KNOWN_VOD_CATEGORIES, *discovered_categories]
                            ))
                            submenu_data["vod_categories"] = expected_categories
                            submenu_data["vod_categories_not_discovered"] = [
                                category for category in expected_categories
                                if category not in discovered_categories
                            ]
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

                        # ALWAYS crawl Series first.
                        if "Series" in discovered_categories:
                            try:
                                Logger.info("Starting VOD → Series first.")
                                self._close_vod_details_drawer()
                                self.page.wait_for_timeout(5000)
                                series_results = self.crawl_vod_series(
                                    menu_name=menu_name,
                                    submenu_name="VOD",
                                )
                                results.extend(series_results)
                                Logger.success(
                                    f"VOD → Series completed. Captured {len(series_results)} result(s)."
                                )
                            except Exception as exc:
                                Logger.error("Unable to crawl VOD → Series.")
                                Logger.error(str(exc))
                        else:
                            Logger.warning("VOD → Series tab was not discovered in the UI.")

                        # Record expected categories that were not present in
                        # this environment's rendered tab list. These are crawl
                        # coverage gaps, not verified application absences.
                        for missing_category in submenu_data.get(
                            "vod_categories_not_discovered", []
                        ):
                            Logger.warning(
                                f"VOD category not discovered: {missing_category}. "
                                "Recording an explicit coverage status."
                            )
                            results.extend(self._vod_category_failure_records(
                                menu_name,
                                missing_category,
                                "NOT_DISCOVERED",
                                "Expected VOD category tab was not found in the rendered navigation; availability is unverified.",
                            ))

                        # Crawl every remaining VOD category after Series.
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

                                # Do not require a table before switching tabs:
                                # the currently selected category can be empty
                                # (for example Trailers) and render no table.
                                # crawl_vod_category selects the requested tab,
                                # then classifies its content state.
                                Logger.info(
                                    f"Starting VOD → {category} without requiring the previous category to have a table."
                                )

                                category_results = self.crawl_vod_category(
                                    menu_name=menu_name,
                                    category=category,
                                )
                                results.extend(category_results)

                            except Exception as exc:
                                # A single VOD category must never stop the
                                # remaining categories from being crawled.
                                Logger.error(
                                    f"Unable to start VOD → {category}."
                                )
                                Logger.error(str(exc))
                                Logger.warning(
                                    f"Skipping VOD → {category} and continuing with the next category."
                                )
                                continue

                        continue

                    if (
                        menu_name == "Household Manager"
                        and submenu_name == "Household"
                    ):
                        household_profile_results = self.crawl_household(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )

                        results.extend(household_profile_results)
                        continue

                    if (
                        str(menu_name).strip().casefold() == "community management"
                        and str(submenu_name).strip().casefold() == "device configuration"
                    ):
                        device_configuration_results = self.crawl_device_configuration(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(device_configuration_results)
                        continue

                    if (
                        str(menu_name).strip().casefold() == "community management"
                        and str(submenu_name).strip().casefold() == "software configurations"
                    ):
                        software_configuration_results = self.crawl_software_configurations(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(software_configuration_results)
                        continue

                    if (
                        str(menu_name).strip().casefold() == "community management"
                        and str(submenu_name).strip().casefold() == "experience management"
                    ):
                        experience_results = self.crawl_experience_management(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(experience_results)
                        continue

                    if (
                        str(menu_name).strip().casefold() == "community management"
                        and str(submenu_name).strip().casefold() == "cohort management"
                    ):
                        cohort_results = self.crawl_cohort_management(
                            menu_name=menu_name,
                            submenu_name=submenu_name,
                        )
                        results.extend(cohort_results)
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

        # Explicitly report known navigation entries that were not discovered.
        # This prevents the report from interpreting a navigation-discovery gap
        # as a confirmed missing screen in the target application.
        discovered_pairs = {
            (str(menu.get("name", "")).strip(), str(sub.get("name", "")).strip())
            for menu in navigation_tree
            for sub in menu.get("submenus", [])
        }
        for expected_menu, expected_submenu in sorted(KNOWN_NAVIGATION_EXPECTATIONS):
            if (expected_menu, expected_submenu) not in discovered_pairs:
                results.append(self._coverage_record(
                    expected_menu,
                    expected_submenu,
                    "NOT_DISCOVERED",
                    "Known navigation item was not present in the discovered navigation tree; availability is unverified.",
                    url=None,
                ))

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
