"""
Environment Manager

Responsible for detecting the application environment from the current URL.

Responsibilities:
- Read the current browser URL
- Extract hostname
- Extract base URL
- Detect environment (stage, test, prod, etc.)
"""

from __future__ import annotations

from urllib.parse import urlparse

from playwright.sync_api import Page

from core.constants import UNKNOWN
from core.logger import Logger


class EnvironmentManager:
    """
    Detects the current application environment.

    Example
    -------
    URL:
        https://opc.astro.stage.xp.irdeto.com

    Environment:
        stage
    """

    ENVIRONMENT_KEYWORDS = (
        "stage",
        "test",
        "prod",
        "preprod",
        "qa",
        "uat",
        "sit",
        "perf",
        "demo",
        "dev",
    )

    def __init__(self, page: Page):
        self.page = page

        self.url = page.url

        parsed = urlparse(self.url)

        self.hostname = parsed.hostname or ""

        self.base_url = f"{parsed.scheme}://{self.hostname}"

        self.environment = self._detect_environment()

    def _detect_environment(self) -> str:
        """
        Detect the environment from the hostname.

        Returns
        -------
        str
            Detected environment name or "unknown".
        """

        hostname = self.hostname.lower()

        for env in self.ENVIRONMENT_KEYWORDS:
            if env in hostname:
                return env

        return UNKNOWN

    def get_environment(self) -> str:
        """
        Return the detected environment.
        """

        return self.environment

    def log(self) -> None:
        """
        Print detected environment information.
        """

        Logger.section("Environment Manager")

        Logger.kv("URL", self.url)
        Logger.kv("Hostname", self.hostname)
        Logger.kv("Base URL", self.base_url)
        Logger.kv("Environment", self.environment)

        Logger.success("Environment detected successfully.")