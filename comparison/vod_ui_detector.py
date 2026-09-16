"""
VisionQA - VOD static UI detector.

Detects the hardcoded/static UI structure of a VOD Details view.
Dynamic catalog values such as IDs, titles, dates, filenames and Yes/No
values are intentionally ignored.
"""

from __future__ import annotations

from playwright.sync_api import Page


class VODUIDetector:
    """Detect static UI structure inside a VOD Details view."""

    def detect_details(self, page: Page) -> dict:
        return page.evaluate(
            """
            () => {
                const SECTION_NAMES = [
                    "Basic Metadata",
                    "Images",
                    "Hierarchy Parents",
                    "Media",
                    "Offers",
                    "Access & Rights",
                    "Package",
                    "Catalogs"
                ];

                const clean = (value) =>
                    (value || "")
                        .replace(/\\s+/g, " ")
                        .trim();

                const visible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return (
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        parseFloat(style.opacity || "1") > 0 &&
                        rect.width > 0 &&
                        rect.height > 0
                    );
                };

                const textOf = (el) => clean(el.innerText || el.textContent || "");

                const unique = (items) => {
                    const seen = new Set();
                    return items.filter((item) => {
                        const key = JSON.stringify(item);
                        if (seen.has(key)) return false;
                        seen.add(key);
                        return true;
                    });
                };

                const isDynamicValue = (text) => {
                    const value = clean(text);
                    if (!value) return true;

                    // IDs / UUID-like values / package IDs.
                    if (/^(PACK|[A-Z]{2,}):?[^\\s]*$/i.test(value) && value.length > 8) return true;
                    if (/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value)) return true;
                    if (/^[a-z0-9_-]{10,}$/i.test(value) && /\\d/.test(value)) return true;

                    // Dates/timestamps.
                    if (/\\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\b.*\\d{1,2}.*\\d{1,2}:\\d{2}/i.test(value)) return true;
                    if (/^\\d{1,4}[\\/-]\\d{1,2}[\\/-]\\d{1,4}/.test(value)) return true;
                    if (/\\d{4}-\\d{2}-\\d{2}/.test(value)) return true;

                    // Common content/file values.
                    if (/\\.(jpg|jpeg|png|gif|webp|mp4|mkv|mov|m3u8)$/i.test(value)) return true;
                    if (/^https?:\\/\\//i.test(value)) return true;
                    if (/^[0-9]+$/.test(value)) return true;

                    return false;
                };

                // Conservative static-field vocabulary for OPC VOD Details.
                // These are UI schema labels, not catalog values.  Keeping this
                // vocabulary separate prevents values such as Series, AMS, Max,
                // Drama, Yes/No, actor names, etc. from being promoted to labels.
                const STATIC_LABELS = new Set([
                    "Content ID", "Central ID", "Source ID's", "Package ID",
                    "Package Type", "Source System", "Modified Date & Time",
                    "Created Date & Time", "Is Deleted", "Merged Central ID's",
                    "Title", "English", "Malay", "Chinese", "Tamil",
                    "Long Synopsis", "Long Synopsis - Malay",
                    "Long Synopsis - Chinese", "Long Synopsis - Tamil",
                    "Short Synopsis", "Short Synopsis - Malay",
                    "Short Synopsis - Chinese", "Short Synopsis - Tamil",
                    "Content Information", "Year of Release", "Audio Language",
                    "Certification", "Credits", "Directors", "Producers",
                    "Actors", "Owner Channels", "Business Unit",
                    "Channel STB Number", "Channel ID", "Channel Name", "Keywords",
                    "Classifications", "Primary Genre", "Label", "Value",
                    "Secondary Genre", "Code", "Image 1", "Image Name",
                    "Image Size (Bytes)", "Image Usage Type", "Orientation",
                    "Image URL", "Checksum", "Dimension", "Profile",
                    "Channel Logo", "Service Label", "Channel Logo Checksum",
                    "Channel Logo URL", "Preview Image", "Subtitle", "Audio",
                    "Media Full Asset", "Media Preview Asset", "Duration (Sec)",
                    "Duration In Frame", "Clip ID", "Services", "AV Preview Asset",
                    "Start Position (Sec)", "Enable", "Image Ribbons",
                    "Image Ribbon ID", "Period Start Date & Time",
                    "Period End Date & Time", "Output Media", "Block Ads",
                    "Ads Enabled", "Ads Supplier", "Ads Pre Roll", "Ads Mid Roll",
                    "Ads Post Roll", "Asset Life Cycle", "Pre Login", "Charge Code",
                    "Third Party Label", "Casting Label", "SFV Account Label",
                    "Availability", "Coming Soon End Date", "Selling Period Start",
                    "Selling Period End", "Offer Start", "Offer End", "Download",
                    "D2GO Retention Period Label",
                    "Download To Go IVP API Provider ID", "D2GO Max Play Count Label",
                    "D2GO Max Play Period Label", "Download 2 Go",
                    "Provider Content Tier", "SKU", "Offer Row", "In App Price",
                    "Offer Type Label", "BM Label", "Max View", "Price Label GST",
                    "Region Label", "Currency Label", "Price Label",
                    "Transformed Price Label", "Transformed Price Label GST",
                    "SW DRM Resolution Cap", "HW DRM Resolution Cap",
                    "CDN Tokenisation", "Across All Device", "Device Specific",
                    "Package Data Provider", "Package Data ID", "Exclude Brand",
                    "New Label Enabled", "Boxset Type Label", "Supplier",
                    "Supplier Label", "Audience Community", "Live Event ID",
                    "Sort Order", "Is Sponsored", "Brand Page",
                    "NDS Package Asset ID", "Additional Info Label",
                    "Additional Info Value", "Name", "Is Playable",
                    "Is Presentable", "Is Purchasable"
                ]);

                const headingCandidates = Array.from(
                    document.querySelectorAll("h1,h2,h3,h4,h5,h6,[role='heading']")
                ).filter(visible);

                const matchingHeadings = headingCandidates.filter((el) =>
                    SECTION_NAMES.includes(textOf(el))
                );

                // Find the smallest useful Details container. The important
                // point is that the VOD listing remains outside this root.
                let root = null;
                let bestScore = -Infinity;

                for (const heading of matchingHeadings) {
                    let ancestor = heading.parentElement;
                    let depth = 0;

                    while (ancestor && depth < 12) {
                        const descendantHeadings = Array.from(
                            ancestor.querySelectorAll("h1,h2,h3,h4,h5,h6,[role='heading']")
                        ).filter(visible);

                        const names = new Set(
                            descendantHeadings
                                .map(textOf)
                                .filter((text) => SECTION_NAMES.includes(text))
                        );

                        const rect = ancestor.getBoundingClientRect();
                        const area = Math.max(1, rect.width * rect.height);
                        const sectionScore = names.size * 1000;
                        const sizePenalty = Math.log(area);
                        const depthPenalty = depth * 8;
                        const score = sectionScore - sizePenalty - depthPenalty;

                        if (
                            names.size >= 2 &&
                            score > bestScore &&
                            ancestor !== document.body &&
                            ancestor !== document.documentElement
                        ) {
                            root = ancestor;
                            bestScore = score;
                        }

                        ancestor = ancestor.parentElement;
                        depth += 1;
                    }
                }

                if (!root && matchingHeadings.length) {
                    root = matchingHeadings[0].parentElement;
                    while (root && root !== document.body) {
                        const headingCount = Array.from(
                            root.querySelectorAll("h1,h2,h3,h4,h5,h6,[role='heading']")
                        ).filter(visible).length;
                        if (headingCount >= 2) break;
                        root = root.parentElement;
                    }
                }

                if (!root) root = document.body;

                const inRoot = (selector) =>
                    Array.from(root.querySelectorAll(selector)).filter(visible);

                const headings = unique(
                    inRoot("h1,h2,h3,h4,h5,h6,[role='heading']")
                        .map((el) => ({ type: "heading", text: textOf(el) }))
                        .filter((item) => SECTION_NAMES.includes(item.text))
                );

                // Angular Material/custom OPC fields often do not use <label>.
                // In the actual VOD Details UI the label is a normal-weight text
                // element and the corresponding value is normally a bold sibling.
                // Therefore labels are detected from the rendered DOM rather than
                // relying only on semantic <label> elements.
                const labelCandidates = [];

                // The Details page uses custom Angular/div based rows rather than
                // semantic <label> elements.  A value can look exactly like a label,
                // so DOM position is important: in a normal field row the static label
                // comes BEFORE its value/control.  This prevents values such as IDs,
                // titles, actors, genres, dates and Yes/No from being reported as labels.
                for (const el of inRoot("*") ) {
                    if (!visible(el)) continue;
                    if (el.children.length !== 0) continue;

                    const text = textOf(el);
                    if (!text || text.length > 70) continue;
                    if (SECTION_NAMES.includes(text)) continue;

                    const tag = el.tagName.toLowerCase();
                    if (["button", "a", "option", "script", "style", "svg"].includes(tag)) continue;
                    if (el.closest("[role='tooltip'],[aria-hidden='true'],.cdk-visually-hidden,[aria-live]")) continue;

                    // Never classify obvious catalog/content values as UI labels.
                    if (isDynamicValue(text)) continue;

                    // For the OPC Details view, only known schema labels are
                    // eligible.  This is intentional: the test compares UI
                    // structure, not whatever content happens to be loaded.
                    if (!STATIC_LABELS.has(text)) continue;

                    const style = window.getComputedStyle(el);
                    const weight = parseInt(style.fontWeight || "400", 10) || 400;
                    const className = typeof el.className === "string" ? el.className : "";
                    const explicitLabelClass = /(^|[-_\\s])(label|field-label|form-label)([-_\\s]|$)/i.test(className);

                    let parent = el.parentElement;
                    let isFieldLabel = false;

                    for (let level = 0; parent && level < 3 && !isFieldLabel; level++, parent = parent.parentElement) {
                        const children = Array.from(parent.children).filter(visible);
                        if (children.length < 2) continue;

                        // Find the direct child container that owns the candidate text.
                        // This lets us compare DOM order even when the actual text is
                        // nested inside a span/div.
                        const candidateIndex = children.findIndex(
                            (child) => child === el || child.contains(el)
                        );
                        if (candidateIndex < 0) continue;

                        const peersAfter = children.slice(candidateIndex + 1);
                        const peersBefore = children.slice(0, candidateIndex);

                        for (const peer of peersAfter) {
                            const peerText = textOf(peer);
                            const peerHasControl = !!peer.querySelector(
                                "input,textarea,select,[role='combobox'],[role='checkbox'],[role='radio'],button,mat-select,mat-checkbox,mat-radio-button"
                            );
                            const peerWeight = parseInt(
                                window.getComputedStyle(peer).fontWeight || "400",
                                10
                            ) || 400;

                            // A later sibling containing a dynamic value, a control,
                            // or a visually emphasized value is strong evidence that
                            // the candidate is the preceding field label.
                            const looksLikeValueAfter =
                                peerHasControl ||
                                (!!peerText && (isDynamicValue(peerText) || peerWeight >= 600));

                            if (looksLikeValueAfter) {
                                isFieldLabel = true;
                                break;
                            }
                        }

                        // Some OPC rows have an explicit label class but an empty or
                        // non-text value container.  Only trust that class when the
                        // candidate is the first meaningful side of the row.
                        if (!isFieldLabel && explicitLabelClass && candidateIndex === 0) {
                            const hasAnotherSide = children.length >= 2 &&
                                children.slice(1).some((child) => visible(child));
                            if (hasAnotherSide) isFieldLabel = true;
                        }

                        // Do not infer a label from a peer that appears before the
                        // candidate; that pattern is normally the value/control side.
                        void peersBefore;
                    }

                    if (isFieldLabel) {
                        labelCandidates.push({
                            type: "label",
                            text,
                            weight,
                            inferred: !el.matches("label")
                        });
                    }
                }

                const labels = unique(labelCandidates)
                    .map(({ type, text }) => ({ type, text }));

                const inputs = unique(
                    inRoot("input,textarea")
                        .filter((el) => {
                            const type = (el.getAttribute("type") || "text").toLowerCase();
                            return !["hidden", "checkbox", "radio"].includes(type);
                        })
                        .map((el) => ({
                            type: "input",
                            tag: el.tagName.toLowerCase(),
                            placeholder: clean(el.getAttribute("placeholder")),
                            ariaLabel: clean(el.getAttribute("aria-label")),
                            name: clean(el.getAttribute("name")),
                            role: clean(el.getAttribute("role"))
                        }))
                );

                const selects = unique(
                    inRoot("select,[role='combobox'],mat-select,[aria-haspopup='listbox']")
                        .map((el) => ({
                            type: "select",
                            tag: el.tagName.toLowerCase(),
                            ariaLabel: clean(el.getAttribute("aria-label")),
                            name: clean(el.getAttribute("name")),
                            role: clean(el.getAttribute("role")) || "combobox"
                        }))
                );

                const checkboxes = unique(
                    inRoot("input[type='checkbox'],[role='checkbox'],mat-checkbox")
                        .map((el) => ({
                            type: "checkbox",
                            text: textOf(el),
                            ariaLabel: clean(el.getAttribute("aria-label")),
                            name: clean(el.getAttribute("name")),
                            role: clean(el.getAttribute("role")) || "checkbox"
                        }))
                );

                const radioButtons = unique(
                    inRoot("input[type='radio'],[role='radio'],mat-radio-button")
                        .map((el) => ({
                            type: "radio_button",
                            text: textOf(el),
                            ariaLabel: clean(el.getAttribute("aria-label")),
                            name: clean(el.getAttribute("name")),
                            role: clean(el.getAttribute("role")) || "radio"
                        }))
                );

                const buttons = unique(
                    inRoot("button,[role='button'],mat-button,mat-raised-button,mat-icon-button")
                        .map((el) => ({
                            type: "button",
                            text: textOf(el),
                            ariaLabel: clean(el.getAttribute("aria-label")),
                            title: clean(el.getAttribute("title")),
                            role: clean(el.getAttribute("role")) || "button"
                        }))
                        .filter((item) => item.text || item.ariaLabel || item.title)
                );

                const tabs = unique(
                    inRoot("[role='tab'],mat-tab,mat-tab-label")
                        .map((el) => ({
                            type: "tab",
                            text: textOf(el),
                            ariaLabel: clean(el.getAttribute("aria-label")),
                            role: clean(el.getAttribute("role")) || "tab"
                        }))
                        .filter((item) => item.text || item.ariaLabel)
                );

                // Tables: capture structure only. Never capture row values.
                const tables = unique(
                    inRoot("table")
                        .map((table) => {
                            const headerCells = Array.from(
                                table.querySelectorAll("thead th, thead td, th")
                            )
                                .filter(visible)
                                .map((cell) => textOf(cell))
                                .filter(Boolean);

                            return {
                                type: "table",
                                columns: unique(headerCells)
                            };
                        })
                );

                return {
                    headings,
                    labels,
                    inputs,
                    selects,
                    checkboxes,
                    radio_buttons: radioButtons,
                    buttons,
                    tabs,
                    tables
                };
            }
            """
        )
