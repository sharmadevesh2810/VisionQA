from __future__ import annotations

import re


class ChannelPosterUIDetector:
    """
    Static UI detector for:
        System Configuration -> Channel Poster

    Runtime values such as image dimensions, file sizes, versions,
    timestamps and other configuration values are intentionally ignored.
    """

    STATIC_HEADINGS = {
        "Channel Poster Configuration",
        "Playout Information",
        "Channel Poster",
    }

    STATIC_LABELS = {
        "Image Height (Pixels)",
        "Image Width (Pixels)",
        "Image Quality (%)",
        "Image Format",
        "Cooling Off Period (mins)",
        "Bandwidth (kbps)",
        "Poster.zip (KB)",
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

    def _static_text(self, value: str | None) -> str:
        value = self._clean(value)
        if not value:
            return ""

        # Do not retain runtime values.
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return ""

        if re.search(
            r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"
            r"|\b\d{1,2}:\d{2}(?::\d{2})?\b",
            value,
        ):
            return ""

        if re.search(r"https?://", value, re.I):
            return ""

        return value

    def _unique(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(x for x in values if x))

    def _texts(self, page, selector: str) -> list[str]:
        result = []
        for node in page.locator(selector).all():
            try:
                text = self._clean(node.inner_text())
            except Exception:
                continue
            if text:
                result.append(text)
        return result

    def detect(self, page) -> dict:
        # Headings
        headings = []
        for text in self._texts(page, "h1,h2,h3,h4,h5,h6"):
            if text in self.STATIC_HEADINGS and text not in headings:
                headings.append(text)

        # Labels
        labels = []
        for text in self._texts(page, "label"):
            # Remove required-field marker.
            text = re.sub(r"\s*\*\s*$", "", text).strip()
            if text in self.STATIC_LABELS and text not in labels:
                labels.append(text)

        # Angular/custom UI can expose labels as plain text.
        body = "\n".join(self._texts(page, "body"))
        for label in self.STATIC_LABELS:
            if label in body and label not in labels:
                labels.append(label)

        # Inputs: structure only, never values.
        inputs = []
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
            if entry not in inputs:
                inputs.append(entry)

        # Selects/custom selects.
        selects = []
        for node in page.locator("select, mat-select, [role='combobox']").all():
            try:
                aria_label = self._clean(node.get_attribute("aria-label"))
                text = self._static_text(node.inner_text())
            except Exception:
                continue

            entry = {
                "type": "select",
                "aria_label": aria_label,
                "text": text,
            }
            if entry not in selects:
                selects.append(entry)

        # Radio controls.
        radio_buttons = []
        for node in page.locator(
            "input[type='radio'], [role='radio'], mat-radio-button"
        ).all():
            try:
                aria_label = self._clean(node.get_attribute("aria-label"))
                text = self._static_text(node.inner_text())
            except Exception:
                continue

            entry = {
                "type": "radio",
                "aria_label": aria_label,
                "text": text,
            }
            if entry not in radio_buttons:
                radio_buttons.append(entry)

        # Buttons: only known static actions.
        buttons = []
        for text in self._texts(page, "button,[role='button']"):
            if text in self.STATIC_BUTTONS and text not in buttons:
                buttons.append(text)

        return {
            "headings": [
                {"type": "heading", "text": text}
                for text in self._unique(headings)
            ],
            "labels": [
                {"type": "label", "text": text}
                for text in self._unique(labels)
            ],
            "inputs": inputs,
            "selects": selects,
            "checkboxes": [],
            "radio_buttons": radio_buttons,
            "buttons": [
                {"type": "button", "text": text}
                for text in self._unique(buttons)
            ],
            "tabs": [],
            "tables": [],
        }
