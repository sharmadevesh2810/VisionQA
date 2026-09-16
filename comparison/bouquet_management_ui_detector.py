"""Static UI detector for Content Management -> Bouquet Management."""

from __future__ import annotations


class BouquetManagementUIDetector:
    """Capture stable Bouquet Management UI structure and ignore dynamic values."""

    LISTING_TEXT = {
        "Bouquet Management",
        "Group Name",
        "Group Id",
        "Total Bouquet",
        "Actions",
        "Add Bouquet Group",
    }

    CREATE_HEADINGS = {
        "Create Group",
        "Group Details",
        "Bouquet Details",
    }

    CREATE_LABELS = {
        "Group Name",
        "Group ID",
        "Bouquet Name",
        "Bouquet ID",
        "External Bouquet ID",
        "Bouquet Type",
    }

    STATIC_TEXT = {
        "Bouquet Management",
        "Add Bouquet Group",
        "Create Group",
        "Group Details",
        "Bouquet Details",
        "Group Name",
        "Group Id",
        "Group ID",
        "Total Bouquet",
        "Actions",
        "Bouquet Name",
        "Bouquet ID",
        "External Bouquet ID",
        "Bouquet Type",
        "Add the Bouquet you want to configure for this group.",
        "Cancel",
        "Save",
    }

    def _visible(self, locator) -> bool:
        try:
            return locator.is_visible()
        except Exception:
            return False

    def _add_text_once(self, page, target: list[dict], text: str, typ: str) -> None:
        try:
            loc = page.get_by_text(text, exact=True)
            for i in range(loc.count()):
                if self._visible(loc.nth(i)):
                    target.append({"type": typ, "text": text})
                    return
        except Exception:
            pass

    def detect_listing(self, page) -> dict:
        headings = []
        labels = []
        inputs = []
        selects = []
        checkboxes = []
        radios = []
        buttons = []
        tabs = []
        tables = []

        self._add_text_once(page, headings, "Bouquet Management", "heading")

        for text in ["Group Name", "Group Id", "Total Bouquet", "Actions"]:
            self._add_text_once(page, labels, text, "label")

        try:
            for i in range(page.locator("input:visible").count()):
                el = page.locator("input:visible").nth(i)
                typ = (el.get_attribute("type") or "text").lower()
                if typ in {"radio", "checkbox"}:
                    continue
                inputs.append({
                    "type": "input",
                    "tag": "input",
                    "inputType": typ,
                    "placeholder": el.get_attribute("placeholder") or "",
                    "ariaLabel": el.get_attribute("aria-label") or "",
                })
        except Exception:
            pass

        try:
            for _ in range(page.locator("select:visible").count()):
                selects.append({"type": "select"})
        except Exception:
            pass

        try:
            for i in range(page.locator("input[type='checkbox']:visible").count()):
                checkboxes.append({"type": "checkbox"})
        except Exception:
            pass

        try:
            for i in range(page.locator("input[type='radio']:visible").count()):
                radios.append({"type": "radio_button"})
        except Exception:
            pass

        for text in ["Add Bouquet Group"]:
            try:
                loc = page.get_by_role("button", name=text, exact=True)
                for i in range(loc.count()):
                    if self._visible(loc.nth(i)):
                        buttons.append({"type": "button", "text": text})
                        break
            except Exception:
                pass

        try:
            loc = page.locator("table:visible")
            for i in range(loc.count()):
                table = loc.nth(i)
                columns = []
                for cell in table.locator("thead th:visible").all_inner_texts():
                    value = " ".join((cell or "").split()).strip()
                    if value and value not in columns:
                        columns.append(value)
                if not columns:
                    columns = ["Group Name", "Group Id", "Total Bouquet", "Actions"]
                tables.append({"type": "table", "columns": columns})
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
            "tabs": tabs,
            "tables": tables,
        }

    def detect_create_group(self, page) -> dict:
        headings = []
        labels = []
        inputs = []
        selects = []
        checkboxes = []
        radios = []
        buttons = []

        for text in self.CREATE_HEADINGS:
            self._add_text_once(page, headings, text, "heading")

        for text in self.CREATE_LABELS:
            self._add_text_once(page, labels, text, "label")

        try:
            for i in range(page.locator("input:visible").count()):
                el = page.locator("input:visible").nth(i)
                typ = (el.get_attribute("type") or "text").lower()
                if typ in {"radio", "checkbox"}:
                    continue
                inputs.append({
                    "type": "input",
                    "tag": "input",
                    "inputType": typ,
                    "placeholder": el.get_attribute("placeholder") or "",
                    "ariaLabel": el.get_attribute("aria-label") or "",
                })
        except Exception:
            pass

        try:
            for _ in range(page.locator("select:visible").count()):
                selects.append({"type": "select"})
        except Exception:
            pass

        try:
            for _ in range(page.locator("input[type='checkbox']:visible").count()):
                checkboxes.append({"type": "checkbox"})
        except Exception:
            pass

        try:
            for _ in range(page.locator("input[type='radio']:visible").count()):
                radios.append({"type": "radio_button"})
        except Exception:
            pass

        for text in ["Cancel", "Save"]:
            try:
                loc = page.get_by_role("button", name=text, exact=True)
                for i in range(loc.count()):
                    if self._visible(loc.nth(i)):
                        buttons.append({"type": "button", "text": text})
                        break
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
