"""
EPG UI structure detector.

Captures static UI schema only. Dynamic event/channel/content values are ignored.
"""
from __future__ import annotations

import re


STATIC_LISTING_LABELS = {
    "Select Channel",
}
STATIC_LISTING_ACTIONS = {
    "Publish EPG",
}
STATIC_LISTING_COLUMNS = {
    "ID", "Event Date", "Schedule Time", "Title", "Season Number",
    "Episode Number", "OTT Blackout", "Highlights", "Live", "Action",
}
STATIC_LISTING_TABS = {"All Programs"}

STATIC_DRAWER_TABS = {"Images", "Videos", "Aggregated Data"}
STATIC_IMAGE_LABELS = {
    "Aspect Ratio", "Channel Logo", "Channel Logo Checksum", "File Name",
    "File Size", "File Url", "Height", "Image Id", "Languages", "Layout",
    "Level", "Preview Image", "Profile", "Service Label", "Type", "Width",
}
STATIC_VIDEO_LABELS = {"Content", "System", "Is HD", "Usage Type"}
STATIC_AGG_LABELS = {
    "Filter by key", "Search", "Dvb Certification Id", "Channel Stb Number",
    "Is Delayed", "Year Of Release", "Content Id",
}

_DYNAMIC_PATTERNS = [
    re.compile(r"^[0-9]+$"),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.I),
    re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    re.compile(r"^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$"),
    re.compile(r"^https?://", re.I),
    re.compile(r"\.(png|jpg|jpeg|webp|gif|mp4|m3u8|ts)(\?|$)", re.I),
]


class EPGUIDetector:
    def _is_dynamic(self, text: str) -> bool:
        value = " ".join((text or "").split()).strip()
        if not value:
            return True
        return any(p.search(value) for p in _DYNAMIC_PATTERNS)

    def _unique(self, items: list[dict]) -> list[dict]:
        seen = set()
        out = []
        for item in items:
            key = tuple(sorted(item.items()))
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    def detect_listing(self, page) -> dict:
        labels = [{"type": "label", "text": x} for x in sorted(STATIC_LISTING_LABELS)]
        buttons = [{"type": "button", "text": x} for x in sorted(STATIC_LISTING_ACTIONS)]
        tabs = [{"type": "tab", "text": x} for x in sorted(STATIC_LISTING_TABS)]

        for text in sorted(STATIC_LISTING_COLUMNS):
            buttons.append({"type": "button", "text": text})

        inputs = []
        for loc in page.locator("input").all():
            try:
                input_type = loc.get_attribute("type") or "text"
                placeholder = loc.get_attribute("placeholder") or ""
                if input_type == "text" and placeholder == "Search by event id/title":
                    inputs.append({"type": "input", "inputType": "text", "placeholder": placeholder})
                elif input_type == "checkbox":
                    inputs.append({"type": "checkbox"})
            except Exception:
                pass

        return {
            "headings": [],
            "labels": self._unique(labels),
            "inputs": [x for x in inputs if x.get("type") == "input"],
            "selects": [{"type": "select"}] if page.locator("select").count() else [],
            "checkboxes": [x for x in inputs if x.get("type") == "checkbox"],
            "radio_buttons": [],
            "buttons": self._unique(buttons),
            "tabs": tabs,
            "tables": [{"type": "table", "columns": list(sorted(STATIC_LISTING_COLUMNS, key=lambda x: list(STATIC_LISTING_COLUMNS).index(x)))}],
        }

    def detect_drawer(self, drawer, active_tab: str) -> dict:
        tabs = [{"type": "tab", "text": x} for x in ["Images", "Videos", "Aggregated Data"]]

        if active_tab == "Images":
            labels_set = STATIC_IMAGE_LABELS
        elif active_tab == "Videos":
            labels_set = STATIC_VIDEO_LABELS
        else:
            labels_set = STATIC_AGG_LABELS

        labels = [{"type": "label", "text": x} for x in sorted(labels_set)]
        inputs = []
        selects = []
        checkboxes = []

        try:
            for loc in drawer.locator("input").all():
                typ = (loc.get_attribute("type") or "text").lower()
                ph = loc.get_attribute("placeholder") or ""
                if typ == "checkbox":
                    checkboxes.append({"type": "checkbox"})
                else:
                    inputs.append({"type": "input", "inputType": typ, "placeholder": ph})
            selects = [{"type": "select"}] * drawer.locator("select").count()
        except Exception:
            pass

        result = {
            "headings": [{"type": "heading", "text": "Event Details"}],
            "labels": labels,
            "inputs": inputs,
            "selects": selects,
            "checkboxes": checkboxes,
            "radio_buttons": [],
            "buttons": [],
            "tabs": tabs,
            "tables": [],
        }
        return result
