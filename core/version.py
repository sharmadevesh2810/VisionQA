from playwright.sync_api import Page


class VersionManager:

    def __init__(self, page: Page):
        self.page = page

    def get_version(self) -> str:
        """
        Reads the application version from the footer.

        Returns:
            Example: 26.07.0-pl

        If the version element is not available, returns "unknown"
        instead of stopping the VisionQA execution.
        """

        try:
            version_locator = self.page.locator(".version-control")

            if not version_locator.is_visible(timeout=5000):
                return "unknown"

            version_text = version_locator.inner_text(timeout=5000).strip()

            if not version_text:
                return "unknown"

            return version_text.replace("Version:", "").strip()

        except Exception:
            return "unknown"
