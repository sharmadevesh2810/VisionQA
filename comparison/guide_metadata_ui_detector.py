from __future__ import annotations

import re


class GuideMetadataUIDetector:
    """Static UI detector for System Configuration -> Guide Metadata."""

    STATIC_HEADINGS = {
        "Guide Metadata Configuration",
        "Playout Information",
        "Guide metadata",
    }

    STATIC_FIELDS = {
        "Server 1",
        "Server 2",
        "Total Bandwidth (Kbps)",
        "Last Publish Date and Time",
        "Last Failed Publish Date and Time",
        "Cooling Off Period (mins)",
    }

    SELECT_FIELDS = {
        "Server 1",
        "Server 2",
    }

    DISPLAY_FIELDS = {
        "Total Bandwidth (Kbps)",
        "Last Publish Date and Time",
        "Last Failed Publish Date and Time",
    }

    STATIC_BUTTONS = {
        "Reset",
        "Publish",
        "Re-Publish",
    }

    def _clean(self, value):
        return re.sub(r"\s+", " ", (value or "")).strip()

    def _unique_dicts(self, values):
        seen = set()
        result = []
        for value in values:
            key = tuple(sorted(value.items()))
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    def _visible_texts(self, page):
        values = []
        for node in page.locator(
            "h1,h2,h3,h4,h5,h6,label,button,[role='button'],"
            "mat-select,[role='combobox'],span,div"
        ).all():
            try:
                if not node.is_visible():
                    continue
                text = self._clean(node.inner_text())
            except Exception:
                continue

            if text and len(text) <= 120:
                values.append(text)

        return list(dict.fromkeys(values))

    def _body_text(self, page):
        try:
            return self._clean(page.locator("body").inner_text())
        except Exception:
            return ""

    def _contains_static(self, texts, body, value):
        target = value.lower()
        for text in texts:
            normalized = self._clean(text).lower()
            if normalized == target or normalized.startswith(target + ":"):
                return True
        return target in body.lower()

    def _headings(self, texts, body):
        result = []
        for heading in (
            "Guide Metadata Configuration",
            "Playout Information",
            "Guide metadata",
        ):
            if self._contains_static(texts, body, heading):
                result.append({
                    "type": "heading",
                    "text": heading,
                })
        return self._unique_dicts(result)

    def _labels(self, texts, body):
        result = []
        for label in (
            "Server 1",
            "Server 2",
            "Total Bandwidth (Kbps)",
            "Last Publish Date and Time",
            "Last Failed Publish Date and Time",
            "Cooling Off Period (mins)",
        ):
            if self._contains_static(texts, body, label):
                result.append({
                    "type": "label",
                    "text": label,
                })
        return self._unique_dicts(result)

    def _inputs(self, page):
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

            result.append({
                "type": "input",
                "input_type": input_type,
                "placeholder": placeholder,
                "aria_label": aria_label,
            })

        return self._unique_dicts(result)

    def _selects(self, page, texts, body):
        result = []

        # Server 1 and Server 2 are select controls in the UI schema.
        for field in ("Server 1", "Server 2"):
            if self._contains_static(texts, body, field):
                result.append({
                    "type": "select",
                    "label": field,
                })

        return self._unique_dicts(result)

    def _buttons(self, texts):
        result = []
        for button in ("Reset", "Publish", "Re-Publish"):
            if button in texts:
                result.append({
                    "type": "button",
                    "text": button,
                })
        return self._unique_dicts(result)

    def detect(self, page):
        texts = self._visible_texts(page)
        body = self._body_text(page)

        headings = self._headings(texts, body)
        labels = self._labels(texts, body)
        inputs = self._inputs(page)
        selects = self._selects(page, texts, body)
        buttons = self._buttons(texts)

        # Keep the hierarchy stable. Runtime values are not included.
        ui_schema = {
            "page": "Guide Metadata",
            "sections": [
                {
                    "name": "Playout Information",
                    "elements": [
                        {
                            "type": "field",
                            "label": "Server 1",
                            "control": "select",
                        },
                        {
                            "type": "field",
                            "label": "Server 2",
                            "control": "select",
                        },
                        {
                            "type": "field",
                            "label": "Total Bandwidth (Kbps)",
                            "control": "display",
                        },
                        {
                            "type": "field",
                            "label": "Last Publish Date and Time",
                            "control": "display",
                        },
                        {
                            "type": "field",
                            "label": "Last Failed Publish Date and Time",
                            "control": "display",
                        },
                    ],
                },
                {
                    "name": "Guide metadata",
                    "elements": [
                        {
                            "type": "field",
                            "label": "Cooling Off Period (mins)",
                            "control": "input",
                        },
                    ],
                },
            ],
            "actions": [
                "Reset",
                "Publish",
                "Re-Publish",
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
            "tables": [],
            "ui_schema": ui_schema,
        }
