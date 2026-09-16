from __future__ import annotations

import re


class SoftwareTargetUIDetector:
    """
    Static UI detector for:
        Broadcast -> Software Target

    Captures the stable UI schema and ignores runtime values such as:
    selected software, smart-card/VSNC numbers, generated IDs, etc.
    """

    STATIC_HEADINGS = {
        "Software Target",
        "On Screen Software Trigger",
    }

    STATIC_RADIO_OPTIONS = {
        "Smart Card",
        "Group",
        "Bulk Update",
        "Global Update",
    }

    STATIC_LABELS = {
        "Software",
        "Smart Card Number",
    }

    STATIC_TEXT = {
        "Enter a 10-digit CSSN or 12-digit VSMC number.",
    }

    STATIC_BUTTONS = {
        "Select Software",
        "Cancel",
        "Publish",
    }

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
        # Angular commonly renders visible labels/headings as div/span.
        values = []
        for node in page.locator(
            "h1,h2,h3,h4,h5,h6,label,button,[role='button'],"
            "input,mat-radio-button,[role='radio'],span,div"
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

    def _has_exact_or_prefixed(self, candidates: list[str], value: str) -> bool:
        target = value.lower()

        for text in candidates:
            text_lower = self._clean(text).lower()
            if text_lower == target:
                return True
            if text_lower.startswith(target + ":"):
                return True

        return False

    def _is_runtime_value(self, value: str) -> bool:
        value = self._clean(value)
        if not value:
            return True

        # Numeric-only IDs / card numbers / values.
        if re.fullmatch(r"\d+", value):
            return True

        # UUID.
        if re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}",
            value,
            re.I,
        ):
            return True

        # URL / file-like runtime values.
        if re.match(r"^(https?://|www\.)", value, re.I):
            return True

        return False

    def _headings(self, page, candidates: list[str], body: str) -> list[dict]:
        result = []

        for heading in self.STATIC_HEADINGS:
            if self._has_exact_or_prefixed(candidates, heading):
                result.append({
                    "type": "heading",
                    "text": heading,
                })
            elif heading in body:
                result.append({
                    "type": "heading",
                    "text": heading,
                })

        return self._dedupe_dicts(result)

    def _labels(self, page, candidates: list[str], body: str) -> list[dict]:
        result = []

        for label in self.STATIC_LABELS:
            if self._has_exact_or_prefixed(candidates, label):
                result.append({
                    "type": "label",
                    "text": label,
                })
            elif label in body:
                result.append({
                    "type": "label",
                    "text": label,
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

            # Do not store actual input values.
            entry = {
                "type": "input",
                "input_type": input_type,
                "placeholder": placeholder,
                "aria_label": aria_label,
            }

            if entry not in result:
                result.append(entry)

        return result

    def _radios(self, page, candidates: list[str]) -> list[dict]:
        result = []

        # First use known static options from the visible page text.
        for option in (
            "Smart Card",
            "Group",
            "Bulk Update",
            "Global Update",
        ):
            if self._has_exact_or_prefixed(candidates, option):
                result.append({
                    "type": "radio",
                    "text": option,
                })

        # Preserve radio-group semantics.
        if result:
            return result

        for node in page.locator(
            "input[type='radio'], [role='radio'], mat-radio-button"
        ).all():
            try:
                text = self._clean(node.inner_text())
                aria_label = self._clean(
                    node.get_attribute("aria-label")
                )
            except Exception:
                continue

            if text and text in self.STATIC_RADIO_OPTIONS:
                result.append({
                    "type": "radio",
                    "text": text,
                    "aria_label": aria_label,
                })

        return self._dedupe_dicts(result)

    def _buttons(self, page, candidates: list[str]) -> list[dict]:
        result = []

        for button in (
            "Select Software",
            "Cancel",
            "Publish",
        ):
            if self._has_exact_or_prefixed(candidates, button):
                result.append({
                    "type": "button",
                    "text": button,
                })

        return self._dedupe_dicts(result)

    def detect(self, page) -> dict:
        candidates = self._static_nodes(page)
        body = self._body_text(page)

        headings = self._headings(page, candidates, body)
        labels = self._labels(page, candidates, body)
        inputs = self._inputs(page)
        radios = self._radios(page, candidates)
        buttons = self._buttons(page, candidates)

        static_text = []
        for text in self.STATIC_TEXT:
            if text in body:
                static_text.append({
                    "type": "help_text",
                    "text": text,
                })

        # Comparison-ready hierarchical schema.
        ui_schema = {
            "page": "Software Target",
            "sections": [
                {
                    "name": "On Screen Software Trigger",
                    "elements": [
                        {
                            "type": "radio_group",
                            "options": [
                                option
                                for option in (
                                    "Smart Card",
                                    "Group",
                                    "Bulk Update",
                                    "Global Update",
                                )
                                if any(
                                    item.get("text") == option
                                    for item in radios
                                )
                            ],
                        },
                        {
                            "type": "field",
                            "label": "Software",
                            "control": "selector",
                            "action": "Select Software",
                        },
                        {
                            "type": "field",
                            "label": "Smart Card Number",
                            "control": "input",
                        },
                        *static_text,
                    ],
                }
            ],
            "actions": [
                button
                for button in ("Cancel", "Publish")
                if any(item.get("text") == button for item in buttons)
            ],
        }

        return {
            # Existing flat structure is retained for backward compatibility.
            "headings": headings,
            "labels": labels,
            "inputs": inputs,
            "selects": [],
            "checkboxes": [],
            "radio_buttons": radios,
            "buttons": buttons,
            "tabs": [],
            "tables": [],

            # New comparison-ready hierarchy.
            "ui_schema": ui_schema,
        }
