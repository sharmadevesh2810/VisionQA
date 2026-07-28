from playwright.sync_api import Page


class VersionManager:

    def __init__(self, page: Page):
        self.page = page

    def get_version(self) -> str:
        """
        Reads the application version from the footer.

        Returns:
            Example: 26.07.0-pl
        """

        version_text = (
            self.page
            .locator(".version-control")
            .inner_text()
            .strip()
        )

        return version_text.replace("Version:", "").strip()