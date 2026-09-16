from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any


class ComparisonReport:
    """Generate a detailed self-contained VisionQA comparison report."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    @staticmethod
    def _esc(value: Any) -> str:
        return "—" if value is None else html.escape(str(value))

    @staticmethod
    def _status_class(status: str) -> str:
        return {
            "SUCCESS": "pass",
            "PASS": "pass",
            "MATCHED": "pass",
            "FAIL": "fail",
            "CHANGED": "fail",
            "ADDED": "added",
            "REMOVED": "removed",
        }.get(status, "neutral")

    @staticmethod
    def _check(matched: bool) -> str:
        if matched:
            return '<span class="check pass">✓ MATCH</span>'
        return '<span class="check fail">✕ DIFFERENT</span>'

    def _relative_asset(self, asset: str | None) -> str | None:
        if not asset:
            return None
        path = Path(asset)
        if not path.exists():
            return None
        try:
            return os.path.relpath(path.resolve(), self.output_dir.resolve()).replace("\\", "/")
        except Exception:
            return None

    def _screenshot(self, label: str, asset: str | None) -> str:
        rel = self._relative_asset(asset)
        if not rel:
            return f'''<div class="screenshot missing">
                <div class="shot-title">{self._esc(label)}</div>
                <div class="missing-text">Screenshot unavailable</div>
            </div>'''
        safe = self._esc(rel)
        return f'''<div class="screenshot">
            <div class="shot-title">{self._esc(label)}</div>
            <a href="{safe}" target="_blank">
                <img src="{safe}" alt="{self._esc(label)}">
            </a>
            <div class="open-shot">Open full resolution ↗</div>
        </div>'''

    def _reason_html(self, reasons: list[dict[str, Any]]) -> str:
        if not reasons:
            return '<div class="no-differences">✓ No differences detected</div>'

        labels = {
            "NAVIGATION_CHANGED": "Navigation Changed",
            "URL_CHANGED": "URL Changed",
            "TITLE_CHANGED": "Title Changed",
            "EXECUTION_STATE_CHANGED": "Execution State Changed",
            "ERROR_CHANGED": "Error Changed",
            "COMPONENT_ADDED": "Component Added",
            "COMPONENT_REMOVED": "Component Removed",
            "COMPONENT_PRESENCE_CHANGED": "Component Presence Changed",
        }
        blocks = []
        for reason in reasons:
            typ = reason.get("type", "UNKNOWN")
            title = labels.get(typ, typ.replace("_", " ").title())
            details = []
            if typ in {"COMPONENT_ADDED", "COMPONENT_REMOVED"}:
                details.append(f"Component: <b>{self._esc(reason.get('component'))}</b>")
            elif typ == "COMPONENT_PRESENCE_CHANGED":
                details.append(f"Component: <b>{self._esc(reason.get('component'))}</b>")
                details.append(f"Baseline: <b>{self._esc(reason.get('baseline'))}</b>")
                details.append(f"Comparison: <b>{self._esc(reason.get('comparison'))}</b>")
            elif typ == "URL_CHANGED":
                details.append(f"Baseline route: <code>{self._esc(reason.get('baseline'))}</code>")
                details.append(f"Comparison route: <code>{self._esc(reason.get('comparison'))}</code>")
            elif typ in {"NAVIGATION_CHANGED", "TITLE_CHANGED"}:
                details.append(f"Baseline: <b>{self._esc(reason.get('baseline'))}</b>")
                details.append(f"Comparison: <b>{self._esc(reason.get('comparison'))}</b>")
            else:
                for key, value in reason.items():
                    if key != "type":
                        details.append(f"{self._esc(key)}: <b>{self._esc(value)}</b>")
            blocks.append(f'''<div class="reason">
                <div class="reason-title">✕ {self._esc(title)}</div>
                <div class="reason-detail">{"<br>".join(details)}</div>
            </div>''')
        return "".join(blocks)

    def _component_matrix(self, components: dict[str, Any]) -> str:
        added = set(components.get("added", []))
        removed = set(components.get("removed", []))
        changed_items = components.get("changed", [])
        changed = {x.get("component") for x in changed_items}
        names = sorted(added | removed | changed)
        if not names:
            return '<div class="component-ok">✓ All compared components match</div>'

        rows = []
        for name in names:
            if name in added:
                baseline, comparison, result, cls = "Missing", "Present", "ADDED", "added"
            elif name in removed:
                baseline, comparison, result, cls = "Present", "Missing", "REMOVED", "removed"
            else:
                item = next((x for x in changed_items if x.get("component") == name), {})
                baseline = item.get("baseline", {}).get("present", "—")
                comparison = item.get("comparison", {}).get("present", "—")
                result, cls = "CHANGED", "changed"
            rows.append(f'''<tr>
                <td><b>{self._esc(name)}</b></td>
                <td>{self._esc(baseline)}</td>
                <td>{self._esc(comparison)}</td>
                <td><span class="pill {cls}">{result}</span></td>
            </tr>''')
        return f'''<table class="component-table">
            <thead><tr><th>Component</th><th>Baseline</th><th>Comparison</th><th>Result</th></tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>'''

    def _page_card(self, page: dict[str, Any], index: int) -> str:
        status = page.get("status", "UNKNOWN")
        cls = self._status_class(status)
        nav = page.get("navigation", {})
        url = page.get("url", {})
        title = page.get("title", {})
        execution = page.get("execution", {})
        components = page.get("components", {})
        reasons = page.get("reasons", [])
        search = self._esc(f"{page.get('menu', '')} {page.get('submenu', '')}".lower())
        return f'''<article class="page-card {cls}" data-status="{self._esc(status)}" data-search="{search}">
            <div class="page-header">
                <div><div class="page-number">PAGE {index:02d}</div>
                <h3>{self._esc(page.get("menu"))} <span>›</span> {self._esc(page.get("submenu"))}</h3></div>
                <div class="status-badge {cls}">{self._esc(status)}</div>
            </div>
            <div class="result-grid">
                {self._result_item("Navigation", nav, "baseline", "comparison")}
                {self._result_item("URL / Route", url, "normalized_baseline", "normalized_comparison", code=True)}
                {self._result_item("Page Title", title, "baseline", "comparison")}
                {self._execution_item(execution)}
            </div>
            <section class="detail-section">
                <div class="section-heading"><span>Component Comparison</span><span class="count">{len(components.get('added', [])) + len(components.get('removed', [])) + len(components.get('changed', []))}</span></div>
                {self._component_matrix(components)}
            </section>
            <section class="detail-section">
                <div class="section-heading"><span>Differences & Failure Reasons</span><span class="count">{len(reasons)}</span></div>
                {self._reason_html(reasons)}
            </section>
            <section class="detail-section">
                <div class="section-heading"><span>Visual Evidence</span></div>
                <div class="screenshots">
                    {self._screenshot("BASELINE", page.get("baseline_screenshot"))}
                    {self._screenshot("COMPARISON", page.get("comparison_screenshot"))}
                </div>
            </section>
        </article>'''

    def _result_item(self, label: str, data: dict[str, Any], base_key: str, comp_key: str, code: bool = False) -> str:
        b = self._esc(data.get(base_key))
        c = self._esc(data.get(comp_key))
        if code:
            b = f"<code>{b}</code>"
            c = f"<code>{c}</code>"
        return f'''<div class="result-item">
            <div class="result-label">{label}</div>
            <div class="result-value">{self._check(bool(data.get("matched")))}</div>
            <div class="pair"><span>Baseline</span><b>{b}</b></div>
            <div class="pair"><span>Comparison</span><b>{c}</b></div>
        </div>'''

    def _execution_item(self, execution: dict[str, Any]) -> str:
        b = execution.get("baseline", {})
        c = execution.get("comparison", {})
        return f'''<div class="result-item">
            <div class="result-label">Execution</div>
            <div class="result-value">{self._check(bool(execution.get("matched")))}</div>
            <div class="pair"><span>Baseline</span><b>{self._esc(b.get("status"))}</b></div>
            <div class="pair"><span>Comparison</span><b>{self._esc(c.get("status"))}</b></div>
        </div>'''

    def _inventory(self, pages: list[dict[str, Any]]) -> str:
        if not pages:
            return '<div class="empty">No pages in this category.</div>'
        rows = []
        for page in pages:
            status = page.get("status", "UNKNOWN")
            rows.append(f'''<tr><td>{self._esc(page.get("menu"))}</td><td>{self._esc(page.get("submenu"))}</td><td><span class="pill {self._status_class(status)}">{self._esc(status)}</span></td></tr>''')
        return f'''<table class="inventory"><thead><tr><th>Menu</th><th>Page</th><th>Status</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'''

    def _special_pages(self, pages: list[dict[str, Any]], status: str, title: str, description: str) -> str:
        if not pages:
            return ""
        rows = []
        for page in pages:
            rows.append(f'''<div class="special-page">
                <div><div class="special-menu">{self._esc(page.get("menu"))}</div><div class="special-submenu">{self._esc(page.get("submenu"))}</div></div>
                <div class="special-url">{self._esc(page.get("url"))}</div>
                <span class="pill {self._status_class(status)}">{status}</span>
            </div>''')
        return f'''<section class="major-section"><div class="section-title"><h2>{title}</h2><span>{len(pages)}</span></div><p class="section-description">{description}</p>{"".join(rows)}</section>'''

    def generate(self, comparison: dict[str, Any], baseline_environment: str, comparison_environment: str, baseline_version: str, comparison_version: str, baseline_tenant: str | None = None, comparison_tenant: str | None = None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        summary = comparison.get("summary", {})
        pages = comparison.get("pages", [])
        matched = summary.get("matched", 0)
        changed = summary.get("changed", 0)
        added = summary.get("added_pages", 0)
        removed = summary.get("removed_pages", 0)
        total = summary.get("total_pages", 0)
        overall = "PASS" if changed == 0 and added == 0 and removed == 0 else "CHANGES DETECTED"
        overall_cls = "pass" if overall == "PASS" else "fail"
        matched_pages = [p for p in pages if p.get("status") == "SUCCESS"]

        html_doc = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>VisionQA Detailed Comparison Report</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#f4f6f8;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}} .topbar{{background:#111827;color:#fff;padding:28px 42px}} .brand{{font-size:28px;font-weight:800}} .subtitle{{color:#cbd5e1;margin-top:5px}} .container{{max-width:1500px;margin:auto;padding:28px 32px 60px}} .environment{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:22px}} .env-card,.summary-card,.rules,.overall,.page-card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px}} .env-card{{padding:20px}} .env-label,.summary-label,.result-label,.page-number,.special-menu{{font-size:11px;text-transform:uppercase;color:#64748b;font-weight:800;letter-spacing:.07em}} .env-name{{font-size:22px;font-weight:800;margin:5px 0}} .env-version{{color:#475569;word-break:break-word}} .summary{{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:28px}} .summary-card{{padding:18px}} .summary-value{{font-size:29px;font-weight:900;margin-top:6px}} .pass{{color:#15803d}} .fail{{color:#b91c1c}} .added{{color:#0369a1}} .removed{{color:#b45309}} .neutral{{color:#475569}} .overall{{padding:20px;margin-bottom:28px;border-width:2px}} .overall.pass{{border-color:#86efac}} .overall.fail{{border-color:#fca5a5}} .overall-title{{font-size:11px;text-transform:uppercase;color:#64748b;font-weight:800}} .overall-result{{font-size:24px;font-weight:900;margin-top:5px}} .rules{{padding:22px;margin-bottom:32px}} .rules-grid{{display:grid;grid-template-columns:1fr 1fr;gap:25px}} .rules ul{{line-height:1.9}} .major-section{{margin-top:36px}} .section-title{{display:flex;align-items:center;justify-content:space-between;margin:20px 0 12px}} .section-title h2{{margin:0;font-size:23px}} .section-title span,.count{{background:#e2e8f0;border-radius:999px;padding:4px 9px;font-weight:800;font-size:12px}} .section-description{{color:#64748b}} .filters{{position:sticky;top:0;z-index:10;background:rgba(244,246,248,.96);padding:12px 0;display:flex;gap:8px;flex-wrap:wrap}} .filter,.search{{border:1px solid #cbd5e1;background:#fff;padding:9px 13px;border-radius:8px;font-weight:700}} .filter{{cursor:pointer}} .filter.active{{background:#111827;color:#fff}} .search{{min-width:260px;font-weight:400}} .page-card{{margin:18px 0;overflow:hidden;box-shadow:0 2px 8px rgba(15,23,42,.04)}} .page-card.fail{{border-left:5px solid #dc2626}} .page-card.pass{{border-left:5px solid #16a34a}} .page-header{{display:flex;justify-content:space-between;gap:15px;padding:20px 22px;border-bottom:1px solid #e2e8f0}} .page-header h3{{margin:5px 0 0;font-size:19px}} .page-header h3 span{{color:#94a3b8;padding:0 4px}} .status-badge{{height:fit-content;padding:7px 12px;border-radius:999px;font-size:12px;font-weight:900}} .status-badge.pass{{background:#dcfce7}} .status-badge.fail{{background:#fee2e2}} .result-grid{{display:grid;grid-template-columns:repeat(4,1fr)}} .result-item{{padding:18px;border-right:1px solid #e2e8f0}} .result-item:last-child{{border-right:none}} .result-value{{margin:7px 0 13px}} .check{{font-weight:900;font-size:13px}} .pair,.route{{display:flex;flex-direction:column;gap:3px;margin-top:9px}} .pair span,.route span{{font-size:10px;color:#94a3b8;text-transform:uppercase}} .pair b{{font-size:13px}} code{{background:#f1f5f9;padding:3px 6px;border-radius:5px;word-break:break-all}} .detail-section{{padding:20px 22px;border-top:1px solid #e2e8f0}} .section-heading{{display:flex;justify-content:space-between;align-items:center;font-weight:900;margin-bottom:14px}} .component-table,.inventory{{width:100%;border-collapse:collapse}} .component-table th,.component-table td,.inventory th,.inventory td{{border:1px solid #e2e8f0;padding:10px;text-align:left}} .component-table th,.inventory th{{background:#f8fafc;font-size:11px;text-transform:uppercase}} .pill{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900}} .pill.pass{{background:#dcfce7}} .pill.fail,.pill.changed{{background:#fee2e2}} .pill.added{{background:#dbeafe}} .pill.removed{{background:#ffedd5}} .component-ok,.no-differences{{background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;padding:13px;border-radius:8px;font-weight:700}} .reason{{border:1px solid #fecaca;background:#fffafa;border-radius:9px;margin:10px 0;overflow:hidden}} .reason-title{{padding:11px 13px;font-weight:900;color:#991b1b;border-bottom:1px solid #fecaca}} .reason-detail{{padding:12px 13px;color:#475569;line-height:1.7}} .screenshots{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} .screenshot{{border:1px solid #e2e8f0;border-radius:10px;padding:12px;background:#f8fafc}} .screenshot img{{display:block;width:100%;max-height:600px;object-fit:contain;background:#fff;border:1px solid #e2e8f0;margin-top:10px;cursor:zoom-in}} .shot-title{{font-size:12px;font-weight:900;letter-spacing:.08em}} .missing-text{{color:#94a3b8;padding:50px 10px;text-align:center}} .open-shot{{font-size:11px;color:#64748b;margin-top:7px}} .special-page{{display:grid;grid-template-columns:1.2fr 2fr auto;gap:15px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:15px;margin:9px 0}} .special-submenu{{font-size:16px;font-weight:800;margin-top:3px}} .special-url{{color:#64748b;word-break:break-all;font-family:monospace;font-size:12px}} .empty{{background:#fff;padding:20px;border-radius:10px;color:#64748b}} .footer{{margin-top:50px;padding-top:20px;border-top:1px solid #cbd5e1;color:#64748b;font-size:12px}} @media(max-width:1000px){{.summary{{grid-template-columns:repeat(3,1fr)}}.result-grid{{grid-template-columns:1fr 1fr}}.environment,.rules-grid,.screenshots{{grid-template-columns:1fr}}}} @media(max-width:650px){{.container{{padding:18px}}.summary{{grid-template-columns:1fr 1fr}}.result-grid{{grid-template-columns:1fr}}.result-item{{border-right:none;border-bottom:1px solid #e2e8f0}}.special-page{{grid-template-columns:1fr}}}}
</style></head><body>
<header class="topbar"><div class="brand">VisionQA</div><div class="subtitle">Detailed Environment Comparison Report</div></header>
<main class="container">
<section class="environment"><div class="env-card"><div class="env-label">Baseline Environment</div><div class="env-name">{self._esc(baseline_environment)}</div><div class="env-version">Version: <b>{self._esc(baseline_version)}</b></div>{f'<div class="env-version">Tenant: <b>{self._esc(baseline_tenant)}</b></div>' if baseline_tenant else ''}</div><div class="env-card"><div class="env-label">Comparison Environment</div><div class="env-name">{self._esc(comparison_environment)}</div><div class="env-version">Version: <b>{self._esc(comparison_version)}</b></div>{f'<div class="env-version">Tenant: <b>{self._esc(comparison_tenant)}</b></div>' if comparison_tenant else ''}</div></section>
<section class="summary"><div class="summary-card"><div class="summary-label">Pages Compared</div><div class="summary-value">{total}</div></div><div class="summary-card"><div class="summary-label">Matched</div><div class="summary-value pass">{matched}</div></div><div class="summary-card"><div class="summary-label">Changed</div><div class="summary-value fail">{changed}</div></div><div class="summary-card"><div class="summary-label">Added</div><div class="summary-value added">{added}</div></div><div class="summary-card"><div class="summary-label">Removed</div><div class="summary-value removed">{removed}</div></div><div class="summary-card"><div class="summary-label">Overall</div><div class="summary-value {overall_cls}">{overall}</div></div></section>
<section class="overall {overall_cls}"><div class="overall-title">Overall Comparison Result</div><div class="overall-result {overall_cls}">{overall}</div></section>
<section class="rules"><h2>Comparison Rules</h2><div class="rules-grid"><div><h3>Compared</h3><ul><li>Page existence</li><li>Navigation type</li><li>Normalized URL / route</li><li>Page title</li><li>Execution state</li><li>Component presence</li></ul></div><div><h3>Not Compared</h3><ul><li>Load time</li><li>Environment hostname</li><li>Timestamps</li><li>Dynamic data values</li><li>Screenshot pixels</li></ul></div></div></section>
<section class="major-section"><div class="section-title"><h2>Page Inventory</h2><span>{len(pages)}</span></div>{self._inventory(pages)}</section>
<section class="major-section"><div class="section-title"><h2>Detailed Page Comparison</h2><span>{len(pages)}</span></div><div class="filters"><button class="filter active" data-filter="ALL">ALL</button><button class="filter" data-filter="SUCCESS">MATCHED ({matched})</button><button class="filter" data-filter="FAIL">CHANGED ({changed})</button><input id="search" class="search" type="search" placeholder="Search menu or page..."></div><div id="pages">{"".join(self._page_card(p, i) for i, p in enumerate(pages, 1))}</div></section>
{self._special_pages(comparison.get('added_pages', []), 'ADDED', 'Added Pages', 'Pages discovered in the comparison environment but not in the baseline environment.')}
{self._special_pages(comparison.get('removed_pages', []), 'REMOVED', 'Removed Pages', 'Pages discovered in the baseline environment but not in the comparison environment.')}
<section class="major-section"><div class="section-title"><h2>Matched Pages</h2><span>{len(matched_pages)}</span></div>{self._inventory(matched_pages)}</section>
<footer class="footer">Generated by <b>VisionQA</b>. Comparison decisions are produced by the VisionQA Comparator. Load time is intentionally excluded from v1.0 comparison criteria.</footer>
</main>
<script>
const buttons=document.querySelectorAll('.filter');const cards=document.querySelectorAll('.page-card');const search=document.getElementById('search');let active='ALL';function apply(){{const q=search.value.toLowerCase().trim();cards.forEach(c=>{{const ok=(active==='ALL'||c.dataset.status===active)&&(!q||c.dataset.search.includes(q));c.style.display=ok?'':'none';}});}}buttons.forEach(b=>b.addEventListener('click',()=>{{buttons.forEach(x=>x.classList.remove('active'));b.classList.add('active');active=b.dataset.filter;apply();}}));search.addEventListener('input',apply);
</script></body></html>'''

        output = self.output_dir / "comparison_report.html"
        output.write_text(html_doc, encoding="utf-8")
        (self.output_dir / "comparison.json").write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")
        return output
