from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_SOC2_CONTROLS = {
    "CC6.1": {
        "name": "Logical and Physical Access Controls",
        "description": "Authentication events are logged with timestamp, key ID, and outcome.",
        "metric": "auth_logs",
    },
    "CC6.7": {
        "name": "Transmission of Confidential Information",
        "description": "All API transmissions are logged; raw content is stored only as SHA-256 hash.",
        "metric": "request_log_coverage",
    },
    "CC7.1": {
        "name": "Detection and Monitoring of Anomalies",
        "description": "Error rates and latency tracked in Prometheus; alerts can be set on thresholds.",
        "metric": "error_rate",
    },
}

_ISO27001_CONTROLS = {
    "A.9.4": {
        "name": "System and Application Access Control",
        "description": "API key authentication enforced on every inference call; keys stored as SHA-256 hashes.",
        "metric": "auth_logs",
    },
    "A.12.4": {
        "name": "Logging and Monitoring",
        "description": "Structured JSON logs emitted to stdout; PostgreSQL audit trail retained.",
        "metric": "request_log_coverage",
    },
    "A.18.1": {
        "name": "Compliance with Legal and Contractual Requirements",
        "description": "No raw prompts stored; content hashed for privacy compliance.",
        "metric": "privacy_hashing",
    },
}

_COVERAGE_GAPS = [
    "No geographic/IP-level audit data collected (potential gap for ISO A.12.4 completeness).",
    "MFA is not enforced on API key provisioning (manual SOC2 CC6.1 gap).",
    "Rate-limit audit records do not capture the token delta that triggered the 429.",
    "Streaming responses counted with estimated token totals, not exact counts.",
]

_HEADER_COLOR = colors.HexColor("#1E3A5F")
_ALT_ROW = colors.HexColor("#F0F4F8")


def _build_table_style(header_row: bool = True) -> TableStyle:
    cmds = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _ALT_ROW]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header_row:
        cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER_COLOR),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    return TableStyle(cmds)


def generate_report(
    start_date: date,
    end_date: date,
    standards: list[str],
    logs: list[dict],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch * 0.75,
        leftMargin=inch * 0.75,
        topMargin=inch * 0.75,
        bottomMargin=inch * 0.75,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=_HEADER_COLOR, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=_HEADER_COLOR, spaceAfter=4)
    body = styles["BodyText"]
    story = []

    standards_label = " + ".join(s.upper() for s in standards)
    story.append(Paragraph("LLM Gateway — Compliance Audit Report", h1))
    story.append(Paragraph(f"Period: {start_date} to {end_date}  |  Standards: {standards_label}", body))
    story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", body))
    story.append(HRFlowable(width="100%", thickness=1, color=_HEADER_COLOR, spaceAfter=12))

    total = len(logs)
    successes = sum(1 for r in logs if r.get("success"))
    failures = total - successes
    error_rate = failures / total if total else 0.0
    total_prompt = sum(r.get("prompt_tokens") or 0 for r in logs)
    total_completion = sum(r.get("completion_tokens") or 0 for r in logs)
    total_cost = sum(r.get("estimated_cost_usd") or 0.0 for r in logs)
    avg_latency = (
        sum(r.get("latency_ms") or 0 for r in logs) / total if total else 0
    )

    story.append(Paragraph("1. Executive Summary", h2))
    summary_data = [
        ["Metric", "Value"],
        ["Total Requests", str(total)],
        ["Successful", str(successes)],
        ["Failed", str(failures)],
        ["Error Rate", f"{error_rate:.2%}"],
        ["Prompt Tokens", f"{total_prompt:,}"],
        ["Completion Tokens", f"{total_completion:,}"],
        ["Estimated Cost (USD)", f"${total_cost:.4f}"],
        ["Avg Latency (ms)", f"{avg_latency:.0f}"],
    ]
    t = Table(summary_data, colWidths=[3.5 * inch, 3.5 * inch])
    t.setStyle(_build_table_style())
    story.append(t)
    story.append(Spacer(1, 16))

    model_stats: dict[str, dict] = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0})
    for r in logs:
        m = r.get("model_used") or r.get("model_requested", "unknown")
        model_stats[m]["requests"] += 1
        model_stats[m]["prompt_tokens"] += r.get("prompt_tokens") or 0
        model_stats[m]["completion_tokens"] += r.get("completion_tokens") or 0
        model_stats[m]["cost"] += r.get("estimated_cost_usd") or 0.0

    story.append(Paragraph("2. Model Usage Breakdown", h2))
    model_data = [["Model", "Requests", "Prompt Tokens", "Completion Tokens", "Cost (USD)"]]
    for model, stats in sorted(model_stats.items()):
        model_data.append([
            model,
            str(stats["requests"]),
            f"{stats['prompt_tokens']:,}",
            f"{stats['completion_tokens']:,}",
            f"${stats['cost']:.4f}",
        ])
    t2 = Table(model_data, colWidths=[2.2 * inch, 1.0 * inch, 1.3 * inch, 1.5 * inch, 1.2 * inch])
    t2.setStyle(_build_table_style())
    story.append(t2)
    story.append(Spacer(1, 16))

    story.append(Paragraph("3. Compliance Control Mapping", h2))

    def render_controls(control_map: dict, standard_name: str) -> None:
        story.append(Paragraph(f"<b>{standard_name}</b>", body))
        story.append(Spacer(1, 6))
        ctrl_data = [["Control", "Name", "Status", "Evidence"]]
        for ctrl_id, ctrl in control_map.items():
            metric = ctrl["metric"]
            if metric == "error_rate":
                status = "PASS" if error_rate < 0.05 else "REVIEW"
            elif metric in ("auth_logs", "request_log_coverage", "privacy_hashing"):
                status = "PASS" if total > 0 else "N/A"
            else:
                status = "PASS"
            ctrl_data.append([ctrl_id, ctrl["name"], status, ctrl["description"]])
        ct = Table(ctrl_data, colWidths=[0.7 * inch, 1.6 * inch, 0.6 * inch, 4.3 * inch])
        ct.setStyle(_build_table_style())
        story.append(ct)
        story.append(Spacer(1, 12))

    if "soc2" in standards:
        render_controls(_SOC2_CONTROLS, "SOC 2 Type II")
    if "iso27001" in standards:
        render_controls(_ISO27001_CONTROLS, "ISO 27001:2022")

    story.append(Paragraph("4. Coverage Gaps", h2))
    for gap in _COVERAGE_GAPS:
        story.append(Paragraph(f"• {gap}", body))
    story.append(Spacer(1, 16))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Confidential — Internal Use Only", styles["Italic"]))

    doc.build(story)
    return buffer.getvalue()
