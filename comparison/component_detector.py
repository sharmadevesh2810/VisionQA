"""
==============================================================================
VisionQA - Component Detector
==============================================================================

Extracts UI structure from a page.

The detector focuses on UI elements rather than content values.

Ignored:
- Actual input values
- IDs containing dynamic content
- Image URLs
- Dynamic dates
- Content-specific text

Captured:
- Headings
- Labels
- Inputs
- Textareas
- Selects / dropdowns
- Checkboxes
- Radio buttons
- Buttons
- Tabs
- Sections
"""

from __future__ import annotations

import re


class ComponentDetector:

    def detect(self, page):

        components = []

        try:
            components = page.evaluate(
                """
                () => {

                    const result = [];

                    function cleanText(text) {
                        if (!text) return "";

                        return text
                            .replace(/\\\\s+/g, " ")
                            .trim();
                    }

                    function add(type, element, extra = {}) {

                        if (!element) return;

                        const rect = element.getBoundingClientRect();

                        // Ignore invisible elements
                        if (
                            rect.width === 0 ||
                            rect.height === 0
                        ) {
                            return;
                        }

                        const style =
                            window.getComputedStyle(element);

                        if (
                            style.display === "none" ||
                            style.visibility === "hidden"
                        ) {
                            return;
                        }

                        result.push({
                            type: type,
                            tag: element.tagName.toLowerCase(),
                            text: cleanText(element.innerText),
                            placeholder:
                                element.getAttribute("placeholder") || "",
                            ariaLabel:
                                element.getAttribute("aria-label") || "",
                            name:
                                element.getAttribute("name") || "",
                            role:
                                element.getAttribute("role") || "",
                            ...extra
                        });
                    }


                    // ------------------------------------------------------
                    // Headings
                    // ------------------------------------------------------

                    document
                        .querySelectorAll(
                            "h1,h2,h3,h4,h5,h6"
                        )
                        .forEach(el => {

                            add(
                                "heading",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Labels
                    // ------------------------------------------------------

                    document
                        .querySelectorAll("label")
                        .forEach(el => {

                            add(
                                "label",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Inputs
                    // ------------------------------------------------------

                    document
                        .querySelectorAll("input")
                        .forEach(el => {

                            const type =
                                (
                                    el.getAttribute("type")
                                    || "text"
                                ).toLowerCase();

                            if (
                                type === "hidden"
                            ) {
                                return;
                            }

                            add(
                                "input",
                                el,
                                {
                                    inputType: type
                                }
                            );

                        });


                    // ------------------------------------------------------
                    // Textareas
                    // ------------------------------------------------------

                    document
                        .querySelectorAll("textarea")
                        .forEach(el => {

                            add(
                                "textarea",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Select / dropdown
                    // ------------------------------------------------------

                    document
                        .querySelectorAll("select")
                        .forEach(el => {

                            add(
                                "dropdown",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Buttons
                    // ------------------------------------------------------

                    document
                        .querySelectorAll(
                            "button,[role='button']"
                        )
                        .forEach(el => {

                            add(
                                "button",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Checkboxes
                    // ------------------------------------------------------

                    document
                        .querySelectorAll(
                            "input[type='checkbox']"
                        )
                        .forEach(el => {

                            add(
                                "checkbox",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Radio buttons
                    // ------------------------------------------------------

                    document
                        .querySelectorAll(
                            "input[type='radio']"
                        )
                        .forEach(el => {

                            add(
                                "radio",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Tabs
                    // ------------------------------------------------------

                    document
                        .querySelectorAll(
                            "[role='tab'],mat-tab"
                        )
                        .forEach(el => {

                            add(
                                "tab",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Tables
                    // ------------------------------------------------------

                    document
                        .querySelectorAll("table")
                        .forEach(el => {

                            add(
                                "table",
                                el
                            );

                        });


                    // ------------------------------------------------------
                    // Remove duplicates
                    // ------------------------------------------------------

                    const seen = new Set();

                    return result.filter(item => {

                        const key = JSON.stringify({
                            type: item.type,
                            tag: item.tag,
                            text: item.text,
                            placeholder: item.placeholder,
                            ariaLabel: item.ariaLabel,
                            inputType: item.inputType
                        });

                        if (seen.has(key)) {
                            return false;
                        }

                        seen.add(key);

                        return true;

                    });

                }
                """
            )

        except Exception as exc:

            print(
                f"[ComponentDetector] Failed: {exc}"
            )

            return []

        return components