from __future__ import annotations

import re


class GuideMetadataUIDetector:
    """
    Static UI detector for:
        System Configuration -> Guide Metadata

    Runtime values such as server IPs, bandwidth values and timestamps are
    intentionally ignored. The detector keeps the existing flat
    ``ui_structure`` format and also emits a comparison-ready ``ui_schema``.
    """

    STATIC_HEADINGS = (
        "Guide Metadata Configuration",
        "Playout Information",
        "Guide metadata",
    )

    # IMPORTANT: the UI displays Kbps with a capital K.
    STATIC_LABELS = (
        "Server 1",
        "Server 2",
        "Total Bandwidth (Kbps)",
        "Last Publish Date and Time",
        "Last Failed Publish Date and Time",
        "Cooling Off Period (mins)",
    )

    STATIC_BUTTONS = (
        "Reset",
        "Publish",
        "Re-Publish",
    )

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

    def _static_text(self, value: str | None) -> str:
        value = self._clean(value)
        if not value:
            return ""

        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return ""

        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
            return ""

        if re.search(
            r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"
            r"|\b\d{1,2}:\d{2}(?::\d{2})?\b",
            value,
        ):
            return ""

        return value

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

    def _extract_static_text_nodes(self, page) -> list[str]:
        values = []
        selectors = (
            "h1,h2,h3,h4,h5,h6,label,button,[role='button'],"
            "span,div"
        )

        for node in page.locator(selectors).all():
            try:
                if not node.is_visible():
                    continue
                text = self._clean(node.inner_text())
            except Exception:
                continue

            if text and len(text) <= 160:
                values.append(text)

        return self._unique(values)

    def _matches_static_name(self, candidates: list[str], name: str) -> bool:
        target = self._clean(name).lower()

        for text in candidates:
            normalized = self._clean(text).lower()
            if normalized == target:
                return True
            if normalized.startswith(target + ":"):
                return True

        return False

    def _contains_static_label(self, body_text: str, label: str) -> bool:
        # Case-insensitive so Kbps/kbps differences in Angular text rendering
        # do not cause a missing UI element.
        pattern = r"(?<!\w)" + re.escape(label) + r"(?=\s*:|\s|$)"
        return re.search(pattern, body_text, re.IGNORECASE) is not None

    def _headings(self, page, candidates: list[str], body: str) -> list[dict]:
        result = []
        semantic = self._texts(page, "h1,h2,h3,h4,h5,h6")

        for heading in self.STATIC_HEADINGS:
            if (
                any(self._clean(x).lower() == heading.lower() for x in semantic)
                or self._matches_static_name(candidates, heading)
                or self._contains_static_label(body, heading)
            ):
                result.append({"type": "heading", "text": heading})

        return self._dedupe_dicts(result)

    def _labels(self, page, candidates: list[str], body: str) -> list[dict]:
        result = []

        for label in self.STATIC_LABELS:
            if (
                self._matches_static_name(candidates, label)
                or self._contains_static_label(body, label)
            ):
                result.append({"type": "label", "text": label})

        # Also inspect actual <label> elements, allowing a trailing required
        # marker while still returning the canonical static label.
        for text in self._texts(page, "label"):
            normalized = re.sub(r"\s*\*\s*$", "", text).strip()
            for label in self.STATIC_LABELS:
                if normalized.lower() == label.lower():
                    result.append({"type": "label", "text": label})

        return self._dedupe_dicts(result)

    def _inputs(self, page) -> list[dict]:
        result = []

        for node in page.locator("input").all():
            try:
                input_type = self._clean(node.get_attribute("type") or "text")
                placeholder = self._clean(node.get_attribute("placeholder"))
                aria_label = self._clean(node.get_attribute("aria-label"))
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

        for node in page.locator("select, mat-select, [role='combobox']").all():
            try:
                if not node.is_visible():
                    continue
                aria_label = self._clean(node.get_attribute("aria-label"))
                text = self._static_text(node.inner_text())
            except Exception:
                continue

            entry = {
                "type": "select",
                "aria_label": aria_label,
                "text": text,
            }
            if entry not in result:
                result.append(entry)

        return result

    def _radios(self, page) -> list[dict]:
        result = []

        for node in page.locator(
            "input[type='radio'], [role='radio'], mat-radio-button"
        ).all():
            try:
                if not node.is_visible():
                    continue
                aria_label = self._clean(node.get_attribute("aria-label"))
                text = self._static_text(node.inner_text())
            except Exception:
                continue

            if text:
                result.append({
                    "type": "radio",
                    "aria_label": aria_label,
                    "text": text,
                })

        return self._dedupe_dicts(result)

    def _buttons(self, page) -> list[dict]:
        result = []

        for text in self._texts(page, "button,[role='button']"):
            for button in self.STATIC_BUTTONS:
                if text.lower() == button.lower():
                    result.append({"type": "button", "text": button})

        return self._dedupe_dicts(result)

    def detect(self, page) -> dict:
        body = self._body_text(page)
        candidates = self._extract_static_text_nodes(page)

        headings = self._headings(page, candidates, body)
        labels = self._labels(page, candidates, body)
        inputs = self._inputs(page)
        selects = self._selects(page)
        radio_buttons = self._radios(page)
        buttons = self._buttons(page)

        ui_schema = {
            "page": "Guide Metadata",
            "sections": [
                {
                    "name": "Playout Information",
                    "elements": [
                        {"type": "field", "label": "Server 1", "control": "select"},
                        {"type": "field", "label": "Server 2", "control": "select"},
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
                        {"type": "button", "text": "Reset"},
                        {"type": "button", "text": "Publish"},
                        {"type": "button", "text": "Re-Publish"},
                    ],
                },
            ],
        }

        return {
            "headings": headings,
            "labels": labels,
            "inputs": inputs,
            "selects": selects,
            "checkboxes": [],
            "radio_buttons": radio_buttons,
            "buttons": buttons,
            "tabs": [],
            "tables": [],
            "ui_schema": ui_schema,
        }
