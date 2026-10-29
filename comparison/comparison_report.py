"""
==============================================================================
VisionQA Comparison Report
==============================================================================
Copyright (c) 2026 Devesh Sharma.
All Rights Reserved.
==============================================================================
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path


class ComparisonReport:
    """Generate an OPC-style, interactive VisionQA comparison report."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    @staticmethod
    def _is_placeholder_value(value):
        """Return True for UI comparison values that carry no actionable information."""
        if value is None:
            return True
        text = str(value).strip().lower()
        return text in {"", "—", "–", "-", "present", "missing", "not available", "n/a", "null", "none"}

    @classmethod
    def _meaningful_ui_difference(cls, item):
        """Keep UI differences only when they identify a real component change."""
        if not isinstance(item, dict):
            return False
        component = item.get("component") or item.get("element") or item.get("name") or item.get("label")
        if cls._is_placeholder_value(component):
            return False

        stage = str(item.get("stage", item.get("baseline", "")) or "").strip().lower()
        comparison = str(item.get("comparison", item.get("prod", item.get("production", ""))) or "").strip().lower()

        # Suppress the exact placeholder patterns requested, but preserve actual
        # additions/removals when a component name is available.
        if stage in {"—", "–", "-"} and comparison in {"present", "—", "–", "-"}:
            return False
        if stage in {"—", "–", "-"} and comparison in {"—", "–", "-"}:
            return False
        return True

    @classmethod
    def _dedupe_records(cls, records, key_builder):
        """Stable de-duplication that preserves first occurrence and order."""
        output = []
        seen = set()
        for item in records or []:
            key = key_builder(item)
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    @classmethod
    def _clean_page_differences(cls, page):
        """Filter placeholder-only reasons and duplicate component/UI differences."""
        reasons = []
        for reason in page.get("reasons") or []:
            if not isinstance(reason, dict):
                continue
            kind = str(reason.get("type", "")).upper()
            if kind == "URL_CHANGED":
                continue
            # Old comparison JSON can contain a generic SCREENSHOT_CHANGED
            # reason with no actual evidence (rendered as "— → —"). Screenshot
            # similarity is already reported separately, so discard this empty
            # placeholder instead of showing it as an actionable difference.
            if kind == "SCREENSHOT_CHANGED":
                baseline_value = reason.get("baseline", reason.get("stage"))
                comparison_value = reason.get("comparison", reason.get("prod"))
                if cls._is_placeholder_value(baseline_value) and cls._is_placeholder_value(comparison_value):
                    continue
            if kind == "UI_STRUCTURE_CHANGED":
                continue
            if kind in {"COMPONENT_ADDED", "COMPONENT_REMOVED", "COMPONENT_PRESENCE_CHANGED"}:
                component = reason.get("component")
                if cls._is_placeholder_value(component):
                    continue
            reasons.append(reason)

        page["reasons"] = cls._dedupe_records(
            reasons,
            lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False, default=str),
        )

        components = page.get("components") or {}
        for field in ("added", "removed"):
            values = components.get(field) or []
            components[field] = list(dict.fromkeys(
                value for value in values if not cls._is_placeholder_value(value)
            ))
        changed = components.get("changed") or []
        components["changed"] = cls._dedupe_records(
            changed,
            lambda c: json.dumps(c, sort_keys=True, ensure_ascii=False, default=str),
        )
        page["components"] = components

        # UI structure is inventory/evidence only, not a pass/fail comparison input.
        # Clear legacy UI-structure diffs from older comparison JSON as well.
        ui = page.get("ui_structure") or {}
        ui["differences"] = []
        page["ui_structure"] = ui

        # A page should fail only when meaningful reasons remain after filtering.
        page["status"] = "SUCCESS" if not page["reasons"] else "FAIL"

    @staticmethod
    def _json(value):
        return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")

    def _asset(self, path):
        """Return a screenshot path relative to the generated report."""
        if not path:
            return ""
        raw = str(path).replace("\\", "/")
        # These legacy paths are already relative to snapshots/comparison.
        if raw.startswith(("../stage/", "../live/", "../qa/")):
            return raw
        source = Path(raw)
        parts = source.parts
        try:
            idx = next(i for i, part in enumerate(parts) if part.lower() == "snapshots")
            target = Path.cwd() / Path(*parts[idx:])
        except StopIteration:
            target = source if source.is_absolute() else Path.cwd() / source
        try:
            return Path(os.path.relpath(target, start=self.output_dir)).as_posix()
        except Exception:
            return source.as_posix()

    @staticmethod
    def _resolve_environment(value, pages, comparison_side=False):
        """Use the supplied environment, but recover an unknown value from URLs."""
        raw = str(value or "").strip().lower()
        if raw and raw not in {"unknown", "none", "null"}:
            return raw
        urls = []
        for page in pages or []:
            url = (page.get("url") or {}).get("comparison" if comparison_side else "baseline")
            if url:
                urls.append(str(url).lower())
        joined = " ".join(urls)
        if "opc.astro.live.xp.irdeto.com" in joined:
            return "production"
        if "opc.astro.stage.xp.irdeto.com" in joined:
            return "stage"
        if "opc.e2eqa.xp.irdeto.com" in joined:
            return "qa"
        return raw or "unknown"

    def generate(
        self,
        comparison: dict,
        baseline_environment: str,
        comparison_environment: str,
        baseline_version: str,
        comparison_version: str,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_name = f"comparison_{timestamp}.json"
        html_name = f"comparison_report_{timestamp}.html"

        pages = comparison.get("pages", [])
        payload = {
            "summary": copy.deepcopy(comparison.get("summary", {})),
            "pages": copy.deepcopy(pages),
            "added_pages": copy.deepcopy(comparison.get("added_pages", [])),
            "removed_pages": copy.deepcopy(comparison.get("removed_pages", [])),
            "baseline_environment": self._resolve_environment(baseline_environment, pages),
            "comparison_environment": self._resolve_environment(comparison_environment, pages, comparison_side=True),
            "baseline_version": baseline_version,
            "comparison_version": comparison_version,
            "tenant": comparison.get("tenant") or comparison.get("baseline_tenant") or comparison.get("comparison_tenant"),
            "generated_at": timestamp,
            "json_name": json_name,
        }

        # URL differences are diagnostic only. Dynamic IDs and environment-specific
        # routes must never turn a screen into a mismatch. Normalize old comparison
        # JSON as well, so reports generated from previous comparator runs follow
        # the same rule.
        for page in payload["pages"]:
            self._clean_page_differences(page)

        # Recalculate common-page match counts from the effective status.
        # Missing-page counts remain supplied by the comparator.
        summary = payload["summary"]
        summary["matched"] = sum(1 for p in payload["pages"] if p.get("status") == "SUCCESS")
        summary["changed"] = sum(1 for p in payload["pages"] if p.get("status") != "SUCCESS")
        summary["total_pages"] = len(payload["pages"])

        # Keep paths relative to snapshots/comparison so the report can directly
        # display crawler screenshots from the project. Convert before writing
        # JSON so the downloadable JSON and HTML contain the same asset paths.
        for p in payload["pages"]:
            p["baseline_screenshot"] = self._asset(p.get("baseline_screenshot"))
            p["comparison_screenshot"] = self._asset(p.get("comparison_screenshot"))
            sc = p.get("screenshot_comparison") or {}
            if sc.get("baseline_screenshots"):
                sc["baseline_screenshots"] = [self._asset(x) for x in sc["baseline_screenshots"]]
            if sc.get("comparison_screenshots"):
                sc["comparison_screenshots"] = [self._asset(x) for x in sc["comparison_screenshots"]]

        (self.output_dir / json_name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        html_doc = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VisionQA for Irdeto Experience — UI Comparison</title>
<style>
:root{--navy:#111b57;--purple:#5a2be7;--text:#18245f;--muted:#7180a9;--line:#e4e8f3;--bg:#f8faff;--green:#13b66b;--red:#ff4141;--blue:#1775ed;--lav:#7445f2}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--text);background:var(--bg)}body{font-size:13px}
button,input,select{font:inherit}a{text-decoration:none;color:inherit}.app{min-height:100vh}
.logo-image{display:block;object-fit:contain}.irdeto-logo{width:92px;height:44px}.visionqa-compare-logo{width:150px;height:auto;max-height:42px}.dashboard-hero{justify-content:flex-start;align-items:center;gap:18px;min-height:0;margin-bottom:12px}.dashboard-brand{width:190px;flex:0 0 190px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;text-align:center}.dashboard-brand .visionqa-compare-logo{width:150px;height:auto;max-height:42px}.visionqa-tagline-compare{font-size:10px;font-weight:700;color:#4864a5;line-height:1.2}.run-meta{min-width:0;flex:1}.env-compare{display:flex;align-items:center;gap:12px}.env-side{flex:1;display:flex;align-items:center;gap:13px}.env-side .env-text{min-width:0}.topbar{height:64px;background:#fff;border-bottom:1px solid #e2e6ef;display:flex;align-items:center;padding:0 24px;position:sticky;top:0;z-index:30}.brand{width:335px;display:flex;align-items:center;gap:14px;flex-shrink:0}.visionqa-logo{font-size:25px;font-weight:900;letter-spacing:-1px;color:#17265e;line-height:1}.visionqa-tagline{font-size:10px;font-weight:700;color:#4864a5;margin-top:5px;line-height:1}.brand-copy{display:flex;flex-direction:column;justify-content:center;line-height:1.05}.brand-title{font-size:22px;font-weight:800;letter-spacing:-.5px;color:#17265e}.brand-subtitle{font-size:10px;font-weight:600;color:#4864a5;margin-top:4px}.top-controls{display:none}.user{margin-left:auto;display:flex;align-items:center;gap:10px;font-weight:700;color:#17265e;font-size:13px}.avatar{width:38px;height:38px;border-radius:50%;background:#5b24e8;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700}.copyright-user{display:flex;align-items:center;gap:4px;white-space:nowrap}.copyright-symbol{font-size:13px;font-weight:700;color:#17265e}


.layout{display:flex;min-height:calc(100vh - 64px);background:#f7f8fb}.sidebar{width:260px;background:#fff;border-right:1px solid #e1e5ee;padding:10px 12px 10px 14px;flex-shrink:0;overflow:auto;scrollbar-width:thin}.nav-section-title{color:#14245f;font-weight:700;padding:11px 10px 7px;font-size:13px;cursor:pointer;user-select:none;display:flex;align-items:center;justify-content:space-between;border-radius:5px}.nav-section-title:hover{background:#f7f4ff}.menu-title{margin-top:3px;border-top:1px solid #edf0f5;padding-top:12px}.chev{font-size:13px;transition:transform .18s ease;color:#17265e}.menu-title.collapsed .chev{transform:rotate(-90deg)}.nav-children{overflow:hidden;transition:max-height .2s ease}.nav-item{display:flex;align-items:center;gap:9px;min-height:30px;padding:5px 10px;color:#18306d;border-radius:5px;cursor:pointer;font-size:12px;line-height:1.35}.nav-item:hover{background:#f5f2ff;color:#4b1fd5}.report-nav.active{background:linear-gradient(90deg,#eee7ff,#f8f6ff);color:#5124e3;border-left:3px solid #6432ed;padding-left:7px}.nav-dot{width:15px;height:15px;border-radius:3px;position:relative;flex:0 0 15px}.nav-dot:before{content:"";position:absolute;left:3px;top:3px;width:9px;height:8px;border-radius:2px;border:2px solid currentColor}.nav-bullet{width:12px;color:#91a3ca;text-align:center;flex:0 0 12px}.nav-nested{padding-left:31px}.nav-submenu-block{margin:2px 0 5px 5px;border-left:1px solid #e5e9f2;padding-left:5px}.nav-submenu-title{font-weight:650;background:#f8f9fc}.nav-subgroup{border-left:1px dashed #d7deeb;margin-top:1px}.nav-subgroup-title{font-weight:500;color:#52638f;padding-top:3px;padding-bottom:3px}.opc-submenu-reference{cursor:default;color:#18306d}.sidebar-footer{border-top:1px solid #e8ebf2;padding:12px 10px 0;color:#52638f;font-size:10px;line-height:1.45;margin-top:8px}
.content{flex:1;padding:18px 20px 30px;overflow:auto;background:#f7f8fb}.page{display:none}.page.active{display:block}.hero{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}.hero h1{margin:0;font-size:29px;line-height:32px;letter-spacing:-.7px}.hero h2{margin:7px 0 2px;font-size:19px}.hero p{margin:6px 0 0;color:#7180a9;font-size:12px}
.run-meta{display:flex;gap:12px}.env-card{width:528px;min-height:94px;background:#fff;border:1px solid #e3e7f1;border-radius:8px;padding:14px 17px;display:flex;align-items:center;gap:13px}.env-icon{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#f0eaff;color:#6a2ce8;font-size:21px}.env-icon.blue{background:#eaf4ff;color:#1375e8}.env-text{flex:1}.env-name{font-weight:850;font-size:17px;line-height:1.25;color:#17265e}.env-tenant{font-size:11px;font-weight:500;color:#7180aa;margin-top:5px}.env-version{display:none;color:#7180aa;font-size:10px;margin-top:4px}.swap{font-size:22px;color:#14245f}.run-details{width:232px;min-height:94px;background:#fff;border:1px solid #e3e7f1;border-radius:8px;padding:11px 15px}.detail-line{margin:3px 0;color:#3f4e7e;font-size:11px}.detail-line b{color:#18265e}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-top:11px;align-items:stretch}.kpi{min-height:166px;min-width:0;max-width:100%;overflow:hidden;box-sizing:border-box;background:#fff;border:1px solid #e4e7f0;border-radius:7px;padding:13px 13px 10px;position:relative;display:flex;flex-direction:column;gap:8px}.kpi.total{background:#fbf9ff;border-color:#e8ddff}.kpi.match{background:#f4fcf8;border-color:#dcf0e6}.kpi.mismatch{background:#fff7f7;border-color:#f4dede}.kpi.missing-prod{background:#f4f9ff;border-color:#dfeeff}.kpi.missing-stage{background:#faf7ff;border-color:#e9e0ff}.kpi-top{display:flex;align-items:center;gap:12px}.kpi-icon{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;background:#eee7ff;color:#6330ea}.match .kpi-icon{background:#d8f5e7;color:#13ad67}.mismatch .kpi-icon{background:#ffe0e0;color:#ff3434}.missing-prod .kpi-icon{background:#e2efff;color:#1478e9}.missing-stage .kpi-icon{background:#eee5ff;color:#7440ed}.kpi-title{font-size:12px;font-weight:700}.kpi-number{font-size:27px;line-height:29px;font-weight:800;margin:0 0 0 59px;min-width:0;overflow-wrap:anywhere}.kpi-percent{font-size:12px;font-weight:700}.green{color:#0fa864}.red{color:#f22f2f}.blue{color:#126fe4}.purple{color:#6330e9}.kpi-link{position:static;left:auto;right:auto;bottom:auto;margin-top:auto;width:100%;min-width:0;box-sizing:border-box;background:#fff;border:1px solid #edf0f5;min-height:36px;display:flex;align-items:center;gap:6px;padding:6px 9px;color:#4e20df;font-weight:700;font-size:11px;cursor:pointer;white-space:normal;overflow-wrap:anywhere;line-height:1.25}.kpi-link span:last-child{margin-left:auto;font-size:18px}
.middle{display:grid;grid-template-columns:1fr 1.7fr;gap:11px;margin-top:13px}.panel{background:#fff;border:1px solid #e0e5ef;border-radius:7px;padding:14px 16px}.panel-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.panel-title{font-size:16px;font-weight:800;display:flex;align-items:center;gap:10px}.round-icon{width:28px;height:28px;border-radius:50%;background:#eee6ff;color:#6030e8;display:flex;align-items:center;justify-content:center;font-weight:800}
.view-all{border:1px solid #e1e4ed;border-radius:6px;background:#fff;color:#5425df;padding:6px 10px;font-size:11px;cursor:pointer}.distribution{display:flex;align-items:center;gap:18px;min-height:190px}.donut{width:195px;height:195px;border-radius:50%;position:relative;flex-shrink:0;background:conic-gradient(var(--green) 0 var(--m),var(--red) var(--m) var(--mm),var(--blue) var(--mm) var(--mp),var(--lav) var(--mp) 100%)}.donut:after{content:"";position:absolute;width:112px;height:112px;border-radius:50%;background:#fff;left:41px;top:41px;box-shadow:0 0 0 1px #f0f2f7}.donut-center{position:absolute;z-index:2;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:800;font-size:23px}.donut-center span{font-size:10px;margin-top:2px}.legend{flex:1}.legend-row{display:grid;grid-template-columns:12px 1fr 30px 52px;align-items:center;gap:7px;margin:13px 0}.legend-dot{width:12px;height:12px;border-radius:50%}.legend-label{font-size:12px}.legend-value{font-size:12px;font-weight:800;text-align:right}.legend-pct{font-size:11px;color:#52618c;text-align:right}
.mismatch-table,.module-table,.result-table,.structure-table{width:100%;border-collapse:collapse}.mismatch-table{font-size:10px}.mismatch-table th,.module-table th,.result-table th{background:#f8f9fc;color:#344473;padding:8px;text-align:left;border-top:1px solid #e8ebf2;border-bottom:1px solid #e8ebf2}.mismatch-table td{padding:8px;border-bottom:1px solid #edf0f5;color:#31416f}.bad-text{color:#ff3535!important}.empty{text-align:center;color:#7c87aa;padding:25px!important}
.bottom{display:grid;grid-template-columns:1fr 394px;gap:13px;margin-top:13px}.module-panel{border:1px solid #a66cff}.module-table{font-size:11px}.module-table th{padding:7px 9px}.module-table td{padding:7px 9px;border-bottom:1px solid #eef0f5}.num-green{color:#0aa763;font-weight:800}.num-red{color:#fa3030;font-weight:800}.bar{width:102px;height:10px;background:#e7ebf2;border-radius:10px;overflow:hidden;display:inline-block;vertical-align:middle;margin-right:20px}.bar>span{display:block;height:100%;background:#16b875;border-radius:10px}
.qa-list{display:flex;flex-direction:column;gap:6px}.qa{border:1px solid #e6eaf2;border-radius:7px;min-height:44px;padding:7px 9px;display:flex;align-items:center;gap:10px;cursor:pointer}.qa:hover{background:#faf9ff}.qa-icon{width:29px;height:29px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px}.qa-title{font-weight:800;font-size:11px}.qa-sub{color:#7884aa;font-size:9px;margin-top:2px}.qa-arrow{margin-left:auto;color:#5626e5;font-size:19px}.action-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:7px}.action-btn{border:1px solid #e3e7ef;background:#fff;border-radius:6px;padding:9px;font-size:10px;color:#26376d;cursor:pointer}
.detail-page .detail-top{display:flex;justify-content:space-between;align-items:flex-start}.breadcrumb{color:#7080a8;font-size:11px;margin-bottom:10px}.detail-title{font-size:24px;margin:0}.status-pill{display:inline-flex;align-items:center;gap:7px;padding:7px 11px;border-radius:15px;font-size:11px;font-weight:800}.status-match{background:#e9f9f1;color:#0ba765}.status-mismatch{background:#ffecec;color:#ed3333}.detail-meta{display:flex;gap:10px;margin-top:13px;flex-wrap:wrap}.meta-box{background:#fff;border:1px solid #e2e6ef;border-radius:7px;padding:9px 12px;min-width:150px}.meta-label{color:#7582a8;font-size:10px}.meta-value{font-weight:800;margin-top:3px}.detail-urls{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.url-box{background:#fff;border:1px solid #e2e6ef;border-radius:7px;padding:10px 12px}.url-label{color:#7582a8;font-size:10px;font-weight:700;margin-bottom:5px}.url-link{display:block;color:#253b8f;font-size:10px;line-height:1.45;word-break:break-all;text-decoration:none}.url-link:hover{text-decoration:underline}.url-unavailable{color:#8a94b0;font-size:10px}@media(max-width:800px){.detail-urls{grid-template-columns:1fr}}.screens{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:13px}.shot-card{background:#fff;border:1px solid #e1e5ee;border-radius:8px;padding:10px}.shot-head{display:flex;justify-content:space-between;font-weight:800;font-size:12px;margin-bottom:8px}.shot{width:100%;max-height:520px;object-fit:contain;object-position:top;border:1px solid #e6e8ef;background:#f7f8fb;border-radius:5px;cursor:zoom-in}.no-shot{height:250px;display:flex;align-items:center;justify-content:center;color:#7b86a8;background:#f7f8fb;border-radius:5px}.diff-panel{margin-top:13px}.check-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}.check{border:1px solid #e2e6ef;border-radius:7px;padding:10px;background:#fff}.check-label{font-size:10px;color:#7180a4}.check-value{font-size:11px;font-weight:800;margin-top:5px}.ok{color:#0aa763}.bad{color:#ef3333}.diff-list{margin:0;padding-left:18px}.diff-list li{margin:5px 0;color:#3d4a76}.difference-list{display:flex;flex-direction:column;gap:9px;margin-top:12px}.difference-item{border:1px solid #e1e5ee;border-left:4px solid #ef3333;border-radius:7px;background:#fff;padding:10px 12px}.difference-item.added{border-left-color:#13b66b}.difference-item.removed{border-left-color:#ef3333}.difference-title{font-size:12px;font-weight:800;color:#18245f;margin-bottom:5px}.difference-values{display:flex;align-items:center;gap:9px;flex-wrap:wrap;color:#40507d;font-size:11px}.difference-side{padding:5px 8px;background:#f7f8fb;border-radius:5px}.difference-arrow{font-weight:900;color:#7445f2}.no-difference{padding:12px;color:#66759f;background:#f7f8fb;border-radius:7px}.filters{display:flex;gap:8px;align-items:center;margin:12px 0}.search{flex:1;height:36px;border:1px solid #dce1eb;border-radius:6px;padding:0 11px;outline:none}.filter-btn{height:36px;border:1px solid #dce1eb;background:#fff;border-radius:6px;padding:0 12px;cursor:pointer}.result-table{background:#fff;border:1px solid #e1e5ed;font-size:11px}.result-table th{font-size:10px}.result-table td{padding:9px 10px;border-top:1px solid #edf0f5}.result-row{cursor:pointer}.screen-link{display:inline-block;color:#18245f;font-weight:800;text-decoration:underline;text-decoration-color:#a9b5d2;text-underline-offset:3px;cursor:pointer;position:relative;z-index:1}.screen-link:hover{color:#5124e3;text-decoration-color:#5124e3}
.table-url{color:#4b24db;font-weight:700;text-decoration:underline;white-space:nowrap}.muted{color:#9aa4bb}.result-row:hover{background:#faf9ff}footer{color:#66759f;font-size:10px;padding:14px 2px}
@media(max-width:1200px){.dashboard-brand{width:220px;flex-basis:220px}.env-card{width:430px}.run-details{width:190px}.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.middle,.bottom{grid-template-columns:1fr}}@media(max-width:800px){.sidebar{width:220px}.hero{display:grid}.dashboard-hero{display:flex;flex-direction:column;align-items:stretch;gap:12px}.dashboard-brand{width:100%;flex-basis:auto;min-height:90px}.run-meta{display:flex;flex-direction:column}.env-card,.run-details{width:auto}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.check-grid{grid-template-columns:repeat(2,1fr)}.screens{grid-template-columns:1fr}}

.ui-evidence{margin:10px 0 2px;font-size:13px;color:#334155}.ui-evidence summary{cursor:pointer;color:#4338ca;font-weight:600}.ui-evidence-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:10px}.ui-evidence-side{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;min-width:0}.ui-evidence-side ul{margin:8px 0 0;padding-left:20px;overflow-wrap:anywhere}.ui-evidence-side li{margin:3px 0}.ui-evidence-note{font-size:12px;color:#64748b;margin:8px 0 0}@media(max-width:700px){.ui-evidence-grid{grid-template-columns:1fr}}
@media(max-width:480px){.kpis{grid-template-columns:minmax(0,1fr)}.kpi{min-height:140px}}
/* Final demo safety: prevent KPI action labels from overlapping counts or adjacent cards. */
.kpis{grid-template-columns:repeat(5,minmax(0,1fr));align-items:stretch}
.kpi{min-width:0;max-width:100%;overflow:hidden;display:flex;flex-direction:column;box-sizing:border-box}
.kpi-top,.kpi-title,.kpi-number{min-width:0;overflow-wrap:anywhere}.kpi-top{align-items:flex-start}.kpi-title{line-height:1.35}.kpi-link{flex:0 0 auto;justify-content:space-between}.kpi-link span:last-child{flex:0 0 auto}
.kpi-link{position:static!important;left:auto!important;right:auto!important;bottom:auto!important;margin-top:auto;width:100%;min-width:0;min-height:36px;box-sizing:border-box;white-space:normal;overflow-wrap:anywhere;line-height:1.25;gap:6px}
@media(max-width:1200px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:800px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:480px){.kpis{grid-template-columns:minmax(0,1fr)}}

</style>
</head>
<body>
<div class="app">
<header class="topbar">
  <div class="brand"><img class="logo-image irdeto-logo" src="data:image/png;base64,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" alt="Irdeto"></div>
  <div class="user"><div class="avatar">DS</div><div class="copyright-user"><span class="copyright-symbol">©</span><span>Devesh Sharma</span></div></div>
</header>
<div class="layout">
<aside class="sidebar" id="sidebar"></aside>
<main class="content">

<section id="dashboard" class="page active">
  <div class="hero dashboard-hero">
    <div class="dashboard-brand"><img class="logo-image visionqa-compare-logo" src="data:image/png;base64,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" alt="VisionQA"><div class="visionqa-tagline-compare">for Irdeto Experience</div></div>
    <div class="run-meta">
      <div class="env-card env-compare">
        <div class="env-side"><div class="env-icon">▣</div><div class="env-text"><div class="env-name" id="base-name"></div><div class="env-tenant" id="base-tenant"></div><div class="env-version" id="base-version"></div></div></div>
        <div class="swap">⇄</div>
        <div class="env-side"><div class="env-icon blue">▣</div><div class="env-text"><div class="env-name" id="comp-name"></div><div class="env-tenant" id="comp-tenant"></div><div class="env-version" id="comp-version"></div></div></div>
      </div>
      <div class="run-details"><div class="detail-line">▣ &nbsp; <b>Run Details</b></div><div class="detail-line">◷ &nbsp; <span id="run-time"></span></div><div class="detail-line">◷ &nbsp; Comparison run</div><div class="detail-line">♙ &nbsp; Triggered by: Devesh Sharma</div></div>
    </div>
  </div>
  <div class="kpis" id="kpis"></div>
  <div class="middle">
    <div class="panel"><div class="panel-head"><div class="panel-title"><span class="round-icon">▱</span>Result Distribution</div></div><div class="distribution"><div class="donut" id="donut"><div class="donut-center"><span id="donut-total" style="font-size:23px;margin:0"></span><span>Total Screens</span></div></div><div class="legend" id="legend"></div></div></div>
    <div class="panel"><div class="panel-head"><div class="panel-title"><span class="round-icon" style="background:#ffe9e9;color:#f33">×</span>Recent Mismatches</div><button class="view-all" onclick="showView('mismatched')">View All →</button></div><table class="mismatch-table"><thead><tr><th>#</th><th>Page / Screen</th><th>Module</th><th>Reason</th><th>Last Seen</th></tr></thead><tbody id="mismatch-body"></tbody></table></div>
  </div>
  <div class="bottom">
    <div class="panel module-panel"><div class="panel-head"><div class="panel-title"><span class="round-icon">▥</span>Comparison by Module</div></div><table class="module-table"><thead><tr><th>Module</th><th>Total</th><th>Matched</th><th>Mismatched</th><th>Missing in Comparison</th><th>Missing in Baseline</th><th>Match %</th></tr></thead><tbody id="module-body"></tbody></table></div>
    <div class="panel"><div class="panel-head"><div class="panel-title"><span class="round-icon">ϟ</span>Quick Actions</div></div><div class="qa-list" id="quick-actions"></div><div class="action-grid"><button class="action-btn" onclick="downloadJson()">⇩ &nbsp; Export Report</button><button class="action-btn" onclick="showView('all')">▧ &nbsp; Compare Screenshots</button></div></div>
  </div>
  <footer>VisionQA v1.0.0 &nbsp; • &nbsp; © Devesh Sharma</footer>
</section>

<section id="results" class="page">
  <div class="hero"><div><h1 id="results-title">All Results</h1><p>Browse every captured screen and open a detailed comparison.</p></div></div>
  <div class="filters"><input class="search" id="search" placeholder="Search screen or module..." oninput="renderResults()"><select class="filter-btn" id="module-filter" onchange="renderResults()"><option value="">All Modules</option></select></div>
  <div class="panel" style="padding:0"><table class="result-table"><thead><tr><th>Module</th><th>Screen</th><th>Status</th><th>Navigation</th></tr></thead><tbody id="results-body"></tbody></table></div>
</section>

<section id="detail" class="page detail-page"><div id="detail-content"></div></section>
</main></div></div>

<script>
const DATA = __DATA__;

const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = n => typeof n === 'number' ? n.toFixed(1)+'%' : '—';
const pageStatus = p => p.status === 'SUCCESS' ? 'MATCH' : 'MISMATCH';
const statusCls = p => p.status === 'SUCCESS' ? 'status-match' : 'status-mismatch';
const modules = [...new Set(DATA.pages.map(p=>p.menu))];

function init(){
  document.getElementById('base-name').textContent = `Baseline (${DATA.baseline_version || 'unknown version'})`;
  document.getElementById('comp-name').textContent = `Comparison (${DATA.comparison_version || 'unknown version'})`;
  const tenant=DATA.tenant||'Astro PayTV';
  document.getElementById('base-tenant').textContent = tenant;
  document.getElementById('comp-tenant').textContent = tenant;
  document.getElementById('base-version').textContent = '';
  document.getElementById('comp-version').textContent = '';
  document.getElementById('run-time').textContent = DATA.generated_at.replace('_',' ');
  buildSidebar(); buildKpis(); buildDistribution(); buildMismatches(); buildModules(); buildActions();
  modules.forEach(m=>document.getElementById('module-filter').insertAdjacentHTML('beforeend',`<option>${esc(m)}</option>`));
  if(location.hash.startsWith('#screen/')) openDetail(Number(location.hash.split('/').pop()));
  else if(['#all','#matched','#mismatched','#missing-prod','#missing-stage'].includes(location.hash)) showView(location.hash.slice(1));
}
function title(s){return String(s||'').replace(/^./,x=>x.toUpperCase())}
function buildSidebar(){
  // Hierarchy: OPC main menu -> OPC submenu -> nested screen/sub-screen.
  const reports=[['Overall Summary','dashboard'],['All Results','all'],['Matched Screens','matched'],['Mismatched Screens','mismatched'],['Missing in Comparison','missing-prod'],['Missing in Baseline','missing-stage']];
  const opcNavigation={
    'Content Management':['VOD','VOD Operational Status','Channel','Channel Operational Status','EPG','EPG Operational Status','Experience Manager','Entitlement Control','Global Configuration','Bouquet Management'],
    'Household Manager':['Household','Update Household','Group Management'],
    'System Configuration':['Channel Logo','Packager Detail Configuration','Channel Poster','Event Poster','Guide Metadata','Device Propagator','Device Lookup'],
    'Community Management':['Cohort Management','Device Configuration','Experience Management','UI Dictionary','Software Configurations','Fingerprint Profile','Watermarking Profile','Client Watermarking Profile','ITAS Global'],
    'Broadcast':['Software Target','Text Message Target','UI Dictionary Target','Schedule Management','Watermarking Target','Client Watermarking Target'],
    'Reports':['Accounts Snapshot'],'Overlay Application':[],
    'Security':['DRM Manager','Watermarking'],'Observability':['Audit logs','Monitoring'],'Advertisement':['ITAS']
  };
  const order=Object.keys(opcNavigation);
  [...modules.filter(m=>!order.includes(m) && m!=='Reports')].forEach(m=>{order.push(m);opcNavigation[m]=[];});
  const escAttr=s=>esc(String(s||''));
  function addEntry(entry){
    const href=entry.kind==='common'?`#screen/${entry.index}`:`#${entry.kind==='prod'?'missing-prod':'missing-stage'}/${entry.index}`;
    return `<a class="nav-item screen-nav" data-kind="${entry.kind}" data-index="${entry.index}" href="${href}"><span class="nav-bullet">•</span><span>${escAttr(entry.label)}${entry.kind==='common'?'':' <small>(missing)</small>'}</span></a>`;
  }
  function addTreeNode(node, depth){
    let out='';
    const entries=node.entries||[];
    if(entries.length){
      // If the same screen path exists on multiple sides, keep every result reachable.
      entries.forEach(e=>out+=addEntry(e));
    } else {
      out+=`<div class="nav-item opc-submenu-reference ${depth>1?'nav-nested':''}" aria-disabled="true"><span class="nav-bullet">•</span><span>${escAttr(node.label)}</span></div>`;
    }
    if(node.children.size){
      for(const child of node.children.values()){
        out+=`<div class="nav-subgroup" style="margin-left:${Math.min(depth,3)*10}px">`;
        out+=`<div class="nav-item nav-subgroup-title"><span class="nav-bullet">${child.children.size?'▸':'•'}</span><span>${escAttr(child.label)}</span></div>`;
        out+=addTreeNode(child,depth+1);
        out+='</div>';
      }
    }
    return out;
  }
  let h='';
  order.forEach(menu=>{
    const sectionId=menu==='Reports'?'reports':'menu-'+menu.toLowerCase().replace(/[^a-z0-9]+/g,'-');
    h+=`<div class="nav-section-title ${menu==='Reports'?'report-heading':'menu-title collapsed'}" data-section="${escAttr(sectionId)}"><span>${escAttr(menu)}</span><span class="chev">⌄</span></div>`;
    h+=`<div class="nav-children" data-children="${escAttr(sectionId)}" ${menu==='Reports'?'':'style="display:none"'}>`;
    if(menu==='Reports'){
      reports.forEach(([label,view],i)=>h+=`<a class="nav-item report-nav ${i===0?'active':''}" data-view="${view}" href="#${view}"><span class="nav-dot"></span><span>${label}</span></a>`);
    }
    const entries=[];
    DATA.pages.forEach((p,index)=>{if(p.menu===menu)entries.push({label:p.submenu||'Unnamed screen',kind:'common',index});});
    (DATA.removed_pages||[]).forEach((p,index)=>{if(p.menu===menu)entries.push({label:p.submenu||'Unnamed screen',kind:'prod',index});});
    (DATA.added_pages||[]).forEach((p,index)=>{if(p.menu===menu)entries.push({label:p.submenu||'Unnamed screen',kind:'stage',index});});
    const root={label:menu,entries:[],children:new Map()};
    entries.forEach(entry=>{
      const parts=String(entry.label).split(/\s+-\s+/).map(x=>x.trim()).filter(Boolean);
      let node=root;
      parts.forEach(part=>{
        if(!node.children.has(part))node.children.set(part,{label:part,entries:[],children:new Map()});
        node=node.children.get(part);
      });
      node.entries.push(entry);
    });
    const canonical=opcNavigation[menu]||[];
    canonical.forEach(label=>{if(!root.children.has(label))root.children.set(label,{label,entries:[],children:new Map()});});
    // Sort first-level submenu nodes to OPC's canonical order; keep any extra discovered submenu after them.
    const sorted=new Map();
    canonical.forEach(label=>{if(root.children.has(label)){sorted.set(label,root.children.get(label));root.children.delete(label);}});
    root.children.forEach((v,k)=>sorted.set(k,v));
    root.children=sorted;
    for(const node of root.children.values()){
      h+=`<div class="nav-submenu-block">`;
      h+=`<div class="nav-item nav-submenu-title"><span class="nav-bullet">${node.children.size?'▸':'•'}</span><span>${escAttr(node.label)}</span></div>`;
      h+=addTreeNode(node,1);
      h+='</div>';
    }
    h+='</div>';
  });
  h+=`<div class="sidebar-footer">VisionQA v1.0.0</div>`;
  document.getElementById('sidebar').innerHTML=h;
  // All click actions are handled by one delegated listener at the end of the document.
  // Do not attach a second set of per-element handlers here.
}
function buildKpis(){
  const s=DATA.summary,total=s.total_unique_pages||((s.common_pages||s.total_pages||0)+((s.added_pages||0)+(s.removed_pages||0)));
  const cards=[
    ['total','▱','Total Screens',total,'all','See All Results',''],
    ['match','✓','Matched',s.matched,'matched','See All Matched','green'],
    ['mismatch','×','Mismatched',s.changed,'mismatched','See All Mismatched','red'],
    ['missing-prod','!','Missing in Comparison',s.removed_pages,'missing-prod','See Missing in Comparison','blue'],
    ['missing-stage','!','Missing in Baseline',s.added_pages,'missing-stage','See Missing in Baseline','purple']
  ];
  document.getElementById('kpis').innerHTML=cards.map(c=>`<div class="kpi ${c[0]}"><div class="kpi-top"><div class="kpi-icon">${c[1]}</div><div class="kpi-title">${c[2]}</div></div><div class="kpi-number">${c[3]} ${c[6]?`<span class="kpi-percent ${c[6]}">(${pct(c[3]/Math.max(total,1)*100)})</span>`:''}</div><div class="kpi-link" onclick="showView('${c[4]}')">${c[5]} <span>→</span></div></div>`).join('');
}
function buildDistribution(){
  const s=DATA.summary;
  const total=Math.max(s.total_unique_pages||((s.common_pages||s.total_pages||0)+(s.added_pages||0)+(s.removed_pages||0)),1);
  const matched=(s.matched||0)/total*100;
  const mismatched=(s.changed||0)/total*100;
  const missingProd=(s.removed_pages||0)/total*100;
  const missingStage=(s.added_pages||0)/total*100;
  const end1=matched;
  const end2=end1+mismatched;
  const end3=end2+missingProd;
  document.getElementById('donut').style.setProperty('--m',end1+'%');
  document.getElementById('donut').style.setProperty('--mm',end2+'%');
  document.getElementById('donut').style.setProperty('--mp',end3+'%');
  document.getElementById('donut-total').textContent=total;
  const rows=[
    ['var(--green)','Matched',s.matched||0,matched],
    ['var(--red)','Mismatched',s.changed||0,mismatched],
    ['var(--blue)','Missing in Comparison',s.removed_pages||0,missingProd],
    ['var(--lav)','Missing in Baseline',s.added_pages||0,missingStage]
  ];
  document.getElementById('legend').innerHTML=rows.map(r=>`<div class="legend-row"><span class="legend-dot" style="background:${r[0]}"></span><span class="legend-label">${r[1]}</span><span class="legend-value">${r[2]}</span><span class="legend-pct">${r[3].toFixed(1)}%</span></div>`).join('');
}
function formatDate(v){const m=String(v||'').match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})$/);if(!m)return String(v||'');const d=new Date(Number(m[1]),Number(m[2])-1,Number(m[3]),Number(m[4]),Number(m[5]),Number(m[6]));return d.toLocaleString('en-GB',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:true}).replace(',', '');}
function shortReason(p){
  const rs=(p.reasons||[]);
  const r=rs.find(x=>!['URL_CHANGED','UI_STRUCTURE_CHANGED'].includes(String(x?.type||'').toUpperCase()));
  if(!r)return 'No actionable difference';
  const t=String(r.type||'').toUpperCase();
  if(t==='SCREENSHOT_CHANGED'){
    const pct=Number(r.difference_percentage);
    return Number.isFinite(pct) ? `Visual difference exceeds 20% threshold (${pct.toFixed(2)}%)` : 'Visual difference exceeds 20% threshold';
  }
  if(t==='UI_STRUCTURE_CHANGED'){
    const category=humanUiCategory(r.category||'UI element');
    const component=humanUiComponent(r.component||r.element||r.name||category);
    if(r.stage==='present' && r.comparison==='missing') return `Missing in ${title(DATA.comparison_environment)}: ${component}`;
    if(r.stage==='missing' && r.comparison==='present') return `Added in ${title(DATA.comparison_environment)}: ${component}`;
    return `UI structure changed: ${component}`;
  }
  if(t==='COMPONENT_ADDED') return `Component added: ${r.component||'unnamed'}`;
  if(t==='COMPONENT_REMOVED') return `Component removed: ${r.component||'unnamed'}`;
  if(t==='COMPONENT_PRESENCE_CHANGED') return `Component presence changed: ${r.component||'unnamed'}`;
  if(t==='NAVIGATION_CHANGED') return `Navigation changed: ${r.baseline||'—'} → ${r.comparison||'—'}`;
  if(t==='TITLE_CHANGED') return `Page title changed: ${r.baseline||'—'} → ${r.comparison||'—'}`;
  if(t==='EXECUTION_STATE_CHANGED') return `Execution state changed: ${r.baseline?.status||'—'} → ${r.comparison?.status||'—'}`;
  if(t==='ERROR_CHANGED') return `Error state changed: ${r.baseline||'None'} → ${r.comparison||'None'}`;
  return t.replaceAll('_',' ').toLowerCase().replace(/^./,x=>x.toUpperCase());
}
function buildMismatches(){
  const rows=(DATA.pages||[]).filter(p=>p.status!=='SUCCESS').slice(0,5);
  document.getElementById('mismatch-body').innerHTML=rows.length?rows.map((p,i)=>{
    const reason=shortReason(p);
    return `<tr><td>${i+1}</td><td><b>${esc(p.submenu)}</b></td><td>${esc(p.menu)}</td><td class="bad-text">${esc(reason)}</td><td>${esc(formatDate(DATA.generated_at))}</td></tr>`;
  }).join(''):'<tr><td colspan="5" class="empty">No mismatches found</td></tr>';
}
function buildModules(){
  const stats={};
  DATA.pages.forEach(p=>{
    const x=stats[p.menu]??={total:0,matched:0,mismatched:0,missingProd:0,missingStage:0};
    x.total++; p.status==='SUCCESS'?x.matched++:x.mismatched++;
  });
  (DATA.removed_pages||[]).forEach(p=>{
    const x=stats[p.menu]??={total:0,matched:0,mismatched:0,missingProd:0,missingStage:0};
    x.total++; x.missingProd++;
  });
  (DATA.added_pages||[]).forEach(p=>{
    const x=stats[p.menu]??={total:0,matched:0,mismatched:0,missingProd:0,missingStage:0};
    x.total++; x.missingStage++;
  });
  document.getElementById('module-body').innerHTML=Object.entries(stats).length?Object.entries(stats).map(([m,x])=>{
    const rate=x.matched/Math.max(x.total,1)*100;
    return `<tr><td>${esc(m)}</td><td>${x.total}</td><td class="num-green">${x.matched}</td><td class="num-red">${x.mismatched}</td><td>${x.missingProd}</td><td>${x.missingStage}</td><td><span class="bar"><span style="width:${rate}%"></span></span>${rate.toFixed(1)}%</td></tr>`;
  }).join(''):'<tr><td colspan="7" class="empty">No module data available</td></tr>';
}
function buildActions(){
  const s=DATA.summary;
  const actions=[['#eee8ff','#6330e9','▣','See All Results',`View ${s.total_unique_pages||s.total_pages} screens`,'all'],['#dcf6e8','#10aa66','✓','See All Matched',`View ${s.matched} matched screens`,'matched'],['#ffe0e0','#ff3838','×','See All Mismatched',`View ${s.changed} mismatched screens`,'mismatched'],['#e5f1ff','#1478e9','!','See Missing in Comparison',`View ${s.removed_pages} screens missing in comparison`,'missing-prod'],['#eee5ff','#7440ed','!','See Missing in Baseline',`View ${s.added_pages} screens missing in baseline`,'missing-stage']];
  document.getElementById('quick-actions').innerHTML=actions.map(a=>`<div class="qa" onclick="showView('${a[5]}')"><div class="qa-icon" style="background:${a[0]};color:${a[1]}">${a[2]}</div><div><div class="qa-title">${a[3]}</div><div class="qa-sub">${a[4]}</div></div><div class="qa-arrow">›</div></div>`).join('');
}
let currentFilter='all';
function showView(view){
  if(view==='dashboard'){activate('dashboard');setNav('dashboard');history.replaceState(null,'','#dashboard');return}
  currentFilter=view;activate('results');document.getElementById('results-title').textContent={all:'All Results',matched:'Matched Screens',mismatched:'Mismatched Screens','missing-prod':'Missing in Comparison','missing-stage':'Missing in Baseline'}[view];renderResults();setNav(view);history.replaceState(null,'','#'+view);
}
function activate(id){document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));document.getElementById(id).classList.add('active')}
function setNav(view){
  document.querySelectorAll('.report-nav').forEach(x=>x.classList.toggle('active',x.dataset.view===view));
}
function filteredPages(){
  const q=(document.getElementById('search')?.value||'').toLowerCase().trim(),mod=document.getElementById('module-filter')?.value||'';
  const missingProd=(DATA.removed_pages||[]).map((p,index)=>({...p,_missing:true,_missing_side:'prod',_missing_index:index}));
  const missingStage=(DATA.added_pages||[]).map((p,index)=>({...p,_missing:true,_missing_side:'stage',_missing_index:index}));
  let source=[];
  if(currentFilter==='missing-prod') source=missingProd;
  else if(currentFilter==='missing-stage') source=missingStage;
  else if(currentFilter==='all') source=[...DATA.pages,...missingProd,...missingStage];
  else source=DATA.pages;
  return source.filter(p=>{
    let ok=currentFilter==='all'||(currentFilter==='matched'&&p.status==='SUCCESS')||(currentFilter==='mismatched'&&p.status!=='SUCCESS')||p._missing;
    if(mod&&p.menu!==mod)ok=false;
    if(q&&!(p.menu+' '+p.submenu).toLowerCase().includes(q))ok=false;
    return ok;
  });
}
function renderResults(){
  const body=document.getElementById('results-body');if(!body)return;const rows=filteredPages();
  body.innerHTML=rows.length?rows.map(p=>{
    const missing=!!p._missing;
    const i=missing?-1:DATA.pages.indexOf(p);
    const status=missing?'MISSING':pageStatus(p),cls=missing?'status-mismatch':statusCls(p);
    const nav=missing
      ? '<span class="muted">—</span>'
      : (p.navigation?.matched?'<span class="ok">MATCH</span>':'<span class="bad">MISMATCH</span>');
    const click=missing
      ? `onclick="openMissingDetail('${p._missing_side}',${(p._missing_index??0)})"`
      : `onclick="openDetail(${i})"`;
    const screenLink = missing
      ? `<a class="screen-link" href="#${p._missing_side==='prod'?'missing-prod':'missing-stage'}/${encodeURIComponent(p.menu||'')}/${encodeURIComponent(p.submenu||'')}" onclick="event.preventDefault();event.stopPropagation();openMissingDetail('${p._missing_side}',${p._missing_index});">${esc(p.submenu)}</a>`
      : `<a class="screen-link" href="#screen/${i}" onclick="event.preventDefault();event.stopPropagation();openDetail(${i});">${esc(p.submenu)}</a>`;
    return `<tr class="result-row" ${click}><td>${esc(p.menu)}</td><td>${screenLink}</td><td><span class="status-pill ${cls}">${status}</span></td><td>${nav}</td></tr>`
  }).join(''):'<tr><td colspan="4" class="empty">No results found.</td></tr>';
}
function asset(p){return p||''}
function imageTag(path,label){return path?`<img class="shot" src="${esc(asset(path))}" alt="${esc(label)}" onclick="window.open(this.src,'_blank')">`:'<div class="no-shot">Screenshot unavailable</div>'}
function imageList(paths,label){
  const list=Array.isArray(paths)?paths.filter(Boolean):(paths?[paths]:[]);
  if(!list.length)return '<div class="no-shot">Screenshot unavailable</div>';
  return list.map((path,i)=>`<div style="margin-bottom:8px"><div style="font-size:10px;color:#7180a9;margin:0 0 4px">Part ${i+1}</div>${imageTag(path,`${label} Part ${i+1}`)}</div>`).join('');
}

function readableReason(r){
  const type=String(r?.type||'').toUpperCase();
  if(type==='URL_CHANGED') return '';
  const base=r?.baseline ?? r?.stage;
  const comp=r?.comparison ?? r?.prod;
  const emptyValue=v=>v===null || v===undefined || ['','—','–','-','null','none','n/a','not available'].includes(String(v).trim().toLowerCase());
  if(type==='SCREENSHOT_CHANGED' && emptyValue(base) && emptyValue(comp)) return '';
  if(type==='NAVIGATION_CHANGED'){
    return `<div class="difference-item"><div class="difference-title">Navigation changed</div><div class="difference-values"><span class="difference-side">${esc(title(DATA.baseline_environment))}: <b>${esc(base||'—')}</b></span><span class="difference-arrow">→</span><span class="difference-side">${esc(title(DATA.comparison_environment))}: <b>${esc(comp||'—')}</b></span></div></div>`;
  }
  if(type==='TITLE_CHANGED'){
    return `<div class="difference-item"><div class="difference-title">Page title changed</div><div class="difference-values"><span class="difference-side">${esc(title(DATA.baseline_environment))}: <b>${esc(base||'—')}</b></span><span class="difference-arrow">→</span><span class="difference-side">${esc(title(DATA.comparison_environment))}: <b>${esc(comp||'—')}</b></span></div></div>`;
  }
  if(type==='EXECUTION_STATE_CHANGED'){
    const bv=base?.healthy?'Successful':'Failed',cv=comp?.healthy?'Successful':'Failed';
    return `<div class="difference-item"><div class="difference-title">Execution state changed</div><div class="difference-values"><span class="difference-side">${esc(title(DATA.baseline_environment))}: <b>${bv}</b></span><span class="difference-arrow">→</span><span class="difference-side">${esc(title(DATA.comparison_environment))}: <b>${cv}</b></span></div></div>`;
  }
  if(type==='ERROR_CHANGED'){
    return `<div class="difference-item"><div class="difference-title">Error state changed</div><div class="difference-values"><span class="difference-side">${esc(title(DATA.baseline_environment))}: <b>${esc(base||'None')}</b></span><span class="difference-arrow">→</span><span class="difference-side">${esc(title(DATA.comparison_environment))}: <b>${esc(comp||'None')}</b></span></div></div>`;
  }
  return `<div class="difference-item"><div class="difference-title">${esc(type.replaceAll('_',' ').toLowerCase().replace(/^./,x=>x.toUpperCase()))}</div><div class="difference-values"><span>${esc(base||'—')}</span><span class="difference-arrow">→</span><span>${esc(comp||'—')}</span></div></div>`;
}

function humanUiCategory(value){
  return String(value||'UI element').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
}
function humanUiComponent(value){
  const raw=String(value||'UI element');
  const parts=raw.split('::');
  if(parts.length>1) return `${humanUiCategory(parts[0])} — ${parts.slice(1).join('::')}`;
  return raw.replace(/^component::/i,'').replace(/^label::/i,'Label — ').replace(/^button::/i,'Button — ').replace(/^input::/i,'Input — ').replace(/^tab::/i,'Tab — ');
}
function formatUiDifference(x){
  const category=humanUiCategory(x?.category || x?.type || 'UI element');
  const rawComponent=x?.component || x?.element || x?.name || x?.label || '';
  const component=humanUiComponent(rawComponent || category);
  const stage=String(x?.stage || x?.baseline || (x?.removed ? 'present' : '') || '').toLowerCase();
  const comparison=String(x?.comparison || x?.prod || x?.production || (x?.added ? 'present' : '') || '').toLowerCase();
  let titleText='UI structure changed', cls='';
  let stageText=stage || 'not available';
  let comparisonText=comparison || 'not available';

  if(stage==='present' && comparison==='missing'){
    titleText=`Missing in ${title(DATA.comparison_environment)}`; cls=' removed';
  } else if(stage==='missing' && comparison==='present'){
    titleText=`Added in ${title(DATA.comparison_environment)}`; cls=' added';
  }

  const stageEvidence=Array.isArray(x?.stage_evidence)?x.stage_evidence:[];
  const comparisonEvidence=Array.isArray(x?.comparison_evidence)?x.comparison_evidence:[];
  const evidence=(label,items)=>`<div class="ui-evidence-side"><b>${esc(label)} inventory (${items.length})</b><ul>${items.length?items.map(item=>`<li>${esc(item)}</li>`).join(''):'<li>No captured elements in this category</li>'}</ul></div>`;
  const hasEvidence=Array.isArray(x?.stage_evidence)||Array.isArray(x?.comparison_evidence);
  return `<div class="difference-item${cls}">
    <div class="difference-title">${esc(titleText)}</div>
    <div class="difference-values">
      <span class="difference-side"><b>${esc(component)}</b></span>
      <span class="difference-side">${esc(title(DATA.baseline_environment))}: <b>${esc(stageText)}</b></span>
      <span class="difference-arrow">→</span>
      <span class="difference-side">${esc(title(DATA.comparison_environment))}: <b>${esc(comparisonText)}</b></span>
    </div>
    ${hasEvidence?`<details class="ui-evidence"><summary>View evidence — ${esc(humanUiCategory(x?.category||'UI elements'))}</summary><div class="ui-evidence-grid">${evidence(title(DATA.baseline_environment),stageEvidence)}${evidence(title(DATA.comparison_environment),comparisonEvidence)}</div><p class="ui-evidence-note">These are the captured static elements in this category. The current crawler does not record exact screen coordinates or DOM parent paths.</p></details>`:''}
  </div>`;
}

function openDetail(i){
  const p=DATA.pages[i];
  if(!p)return;
  renderDetail(p,null,i);
}
function openMissingDetail(side,index){
  const source=side==='prod'?(DATA.removed_pages||[]):(DATA.added_pages||[]);
  const p=source[index];
  if(!p)return;
  renderDetail(p,side,null);
}
function renderDetail(p,missingSide,commonIndex){
  const missing=!!missingSide;
  const meaningfulReasons=(p.reasons||[]).filter(r=>!['URL_CHANGED','UI_STRUCTURE_CHANGED'].includes(String(r?.type||'').toUpperCase())).map(readableReason).filter(Boolean).join('');
  const comps=missing?'':[
    ...(p.components?.changed||[]).map(c=>`<div class="difference-item"><div class="difference-title">Component changed</div><div class="difference-values"><b>${esc(c.component||c)}</b></div></div>`),
    ...(p.components?.added||[]).map(c=>`<div class="difference-item added"><div class="difference-title">Component added</div><div class="difference-values"><b>${esc(c)}</b></div></div>`),
    ...(p.components?.removed||[]).map(c=>`<div class="difference-item removed"><div class="difference-title">Component removed</div><div class="difference-values"><b>${esc(c)}</b></div></div>`)
  ].join('');
  let differences=meaningfulReasons+comps;

  let baselineUrl='',comparisonUrl='';
  if(missing){
    const availableUrl=typeof p.url==='string'?p.url:(p.url?.baseline||p.url?.comparison||'');
    if(missingSide==='prod') baselineUrl=availableUrl;
    else comparisonUrl=availableUrl;
    const missingEnv=missingSide==='prod'?title(DATA.comparison_environment):title(DATA.baseline_environment);
    const availableEnv=missingSide==='prod'?title(DATA.baseline_environment):title(DATA.comparison_environment);
    differences=`<div class="difference-item removed"><div class="difference-title">Screen missing in ${esc(missingEnv)}</div><div class="difference-values"><span class="difference-side">${esc(availableEnv)}: <b>Present</b></span><span class="difference-arrow">→</span><span class="difference-side">${esc(missingEnv)}: <b>Missing</b></span></div></div>`;
  } else {
    baselineUrl=p.url?.baseline||'';
    comparisonUrl=p.url?.comparison||'';
  }

  const backView=missing?(missingSide==='prod'?'missing-prod':'missing-stage'):'all';
  const status=missing?'MISSING':pageStatus(p);
  const statusClass=missing?'status-mismatch':statusCls(p);
  const baselineShots=missing?[]:(p.screenshot_comparison?.baseline_screenshots||p.baseline_screenshot||[]);
  const comparisonShots=missing?[]:(p.screenshot_comparison?.comparison_screenshots||p.comparison_screenshot||[]);
  const baselineCount=Array.isArray(baselineShots)?baselineShots.length:(baselineShots?1:0);
  const comparisonCount=Array.isArray(comparisonShots)?comparisonShots.length:(comparisonShots?1:0);
  const urlBox=(label,url)=>url
    ? `<a class="url-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a>`
    : '<div class="url-unavailable">URL unavailable</div>';

  document.getElementById('detail-content').innerHTML=`
  <div class="breadcrumb">Reports › ${esc(p.menu)} › ${esc(p.submenu)}</div>
  <div class="detail-top"><div><h1 class="detail-title">${esc(p.submenu)}</h1><p style="color:#7180a8">${esc(p.menu)}</p></div><span class="status-pill ${statusClass}">${status}</span></div>
  <div class="detail-meta"><div class="meta-box"><div class="meta-label">Baseline</div><div class="meta-value">${esc(title(DATA.baseline_environment))} · ${esc(DATA.baseline_version)}</div></div><div class="meta-box"><div class="meta-label">Comparison</div><div class="meta-value">${esc(title(DATA.comparison_environment))} · ${esc(DATA.comparison_version)}</div></div></div>
  <div class="screens"><div class="shot-card"><div class="shot-head"><span>${esc(title(DATA.baseline_environment))}</span><span>${baselineCount} part(s)</span></div>${imageList(baselineShots,'Baseline')}</div><div class="shot-card"><div class="shot-head"><span>${esc(title(DATA.comparison_environment))}</span><span>${comparisonCount} part(s)</span></div>${imageList(comparisonShots,'Comparison')}</div></div>
  <div class="panel diff-panel"><div class="panel-title">Differences</div><div class="difference-list">${differences||'<div class="no-difference">No structural or navigation differences detected.</div>'}</div></div>
  <div class="panel diff-panel"><div class="panel-title">Comparison Checks</div><div class="check-grid">${missing?'<div class="check"><div class="check-label">Navigation</div><div class="check-value">N/A</div></div><div class="check"><div class="check-label">URL</div><div class="check-value">N/A</div></div>':`${check('Navigation',p.navigation?.matched)}${checkIgnored('URL','Dynamic route ignored')}${check('Title',p.title?.matched)}${check('Execution',p.execution?.matched)}${check('Components',p.components?.matched)}`}</div></div>
  <div style="margin-top:12px"><button class="view-all" onclick="showView('${backView}')">← Back to Results</button></div>`;
  // Critical: rendering the detail markup alone does not display it; switch
  // away from the results/dashboard page before updating the URL hash.
  activate('detail');
  setNav('');
  history.replaceState(null,'',missing?`#${backView}/${encodeURIComponent(p.menu||'')}/${encodeURIComponent(p.submenu||'')}`:`#screen/${commonIndex}`);
  window.scrollTo({top:0,behavior:'auto'});
}
function check(label,ok){
  if(ok===null || ok===undefined) return `<div class="check"><div class="check-label">${label}</div><div class="check-value">N/A</div></div>`;
  return `<div class="check"><div class="check-label">${label}</div><div class="check-value ${ok?'ok':'bad'}">${ok?'MATCH':'MISMATCH'}</div></div>`
}
function checkIgnored(label,text){
  return `<div class="check"><div class="check-label">${esc(label)}</div><div class="check-value" style="color:#6b5bd2">IGNORED</div><div style="font-size:9px;color:#7a86a8;margin-top:3px">${esc(text)}</div></div>`;
}
function downloadJson(){const b=new Blob([JSON.stringify(DATA,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=DATA.json_name;a.click();URL.revokeObjectURL(a.href)}
init();
</script>
<script>
/* Single delegated click handler for all dynamically generated report controls. */
(function(){
  function toggleBlock(titleEl, selector) {
    const block = titleEl.nextElementSibling;
    if (!block || !block.matches(selector)) return;
    const collapsed = titleEl.classList.toggle('collapsed');
    block.style.display = collapsed ? 'none' : 'block';
  }
  document.addEventListener('click', function(event){
    const target = event.target && event.target.closest ? event.target.closest(
      '.menu-title, .report-heading, .nav-submenu-title, .nav-subgroup-title, .report-nav, .screen-nav, .result-row'
    ) : null;
    if (!target) return;

    if (target.matches('.menu-title, .report-heading')) {
      event.preventDefault();
      const id = target.dataset.section;
      const children = document.querySelector('[data-children="' + id.replace(/\\/g,'\\\\').replace(/"/g,'\\"') + '"]');
      if (children) {
        const collapsed = target.classList.toggle('collapsed');
        children.style.display = collapsed ? 'none' : 'block';
      }
      return;
    }
    if (target.matches('.nav-submenu-title')) {
      event.preventDefault();
      const block = target.parentElement;
      const children = block && Array.from(block.children).find(el => el !== target && (el.classList.contains('nav-item') || el.classList.contains('nav-subgroup') || el.classList.contains('screen-nav')));
      // Hide/show all descendants in this submenu block without affecting sibling submenus.
      if (block) {
        const collapsed = target.classList.toggle('collapsed');
        Array.from(block.children).filter(el => el !== target).forEach(el => { el.style.display = collapsed ? 'none' : ''; });
      }
      return;
    }
    if (target.matches('.nav-subgroup-title')) {
      event.preventDefault();
      const block = target.parentElement;
      if (block) {
        const collapsed = target.classList.toggle('collapsed');
        Array.from(block.children).filter(el => el !== target).forEach(el => { el.style.display = collapsed ? 'none' : ''; });
      }
      return;
    }
    if (target.matches('.report-nav')) {
      event.preventDefault();
      if (typeof showView === 'function') showView(target.dataset.view);
      return;
    }
    if (target.matches('.screen-nav')) {
      event.preventDefault();
      const index = Number(target.dataset.index);
      if (!Number.isInteger(index) || index < 0) return;
      if (target.dataset.kind === 'common') openDetail(index);
      else openMissingDetail(target.dataset.kind, index);
      return;
    }
    if (target.matches('.result-row')) {
      if (event.target.closest('a,button,input,select,textarea')) return;
      const common = target.getAttribute('onclick') || '';
      let match = common.match(/openDetail\((\d+)\)/);
      if (match) { openDetail(Number(match[1])); return; }
      match = common.match(/openMissingDetail\('([^']+)',\s*(\d+)\)/);
      if (match) openMissingDetail(match[1], Number(match[2]));
    }
  });
})();
</script>
</body>
</html>"""
        html_doc = html_doc.replace("__DATA__", self._json(payload))
        report_path = self.output_dir / html_name
        report_path.write_text(html_doc, encoding="utf-8")
        return report_path
