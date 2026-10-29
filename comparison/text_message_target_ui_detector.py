from __future__ import annotations

import re


class TextMessageTargetUIDetector:
    """
    Static UI detector for:
        Broadcast -> Text Message Target

    Captures the stable UI schema and ignores runtime/user-entered values.
    """

    STATIC_HEADINGS = {
        "Text Message Target",
        "On Screen Text Message",
    }

    STATIC_RADIO_OPTIONS = {
        "Smart Card",
        "Group Message",
        "Bulk Update",
        "Global Update",
    }

    STATIC_LABELS = {
        "Message",
        "Smart Card Number",
    }

    STATIC_HELP_TEXT = {
        "Enter a 10-digit CSSN or 12-digit VSMC number.",
    }

    STATIC_BUTTONS = {
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
        # Angular commonly renders labels/headings as div/span.
        values = []

        for node in page.locator(
            "h1,h2,h3,h4,h5,h6,label,button,[role='button'],"
            "textarea,input,mat-radio-button,[role='radio'],span,div"
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

    def _has_exact_or_prefixed(
        self,
        candidates: list[str],
        value: str,
    ) -> bool:
        target = value.lower()

        for text in candidates:
            normalized = self._clean(text).lower()

            if normalized == target:
                return True

            if normalized.startswith(target + ":"):
                return True

        return False

    def _headings(
        self,
        candidates: list[str],
        body: str,
    ) -> list[dict]:
        result = []

        for heading in self.STATIC_HEADINGS:
            if self._has_exact_or_prefixed(candidates, heading):
                result.append({
                    "type": "heading",
                    "text": heading,
                })
            elif heading.lower() in body.lower():
                result.append({
                    "type": "heading",
                    "text": heading,
                })

        return self._dedupe_dicts(result)

    def _labels(
        self,
        candidates: list[str],
        body: str,
    ) -> list[dict]:
        result = []

        for label in self.STATIC_LABELS:
            if self._has_exact_or_prefixed(candidates, label):
                result.append({
                    "type": "label",
                    "text": label,
                })
            elif label.lower() in body.lower():
                result.append({
                    "type": "label",
                    "text": label,
                })

        return self._dedupe_dicts(result)

    def _inputs(self, page) -> list[dict]:
        result = []

        # Text inputs only. Actual values are intentionally ignored.
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

            if input_type.lower() == "radio":
                continue

            entry = {
                "type": "input",
                "input_type": input_type,
                "placeholder": placeholder,
                "aria_label": aria_label,
            }

            if entry not in result:
                result.append(entry)

        # The Message control is a textarea in the UI.
        for node in page.locator("textarea").all():
            try:
                placeholder = self._clean(
                    node.get_attribute("placeholder")
                )
                aria_label = self._clean(
                    node.get_attribute("aria-label")
                )
            except Exception:
                continue

            entry = {
                "type": "textarea",
                "placeholder": placeholder,
                "aria_label": aria_label,
            }

            if entry not in result:
                result.append(entry)

        return result

    def _radios(
        self,
        page,
        candidates: list[str],
    ) -> list[dict]:
        result = []

        # Prefer the known static option names so runtime state/selection
        # never becomes part of the structure.
        for option in (
            "Smart Card",
            "Group Message",
            "Bulk Update",
            "Global Update",
        ):
            if self._has_exact_or_prefixed(candidates, option):
                result.append({
                    "type": "radio",
                    "text": option,
                })

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

            if text in self.STATIC_RADIO_OPTIONS:
                result.append({
                    "type": "radio",
                    "text": text,
                    "aria_label": aria_label,
                })

        return self._dedupe_dicts(result)

    def _buttons(
        self,
        page,
        candidates: list[str],
    ) -> list[dict]:
        result = []

        for button in ("Cancel", "Publish"):
            if self._has_exact_or_prefixed(candidates, button):
                result.append({
                    "type": "button",
                    "text": button,
                })

        return self._dedupe_dicts(result)

    def detect(self, page) -> dict:
        candidates = self._static_nodes(page)
        body = self._body_text(page)

        headings = self._headings(candidates, body)
        labels = self._labels(candidates, body)
        inputs = self._inputs(page)
        radios = self._radios(page, candidates)
        buttons = self._buttons(page, candidates)

        help_text = []

        for text in self.STATIC_HELP_TEXT:
            if text.lower() in body.lower():
                help_text.append({
                    "type": "help_text",
                    "text": text,
                })

        ui_schema = {
            "page": "Text Message Target",
            "sections": [
                {
                    "name": "On Screen Text Message",
                    "elements": [
                        {
                            "type": "radio_group",
                            "options": [
                                option
                                for option in (
                                    "Smart Card",
                                    "Group Message",
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
                            "label": "Message",
                            "control": "textarea",
                        },
                        {
                            "type": "field",
                            "label": "Smart Card Number",
                            "control": "input",
                        },
                        *help_text,
                    ],
                }
            ],
            "actions": [
                button
                for button in ("Cancel", "Publish")
                if any(
                    item.get("text") == button
                    for item in buttons
                )
            ],
        }

        return {
            "headings": headings,
            "labels": labels,
            "inputs": inputs,
            "selects": [],
            "checkboxes": [],
            "radio_buttons": radios,
            "buttons": buttons,
            "tabs": [],
            "tables": [],
            "ui_schema": ui_schema,
        }
