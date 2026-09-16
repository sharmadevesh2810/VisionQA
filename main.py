from comparison.comparison_report import ComparisonReport
from comparison.comparator import Comparator
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
import argparse

SESSION_FILE = Path("auth/stage.json")

def execute_run(
    browser,
    url,
    tenant_name,
):

    page = browser.page

    Logger.section(
        f"Opening {url}"
    )

    page.goto(
        url,
        wait_until="networkidle",
        timeout=60000,
    )

    #
    # Tenant
    #

    Logger.section("Tenant")

    tenant = TenantManager(page)
    tenant.switch_tenant(
    tenant_name
)
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
        tenant=tenant_name,
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
    tenant=tenant_name,
    results=results,
)

    Logger.success(
        "report.html created."
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
    tenant_name,
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

    return {
        "environment": environment,
        "version": version,
        "snapshot_dir": snapshot_dir,
        "results": results,
    }


def parse_args():

    parser = argparse.ArgumentParser(
    description="VisionQA"
    )

    parser.add_argument(
        "--url",
        help="Single URL mode",
    )

    parser.add_argument(
        "--baseline",
        help="Baseline URL",
    )

    parser.add_argument(
        "--compare",
        help="Comparison URL",
    )

    parser.add_argument(
        "--tenant",
        help="Tenant for single URL",
    )

    parser.add_argument(
        "--baseline-tenant",
        help="Baseline tenant",
    )

    parser.add_argument(
        "--compare-tenant",
        help="Comparison tenant",
    )

    return parser.parse_args()

def main():

    #
    # Ensure auth directory exists
    #

    args = parse_args()

    if args.url:

        mode = "single"

    elif args.baseline and args.compare:

        mode = "compare"

    else:

        raise ValueError(
            "Use either --url OR both --baseline and --compare."
        )

    SESSION_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    browser = Browser(
    storage_state=str(SESSION_FILE),
)

    browser.open(
    args.url
    or args.baseline
)

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

        if mode == "single":

            execute_run(
    browser,
    args.url,
    args.tenant,
)

        else:

            Logger.section("Baseline")

            baseline_run = execute_run(
    browser,
    args.baseline,
    args.baseline_tenant,
)

            Logger.section("Comparison")

            comparison_run = execute_run(
    browser,
    args.compare,
    args.compare_tenant,
)

            Logger.success(
                "Both environments captured successfully."
            )

    # Comparison report generation will be added here

            Logger.section("Comparison")

            comparison = Comparator(
                baseline_run["results"],
                comparison_run["results"],
            ).compare()

            Logger.success(
                "Comparison completed successfully."
            )

            Logger.section(
                "Comparison Report"
            )

            comparison_dir = (
                SNAPSHOTS_DIR / "comparison"
            )

            comparison_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            ComparisonReport(
                comparison_dir
            ).generate(
                comparison=comparison,
                baseline_environment=baseline_run["environment"],
                comparison_environment=comparison_run["environment"],
                baseline_version=baseline_run["version"],
                comparison_version=comparison_run["version"],
            )

            Logger.success(
                "comparison_report.html created."
            )

    finally:

        Logger.close()
        browser.close()


if __name__ == "__main__":
    main()