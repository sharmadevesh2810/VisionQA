from pprint import pprint

from core.browser import Browser
from core.crawler import Crawler
from core.environment import EnvironmentManager
from core.logger import Logger
from core.metadata import MetadataManager
from core.navigation import Navigation
from core.navigation_manifest import NavigationManifest
from core.tenant import TenantManager
from core.version import VersionManager


TENANT = "Astro PayTV"


def main():

    browser = Browser(
        storage_state="auth/stage.json"
    )

    page = browser.open()

    try:

        Logger.section("VisionQA")

        #
        # Authentication
        #

        Logger.section("Authentication")
        Logger.success("Loaded existing browser session.")

        #
        # Tenant
        #

        Logger.section("Tenant")

        tenant = TenantManager(page)
        tenant.switch_tenant(TENANT)

        #
        # Environment
        #

        Logger.section("Environment")

        environment_manager = EnvironmentManager(page)

        environment = environment_manager.get_environment()

        environment_manager.log()

        #
        # Version
        #

        Logger.section("Version")

        version_manager = VersionManager(page)

        version = version_manager.get_version()

        Logger.kv("Application Version", version)

        #
        # Navigation Discovery
        #

        Logger.section("Navigation Discovery")

        navigation = Navigation(page)

        navigation_tree = navigation.discover()

        Logger.kv(
            "Menus Discovered",
            len(navigation_tree)
        )

        #
        # Crawl
        #

        Logger.section("Crawler")

        crawler = Crawler(
            page=page,
            environment=environment,
            version=version,
        )

        results = crawler.crawl(
            navigation_tree
        )

        #
        # Metadata
        #

        Logger.section("Metadata")

        snapshot_dir = MetadataManager().write(
            environment=environment,
            version=version,
            tenant=TENANT,
            url=page.url,
        )

        Logger.success(
            f"metadata.json written to {snapshot_dir}"
        )

        #
        # Navigation Manifest
        #

        Logger.section("Navigation Manifest")

        NavigationManifest(snapshot_dir).write(results)

        Logger.success("navigation.json created.")

        #
        # Summary
        #

        Logger.section("Run Summary")

        Logger.kv("Environment", environment)
        Logger.kv("Version", version)
        Logger.kv("Tenant", TENANT)
        Logger.kv("Pages Crawled", len(results))

        success = sum(
            1
            for r in results
            if r["status"] == "SUCCESS"
        )

        Logger.kv("Successful", success)
        Logger.kv("Failed", len(results) - success)

        pprint(results)

        input("\nPress ENTER to close...")

    finally:

        browser.close()


if __name__ == "__main__":
    main()