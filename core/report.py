from pathlib import Path


class ReportManager:

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def generate(
        self,
        environment: str,
        version: str,
        tenant: str,
        results: list[dict],
    ) -> None:

        total_pages = len(results)

        successful = sum(
            1
            for r in results
            if r.get("status") == "SUCCESS"
        )

        failed = total_pages - successful

        gallery = ""

        for result in results:

            status = result.get("status", "UNKNOWN")

            badge = (
                "#16a34a"
                if status == "SUCCESS"
                else "#dc2626"
            )

            screenshot = result.get("screenshot")

            if screenshot:

                image = Path(screenshot)

                rel = (
                    f"{image.parent.name}/{image.name}"
                ).replace("\\", "/")

                shot = (
                    f'<a href="{rel}" target="_blank">'
                    f'<img class="thumbnail" src="{rel}">'
                    f'</a>'
                )

            else:

                shot = (
                    '<div class="thumbnail-placeholder">'
                    'No Screenshot Available'
                    '</div>'
                )

            navigation_type = result.get(
                "navigation_type",
                "N/A",
            )

            menu = result.get(
                "menu",
                "N/A",
            )

            submenu = result.get(
                "submenu",
                "N/A",
            )

            gallery += f"""
<div class="page-card">

    <div class="page-header">

        <div>

            <div class="page-menu">
                {menu}
            </div>

            <div class="page-title">
                {submenu}
            </div>

        </div>

        <span
            class="badge"
            style="background:{badge};"
        >
            {status}
        </span>

    </div>

    <div class="page-info">

        <div>
            <strong>Navigation</strong>
            <br>
            {navigation_type}
        </div>

    </div>

    {shot}

</div>
"""

        html = f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<title>VisionQA Report</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: #f3f4f6;
    font-family: Arial, sans-serif;
    color: #111827;
}}

.header {{
    background: #ffffff;
    padding: 30px;
    border-bottom: 1px solid #e5e7eb;
}}

.header h1 {{
    margin: 0 0 8px 0;
}}

.header p {{
    margin: 0;
    color: #6b7280;
}}

.summary {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(180px, 1fr));

    gap: 20px;
    padding: 30px;
}}

.summary-card {{
    background: #ffffff;
    border-radius: 10px;
    box-shadow:
        0 2px 8px rgba(0, 0, 0, 0.08);

    padding: 20px;
}}

.summary-value {{
    font-size: 28px;
    font-weight: bold;
    margin-top: 8px;
}}

.gallery {{
    display: grid;
    grid-template-columns:
        repeat(auto-fill, minmax(420px, 1fr));

    gap: 24px;
    padding: 30px;
}}

.page-card {{
    background: #ffffff;
    border-radius: 10px;

    box-shadow:
        0 2px 8px rgba(0, 0, 0, 0.08);

    padding: 20px;
}}

.page-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;

    margin-bottom: 16px;
}}

.page-menu {{
    font-size: 13px;
    color: #6b7280;
    margin-bottom: 5px;
}}

.page-title {{
    font-size: 18px;
    font-weight: bold;
}}

.badge {{
    color: #ffffff;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: bold;
}}

.page-info {{
    padding: 12px 0;
    border-top: 1px solid #e5e7eb;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: 16px;
}}

.thumbnail {{
    width: 100%;
    height: auto;
    display: block;
    border-radius: 6px;
    border: 1px solid #e5e7eb;
}}

.thumbnail-placeholder {{
    height: 260px;

    display: flex;
    align-items: center;
    justify-content: center;

    background: #f5f5f5;
    border-radius: 6px;

    color: #6b7280;
}}

.section-title {{
    padding: 0 30px;
    margin-top: 10px;
}}

.footer {{
    text-align: center;
    padding: 40px;
    color: #6b7280;
}}

</style>

</head>

<body>

<div class="header">

    <h1>VisionQA</h1>

    <p>
        Visual Regression Report
    </p>

</div>


<div class="summary">

    <div class="summary-card">

        <b>Environment</b>

        <div class="summary-value">
            {environment}
        </div>

    </div>


    <div class="summary-card">

        <b>Version</b>

        <div class="summary-value">
            {version}
        </div>

    </div>


    <div class="summary-card">

        <b>Tenant</b>

        <div class="summary-value">
            {tenant}
        </div>

    </div>


    <div class="summary-card">

        <b>Total Pages</b>

        <div class="summary-value">
            {total_pages}
        </div>

    </div>


    <div class="summary-card">

        <b>Passed</b>

        <div class="summary-value">
            {successful}
        </div>

    </div>


    <div class="summary-card">

        <b>Failed</b>

        <div class="summary-value">
            {failed}
        </div>

    </div>

</div>


<h2 class="section-title">
    Screenshot Gallery
</h2>


<div class="gallery">

    {gallery}

</div>


<div class="footer">

    Generated by VisionQA

</div>

</body>

</html>
"""

        report_path = (
            self.output_dir / "report.html"
        )

        report_path.write_text(
            html,
            encoding="utf-8",
        )