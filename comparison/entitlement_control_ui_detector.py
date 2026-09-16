"""
Entitlement Control UI structure detector.

Captures static UI schema only. Dynamic offer/content values are ignored.
"""
from __future__ import annotations

import re


STATIC_LISTING_ACTIONS = {"Filter", "Add Offer"}
STATIC_LISTING_LABELS = {"Offers"}
STATIC_LISTING_COLUMNS = {
    "Offer ID", "Offer Name", "Duration", "Start Date", "End Date",
    "Product ID", "Enabled", "Action",
}
STATIC_LISTING_TABS = {"Subscription", "PPV"}

STATIC_DETAILS_LABELS = {
    "Offer ID",
    "Offer Name",
    "Offer Type",
    "Enabled",
    "Broadcast Product ID",
    "Start Date & Time",
    "End Date & Time",
}
STATIC_DETAILS_HEADINGS = {"Subscription Offer Detail", "PPV Offer Detail"}

_DYNAMIC_PATTERNS = [
    re.compile(r"^[0-9]+$"),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.I),
    re.compile(r"^https?://", re.I),
    re.compile(r"^[0-9]{2}-[0-9]{2}-[0-9]{4}"),
    re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    re.compile(r"^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$"),
]


class EntitlementControlUIDetector:
    def _is_dynamic(self, text: str) -> bool:
        value = " ".join((text or "").split()).strip()
        if not value:
            return True
        return any(pattern.search(value) for pattern in _DYNAMIC_PATTERNS)

    def _unique(self, items: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for item in items:
            key = tuple(sorted(item.items()))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def _visible_static_heading(self, page) -> list[dict]:
        headings = []
        for text in sorted(STATIC_DETAILS_HEADINGS):
            try:
                if page.get_by_text(text, exact=True).first.is_visible(timeout=500):
                    headings.append({"type": "heading", "text": text})
            except Exception:
                pass
        return headings

    def detect_listing(self, page) -> dict:
        labels = [{"type": "label", "text": x} for x in sorted(STATIC_LISTING_LABELS)]
        buttons = [{"type": "button", "text": x} for x in sorted(STATIC_LISTING_ACTIONS)]
        tabs = [{"type": "tab", "text": x} for x in sorted(STATIC_LISTING_TABS)]

        # Table headers are represented as static button/header entries so
        # the schema remains independent of dynamic offer rows.
        buttons.extend(
            {"type": "button", "text": x}
            for x in sorted(STATIC_LISTING_COLUMNS)
        )

        inputs = []
        checkboxes = []
        radios = []
        try:
            for loc in page.locator("input").all():
                typ = (loc.get_attribute("type") or "text").lower()
                placeholder = loc.get_attribute("placeholder") or ""
                if typ in {"text", "search"} and placeholder == "Search by Offer ID":
                    inputs.append({
                        "type": "input",
                        "inputType": typ,
                        "placeholder": placeholder,
                    })
                elif typ == "checkbox":
                    checkboxes.append({"type": "checkbox"})
                elif typ == "radio":
                    radios.append({"type": "radio"})
        except Exception:
            pass

        return {
            "headings": [],
            "labels": self._unique(labels),
            "inputs": self._unique(inputs),
            "selects": [{"type": "select"}] if page.locator("select").count() else [],
            "checkboxes": checkboxes,
            "radio_buttons": radios,
            "buttons": self._unique(buttons),
            "tabs": tabs,
            "tables": [{
                "type": "table",
                "columns": sorted(STATIC_LISTING_COLUMNS),
            }],
        }

    def detect_details(self, page) -> dict:
        labels = [
            {"type": "label", "text": x}
            for x in sorted(STATIC_DETAILS_LABELS)
        ]

        inputs = []
        selects = []
        checkboxes = []
        radios = []
        try:
            for loc in page.locator("input").all():
                typ = (loc.get_attribute("type") or "text").lower()
                placeholder = loc.get_attribute("placeholder") or ""
                if typ == "checkbox":
                    checkboxes.append({"type": "checkbox"})
                elif typ == "radio":
                    radios.append({"type": "radio"})
                else:
                    inputs.append({
                        "type": "input",
                        "inputType": typ,
                        "placeholder": placeholder,
                    })
            selects = [{"type": "select"}] * page.locator("select").count()
        except Exception:
            pass

        return {
            "headings": self._visible_static_heading(page),
            "labels": labels,
            "inputs": self._unique(inputs),
            "selects": selects,
            "checkboxes": checkboxes,
            "radio_buttons": radios,
            "buttons": [],
            "tabs": [],
            "tables": [],
        }
