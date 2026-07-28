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

    Usage:

        browser = Browser(storage_state="auth/stage.json")
        page = browser.open()

        ...

        browser.close()
    """

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

    def open(self) -> Page:
        """
        Launch browser and return a Playwright page.
        """

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

        return self.page

    def save_session(self, path: str) -> None:
        """
        Save browser session.
        """

        if self.context:
            self.context.storage_state(path=path)

    def close(self) -> None:
        """
        Close browser and cleanup resources.
        """

        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()