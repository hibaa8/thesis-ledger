import csv
from html import escape
from io import BytesIO, StringIO
from urllib.parse import quote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile


def csv_text(rows, columns):
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        cells = {}
        for column in columns:
            value = row.get(column)
            if isinstance(value, (list, tuple)):
                value = " | ".join(map(str, value))
            if isinstance(value, str) and (
                value.lstrip().startswith(("=", "+", "-", "@"))
                or value.startswith(("\t", "\r", "\n"))
            ):
                value = "'" + value
            cells[column] = value
        writer.writerow(cells)
    return output.getvalue()


def markdown_text(value):
    return escape(str(value), quote=False).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def source_link(item):
    title = markdown_text(item["title"]).replace("\n", " ")
    url = item.get("url") or ""
    try:
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            encoded = quote(url, safe=":/?#[]@!$&()*+,;=%")
            return f"[{title}](<{encoded}>)"
    except ValueError:
        pass
    return title


def research_archive(run):
    request = run["request"]
    snapshot = run["snapshot"]
    forecast = run["forecast"]
    evidence = {item["id"]: item for item in snapshot["evidence"]}
    reports = [{"stage": "conclusion", **run["decision"]}] + [
        {"stage": stage, **report} for stage, report in run["reports"].items()
    ]
    lines = [
        f"# {request['ticker']} research report",
        "",
        f"Analysis date: {request['as_of']}  ",
        f"Run ID: {run['id']}  ",
        f"Price source: {markdown_text(snapshot['provider'])}  ",
        f"Forecast horizon: {request['horizon']} trading sessions",
        "",
        f"**Research question:** {markdown_text(request['question'])}",
        "",
    ]
    for report in reports:
        stage = report["stage"].replace("-", " ").title()
        lines.extend([
            f"## {stage} · {report['stance'].title()}",
            "",
            markdown_text(report["summary"]),
            "",
            f"**Invalidation:** {markdown_text(report['invalidation'])}",
            "",
        ])
        lines.extend(f"- Risk: {markdown_text(risk)}" for risk in report.get("risks", []))
        lines.extend(
            f"- Source: {source_link(evidence[item_id])}"
            for item_id in dict.fromkeys(report["evidence_ids"])
            if item_id in evidence
        )
        lines.append("")
    lines.extend(["## Evidence", ""])
    for item in evidence.values():
        lines.extend([
            f"- {source_link(item)} · {markdown_text(item.get('published') or 'Undated')}",
            f"  {markdown_text(item['text']).replace(chr(10), ' ')}",
        ])
    lines.extend(["", "## Forecast and limitations", "", markdown_text(forecast["label"]), "",
                  markdown_text(forecast["disclaimer"]), ""])
    lines.extend(f"- {markdown_text(warning)}" for warning in snapshot["warnings"])
    lines.extend([
        "", "## Included data", "",
        "- Analyst reports, debate, risk review, and the final conclusion",
        "- Source evidence, observed prices, forecast ranges, forecast checks, and the harness trace",
        "",
    ])
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zipped:
        zipped.writestr("report.md", "\n".join(lines))
        tables = [
            ("reports", reports, ("stage", "role", "stance", "summary", "invalidation", "risks", "evidence_ids")),
            ("evidence", evidence.values(), ("id", "kind", "source", "title", "published", "url", "text")),
            ("observed-prices", snapshot["bars"], ("date", "open", "high", "low", "close", "volume")),
            ("forecast", forecast["points"], ("date", "low", "median", "high")),
            ("market-metrics", [run["metrics"]], tuple(run["metrics"])),
            ("forecast-checks", [run["evaluation"]], tuple(run["evaluation"])),
            ("harness-trace", run["trace"], ("at", "stage", "detail")),
        ]
        for name, rows, columns in tables:
            zipped.writestr(f"{name}.csv", csv_text(rows, columns))
    return archive.getvalue()
