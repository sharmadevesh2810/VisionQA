
"""
==============================================================================
VisionQA Comparator
==============================================================================

Copyright (c) 2026 Devesh Sharma.
All Rights Reserved.

Author      : Devesh Sharma
Framework   : VisionQA

Compares two VisionQA executions.

Comparison criteria:
- Page existence
- Navigation type
- Normalized URL / route
- Page title
- Page execution status / errors
- Important component presence

Not compared:
- Load time
- Environment hostname
- Timestamps
- Screenshot pixels (reserved for visual-diff phase)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass
class PageComparison:
    menu: str
    submenu: str
    status: str
    reasons: list[dict[str, Any]]
    navigation: dict[str, Any]
    url: dict[str, Any]
    title: dict[str, Any]
    execution: dict[str, Any]
    components: dict[str, Any]
    baseline_screenshot: str | None
    comparison_screenshot: str | None


@dataclass
class ComparisonSummary:
    baseline_pages: int
    comparison_pages: int
    common_pages: int
    matched: int
    changed: int
    added_pages: int
    removed_pages: int


class Comparator:
    """
    Compare two VisionQA runs using only meaningful functional/UI criteria.

    A page passes when:
      1. It exists in both runs.
      2. Navigation type matches.
      3. Normalized route matches.
      4. Page title matches.
      5. Execution status/error state is healthy in both runs.
      6. Important component presence matches.

    Load time is intentionally NOT part of the comparison.
    """

    def __init__(
        self,
        baseline_results: list[dict],
        comparison_results: list[dict],
    ):
        self.baseline_results = baseline_results
        self.comparison_results = comparison_results

    # ------------------------------------------------------------------
    # Page identity
    # ------------------------------------------------------------------

    @staticmethod
    def _page_key(page: dict) -> tuple[str, str]:
        """
        Use menu + submenu as page identity.

        This is important: URL must be compared as a property of the page,
        not used to decide whether the page itself was added/removed.
        """

        return (
            str(page.get("menu", "")),
            str(page.get("submenu", "")),
        )

    # ------------------------------------------------------------------
    # URL
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str | None) -> str:
        """
        Compare environment-independent routes.

        Example:
            https://stage.example.com/foo/bar
            https://qa.example.com/foo/bar

        Both become:
            /foo/bar
        """

        if not url:
            return ""

        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")
            return path or "/"
        except Exception:
            return url.rstrip("/") or "/"

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------

    @staticmethod
    def _component_map(
        components: list[dict] | None,
    ) -> dict[str, dict[str, Any]]:
        """
        Build a stable map of important component presence.

        We intentionally do NOT compare selectors or element counts.
        Selectors are implementation details and counts can legitimately
        vary because of dynamic data.

        Supported crawler formats:
          {"component": "table", "present": True}
          {"component": "table", "visible": True}
          {"component": "table", "count": 10}
        """

        mapping: dict[str, dict[str, Any]] = {}

        for component in components or []:
            name = str(
                component.get("component", "")
            ).strip()

            if not name:
                continue

            if "present" in component:
                present = bool(component["present"])
            elif "visible" in component:
                present = bool(component["visible"])
            elif "count" in component:
                present = bool(component["count"])
            else:
                present = True

            mapping[name] = {
                "present": present,
            }

        return mapping

    # ------------------------------------------------------------------

    def _compare_components(
        self,
        baseline: list[dict] | None,
        comparison: list[dict] | None,
    ) -> dict[str, Any]:

        baseline_map = self._component_map(baseline)
        comparison_map = self._component_map(comparison)

        added: list[str] = []
        removed: list[str] = []
        changed: list[dict[str, Any]] = []
        reasons: list[dict[str, Any]] = []

        all_components = sorted(
            set(baseline_map)
            | set(comparison_map)
        )

        for component in all_components:

            baseline_component = baseline_map.get(
                component
            )

            comparison_component = comparison_map.get(
                component
            )

            if baseline_component is None:
                added.append(component)

                reasons.append(
                    {
                        "type": "COMPONENT_ADDED",
                        "component": component,
                    }
                )
                continue

            if comparison_component is None:
                removed.append(component)

                reasons.append(
                    {
                        "type": "COMPONENT_REMOVED",
                        "component": component,
                    }
                )
                continue

            if (
                baseline_component["present"]
                != comparison_component["present"]
            ):
                changed.append(
                    {
                        "component": component,
                        "baseline": baseline_component,
                        "comparison": comparison_component,
                    }
                )

                reasons.append(
                    {
                        "type": "COMPONENT_PRESENCE_CHANGED",
                        "component": component,
                        "baseline": baseline_component["present"],
                        "comparison": comparison_component["present"],
                    }
                )

        return {
            "matched": not reasons,
            "added": added,
            "removed": removed,
            "changed": changed,
            "reasons": reasons,
        }

    # ------------------------------------------------------------------
    # Page execution state
    # ------------------------------------------------------------------

    @staticmethod
    def _execution_state(
        page: dict,
    ) -> dict[str, Any]:

        status = page.get("status")
        error = page.get("error")

        healthy = (
            status == "SUCCESS"
            and not error
        )

        return {
            "status": status,
            "error": error,
            "healthy": healthy,
        }

    # ------------------------------------------------------------------
    # Page comparison
    # ------------------------------------------------------------------

    def _compare_page(
        self,
        baseline: dict,
        comparison: dict,
    ) -> PageComparison:

        reasons: list[dict[str, Any]] = []

        # Navigation
        baseline_navigation = baseline.get(
            "navigation_type"
        )
        comparison_navigation = comparison.get(
            "navigation_type"
        )

        navigation_match = (
            baseline_navigation
            == comparison_navigation
        )

        if not navigation_match:
            reasons.append(
                {
                    "type": "NAVIGATION_CHANGED",
                    "baseline": baseline_navigation,
                    "comparison": comparison_navigation,
                }
            )

        # URL / route
        baseline_url = self._normalize_url(
            baseline.get("url")
        )
        comparison_url = self._normalize_url(
            comparison.get("url")
        )

        url_match = (
            baseline_url
            == comparison_url
        )

        if not url_match:
            reasons.append(
                {
                    "type": "URL_CHANGED",
                    "baseline": baseline_url,
                    "comparison": comparison_url,
                }
            )

        # Title
        baseline_title = baseline.get(
            "title",
            "",
        )
        comparison_title = comparison.get(
            "title",
            "",
        )

        title_match = (
            baseline_title
            == comparison_title
        )

        if not title_match:
            reasons.append(
                {
                    "type": "TITLE_CHANGED",
                    "baseline": baseline_title,
                    "comparison": comparison_title,
                }
            )

        # Execution state / crawler health
        baseline_execution = self._execution_state(
            baseline
        )
        comparison_execution = self._execution_state(
            comparison
        )

        execution_match = (
            baseline_execution["healthy"]
            == comparison_execution["healthy"]
        )

        if (
            baseline_execution["healthy"]
            != comparison_execution["healthy"]
        ):
            reasons.append(
                {
                    "type": "EXECUTION_STATE_CHANGED",
                    "baseline": baseline_execution,
                    "comparison": comparison_execution,
                }
            )

        # If both are unhealthy, also surface the actual errors when they
        # differ. This makes failures explainable without treating load time
        # as a comparison criterion.
        if (
            baseline_execution["error"]
            != comparison_execution["error"]
        ):
            if (
                baseline_execution["error"]
                or comparison_execution["error"]
            ):
                reasons.append(
                    {
                        "type": "ERROR_CHANGED",
                        "baseline": baseline_execution["error"],
                        "comparison": comparison_execution["error"],
                    }
                )

        # Components
        component_result = self._compare_components(
            baseline.get("components", []),
            comparison.get("components", []),
        )

        reasons.extend(
            component_result["reasons"]
        )

        page_match = not reasons

        # Load time is retained only as raw metadata for possible future
        # diagnostics. It NEVER affects status.
        baseline_load = baseline.get("load_time")
        comparison_load = comparison.get("load_time")

        return PageComparison(
            menu=str(
                baseline.get("menu", "")
            ),
            submenu=str(
                baseline.get("submenu", "")
            ),
            status=(
                "SUCCESS"
                if page_match
                else "FAIL"
            ),
            reasons=reasons,
            navigation={
                "baseline": baseline_navigation,
                "comparison": comparison_navigation,
                "matched": navigation_match,
            },
            url={
                "baseline": baseline.get("url"),
                "comparison": comparison.get("url"),
                "normalized_baseline": baseline_url,
                "normalized_comparison": comparison_url,
                "matched": url_match,
            },
            title={
                "baseline": baseline_title,
                "comparison": comparison_title,
                "matched": title_match,
            },
            execution={
                "baseline": baseline_execution,
                "comparison": comparison_execution,
                "matched": execution_match,
            },
            components=component_result,
            baseline_screenshot=baseline.get(
                "screenshot"
            ),
            comparison_screenshot=comparison.get(
                "screenshot"
            ),
        )

    # ------------------------------------------------------------------
    # Full comparison
    # ------------------------------------------------------------------

    def compare(self) -> dict[str, Any]:

        # Group pages instead of using a dict comprehension. A dict would
        # silently overwrite duplicate menu/submenu entries.
        baseline_groups: dict[tuple[str, str], list[dict]] = {}
        comparison_groups: dict[tuple[str, str], list[dict]] = {}

        for page in self.baseline_results:
            baseline_groups.setdefault(
                self._page_key(page), []
            ).append(page)

        for page in self.comparison_results:
            comparison_groups.setdefault(
                self._page_key(page), []
            ).append(page)

        comparisons: list[PageComparison] = []
        added_pages: list[dict[str, Any]] = []
        removed_pages: list[dict[str, Any]] = []

        matched = 0
        changed = 0

        all_keys = sorted(
            set(baseline_groups)
            | set(comparison_groups)
        )

        for key in all_keys:

            baseline_list = list(
                baseline_groups.get(key, [])
            )
            comparison_list = list(
                comparison_groups.get(key, [])
            )

            pairs: list[tuple[dict, dict]] = []

            # First pair pages whose normalized routes are identical.
            # This avoids pairing two duplicate-named pages incorrectly.
            for baseline_page in list(baseline_list):

                baseline_route = self._normalize_url(
                    baseline_page.get("url")
                )

                match_index = next(
                    (
                        index
                        for index, comparison_page
                        in enumerate(comparison_list)
                        if self._normalize_url(
                            comparison_page.get("url")
                        ) == baseline_route
                    ),
                    None,
                )

                if match_index is not None:
                    pairs.append(
                        (
                            baseline_page,
                            comparison_list.pop(match_index),
                        )
                    )
                    baseline_list.remove(baseline_page)

            # Pair remaining same-name pages one-to-one. This means a route
            # change is reported as CHANGED instead of ADDED + REMOVED.
            while baseline_list and comparison_list:
                pairs.append(
                    (
                        baseline_list.pop(0),
                        comparison_list.pop(0),
                    )
                )

            # Anything left in comparison exists only there.
            for comparison in comparison_list:
                added_pages.append(
                    {
                        "menu": comparison.get("menu", ""),
                        "submenu": comparison.get("submenu", ""),
                        "url": comparison.get("url"),
                        "navigation": comparison.get(
                            "navigation_type"
                        ),
                    }
                )

            # Anything left in baseline exists only there.
            for baseline in baseline_list:
                removed_pages.append(
                    {
                        "menu": baseline.get("menu", ""),
                        "submenu": baseline.get("submenu", ""),
                        "url": baseline.get("url"),
                        "navigation": baseline.get(
                            "navigation_type"
                        ),
                    }
                )

            for baseline, comparison in pairs:

                result = self._compare_page(
                    baseline,
                    comparison,
                )

                comparisons.append(result)

                if result.status == "SUCCESS":
                    matched += 1
                else:
                    changed += 1

        summary = ComparisonSummary(
            baseline_pages=len(self.baseline_results),
            comparison_pages=len(self.comparison_results),
            common_pages=len(comparisons),
            matched=matched,
            changed=changed,
            added_pages=len(added_pages),
            removed_pages=len(removed_pages),
        )

        return {
            "summary": {
                # Kept for compatibility with the existing report.
                # It represents common/pairable pages, not all unique pages.
                "total_pages": summary.common_pages,
                "baseline_pages": summary.baseline_pages,
                "comparison_pages": summary.comparison_pages,
                "common_pages": summary.common_pages,
                "matched": summary.matched,
                "changed": summary.changed,
                "added_pages": summary.added_pages,
                "removed_pages": summary.removed_pages,
                "total_unique_pages": (
                    summary.common_pages
                    + summary.added_pages
                    + summary.removed_pages
                ),
            },
            "pages": [
                {
                    "menu": page.menu,
                    "submenu": page.submenu,
                    "status": page.status,
                    "reasons": page.reasons,
                    "navigation": page.navigation,
                    "url": page.url,
                    "title": page.title,
                    "execution": page.execution,
                    "components": page.components,
                    "baseline_screenshot": page.baseline_screenshot,
                    "comparison_screenshot": page.comparison_screenshot,
                }
                for page in comparisons
            ],
            "added_pages": added_pages,
            "removed_pages": removed_pages,
        }

