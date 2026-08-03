from comparison.baseline import BaselineManager
from datetime import datetime
from pathlib import Path
from core.report import ReportManager
from core.browser import Browser
from core.constants import SNAPSHOTS_DIR
from core.crawler import Crawler
from core.environment import EnvironmentManager
from core.logger import Logger
from core.metadata import MetadataManager
from core.navigation import Navigation
from core.navigation_manifest import NavigationManifest
from core.tenant import TenantManager
from core.version import VersionManager

TENANT = "Astro PayTV"

SESSION_FILE = Path("auth/stage.json")


def main():

    #
    # Ensure auth directory exists
    #

    SESSION_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    browser = Browser(
        storage_state=str(SESSION_FILE),
    )

    page = browser.open()

    try:

        Logger.section("VisionQA")

        #
        # Authentication
        #

        Logger.section("Authentication")

        if browser.is_authenticated():

            Logger.success(
                "Loaded existing browser session."
            )

        else:

            Logger.warning(
                "No valid browser session found."
            )

            Logger.info(
                "Please login in the browser."
            )

            input(
                "\nAfter login completes, press ENTER..."
            )

            browser.save_session(
                str(SESSION_FILE)
            )

            Logger.success(
                "Browser session saved."
            )

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

        Logger.kv(
            "Application Version",
            version,
        )

        #
        # Create Run Directory
        #

        run_timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        snapshot_dir = (
            SNAPSHOTS_DIR
            / environment
            / version
            / run_timestamp
        )

        snapshot_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        #
        # Initialize Logger
        #

        Logger.initialize(
            snapshot_dir / "run.log"
        )

        Logger.kv(
            "Run Directory",
            snapshot_dir,
        )

        #
        # Navigation Discovery
        #

        Logger.section(
            "Navigation Discovery"
        )

        navigation = Navigation(page)

        navigation_tree = navigation.discover()

        Logger.kv(
            "Menus Discovered",
            len(navigation_tree),
        )

        #
        # Crawl
        #

        Logger.section("Crawler")

        crawler = Crawler(
            page=page,
            snapshot_dir=snapshot_dir,
        )

        results = crawler.crawl(
            navigation_tree
        )

        #
        # Metadata
        #

        Logger.section("Metadata")

        MetadataManager(
            snapshot_dir
        ).write(
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

        Logger.section(
            "Navigation Manifest"
        )

        NavigationManifest(
            snapshot_dir
        ).write(results)

        Logger.success(
            "navigation.json created."
        )



                #
        # HTML Report
        #

        Logger.section("HTML Report")

        ReportManager(
            snapshot_dir
        ).generate(
            environment=environment,
            version=version,
            tenant=TENANT,
            results=results,
        )

        Logger.success(
            "report.html created."
        )

        #
        # Baseline
        #

        Logger.section("Baseline")

        baseline = BaselineManager()

        if baseline.exists(
            environment,
            version,
        ):

            Logger.info(
                "Baseline already exists."
            )

        else:

            path = baseline.create(
                run_directory=snapshot_dir,
                environment=environment,
                version=version,
            )

            Logger.success(
                f"Baseline created at {path}"
            )


        #
        # Summary
        #

        Logger.section(
            "Run Summary"
        )

        Logger.kv(
            "Environment",
            environment,
        )

        Logger.kv(
            "Version",
            version,
        )

        Logger.kv(
            "Tenant",
            TENANT,
        )

        Logger.kv(
            "Run Directory",
            snapshot_dir,
        )

        Logger.kv(
            "Pages Crawled",
            len(results),
        )

        success = sum(
            1
            for r in results
            if r["status"] == "SUCCESS"
        )

        Logger.kv(
            "Successful",
            success,
        )

        Logger.kv(
            "Failed",
            len(results) - success,
        )

        DEBUG = False

        if DEBUG:
            input(
                "\nPress ENTER to close..."
            )

    finally:

        Logger.close()
        browser.close()


if __name__ == "__main__":
    main()