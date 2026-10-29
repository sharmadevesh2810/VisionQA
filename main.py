import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from comparison.comparison_report import ComparisonReport
from comparison.comparator import Comparator
from core.browser import Browser
from core.constants import SNAPSHOTS_DIR
from core.crawler import Crawler
from core.environment import EnvironmentManager
from core.logger import Logger
from core.metadata import MetadataManager
from core.navigation import Navigation
from core.navigation_manifest import NavigationManifest
from core.report import ReportManager
from core.tenant import TenantManager
from core.version import VersionManager

AUTH_DIR = Path("auth")
STAGE_SESSION_FILE = AUTH_DIR / "stage.json"
LIVE_SESSION_FILE = AUTH_DIR / "live.json"
TENANT_HEADING = ".tenant-selection .heading"


def _wait_for_opc(page, timeout_ms=30000):
    try:
        page.locator(TENANT_HEADING).wait_for(state="visible", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def prepare_session(url, session_file, label):
    """Validate and refresh an environment-specific saved session."""
    session_file.parent.mkdir(parents=True, exist_ok=True)
    browser = Browser(storage_state=str(session_file), headless=False)
    try:
        print(f"\n[AUTH CHECK] {label}: {url}", flush=True)
        browser.open(url)
        page = browser.page

        if not _wait_for_opc(page, timeout_ms=25000):
            print(
                f"[AUTH REQUIRED] {label} is not authenticated. Current URL: {page.url}",
                flush=True,
            )
            print(
                f"Complete the {label} SSO login in the opened browser. "
                "Wait until OPC has fully loaded and the tenant selector is visible, "
                "then return here and press ENTER.",
                flush=True,
            )
            input()
            if not _wait_for_opc(page, timeout_ms=60000):
                raise RuntimeError(
                    f"{label} login was not confirmed. Current URL: {page.url}; "
                    f"expected selector {TENANT_HEADING!r}."
                )

        browser.save_session(str(session_file))
        print(f"[AUTH SAVED] {label} state refreshed: {session_file}", flush=True)
    finally:
        browser.close()


def execute_run(browser, url, tenant_name):
    """Run a full crawl in an already authenticated browser context."""
    page = browser.page
    if not _wait_for_opc(page, timeout_ms=20000):
        raise RuntimeError(
            f"OPC shell is not ready for {url}. Current URL: {page.url}"
        )

    Logger.section(f"Opening {url}")
    Logger.info(f"Current browser URL: {page.url}")

    Logger.section("Tenant")
    TenantManager(page).switch_tenant(tenant_name)

    Logger.section("Environment")
    environment_manager = EnvironmentManager(page)
    environment = environment_manager.get_environment()
    environment_manager.log()

    Logger.section("Version")
    version_manager = VersionManager(page)
    version = version_manager.get_version()
    Logger.kv("Application Version", version)

    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    safe_version = str(version or "unknown").replace("/", "_").replace("\\", "_")
    snapshot_dir = SNAPSHOTS_DIR / environment / safe_version / run_timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    Logger.initialize(snapshot_dir / "run.log")
    Logger.kv("Run Directory", snapshot_dir)

    Logger.section("Navigation Discovery")
    navigation_tree = Navigation(page).discover()
    Logger.kv("Menus Discovered", len(navigation_tree))

    Logger.section("Crawler")
    results = Crawler(page=page, snapshot_dir=snapshot_dir).crawl(navigation_tree)

    Logger.section("Metadata")
    MetadataManager(snapshot_dir).write(
        environment=environment,
        version=version,
        tenant=tenant_name,
        url=page.url,
    )
    Logger.success(f"metadata.json written to {snapshot_dir}")

    Logger.section("Navigation Manifest")
    NavigationManifest(snapshot_dir).write(results)
    Logger.success("navigation.json created.")

    Logger.section("HTML Report")
    ReportManager(snapshot_dir).generate(
        environment=environment,
        version=version,
        tenant=tenant_name,
        results=results,
    )
    Logger.success("report.html created.")

    Logger.section("Run Summary")
    Logger.kv("Environment", environment)
    Logger.kv("Version", version)
    Logger.kv("Tenant", tenant_name)
    Logger.kv("Run Directory", snapshot_dir)
    Logger.kv("Pages Crawled", len(results))

    success = sum(1 for result in results if result.get("status") == "SUCCESS")
    Logger.kv("Successful", success)
    Logger.kv("Failed", len(results) - success)

    return {
        "environment": environment,
        "version": version,
        "snapshot_dir": snapshot_dir,
        "results": results,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="VisionQA")
    parser.add_argument("--url", help="Single URL mode")
    parser.add_argument("--baseline", help="Baseline URL")
    parser.add_argument("--compare", help="Comparison URL")
    parser.add_argument("--tenant", help="Tenant for single URL")
    parser.add_argument("--baseline-tenant", help="Tenant for baseline environment")
    parser.add_argument("--compare-tenant", help="Tenant for comparison environment")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.url:
        mode = "single"
    elif args.baseline and args.compare:
        mode = "compare"
    else:
        raise ValueError("Use either --url OR both --baseline and --compare.")

    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    if mode == "single":
        session_file = (
            LIVE_SESSION_FILE
            if "live" in args.url.lower() or "prod" in args.url.lower()
            else STAGE_SESSION_FILE
        )
        browser = Browser(storage_state=str(session_file), headless=False)
        try:
            browser.open(args.url)
            page = browser.page
            if not _wait_for_opc(page, timeout_ms=25000):
                print("Log in and wait for OPC to load, then press ENTER.", flush=True)
                input()
                if not _wait_for_opc(page, timeout_ms=60000):
                    raise RuntimeError("OPC tenant selector is still not visible.")
            browser.save_session(str(session_file))
            execute_run(browser, args.url, args.tenant)
        finally:
            try:
                Logger.close()
            except Exception:
                pass
            browser.close()
        return

    def run_environment(url, tenant_name, session_file, label):
        """
        Authenticate and crawl in the same browser context.
        This avoids depending on sessionStorage/token state surviving a browser
        close and restore between preparation and the comparison crawl.
        """
        browser = Browser(storage_state=str(session_file), headless=False)
        try:
            print(f"\\n[AUTH CHECK] {label}: {url}", flush=True)
            browser.open(url)
            page = browser.page

            if not _wait_for_opc(page, timeout_ms=25000):
                print(
                    f"[AUTH REQUIRED] Complete the {label} SSO login in the opened "
                    "browser. Wait until OPC and the tenant selector are visible, "
                    "then return here and press ENTER.",
                    flush=True,
                )
                input()
                if not _wait_for_opc(page, timeout_ms=60000):
                    raise RuntimeError(
                        f"{label} login was not confirmed. Current URL={page.url}; "
                        f"expected selector {TENANT_HEADING!r}."
                    )

            # Save refreshed state for the next run, but keep using this live
            # browser context for the current crawl.
            browser.save_session(str(session_file))
            print(f"[AUTH READY] {label}: {page.url}", flush=True)

            result = execute_run(browser, url, tenant_name)
            print(f"[ENVIRONMENT COMPLETE] {label}", flush=True)
            return result
        finally:
            try:
                Logger.close()
            except Exception:
                pass
            browser.close()

    Logger.section("VisionQA")
    Logger.section("Stage Crawl")
    baseline_run = run_environment(
        args.baseline,
        args.baseline_tenant,
        STAGE_SESSION_FILE,
        "Stage",
    )

    Logger.section("Live Crawl")
    comparison_run = run_environment(
        args.compare,
        args.compare_tenant,
        LIVE_SESSION_FILE,
        "Live",
    )

    Logger.success("Both environments captured successfully.")
    Logger.section("Comparison")
    comparison = Comparator(
        baseline_run["results"],
        comparison_run["results"],
    ).compare()
    Logger.success("Comparison completed successfully.")

    comparison_dir = SNAPSHOTS_DIR / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    ComparisonReport(comparison_dir).generate(
        comparison=comparison,
        baseline_environment=baseline_run["environment"],
        comparison_environment=comparison_run["environment"],
        baseline_version=baseline_run["version"],
        comparison_version=comparison_run["version"],
    )
    Logger.success("comparison_report.html created.")


if __name__ == "__main__":
    main()
