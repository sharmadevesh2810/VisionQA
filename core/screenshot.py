"""
Screenshot Engine

Responsible for capturing screenshots of application pages.

Responsibilities:
- Wait until the page is stable
- Detect application scroll containers
- Capture normal application pages
- Capture long/detail pages in readable viewport-sized parts
- Create snapshot directories
- Sanitize filenames
"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Page

from core.constants import SCREENSHOT_EXTENSION
from core.logger import Logger


class ScreenshotEngine:
    """
    Screenshot Engine.

    Normal pages:
        <submenu>.png

    Detail pages:
        <submenu> - Part 01.png
        <submenu> - Part 02.png
        ...
    """

    def __init__(
        self,
        snapshot_dir: Path,
        stabilization_time: int = 3000,
        full_page: bool = True,
    ):
        self.snapshot_dir = snapshot_dir
        self.stabilization_time = stabilization_time
        self.full_page = full_page

    # -------------------------------------------------------------------------
    # Public API - NORMAL PAGE
    # -------------------------------------------------------------------------

    def capture(
        self,
        page: Page,
        menu: str,
        submenu: str,
    ) -> Path:
        """
        Capture a normal application page.

        Existing behavior is preserved for normal pages.
        """

        self._wait_until_stable(page)

        directory = self._prepare_directory(menu)

        filename = (
            self._sanitize(submenu)
            + SCREENSHOT_EXTENSION
        )

        screenshot_path = directory / filename

        restore_scroll = self._expand_main_scroll_container(page)

        try:
            page.wait_for_timeout(500)

            page.screenshot(
                path=str(screenshot_path),
                full_page=self.full_page,
            )

        finally:
            self._restore_scroll_container(
                page,
                restore_scroll,
            )

        Logger.success(
            f"Screenshot saved -> {screenshot_path}"
        )

        return screenshot_path

    # -------------------------------------------------------------------------
    # Public API - DETAIL PAGE
    # -------------------------------------------------------------------------

    def capture_details(
        self,
        page: Page,
        menu: str,
        submenu: str,
        overlap: int = 80,
    ) -> list[Path]:
        """
        Capture a long/detail page as readable viewport-sized screenshots.

        The page is NOT zoomed out and is NOT compressed into one giant image.

        Example:
            VOD - Series - Details - Part 01.png
            VOD - Series - Details - Part 02.png
            VOD - Series - Details - Part 03.png
        """

        self._wait_until_stable(page)

        directory = self._prepare_directory(menu)

        # Make sure the application has rendered the details content.
        page.wait_for_timeout(1000)

        dimensions = page.evaluate(
            """
            () => {
                const root =
                    document.scrollingElement ||
                    document.documentElement;

                return {
                    documentHeight: root.scrollHeight,
                    viewportHeight: window.innerHeight,
                    viewportWidth: window.innerWidth,
                    windowScrollY: window.scrollY
                };
            }
            """
        )

        document_height = int(
            dimensions["documentHeight"]
        )

        viewport_height = int(
            dimensions["viewportHeight"]
        )

        original_scroll = int(
            dimensions["windowScrollY"]
        )

        Logger.info(
            f"Details page height: {document_height}px"
        )

        Logger.info(
            f"Viewport height: {viewport_height}px"
        )

        # ---------------------------------------------------------------------
        # IMPORTANT:
        #
        # If the application uses an internal scroll container, scrolling
        # window/document may not move the actual content.
        #
        # Find the real scroll container and use it when available.
        # ---------------------------------------------------------------------

        scroll_info = self._find_scroll_container(page)

        if scroll_info:
            Logger.info(
                "Using application internal scroll container for detail capture."
            )

            container_selector = scroll_info["selector"]
            scroll_height = int(scroll_info["scrollHeight"])
            container_height = int(scroll_info["clientHeight"])

            effective_height = max(
                scroll_height,
                document_height,
            )

            effective_viewport = max(
                container_height,
                viewport_height,
            )

            scroll_target = "container"

        else:
            Logger.info(
                "No application scroll container detected. "
                "Using document scroll."
            )

            effective_height = document_height
            effective_viewport = viewport_height
            container_selector = None
            scroll_target = "document"

        # ---------------------------------------------------------------------
        # Short page
        # ---------------------------------------------------------------------

        if effective_height <= effective_viewport + 20:

            screenshot_path = directory / (
                self._sanitize(submenu)
                + SCREENSHOT_EXTENSION
            )

            page.screenshot(
                path=str(screenshot_path),
                full_page=False,
            )

            Logger.success(
                f"Detail screenshot saved -> {screenshot_path}"
            )

            return [screenshot_path]

        # ---------------------------------------------------------------------
        # Calculate readable screenshot positions
        # ---------------------------------------------------------------------

        step = max(
            effective_viewport - overlap,
            100,
        )

        max_scroll = max(
            effective_height - effective_viewport,
            0,
        )

        positions = list(
            range(
                0,
                max_scroll + 1,
                step,
            )
        )

        if max_scroll not in positions:
            positions.append(max_scroll)

        positions = sorted(set(positions))

        screenshot_paths: list[Path] = []

        # ---------------------------------------------------------------------
        # Capture each viewport
        # ---------------------------------------------------------------------

        try:

            for index, position in enumerate(
                positions,
                start=1,
            ):

                if scroll_target == "container":

                    page.evaluate(
                        """
                        ({selector, position}) => {
                            const container =
                                document.querySelector(selector);

                            if (container) {
                                container.scrollTop = position;
                            }
                        }
                        """,
                        {
                            "selector": container_selector,
                            "position": position,
                        },
                    )

                else:

                    page.evaluate(
                        """
                        (position) => {
                            const root =
                                document.scrollingElement ||
                                document.documentElement;

                            root.scrollTo({
                                top: position,
                                behavior: "instant"
                            });
                        }
                        """,
                        position,
                    )

                # Allow Angular/material components to settle after scrolling.
                page.wait_for_timeout(350)

                filename = (
                    f"{self._sanitize(submenu)}"
                    f" - Part {index:02d}"
                    f"{SCREENSHOT_EXTENSION}"
                )

                screenshot_path = (
                    directory / filename
                )

                page.screenshot(
                    path=str(screenshot_path),
                    full_page=False,
                )

                screenshot_paths.append(
                    screenshot_path
                )

                Logger.success(
                    f"Detail screenshot saved -> {screenshot_path}"
                )

        finally:

            # -----------------------------------------------------------------
            # Restore original scroll position
            # -----------------------------------------------------------------

            try:

                if scroll_target == "container":

                    page.evaluate(
                        """
                        ({selector}) => {
                            const container =
                                document.querySelector(selector);

                            if (container) {
                                container.scrollTop = 0;
                            }
                        }
                        """,
                        {
                            "selector": container_selector,
                        },
                    )

                else:

                    page.evaluate(
                        """
                        (position) => {
                            const root =
                                document.scrollingElement ||
                                document.documentElement;

                            root.scrollTo({
                                top: position,
                                behavior: "instant"
                            });
                        }
                        """,
                        original_scroll,
                    )

            except Exception as exc:

                Logger.warning(
                    "Unable to restore detail page scroll position."
                )

                Logger.warning(str(exc))

        Logger.success(
            f"Detail page captured in "
            f"{len(screenshot_paths)} readable parts."
        )

        return screenshot_paths

    # -------------------------------------------------------------------------
    # Scroll Container Detection
    # -------------------------------------------------------------------------

    def _find_scroll_container(
        self,
        page: Page,
    ) -> dict | None:
        """
        Find the most likely application content scroll container.

        Returns a stable CSS selector and dimensions.
        """

        try:

            result = page.evaluate(
                """
                () => {

                    const elements =
                        Array.from(
                            document.querySelectorAll('*')
                        );

                    const candidates = [];

                    for (const el of elements) {

                        const style =
                            window.getComputedStyle(el);

                        const rect =
                            el.getBoundingClientRect();

                        const scrollable =
                            el.scrollHeight >
                            el.clientHeight + 100;

                        const verticalOverflow =
                            style.overflowY === 'auto' ||
                            style.overflowY === 'scroll';

                        if (
                            scrollable &&
                            verticalOverflow &&
                            rect.width > 500 &&
                            rect.height > 300
                        ) {

                            candidates.push({
                                el,
                                area:
                                    rect.width *
                                    rect.height,
                                scrollHeight:
                                    el.scrollHeight,
                                clientHeight:
                                    el.clientHeight
                            });
                        }
                    }

                    candidates.sort(
                        (a, b) => b.area - a.area
                    );

                    if (!candidates.length) {
                        return null;
                    }

                    const target =
                        candidates[0].el;

                    // Prefer id when available.
                    if (target.id) {

                        return {
                            selector:
                                "#" +
                                CSS.escape(target.id),
                            scrollHeight:
                                target.scrollHeight,
                            clientHeight:
                                target.clientHeight
                        };
                    }

                    // Otherwise assign a temporary unique attribute.
                    const marker =
                        "visionqa-scroll-container";

                    document
                        .querySelectorAll(
                            "[data-visionqa-scroll]"
                        )
                        .forEach(
                            el =>
                                el.removeAttribute(
                                    "data-visionqa-scroll"
                                )
                        );

                    target.setAttribute(
                        "data-visionqa-scroll",
                        marker
                    );

                    return {
                        selector:
                            '[data-visionqa-scroll="' +
                            marker +
                            '"]',
                        scrollHeight:
                            target.scrollHeight,
                        clientHeight:
                            target.clientHeight
                    };
                }
                """
            )

            return result

        except Exception as exc:

            Logger.warning(
                "Unable to detect application scroll container."
            )

            Logger.warning(str(exc))

            return None

    # -------------------------------------------------------------------------
    # Existing Full-Page Scroll Handling
    # -------------------------------------------------------------------------

    def _expand_main_scroll_container(
        self,
        page: Page,
    ) -> list[dict]:
        """
        Detect and temporarily expand the main application scroll container.

        Used only by the normal full-page capture().
        """

        try:

            result = page.evaluate(
                """
                () => {

                    const elements = Array.from(
                        document.querySelectorAll('*')
                    );

                    const candidates = [];

                    for (const el of elements) {

                        const style =
                            window.getComputedStyle(el);

                        const rect =
                            el.getBoundingClientRect();

                        const scrollable =
                            el.scrollHeight >
                            el.clientHeight + 100;

                        const verticalOverflow =
                            style.overflowY === 'auto' ||
                            style.overflowY === 'scroll';

                        if (
                            scrollable &&
                            verticalOverflow &&
                            rect.width > 500 &&
                            rect.height > 300
                        ) {

                            candidates.push({
                                element: el,
                                area:
                                    rect.width *
                                    rect.height
                            });
                        }
                    }

                    candidates.sort(
                        (a, b) => b.area - a.area
                    );

                    if (!candidates.length) {
                        return [];
                    }

                    const target =
                        candidates[0].element;

                    const original = {
                        height:
                            target.style.height,
                        maxHeight:
                            target.style.maxHeight,
                        minHeight:
                            target.style.minHeight,
                        overflow:
                            target.style.overflow,
                        overflowY:
                            target.style.overflowY
                    };

                    target.dataset.visionqaExpanded =
                        "true";

                    target.style.height =
                        target.scrollHeight + "px";

                    target.style.maxHeight =
                        "none";

                    target.style.minHeight =
                        target.scrollHeight + "px";

                    target.style.overflow =
                        "visible";

                    target.style.overflowY =
                        "visible";

                    return [{
                        height:
                            original.height,
                        maxHeight:
                            original.maxHeight,
                        minHeight:
                            original.minHeight,
                        overflow:
                            original.overflow,
                        overflowY:
                            original.overflowY
                    }];
                }
                """
            )

            if result:

                Logger.info(
                    "Expanded main scroll container for full screenshot."
                )

            else:

                Logger.info(
                    "No internal scroll container detected."
                )

            return result

        except Exception as exc:

            Logger.warning(
                "Unable to expand main scroll container."
            )

            Logger.warning(str(exc))

            return []

    def _restore_scroll_container(
        self,
        page: Page,
        restore_data: list[dict],
    ) -> None:
        """
        Restore the application's scroll container after normal screenshot.
        """

        if not restore_data:
            return

        try:

            page.evaluate(
                """
                (restoreData) => {

                    const target =
                        document.querySelector(
                            '[data-visionqa-expanded="true"]'
                        );

                    if (!target) {
                        return;
                    }

                    const original =
                        restoreData[0];

                    target.style.height =
                        original.height;

                    target.style.maxHeight =
                        original.maxHeight;

                    target.style.minHeight =
                        original.minHeight;

                    target.style.overflow =
                        original.overflow;

                    target.style.overflowY =
                        original.overflowY;

                    delete target.dataset
                        .visionqaExpanded;
                }
                """,
                restore_data,
            )

        except Exception as exc:

            Logger.warning(
                "Unable to restore scroll container."
            )

            Logger.warning(str(exc))

    # -------------------------------------------------------------------------
    # Directory Handling
    # -------------------------------------------------------------------------

    def _prepare_directory(
        self,
        menu: str,
    ) -> Path:

        directory = (
            self.snapshot_dir
            / self._sanitize(menu)
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        return directory

    # -------------------------------------------------------------------------
    # Page Stabilization
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Filename Handling
    # -------------------------------------------------------------------------

    @staticmethod
    def _sanitize(
        name: str,
    ) -> str:

        name = re.sub(
            r'[<>:"/\\|?*]',
            "_",
            name,
        )

        name = re.sub(
            r"\s+",
            " ",
            name,
        )

        return name.strip()
