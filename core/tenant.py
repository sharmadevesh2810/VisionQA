from playwright.sync_api import Page, expect


class TenantManager:
    def __init__(self, page: Page):
        self.page = page

    def get_current_tenant(self) -> str:
        """Returns the currently selected tenant."""
        return (
            self.page
            .locator(".tenant-selection .heading")
            .inner_text()
            .strip()
        )

    def switch_tenant(self, tenant_name: str):
        """Switch to the required tenant if it's not already selected."""

        current_tenant = self.get_current_tenant()

        print(f"Current Tenant : {current_tenant}")

        if current_tenant == tenant_name:
            print(f"✅ Already on '{tenant_name}'")
            return

        print(f"🔄 Switching to '{tenant_name}'...")

        # Open tenant dropdown
        self.page.locator(".tenant-selection").click()

        # Select tenant
        self.page.get_by_text(tenant_name, exact=True).click()

        # Wait until heading changes
        expect(
            self.page.locator(".tenant-selection .heading")
        ).to_have_text(tenant_name)

        # Wait for page reload
        self.page.wait_for_load_state("networkidle")

        print(f"✅ Switched to '{tenant_name}'")