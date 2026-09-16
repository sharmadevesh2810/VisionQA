from __future__ import annotations

import re


class ChannelLogoUIDetector:
    """
    Static UI detector for System Configuration -> Channel Logo.

    Dynamic values such as sizes, versions, timestamps and other runtime
    values are intentionally ignored.
    """

    STATIC_HEADINGS = {
        "Channel Logo Configuration",
        "Playout Information",
        "Channel Logo",
    }

    STATIC_LABELS = {
        "Image Height (Pixels)",
        "Image Width (Pixels)",
        "Image Quality (%)",
        "Image Format",
        "Cooling Off Period (mins)",
        "Bandwidth(kbps)",
        "Logo.zip(KB)",
        "Property Version",
        "Last Publish Date and Time",
        "Last Failed Publish Date and Time",
    }

    STATIC_BUTTONS = {
        "Reset",
        "Publish",
        "Re-Publish",
    }

    def _clean(self, value: str | None) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip()

    def _is_dynamic(self, value: str) -> bool:
        value = self._clean(value)
        if not value:
            return True

        # IDs / UUIDs / URLs
        if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}", value):
            return True
        if re.search(r"https?://", value, re.I):
            return True

        # Dates / times
        if re.search(
            r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d{1,2}:\d{2}(?::\d{2})?\b",
            value,
        ):
            return True

        # Numeric-only runtime values
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return True

        return False

    def _texts(self, page, selector: str) -> list[str]:
        values = []
        for item in page.locator(selector).all():
            try:
                text = self._clean(item.inner_text())
            except Exception:
                continue
            if text:
                values.append(text)
        return values

    def detect(self, page) -> dict:
        headings = []
        for text in self._texts(page, "h1,h2,h3,h4,h5,h6"):
            if text in self.STATIC_HEADINGS and text not in headings:
                headings.append(text)

        labels = []
        for text in self._texts(page, "label"):
            text = re.sub(r"\s*\*\s*$", "", text).strip()
            if text in self.STATIC_LABELS and text not in labels:
                labels.append(text)

        # Some Angular custom controls expose field names as plain text.
        if not labels:
            body_text = self._texts(page, "body")
            body = "\n".join(body_text)
            for label in self.STATIC_LABELS:
                if label in body:
                    labels.append(label)

        inputs = []
        for item in page.locator("input").all():
            try:
                placeholder = self._clean(item.get_attribute("placeholder"))
                input_type = self._clean(item.get_attribute("type") or "text")
                aria = self._clean(item.get_attribute("aria-label"))
            except Exception:
                continue

            # Values are deliberately not captured.
            if placeholder or input_type:
                entry = {
                    "type": "input",
                    "placeholder": placeholder,
                    "input_type": input_type,
                    "aria_label": aria,
                }
                if entry not in inputs:
                    inputs.append(entry)

        selects = []
        for item in page.locator("select, mat-select").all():
            try:
                aria = self._clean(item.get_attribute("aria-label"))
                text = self._clean(item.inner_text())
            except Exception:
                continue
            selects.append({
                "type": "select",
                "aria_label": aria,
                "text": "" if self._is_dynamic(text) else text,
            })

        radio_buttons = []
        for item in page.locator(
            "input[type='radio'], [role='radio'], mat-radio-button"
        ).all():
            try:
                aria = self._clean(item.get_attribute("aria-label"))
                text = self._clean(item.inner_text())
            except Exception:
                continue
            radio_buttons.append({
                "type": "radio",
                "aria_label": aria,
                "text": "" if self._is_dynamic(text) else text,
            })

        buttons = []
        for text in self._texts(page, "button,[role='button']"):
            if text in self.STATIC_BUTTONS and text not in buttons:
                buttons.append(text)

        tables = []
        for table in page.locator("table").all():
            try:
                headers = []
                for cell in table.locator("th").all():
                    text = self._clean(cell.inner_text())
                    if text and not self._is_dynamic(text):
                        headers.append(text)
                if headers:
                    tables.append({
                        "type": "table",
                        "columns": list(dict.fromkeys(headers)),
                    })
            except Exception:
                continue

        return {
            "headings": [{"type": "heading", "text": x} for x in headings],
            "labels": [{"type": "label", "text": x} for x in labels],
            "inputs": inputs,
            "selects": selects,
            "checkboxes": [],
            "radio_buttons": radio_buttons,
            "buttons": [{"type": "button", "text": x} for x in buttons],
            "tabs": [],
            "tables": tables,
        }
