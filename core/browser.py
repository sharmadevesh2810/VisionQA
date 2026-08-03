from pathlib import Path

from playwright.sync_api import (
    Browser as PlaywrightBrowser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)


class Browser:
    """
    Browser manager for VisionQA.
    """

    DEFAULT_URL = "https://opc.astro.stage.xp.irdeto.com/"

    def __init__(
        self,
        headless: bool = False,
        storage_state: str | None = None,
        slow_mo: int = 200,
    ):

        self.headless = headless
        self.storage_state = storage_state
        self.slow_mo = slow_mo

        self.playwright: Playwright | None = None
        self.browser: PlaywrightBrowser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def open(
        self,
        url: str | None = None,
    ) -> Page:
        """
        Launch browser and navigate to the given URL.

        If no URL is supplied, VisionQA uses DEFAULT_URL.
        """

        target_url = url or self.DEFAULT_URL

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )

        context_args = {}

        if (
            self.storage_state
            and Path(self.storage_state).exists()
        ):
            context_args["storage_state"] = self.storage_state

        self.context = self.browser.new_context(
            viewport={
                "width": 1920,
                "height": 1080,
            },
            **context_args,
        )

        self.page = self.context.new_page()

        self.page.goto(
            target_url,
            wait_until="networkidle",
            timeout=60000,
        )

        return self.page

    def is_authenticated(self) -> bool:
        """
        Returns True if the current page is not the login page.
        """

        if self.page is None:
            return False

        if "login" in self.page.url.lower():
            return False

        try:
            if self.page.locator(
                "input[type='password']"
            ).count():
                return False
        except Exception:
            pass

        return True

    def save_session(
        self,
        path: str,
    ) -> None:

        if self.context:
            self.context.storage_state(path=path)

    def delete_session(self) -> None:

        if (
            self.storage_state
            and Path(self.storage_state).exists()
        ):
            Path(self.storage_state).unlink()

    def close(self) -> None:

        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()