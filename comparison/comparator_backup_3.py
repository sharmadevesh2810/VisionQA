"""
==============================================================================
VisionQA Comparator
==============================================================================

Copyright (c) 2026 Devesh Sharma.
All Rights Reserved.

Author      : Devesh Sharma
Framework   : VisionQA

Compares two VisionQA executions.

Comparison rule:
    1. Screenshot comparison ALWAYS runs.
    2. If BOTH pages contain usable ui_structure:
           comparison_type = "DEEP"
           compare screenshot + static UI structure.
    3. Otherwise:
           comparison_type = "SCREENSHOT"
           compare screenshots only.

The comparison is intentionally environment-independent:
    - Hostnames are not compared.
    - Timestamps are not compared.
    - Load time is not a pass/fail criterion.
    - Dynamic UI values are ignored during UI-structure comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import hashlib
import re


# ------------------------------------------------------------------------------
# Screenshot comparison tolerance
# ------------------------------------------------------------------------------
# Small pixel variations can occur between two crawls of the same environment
# because of rendering timing, dynamic table content, anti-aliasing, etc.
# A screenshot is considered visually matching when the changed-pixel
# percentage is at or below this tolerance.
SCREENSHOT_DIFF_THRESHOLD = 5.0
# Above this percentage, screenshot-only comparisons are treated as changed.
# For DEEP comparisons, screenshot differences within this tolerance are
# treated as normal rendering variation; UI structure remains the primary
# structural check.


# ------------------------------------------------------------------------------
# Dynamic-value filtering
# ------------------------------------------------------------------------------

_DYNAMIC_PATTERNS = [
    re.compile(r"^[0-9]+$"),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.I),  # UUID-like
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}"),
    re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$"),
    re.compile(r"^https?://", re.I),
    re.compile(r"^www\.", re.I),
    re.compile(r".*\.(png|jpg|jpeg|gif|webp|svg|mp4|m3u8|ts)$", re.I),
]


def _is_dynamic_string(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    return any(pattern.match(value) for pattern in _DYNAMIC_PATTERNS)


def _static_token(value: Any) -> str | None:
    """
    Convert a UI-structure item into a stable static token.

    Supported common detector formats:
      "Publish"
      {"text": "Publish"}
      {"label": "Publish"}
      {"name": "Publish", "present": True}
      {"component": "button", "text": "Publish"}

    Dynamic values, IDs, URLs, dates, filenames and numeric values are ignored.
    """
    if value is None:
        return None

    if isinstance(value, str):
        value = re.sub(r"\s+", " ", value).strip()
        if not value or _is_dynamic_string(value):
            return None
        return value

    if isinstance(value, (int, float, bool)):
        # Counts/presence flags are not UI identity.
        return None

    if isinstance(value, dict):
        # Prefer human-facing static identity fields.
        for key in (
            "text",
            "label",
            "name",
            "title",
            "placeholder",
            "component",
            "type",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str):
                token = _static_token(candidate)
                if token:
                    # Include component type where useful, without making
                    # selectors/counts part of the comparison.
                    if key not in ("component", "type"):
                        component = value.get("component") or value.get("type")
                        if isinstance(component, str) and component.strip():
                            return f"{component.strip()}::{token}"
                    return token

        # If the detector gives a nested static structure, recurse through
        # human-facing fields only.
        tokens = []
        for key, nested in value.items():
            if key.lower() in {
                "selector", "xpath", "css", "count", "present", "visible",
                "value", "id", "uuid", "href", "url", "timestamp",
            }:
                continue
            token = _static_token(nested)
            if token:
                tokens.append(f"{key}::{token}")
        if tokens:
            return "|".join(sorted(tokens))

        return None

    if isinstance(value, (list, tuple, set)):
        tokens = [_static_token(item) for item in value]
        tokens = [item for item in tokens if item]
        return "|".join(sorted(tokens)) if tokens else None

    return None


def _normalise_structure(ui_structure: Any) -> dict[str, list[str]]:
    """
    Return a deterministic static representation of ui_structure.

    Empty categories are retained only as empty lists. Dynamic values and
    implementation-specific selectors/counts are removed.
    """
    if not isinstance(ui_structure, dict):
        return {}

    normalized: dict[str, list[str]] = {}

    for category, items in ui_structure.items():
        category_name = str(category)

        if isinstance(items, list):
            tokens = []
            for item in items:
                token = _static_token(item)
                if token:
                    tokens.append(token)
        else:
            token = _static_token(items)
            tokens = [token] if token else []

        normalized[category_name] = sorted(set(tokens))

    return normalized


def has_ui_structure(record: dict[str, Any]) -> bool:
    """
    A page is eligible for DEEP comparison only when it contains at least one
    non-empty UI-structure category.

    This deliberately avoids treating {} or empty lists as usable structure.
    """
    ui = record.get("ui_structure")
    if not isinstance(ui, dict):
        return False

    return any(
        isinstance(value, list) and len(value) > 0
        for value in ui.values()
    )


# ------------------------------------------------------------------------------
# Screenshot comparison
# ------------------------------------------------------------------------------

def _screenshot_paths(record: dict[str, Any]) -> list[str]:
    """
    Support both the current single-screenshot field and possible multi-part
    screenshot fields used by long/detail-page captures.
    """
    candidates = []

    for key in (
        "screenshots",
        "screenshot_paths",
        "screenshot_parts",
    ):
        value = record.get(key)
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if item)
        elif isinstance(value, str) and value:
            candidates.append(value)

    single = record.get("screenshot")
    if isinstance(single, str) and single:
        candidates.insert(0, single)

    # De-duplicate while preserving order.
    result = []
    seen = set()
    for path in candidates:
        if path not in seen:
            seen.add(path)
            result.append(path)

    return result


def _resolve_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None

    path = Path(path_value)
    if path.exists():
        return path

    # Useful when JSON was generated on Windows but is being read elsewhere.
    path = Path(str(path_value).replace("\\", "/"))
    return path if path.exists() else None


def _image_diff_percentage(left: Path, right: Path) -> float | None:
    """
    Pixel difference percentage.

    Returns None if Pillow is unavailable or either image cannot be read.
    The caller applies SCREENSHOT_DIFF_THRESHOLD to determine MATCH/MISMATCH.
    """
    try:
        from PIL import Image, ImageChops
    except Exception:
        return None

    try:
        image_a = Image.open(left).convert("RGB")
        image_b = Image.open(right).convert("RGB")

        if image_a.size != image_b.size:
            image_b = image_b.resize(image_a.size)

        diff = ImageChops.difference(image_a, image_b)
        bbox = diff.getbbox()

        if bbox is None:
            return 0.0

        # Count changed pixels rather than summing channel magnitudes.
        diff_pixels = 0
        total_pixels = image_a.width * image_a.height

        # ImageChops difference bbox only tells us whether something changed.
        # Use a grayscale threshold to avoid tiny anti-aliasing noise.
        gray = diff.convert("L")
        threshold = gray.point(lambda p: 255 if p > 8 else 0)
        diff_pixels = sum(1 for pixel in threshold.getdata() if pixel)

        return round((diff_pixels / total_pixels) * 100, 4)
    except Exception:
        return None


def compare_screenshots(
    baseline: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    """
    Always compare screenshot evidence.

    For multi-part pages, screenshots are paired by order. The result contains
    per-part evidence plus an overall result.
    """
    baseline_paths = _screenshot_paths(baseline)
    comparison_paths = _screenshot_paths(comparison)

    if not baseline_paths or not comparison_paths:
        return {
            "result": "NOT_AVAILABLE",
            "matched": False,
            "difference_percentage": None,
            "baseline_screenshots": baseline_paths,
            "comparison_screenshots": comparison_paths,
            "details": [],
        }

    details = []
    max_difference = 0.0
    any_unavailable = False

    pair_count = min(len(baseline_paths), len(comparison_paths))

    for index in range(pair_count):
        left_raw = baseline_paths[index]
        right_raw = comparison_paths[index]

        left = _resolve_path(left_raw)
        right = _resolve_path(right_raw)

        if left is None or right is None:
            any_unavailable = True
            details.append({
                "part": index + 1,
                "result": "NOT_AVAILABLE",
                "baseline": left_raw,
                "comparison": right_raw,
                "difference_percentage": None,
            })
            continue

        difference = _image_diff_percentage(left, right)

        # If image diff is unavailable, fall back to SHA-256 equality. This
        # still gives a deterministic result for identical screenshots.
        if difference is None:
            left_hash = hashlib.sha256(left.read_bytes()).hexdigest()
            right_hash = hashlib.sha256(right.read_bytes()).hexdigest()
            matched = left_hash == right_hash
            difference = 0.0 if matched else None
        else:
            matched = difference <= SCREENSHOT_DIFF_THRESHOLD

        if difference is not None:
            max_difference = max(max_difference, difference)

        details.append({
            "part": index + 1,
            "result": "MATCH" if matched else "MISMATCH",
            "baseline": left_raw,
            "comparison": right_raw,
            "difference_percentage": difference,
        })

    if len(baseline_paths) != len(comparison_paths):
        any_unavailable = True
        details.append({
            "part": "COUNT",
            "result": "MISMATCH",
            "baseline_count": len(baseline_paths),
            "comparison_count": len(comparison_paths),
        })

    if any_unavailable and not details:
        result = "NOT_AVAILABLE"
    elif any(item.get("result") == "MISMATCH" for item in details):
        result = "MISMATCH"
    elif any(item.get("result") == "NOT_AVAILABLE" for item in details):
        result = "NOT_AVAILABLE"
    else:
        result = "MATCH"

    return {
        "result": result,
        "matched": result == "MATCH",
        "difference_percentage": round(max_difference, 4)
        if details else None,
        "threshold_percentage": SCREENSHOT_DIFF_THRESHOLD,
        "baseline_screenshots": baseline_paths,
        "comparison_screenshots": comparison_paths,
        "details": details,
    }


# ------------------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------------------

@dataclass
class PageComparison:
    menu: str
    submenu: str
    status: str
    comparison_type: str
    reasons: list[dict[str, Any]]
    navigation: dict[str, Any]
    url: dict[str, Any]
    title: dict[str, Any]
    execution: dict[str, Any]
    components: dict[str, Any]
    ui_structure: dict[str, Any]
    screenshot_comparison: dict[str, Any]
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


# ------------------------------------------------------------------------------
# Comparator
# ------------------------------------------------------------------------------

class Comparator:
    """
    Compare two VisionQA runs.

    Core rule:
        if stage.ui_structure AND comparison.ui_structure:
            DEEP comparison
        else:
            SCREENSHOT comparison

    Screenshot comparison ALWAYS runs.
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
        return (
            str(page.get("menu", "")),
            str(page.get("submenu", "")),
        )

    # ------------------------------------------------------------------
    # URL
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str | None) -> str:
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
        mapping: dict[str, dict[str, Any]] = {}

        for component in components or []:
            name = str(component.get("component", "")).strip()
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

            mapping[name] = {"present": present}

        return mapping

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
            set(baseline_map) | set(comparison_map)
        )

        for component in all_components:
            baseline_component = baseline_map.get(component)
            comparison_component = comparison_map.get(component)

            if baseline_component is None:
                added.append(component)
                reasons.append({
                    "type": "COMPONENT_ADDED",
                    "component": component,
                })
                continue

            if comparison_component is None:
                removed.append(component)
                reasons.append({
                    "type": "COMPONENT_REMOVED",
                    "component": component,
                })
                continue

            if (
                baseline_component["present"]
                != comparison_component["present"]
            ):
                changed.append({
                    "component": component,
                    "baseline": baseline_component,
                    "comparison": comparison_component,
                })
                reasons.append({
                    "type": "COMPONENT_PRESENCE_CHANGED",
                    "component": component,
                    "baseline": baseline_component["present"],
                    "comparison": comparison_component["present"],
                })

        return {
            "matched": not reasons,
            "added": added,
            "removed": removed,
            "changed": changed,
            "reasons": reasons,
        }

    # ------------------------------------------------------------------
    # UI structure
    # ------------------------------------------------------------------

    def _compare_ui_structure(
        self,
        baseline: dict[str, Any],
        comparison: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Compare only static UI structure.

        This intentionally ignores:
          - dynamic values
          - IDs/UUIDs
          - dates/times
          - URLs
          - filenames
          - numeric counts
          - selectors
        """
        baseline_ui = _normalise_structure(
            baseline.get("ui_structure")
        )
        comparison_ui = _normalise_structure(
            comparison.get("ui_structure")
        )

        categories = sorted(
            set(baseline_ui) | set(comparison_ui)
        )

        category_results = {}
        differences = []

        for category in categories:
            baseline_items = set(baseline_ui.get(category, []))
            comparison_items = set(comparison_ui.get(category, []))

            added = sorted(comparison_items - baseline_items)
            removed = sorted(baseline_items - comparison_items)

            category_match = not added and not removed

            category_results[category] = {
                "result": "MATCH" if category_match else "MISMATCH",
                "baseline": sorted(baseline_items),
                "comparison": sorted(comparison_items),
                "added": added,
                "removed": removed,
            }

            if added:
                for item in added:
                    differences.append({
                        "category": category,
                        "component": item,
                        "stage": "missing",
                        "comparison": "present",
                    })

            if removed:
                for item in removed:
                    differences.append({
                        "category": category,
                        "component": item,
                        "stage": "present",
                        "comparison": "missing",
                    })

        matched = not differences

        return {
            "result": "MATCH" if matched else "MISMATCH",
            "matched": matched,
            "categories": category_results,
            "differences": differences,
        }

    # ------------------------------------------------------------------
    # Page execution state
    # ------------------------------------------------------------------

    @staticmethod
    def _execution_state(page: dict) -> dict[str, Any]:
        status = page.get("status")
        error = page.get("error")

        healthy = status == "SUCCESS" and not error

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

        # --------------------------------------------------------------
        # Comparison mode
        # --------------------------------------------------------------
        baseline_deep = has_ui_structure(baseline)
        comparison_deep = has_ui_structure(comparison)

        comparison_type = (
            "DEEP"
            if baseline_deep and comparison_deep
            else "SCREENSHOT"
        )

        # --------------------------------------------------------------
        # Screenshot comparison ALWAYS runs.
        # Small differences within SCREENSHOT_DIFF_THRESHOLD are treated as
        # MATCH so normal rendering noise does not make a page FAIL.
        # --------------------------------------------------------------
        screenshot_result = compare_screenshots(
            baseline,
            comparison,
        )

        if screenshot_result["result"] == "MISMATCH":
            reasons.append({
                "type": "SCREENSHOT_CHANGED",
                "difference_percentage": screenshot_result.get(
                    "difference_percentage"
                ),
            })

        # --------------------------------------------------------------
        # Deep comparison only when BOTH structures are usable
        # --------------------------------------------------------------
        ui_result = {
            "result": "NOT_APPLICABLE",
            "matched": None,
            "differences": [],
            "categories": {},
        }

        if comparison_type == "DEEP":
            ui_result = self._compare_ui_structure(
                baseline,
                comparison,
            )

            if ui_result["result"] == "MISMATCH":
                reasons.extend(
                    {
                        "type": "UI_STRUCTURE_CHANGED",
                        **difference,
                    }
                    for difference in ui_result["differences"]
                )

        # --------------------------------------------------------------
        # Navigation
        # --------------------------------------------------------------
        baseline_navigation = baseline.get("navigation_type")
        comparison_navigation = comparison.get("navigation_type")
        navigation_match = baseline_navigation == comparison_navigation

        if not navigation_match:
            reasons.append({
                "type": "NAVIGATION_CHANGED",
                "baseline": baseline_navigation,
                "comparison": comparison_navigation,
            })

        # --------------------------------------------------------------
        # URL / route
        # --------------------------------------------------------------
        baseline_url = self._normalize_url(baseline.get("url"))
        comparison_url = self._normalize_url(comparison.get("url"))
        url_match = baseline_url == comparison_url

        if not url_match:
            reasons.append({
                "type": "URL_CHANGED",
                "baseline": baseline_url,
                "comparison": comparison_url,
            })

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------
        baseline_title = baseline.get("title", "")
        comparison_title = comparison.get("title", "")
        title_match = baseline_title == comparison_title

        if not title_match:
            reasons.append({
                "type": "TITLE_CHANGED",
                "baseline": baseline_title,
                "comparison": comparison_title,
            })

        # --------------------------------------------------------------
        # Execution state
        # --------------------------------------------------------------
        baseline_execution = self._execution_state(baseline)
        comparison_execution = self._execution_state(comparison)

        execution_match = (
            baseline_execution["healthy"]
            == comparison_execution["healthy"]
        )

        if not execution_match:
            reasons.append({
                "type": "EXECUTION_STATE_CHANGED",
                "baseline": baseline_execution,
                "comparison": comparison_execution,
            })

        if baseline_execution["error"] != comparison_execution["error"]:
            if baseline_execution["error"] or comparison_execution["error"]:
                reasons.append({
                    "type": "ERROR_CHANGED",
                    "baseline": baseline_execution["error"],
                    "comparison": comparison_execution["error"],
                })

        # --------------------------------------------------------------
        # Existing generic components
        # --------------------------------------------------------------
        component_result = self._compare_components(
            baseline.get("components", []),
            comparison.get("components", []),
        )

        # Generic component comparison is retained as supporting evidence,
        # but the comparison mode determines whether it can fail the page.
        #
        # DEEP:
        #   - static UI structure is the structural source of truth
        #   - screenshot is still compared and reported
        #   - small screenshot differences (<= threshold) do not fail the page
        #
        # SCREENSHOT:
        #   - screenshot result is the visual source of truth
        #   - no UI-structure failure is possible because structure is absent
        if comparison_type == "DEEP":
            reasons.extend(component_result["reasons"])
        else:
            # Components are not used to fail screenshot-only pages because
            # the agreed fallback mode is screenshot comparison only.
            pass

        # Screenshot is already represented in `reasons` only when its
        # difference exceeds SCREENSHOT_DIFF_THRESHOLD.
        page_match = not reasons

        return PageComparison(
            menu=str(baseline.get("menu", "")),
            submenu=str(baseline.get("submenu", "")),
            status="SUCCESS" if page_match else "FAIL",
            comparison_type=comparison_type,
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
            ui_structure=ui_result,
            screenshot_comparison=screenshot_result,
            baseline_screenshot=baseline.get("screenshot"),
            comparison_screenshot=comparison.get("screenshot"),
        )

    # ------------------------------------------------------------------
    # Full comparison
    # ------------------------------------------------------------------

    def compare(self) -> dict[str, Any]:

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
            set(baseline_groups) | set(comparison_groups)
        )

        for key in all_keys:

            baseline_list = list(baseline_groups.get(key, []))
            comparison_list = list(comparison_groups.get(key, []))

            pairs: list[tuple[dict, dict]] = []

            # First pair pages whose normalized routes are identical.
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
                    pairs.append((
                        baseline_page,
                        comparison_list.pop(match_index),
                    ))
                    baseline_list.remove(baseline_page)

            # Pair remaining same-name pages one-to-one.
            while baseline_list and comparison_list:
                pairs.append((
                    baseline_list.pop(0),
                    comparison_list.pop(0),
                ))

            # Pages only in comparison.
            for comparison in comparison_list:
                added_pages.append({
                    "menu": comparison.get("menu", ""),
                    "submenu": comparison.get("submenu", ""),
                    "url": comparison.get("url"),
                    "navigation": comparison.get("navigation_type"),
                })

            # Pages only in baseline.
            for baseline in baseline_list:
                removed_pages.append({
                    "menu": baseline.get("menu", ""),
                    "submenu": baseline.get("submenu", ""),
                    "url": baseline.get("url"),
                    "navigation": baseline.get("navigation_type"),
                })

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

        deep_count = sum(
            page.comparison_type == "DEEP"
            for page in comparisons
        )
        screenshot_only_count = sum(
            page.comparison_type == "SCREENSHOT"
            for page in comparisons
        )

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
                "deep_comparisons": deep_count,
                "screenshot_only_comparisons": screenshot_only_count,
            },
            "pages": [
                {
                    "menu": page.menu,
                    "submenu": page.submenu,
                    "status": page.status,
                    "comparison_type": page.comparison_type,
                    "reasons": page.reasons,
                    "navigation": page.navigation,
                    "url": page.url,
                    "title": page.title,
                    "execution": page.execution,
                    "components": page.components,
                    "ui_structure": page.ui_structure,
                    "screenshot_comparison": page.screenshot_comparison,
                    "baseline_screenshot": page.baseline_screenshot,
                    "comparison_screenshot": page.comparison_screenshot,
                }
                for page in comparisons
            ],
            "added_pages": added_pages,
            "removed_pages": removed_pages,
        }
