"""Static UI structure detector for OPC Channel screens.

The detector captures only UI shape/schema. Backend/content values are ignored.
Table-row controls and row values are intentionally excluded from the static
structure so the result is stable for later comparison.
"""
from __future__ import annotations

import re

DYNAMIC_RE = re.compile(
    r"^(?:\d+|[0-9a-f]{8}-[0-9a-f-]{27,}|https?://|www\.|.*\.(?:png|jpg|jpeg|gif|webp|mp4|m3u8))$",
    re.I,
)

SECTION_NAMES = {
    "General Details", "Delivery Details", "Security Details",
    "Enabler Details", "Advertising Details", "Video Details",
}

STATIC_ACTIONS = {
    "Filter", "Add Channel", "Export", "Version History", "Recordings",
    "Load More",
}

STATIC_LISTING_COLUMNS = {
    "CH ID", "SEK ID", "Name", "Logo", "Enabled", "WM",
    "Primary Origin", "Actions", "General", "Broadcast", "OTT",
}

STATIC_TABS = {"Commercial TV", "Commercial Radio", "App Launch Point"}

STATIC_DETAIL_LABELS = {
    "Channel ID", "Channel Name", "Channel STB Number", "Business Unit",
    "Primary Genre", "Secondary Genre", "Audio Language", "Keywords",
    "Profile", "Service Label", "Channel Logo", "Channel Logo Checksum",
    "Channel Logo URL", "Preview Image", "Image 1", "Image Name",
    "Image Size (Bytes)", "Image Usage Type", "Image URL", "Checksum",
    "Enable", "Services", "Output Media", "Block Ads", "Ads Enabled",
    "Ads Supplier", "Ads Pre Roll", "Ads Mid Roll", "Ads Post Roll",
    "Asset Life Cycle", "Pre Login", "Coming Soon End Date",
    "Selling Period Start", "Selling Period End", "Offer Start", "Offer End",
    "SKU", "In App Price", "Max View", "Region Label", "Currency Label",
    "Price Label", "Transformed Price Label", "SW DRM Resolution Cap",
    "HW DRM Resolution Cap", "CDN Tokenisation", "Across All Device",
    "Device Specific", "Package Data Provider", "Package Data ID",
    "Exclude Brand", "New Label Enabled", "Supplier", "Supplier Label",
    "Audience Community", "Live Event ID", "Sort Order", "Is Sponsored",
    "Brand Page", "Additional Info Label", "Additional Info Value",
}

def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())

def _is_dynamic(value: str) -> bool:
    value = _clean(value)
    if not value or DYNAMIC_RE.match(value):
        return True
    if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", value, re.I):
        return True
    if re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", value):
        return True
    return False

class ChannelUIDetector:
    """Capture stable Channel listing/details UI structure."""

    def detect_listing(self, page) -> dict:
        return {
            "headings": self._headings(page),
            "labels": self._listing_labels(page),
            "inputs": self._inputs(page),
            "selects": self._selects(page),
            "checkboxes": self._checkboxes(page),
            "radio_buttons": self._radios(page),
            "buttons": self._buttons(page, STATIC_ACTIONS),
            "tabs": self._tabs(page),
            "tables": self._tables(page),
        }

    def detect_details(self, page) -> dict:
        return {
            "headings": self._headings(page),
            "labels": self._labels(page),
            "inputs": self._inputs(page),
            "selects": self._selects(page),
            "checkboxes": self._checkboxes(page),
            "radio_buttons": self._radios(page),
            "buttons": self._buttons(page, STATIC_ACTIONS),
            "tabs": self._tabs(page),
            "tables": self._tables(page),
        }

    def _headings(self, page):
        found, seen = [], set()
        loc = page.locator("h1,h2,h3,h4,h5,h6,mat-expansion-panel-header")
        for i in range(loc.count()):
            try: text = _clean(loc.nth(i).inner_text())
            except Exception: continue
            if not text or _is_dynamic(text) or text in seen: continue
            if text not in SECTION_NAMES and "expansion-panel-header" in (loc.nth(i).get_attribute("class") or ""): continue
            seen.add(text); found.append({"type":"heading","text":text})
        return found

    def _labels(self, page):
        found, seen = [], set()
        loc = page.locator("label,mat-label,legend,[class*='label']")
        for i in range(loc.count()):
            try: text = _clean(loc.nth(i).inner_text())
            except Exception: continue
            if text in seen or _is_dynamic(text) or len(text) > 100 or "\n" in text: continue
            if text not in STATIC_DETAIL_LABELS: continue
            seen.add(text); found.append({"type":"label","text":text})
        return found

    def _listing_labels(self, page):
        # Listing labels are structural controls only; table-row text is excluded.
        return [{"type":"label","text":"Search"}] if page.locator("input[placeholder]").count() else []

    def _inputs(self, page):
        found=[]
        loc=page.locator("input:not([type='checkbox']):not([type='radio']):not(table input)")
        for i in range(loc.count()):
            el=loc.nth(i)
            try:
                ph=_clean(el.get_attribute("placeholder") or "")
                typ=(el.get_attribute("type") or "text").strip()
            except Exception: continue
            found.append({"type":"input","inputType":typ,"placeholder":ph})
        return found

    def _selects(self,page):
        return [{"type":"select"} for _ in range(page.locator("select:not(table select),mat-select").count())]

    def _checkboxes(self,page):
        return [{"type":"checkbox"} for _ in range(page.locator("input[type='checkbox']:not(table input),mat-checkbox").count())]

    def _radios(self,page):
        return [{"type":"radio_button"} for _ in range(page.locator("input[type='radio']:not(table input),mat-radio-button").count())]

    def _buttons(self,page,allowed):
        found=[]; seen=set()
        loc=page.locator("button:not(table button),[role='button']:not(table [role='button'])")
        for i in range(loc.count()):
            try: text=_clean(loc.nth(i).inner_text())
            except Exception: continue
            if text in allowed and text not in seen:
                seen.add(text); found.append({"type":"button","text":text})
        return found

    def _tabs(self,page):
        found=[]; seen=set()
        loc=page.locator(".generic-child-tab,[role='tab']")
        for i in range(loc.count()):
            try: text=_clean(loc.nth(i).inner_text())
            except Exception: continue
            if text in STATIC_TABS and text not in seen:
                seen.add(text); found.append({"type":"tab","text":text})
        return found

    def _tables(self,page):
        found=[]
        for i in range(page.locator("table").count()):
            table=page.locator("table").nth(i)
            columns=[]
            try:
                cells=table.locator("thead th,thead td").all_inner_texts()
                columns=[_clean(x) for x in cells if _clean(x) in STATIC_LISTING_COLUMNS]
            except Exception: pass
            if not columns:
                try:
                    cells=table.locator("tr").first.locator("th,td").all_inner_texts()
                    columns=[_clean(x) for x in cells if _clean(x) in STATIC_LISTING_COLUMNS]
                except Exception: pass
            found.append({"type":"table","columns":columns})
        return found
