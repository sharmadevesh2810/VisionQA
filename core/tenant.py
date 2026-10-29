from playwright.sync_api import Page, expect, TimeoutError as PlaywrightTimeoutError


class TenantManager:
    def __init__(self, page: Page):
        self.page = page

    def get_current_tenant(self) -> str:
        """Return the selected tenant, with diagnostics if the selector is absent."""
        locator = self.page.locator(".tenant-selection .heading")

        try:
            locator.wait_for(state="visible", timeout=15000)
            return locator.inner_text(timeout=5000).strip()
        except PlaywrightTimeoutError as exc:
            try:
                current_url = self.page.url
            except Exception:
                current_url = "<unavailable>"

            try:
                page_title = self.page.title()
            except Exception:
                page_title = "<unavailable>"

            try:
                body_text = self.page.locator("body").inner_text(timeout=3000)
                body_text = " ".join(body_text.split())[:500]
            except Exception:
                body_text = "<body text unavailable>"

            raise RuntimeError(
                "Could not locate the visible tenant selector "
                "'.tenant-selection .heading'. "
                f"Current URL: {current_url!r}; page title: {page_title!r}; "
                f"visible page text (first 500 chars): {body_text!r}. "
                "Check whether OPC is showing a login/redirect/error page or "
                "whether the tenant selector markup has changed."
            ) from exc

    def switch_tenant(self, tenant_name: str):
        """Switch to the required tenant if it is not already selected."""
        current_tenant = self.get_current_tenant()
        print(f"Current Tenant : {current_tenant}")

        if current_tenant == tenant_name:
            print(f"Already on '{tenant_name}'")
            return

        print(f"Switching to '{tenant_name}'...")

        tenant_selector = self.page.locator(".tenant-selection")
        tenant_selector.wait_for(state="visible", timeout=15000)
        tenant_selector.click()

        option = self.page.get_by_text(tenant_name, exact=True)
        option.wait_for(state="visible", timeout=15000)
        option.click()

        heading = self.page.locator(".tenant-selection .heading")
        expect(heading).to_have_text(tenant_name, timeout=30000)

        # OPC may keep background requests active; do not block on networkidle.
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except PlaywrightTimeoutError:
            pass

        print(f"Switched to '{tenant_name}'")
