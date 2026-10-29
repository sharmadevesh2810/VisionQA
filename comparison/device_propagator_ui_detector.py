from __future__ import annotations

import re


class DevicePropagatorUIDetector:
    """Static UI detector for System Configuration -> Device Propagator."""

    LISTING_HEADINGS = {
        "Device Propagator",
    }

    DETAILS_HEADINGS = {
        "ZIP Details",
        "Service Status",
    }

    LISTING_LABELS = {
        "Upload ID",
        "File Name",
        "Map Attached",
        "Started Date & Time",
        "Status",
        "Actions",
    }

    DETAILS_LABELS = {
        "Upload ID",
        "SCPC File Name",
        "MAP File Name",
        "Uploaded By",
        "Status",
        "Total Devices",
        "Device Chipset Type",
        "Start Date & Time",
        "Completed Date & Time",
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

    ZIP_DETAILS_FIELDS = [
        "Upload ID",
        "SCPC File Name",
        "MAP File Name",
        "Uploaded By",
        "Status",
        "Total Devices",
        "Device Chipset Type",
        "Start Date & Time",
        "Completed Date & Time",
    ]

    SERVICE_STATUS_FIELDS = [
        "SCPC Files Upload",
        "KMS MAP Upload",
        "KMS SCD Upload",
        "KMS OSC Upload",
        "KMS IID Upload",
        "Account Manager Import",
        "Operator IEP Upload",
    ]

    def _clean(self, value: str | None) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip()

    def _unique(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(x for x in values if x))

    def _dedupe_dicts(self, values: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for value in values:
            key = tuple(sorted(value.items()))
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    def _texts(self, page, selector: str) -> list[str]:
        result = []
        for node in page.locator(selector).all():
            try:
                if not node.is_visible():
                    continue
                text = self._clean(node.inner_text())
            except Exception:
                continue
            if text:
                result.append(text)
        return self._unique(result)

    def _body_text(self, page) -> str:
        try:
            return self._clean(page.locator("body").inner_text())
        except Exception:
            return ""

    def _static_nodes(self, page) -> list[str]:
        values = []
        for node in page.locator(
            "h1,h2,h3,h4,h5,h6,label,button,[role='button'],"
            "mat-radio-button,[role='radio'],span,div"
        ).all():
            try:
                if not node.is_visible():
                    continue
                text = self._clean(node.inner_text())
            except Exception:
                continue

            if text and len(text) <= 120:
                values.append(text)

        return self._unique(values)

    def _has_name(self, candidates: list[str], body: str, name: str) -> bool:
        target = name.lower()

        for text in candidates:
            normalized = self._clean(text).lower()
            if normalized == target:
                return True
            if normalized.startswith(target + ":"):
                return True

        return name.lower() in body.lower()

    def _headings(
        self,
        candidates: list[str],
        body: str,
        names: set[str],
    ) -> list[dict]:
        result = []

        # Semantic headings first.
        for text in candidates:
            if text in names:
                result.append({
                    "type": "heading",
                    "text": text,
                })

        # Angular div/span based headings.
        for name in names:
            if self._has_name(candidates, body, name):
                result.append({
                    "type": "heading",
                    "text": name,
                })

        return self._dedupe_dicts(result)

    def _labels(
        self,
        candidates: list[str],
        body: str,
        names: set[str],
    ) -> list[dict]:
        result = []

        for name in names:
            if self._has_name(candidates, body, name):
                result.append({
                    "type": "label",
                    "text": name,
                })

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

    def _buttons(self, page, include_view: bool) -> list[dict]:
        result = []

        for text in self._texts(page, "button,[role='button']"):
            if text in self.STATIC_BUTTONS:
                result.append({
                    "type": "button",
                    "text": text,
                })

        if include_view:
            try:
                if page.locator("#viewIcon").count():
                    result.append({
                        "type": "button",
                        "text": "View",
                        "selector": "#viewIcon",
                    })
            except Exception:
                pass

        return self._dedupe_dicts(result)

    def _tables(self, page) -> list[dict]:
        result = []

        for table in page.locator("table").all():
            try:
                columns = []

                for cell in table.locator(
                    "thead th, thead td, "
                    "tr:first-child th, tr:first-child td, "
                    "[role='columnheader']"
                ).all():
                    text = self._clean(cell.inner_text())
                    if text in self.LISTING_COLUMNS:
                        columns.append(text)

                if columns:
                    result.append({
                        "type": "table",
                        "columns": self._unique(columns),
                    })
            except Exception:
                continue

        return result

    def detect_listing(self, page) -> dict:
        candidates = self._static_nodes(page)
        body = self._body_text(page)

        headings = self._headings(
            candidates,
            body,
            self.LISTING_HEADINGS,
        )

        labels = self._labels(
            candidates,
            body,
            self.LISTING_LABELS,
        )

        inputs = self._inputs(page)
        selects = self._selects(page)
        buttons = self._buttons(page, include_view=True)
        tables = self._tables(page)

        ui_schema = {
            "page": "Device Propagator",
            "sections": [
                {
                    "name": "Device Propagator",
                    "elements": [
                        {
                            "type": "table",
                            "columns": list(self.LISTING_COLUMNS),
                        }
                    ],
                }
            ],
            "actions": [
                "Upload File",
                "Load More",
                "View",
            ],
        }

        return {
            "headings": headings,
            "labels": labels,
            "inputs": inputs,
            "selects": selects,
            "checkboxes": [],
            "radio_buttons": [],
            "buttons": buttons,
            "tabs": [],
            "tables": tables,
            "ui_schema": ui_schema,
        }

    def detect_details(self, page) -> dict:
        candidates = self._static_nodes(page)
        body = self._body_text(page)

        headings = self._headings(
            candidates,
            body,
            self.DETAILS_HEADINGS,
        )

        labels = self._labels(
            candidates,
            body,
            self.DETAILS_LABELS,
        )

        inputs = self._inputs(page)
        selects = self._selects(page)

        # Details page does not use business actions.
        buttons = []

        ui_schema = {
            "page": "Device Propagator - Details",
            "sections": [
                {
                    "name": "ZIP Details",
                    "elements": [
                        {
                            "type": "field",
                            "label": field,
                            "control": "detail_field",
                        }
                        for field in self.ZIP_DETAILS_FIELDS
                        if any(
                            item.get("text") == field
                            for item in labels
                        )
                    ],
                },
                {
                    "name": "Service Status",
                    "elements": [
                        {
                            "type": "service_status",
                            "label": field,
                        }
                        for field in self.SERVICE_STATUS_FIELDS
                        if any(
                            item.get("text") == field
                            for item in labels
                        )
                    ],
                },
            ],
            "actions": [],
        }

        return {
            "headings": headings,
            "labels": labels,
            "inputs": inputs,
            "selects": selects,
            "checkboxes": [],
            "radio_buttons": [],
            "buttons": buttons,
            "tabs": [],
            "tables": [],
            "ui_schema": ui_schema,
        }
