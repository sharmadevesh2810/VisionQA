"""
==============================================================================
VisionQA - Component Detector
==============================================================================

Copyright (c) 2026 Devesh Sharma.
All Rights Reserved.

Author      : Devesh Sharma
Framework   : VisionQA
"""

from comparison.component_registry import COMPONENT_RULES


class ComponentDetector:

    def detect(self, page):

        components = []

        for component, selectors in COMPONENT_RULES.items():

            unique_elements = set()
            matched_selector = None

            for selector in selectors:

                try:

                    locator = page.locator(selector)

                    count = locator.count()

                    for i in range(count):

                        element = locator.nth(i)

                        # Ignore hidden elements
                        if not element.is_visible():
                            continue

                        # Create a fingerprint for the element
                        fingerprint = element.evaluate(
                            "el => el.outerHTML"
                        )

                        if fingerprint not in unique_elements:

                            unique_elements.add(fingerprint)

                            if matched_selector is None:
                                matched_selector = selector

                except Exception:
                    continue

            if unique_elements:

                components.append(
    {
        "component": component,
        "present": True,
        "selector": matched_selector,
    }
)

        return components