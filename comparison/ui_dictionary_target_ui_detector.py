from __future__ import annotations

import re


class UIDictionaryTargetUIDetector:
    """Static UI detector for Broadcast -> UI Dictionary Target."""

    STATIC_HEADINGS = {
        "UI Dictionary Target",
        "UI Dictionary Version",
    }

    STATIC_LABELS = {
        "Select UI Dictionary Version",
    }

    STATIC_BUTTONS = {
        "Select Version",
        "Reset",
        "Publish",
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
            "input,select,mat-select,[role='combobox'],span,div"
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
            "UI Dictionary Target",
            "UI Dictionary Version",
        ):
            if self._contains_static(texts, body, heading):
                result.append({
                    "type": "heading",
                    "text": heading,
                })

        return self._unique_dicts(result)

    def _labels(self, texts, body):
        result = []

        label = "Select UI Dictionary Version"
        if self._contains_static(texts, body, label):
            result.append({
                "type": "label",
                "text": label,
            })

        return result

    def _inputs(self, page):
        result = []

        # Capture control type/placeholder only; never capture its value.
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

        # The UI shows a version-selection control. Treat it as a select
        # business control even if Angular renders it as a custom element.
        if self._contains_static(
            texts,
            body,
            "Select UI Dictionary Version",
        ):
            result.append({
                "type": "select",
                "label": "Select UI Dictionary Version",
            })

        return result

    def _buttons(self, texts):
        result = []

        for button in (
            "Select Version",
            "Reset",
            "Publish",
        ):
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

        ui_schema = {
            "page": "UI Dictionary Target",
            "sections": [
                {
                    "name": "UI Dictionary Version",
                    "elements": [
                        {
                            "type": "field",
                            "label": "Select UI Dictionary Version",
                            "control": "select",
                        },
                        {
                            "type": "action",
                            "label": "Select Version",
                            "control": "button",
                        },
                    ],
                }
            ],
            "actions": [
                "Reset",
                "Publish",
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
