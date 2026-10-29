import json
from pathlib import Path

from playwright.sync_api import (
    Browser as PlaywrightBrowser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)


class Browser:
    """Browser manager for VisionQA, including optional sessionStorage restore."""

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

    def _load_storage_state(self):
        """Load standard Playwright state and VisionQA's sessionStorage extension."""
        if not self.storage_state or not Path(self.storage_state).exists():
            return None, {}

        try:
            data = json.loads(Path(self.storage_state).read_text(encoding="utf-8"))
        except Exception:
            return self.storage_state, {}

        session_extension = data.pop("_visionqa_session_storage", {})
        return data, session_extension if isinstance(session_extension, dict) else {}

    def open(self, url: str | None = None) -> Page:
        """Launch Chromium, restore saved browser state, and navigate to OPC."""
        target_url = url or self.DEFAULT_URL
        self.playwright = sync_playwright().start()

        try:
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
            )

            state, session_storage_by_host = self._load_storage_state()
            context_args = {}
            if state:
                context_args["storage_state"] = state

            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                **context_args,
            )

            # sessionStorage must be seeded before app JavaScript runs. Inject
            # only for the matching hostname; do not leak values across domains.
            if session_storage_by_host:
                serialized = json.dumps(session_storage_by_host)
                self.context.add_init_script(
                    """
                    (() => {
                        const saved = %s;
                        const values = saved[window.location.host];
                        if (!values) return;
                        for (const [key, value] of Object.entries(values)) {
                            try { window.sessionStorage.setItem(key, value); }
                            catch (_) {}
                        }
                    })();
                    """ % serialized
                )

            self.page = self.context.new_page()
            self.page.set_default_timeout(60000)
            self.page.set_default_navigation_timeout(120000)
            self.page.goto(
    target_url,
    wait_until="domcontentloaded",
    timeout=120000,
)
            return self.page
        except Exception:
            self.close()
            raise

    def is_authenticated(self) -> bool:
        if self.page is None:
            return False
        if "login" in self.page.url.lower():
            return False
        try:
            if self.page.locator("input[type='password']").count():
                return False
        except Exception:
            pass
        return True

    def save_session(self, path: str) -> None:
        """Save cookies/localStorage and the current page's sessionStorage."""
        if not self.context:
            return

        self.context.storage_state(path=path)
        session_storage = {}
        page_host = None

        if self.page is not None:
            try:
                page_host = self.page.evaluate("() => window.location.host")
                session_storage = self.page.evaluate(
                    "() => Object.fromEntries("
                    "Array.from({length: sessionStorage.length}, (_, i) => {"
                    "const key = sessionStorage.key(i);"
                    "return [key, sessionStorage.getItem(key)];"
                    "})"
                    ")"
                )
            except Exception:
                session_storage = {}

        if page_host:
            path_obj = Path(path)
            try:
                data = json.loads(path_obj.read_text(encoding="utf-8"))
            except Exception:
                data = {"cookies": [], "origins": []}
            data["_visionqa_session_storage"] = {page_host: session_storage}
            path_obj.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def delete_session(self) -> None:
        if self.storage_state and Path(self.storage_state).exists():
            Path(self.storage_state).unlink()

    def close(self) -> None:
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
