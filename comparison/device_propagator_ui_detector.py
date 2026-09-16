from __future__ import annotations

import re


class DevicePropagatorUIDetector:
    """Static UI detector for System Configuration -> Device Propagator."""

    STATIC_HEADINGS = {
        "Device Propagator",
        "ZIP Details",
        "Service Status",
    }

    STATIC_LABELS = {
        # Listing
        "Upload ID",
        "File Name",
        "Map Attached",
        "Started Date & Time",
        "Status",
        "Actions",
        # ZIP details
        "SCPC File Name",
        "MAP File Name",
        "Uploaded By",
        "Total Devices",
        "Device Chipset Type",
        "Start Date & Time",
        "Completed Date & Time",
        # Service status
        "SCPC Files Upload",
        "KMS MAP Upload",
        "KMS SCD Upload",
        "KMS OSC Upload",
        "KMS IID Upload",
        "Account Manager Import",
        "Operator IEP Upload",
    }

    STATIC_BUTTONS = {
        "Upload File",
        "Load More",
    }

    LISTING_COLUMNS = [
        "Upload ID",
        "File Name",
        "Map Attached",
        "Started Date & Time",
        "Status",
        "Actions",
    ]

    def _clean(self, value: str | None) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip()

    def _unique(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(x for x in values if x))

    def _is_dynamic(self, value: str) -> bool:
        value = self._clean(value)
        if not value:
            return True

        # Numeric IDs, counts and values.
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return True

        # IP addresses.
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
            return True

        # UUIDs / UUID-like identifiers.
        if re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}",
            value,
            re.I,
        ):
            return True

        # Date/time values.
        if re.search(
            r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"
            r"|\b\d{1,2}:\d{2}(?::\d{2})?\b",
            value,
        ):
            return True

        return False

    def _texts(self, page, selector: str) -> list[str]:
        values = []
        for node in page.locator(selector).all():
            try:
                text = self._clean(node.inner_text())
            except Exception:
                continue
            if text:
                values.append(text)
        return values

    def _headings(self, page) -> list[dict]:
        result = []
        for text in self._texts(page, "h1,h2,h3,h4,h5,h6"):
            # The listing heading is rendered as "Device Propagator (10)".
            normalized = re.sub(r"\s*\(\d+\)\s*$", "", text).strip()
            if normalized in self.STATIC_HEADINGS:
                result.append({"type": "heading", "text": normalized})

        return self._dedupe_dicts(result)

    def _labels(self, page) -> list[dict]:
        result = []

        # Native labels.
        for text in self._texts(page, "label"):
            text = re.sub(r"\s*\*\s*$", "", text).strip()
            if text in self.STATIC_LABELS:
                result.append({"type": "label", "text": text})

        # Angular/div-based field labels.
        for text in self._texts(page, "body"):
            for label in self.STATIC_LABELS:
                if label in text and label not in {
                    item["text"] for item in result
                }:
                    result.append({"type": "label", "text": label})

        return self._dedupe_dicts(result)

    def _inputs(self, page) -> list[dict]:
        result = []
        for node in page.locator("input").all():
            try:
                input_type = self._clean(
                    node.get_attribute("type") or "text"
                )
                placeholder = self._clean(
                    node.get_attribute("placeholder")
                )
                aria_label = self._clean(
                    node.get_attribute("aria-label")
                )
            except Exception:
                continue

            entry = {
                "type": "input",
                "input_type": input_type,
                "placeholder": placeholder,
                "aria_label": aria_label,
            }

            if entry not in result:
                result.append(entry)

        return result

    def _selects(self, page) -> list[dict]:
        result = []
        for node in page.locator(
            "select, mat-select, [role='combobox']"
        ).all():
            try:
                aria_label = self._clean(
                    node.get_attribute("aria-label")
                )
            except Exception:
                continue

            entry = {
                "type": "select",
                "aria_label": aria_label,
            }

            if entry not in result:
                result.append(entry)

        return result

    def _buttons(self, page, details: bool = False) -> list[dict]:
        result = []

        for text in self._texts(page, "button,[role='button']"):
            if text in self.STATIC_BUTTONS:
                result.append({
                    "type": "button",
                    "text": text,
                })

        # The listing's eye icon has no stable visible text.
        if not details:
            try:
                view_count = page.locator("#viewIcon").count()
            except Exception:
                view_count = 0

            if view_count:
                result.append({
                    "type": "button",
                    "text": "View",
                    "selector": "#viewIcon",
                })

        return self._dedupe_dicts(result)

    def _tables(self, page, details: bool = False) -> list[dict]:
        if details:
            return []

        tables = []
        for table in page.locator("table").all():
            try:
                header_cells = table.locator(
                    "thead th, thead td"
                ).all()
                columns = []
                for cell in header_cells:
                    text = self._clean(cell.inner_text())
                    if text in self.LISTING_COLUMNS:
                        columns.append(text)

                if not columns:
                    # Fallback for Angular tables where headers are divs.
                    header_row = table.locator(
                        "tr"
                    ).first
                    for cell in header_row.locator(
                        "th,td,[role='columnheader']"
                    ).all():
                        text = self._clean(cell.inner_text())
                        if text in self.LISTING_COLUMNS:
                            columns.append(text)

                if columns:
                    tables.append({
                        "type": "table",
                        "columns": self._unique(columns),
                    })
            except Exception:
                continue

        return tables

    def _dedupe_dicts(self, values: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for value in values:
            key = tuple(sorted(value.items()))
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    def detect_listing(self, page) -> dict:
        return {
            "headings": self._headings(page),
            "labels": self._labels(page),
            "inputs": self._inputs(page),
            "selects": self._selects(page),
            "checkboxes": [],
            "radio_buttons": [],
            "buttons": self._buttons(page, details=False),
            "tabs": [],
            "tables": self._tables(page, details=False),
        }

    def detect_details(self, page) -> dict:
        return {
            "headings": self._headings(page),
            "labels": self._labels(page),
            "inputs": self._inputs(page),
            "selects": self._selects(page),
            "checkboxes": [],
            "radio_buttons": [],
            "buttons": self._buttons(page, details=True),
            "tabs": [],
            "tables": self._tables(page, details=True),
        }
