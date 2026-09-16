"""Static UI detector for the Content Management -> Global Configuration page."""

from __future__ import annotations


class GlobalConfigurationUIDetector:
    """Capture stable UI structure while ignoring backend/dynamic values."""

    SECTION_NAMES = {
        "Watermarking",
        "SSAI",
        "CDN Auth Token",
        "Primary Origin",
    }

    STATIC_TEXT = {
        "Watermarking",
        "SSAI",
        "CDN Auth Token",
        "Primary Origin",
        "This Watermarking change affects all the channels who have watermarking enabled. Ensure the setting is correct before applying.",
        "This SSAI change affects every channel in your platform. Ensure the setting is correct before applying.",
        "This CDN Auth. change affects every channel in your platform. Ensure the setting is correct before applying.",
        "Changing the Primary Origin affects all the channels who have On-Prem or On-Cloud origins configured. Ensure the setting is correct before applying.",
        "Enabled",
        "Channel Level",
        "Enable",
        "Disable",
        "On Prem",
        "On Cloud",
        "Apply",
    }

    def _visible_text(self, page) -> list[str]:
        try:
            texts = page.locator("body *:visible").all_inner_texts()
        except Exception:
            texts = []
        result = []
        seen = set()
        for text in texts:
            value = " ".join((text or "").split()).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _matches(self, value: str, allowed: set[str]) -> bool:
        return value in allowed

    def detect(self, page) -> dict:
        headings = []
        labels = []
        inputs = []
        selects = []
        checkboxes = []
        radios = []
        buttons = []

        # Headings / cards are stable schema elements.
        for name in self.SECTION_NAMES:
            try:
                loc = page.get_by_text(name, exact=True).first
                if loc.count() and loc.is_visible():
                    headings.append({"type": "heading", "text": name})
            except Exception:
                pass

        # Stable labels/text. Keep only known static strings.
        for name in [
            "Enabled", "Channel Level", "Enable", "Disable", "On Prem", "On Cloud"
        ]:
            try:
                loc = page.get_by_text(name, exact=True)
                count = loc.count()
                for i in range(count):
                    item = loc.nth(i)
                    if item.is_visible():
                        labels.append({"type": "label", "text": name})
                        break
            except Exception:
                pass

        # Inputs: radio controls are represented separately; do not capture
        # dynamic/internal values.
        try:
            count = page.locator("input:visible").count()
            for i in range(count):
                el = page.locator("input:visible").nth(i)
                typ = (el.get_attribute("type") or "").lower()
                if typ in {"radio", "checkbox"}:
                    continue
                inputs.append({
                    "type": "input",
                    "tag": "input",
                    "inputType": typ or "text",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "ariaLabel": el.get_attribute("aria-label") or "",
                })
        except Exception:
            pass

        # Radio groups are the important controls on this page.
        try:
            count = page.locator("input[type='radio']:visible").count()
            for i in range(count):
                el = page.locator("input[type='radio']:visible").nth(i)
                radios.append({
                    "type": "radio_button",
                    "value": el.get_attribute("value") or "",
                    "ariaLabel": el.get_attribute("aria-label") or "",
                })
        except Exception:
            pass

        try:
            count = page.locator("input[type='checkbox']:visible").count()
            for i in range(count):
                checkboxes.append({"type": "checkbox"})
        except Exception:
            pass

        # No select is visible in the supplied UI, but keep schema support.
        try:
            count = page.locator("select:visible").count()
            for _ in range(count):
                selects.append({"type": "select"})
        except Exception:
            pass

        # Apply buttons are stable; avoid harvesting arbitrary DOM buttons.
        try:
            loc = page.get_by_role("button", name="Apply", exact=True)
            for i in range(loc.count()):
                if loc.nth(i).is_visible():
                    buttons.append({"type": "button", "text": "Apply"})
        except Exception:
            pass

        return {
            "headings": headings,
            "labels": labels,
            "inputs": inputs,
            "selects": selects,
            "checkboxes": checkboxes,
            "radio_buttons": radios,
            "buttons": buttons,
            "tabs": [],
            "tables": [],
        }
