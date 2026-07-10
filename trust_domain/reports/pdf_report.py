"""
PDF exception report generator for NZ trust account integrity reviews.

Produces a self-contained PDF version of the exception report that can be
handed to a client without source code.

PDF structure:
  - Cover block: firm name, period, generated date, total exceptions in large type
  - CRITICAL section: one violation per page (rule_id, nzls_ref, record_id,
    evidence, action required)
  - HIGH section: same structure
  - Summary table: CRITICAL / HIGH / Total counts
  - Footer on every page: CONFIDENTIAL — firm name — period
  - Page numbers on every page: Page N of M

Zero violations: a single "No exceptions found" page.

No datetime.now() or date.today() called here. The caller injects generated_at.

Usage:
    from trust_domain.reports.pdf_report import generate_pdf_report
    import datetime
    from pathlib import Path

    path = generate_pdf_report(
        report_dict=report_dict,
        output_path=Path("output/exception_report.pdf"),
        generated_at=datetime.datetime(2026, 6, 25, 10, 30, 0),
    )
"""

from __future__ import annotations

import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfgen_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN = 20 * mm
_FOOTER_Y = 10 * mm
_FRAME_BOTTOM = _FOOTER_Y + 8 * mm

_ACTION_TEXT = (
    "Investigate and resolve immediately. "
    "Provide written explanation to TAS within 2 business days."
)


def _make_footer_canvas(firm_name: str, period: str):
    """Return a Canvas subclass that stamps footer + page numbers on every page."""
    footer_line = (
        f"CONFIDENTIAL — Trust Account Exception Report "
        f"— {firm_name} — {period}"
    )

    class _FooterCanvas(pdfgen_canvas.Canvas):
        def __init__(self, filename, **kwargs):
            super().__init__(filename, **kwargs)
            self._page_states: list = []

        def showPage(self) -> None:
            self._page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._page_states)
            for page_num, state in enumerate(self._page_states, start=1):
                self.__dict__.update(state)
                self._stamp_footer(page_num, total)
                pdfgen_canvas.Canvas.showPage(self)
            pdfgen_canvas.Canvas.save(self)

        def _stamp_footer(self, page_num: int, total: int) -> None:
            self.saveState()
            self.setFont("Helvetica", 7)
            self.drawCentredString(_PAGE_WIDTH / 2, _FOOTER_Y, footer_line)
            self.setFont("Helvetica", 8)
            self.drawRightString(
                _PAGE_WIDTH - _MARGIN,
                _FOOTER_Y,
                f"Page {page_num} of {total}",
            )
            self.restoreState()

    return _FooterCanvas


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=20,
            spaceAfter=6,
            textColor=colors.HexColor("#1a1a2e"),
        ),
        "cover": ParagraphStyle(
            "CoverField",
            parent=base["Normal"],
            fontSize=12,
            spaceAfter=4,
        ),
        "critical_head": ParagraphStyle(
            "CriticalHead",
            parent=base["Heading1"],
            fontSize=14,
            textColor=colors.HexColor("#c0392b"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "high_head": ParagraphStyle(
            "HighHead",
            parent=base["Heading1"],
            fontSize=14,
            textColor=colors.HexColor("#d35400"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "violation_label": ParagraphStyle(
            "ViolationLabel",
            parent=base["Heading2"],
            fontSize=12,
            spaceAfter=4,
        ),
        "body": base["Normal"],
    }


def _violation_block(v: dict, st: dict) -> list:
    """Return Flowables for one violation (label + detail table)."""
    action = (
        f"ESCALATE — {_ACTION_TEXT}"
        if v.get("recommended_action") == "ESCALATE"
        else v.get("recommended_action", "REVIEW")
    )
    rows = [
        [Paragraph("<b>Rule ID</b>", st["body"]),     Paragraph(v["rule_id"], st["body"])],
        [Paragraph("<b>Regulation</b>", st["body"]),  Paragraph(v["nzls_ref"], st["body"])],
        [Paragraph("<b>Record</b>", st["body"]),      Paragraph(v["record_id"], st["body"])],
        [Paragraph("<b>Finding</b>", st["body"]),     Paragraph(v["evidence"], st["body"])],
        [Paragraph("<b>Action</b>", st["body"]),      Paragraph(action, st["body"])],
    ]
    tbl = Table(rows, colWidths=[38 * mm, 132 * mm])
    tbl.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("GRID",        (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND",  (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    return [
        Paragraph(f"{v['severity']} — {v['label']}", st["violation_label"]),
        Spacer(1, 3 * mm),
        tbl,
    ]


def generate_pdf_report(
    report_dict: dict,
    output_path: Path,
    generated_at: datetime.datetime,
) -> Path:
    """
    Generate a PDF exception report from a structured report dict.

    Parameters
    ----------
    report_dict    The dict returned by build_report_dict() / exception_report.json.
    output_path    Full path where the PDF will be written (parent dirs created).
    generated_at   Injected datetime — never sampled inside this function.

    Returns
    -------
    output_path — the Path that was written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    firm_name  = report_dict["firm_name"]
    period     = report_dict["report_period"]
    total      = report_dict["total_violations"]
    n_critical = report_dict["critical_count"]
    n_high     = report_dict["high_count"]
    violations = report_dict["violations"]
    date_str   = generated_at.strftime("%d %B %Y")

    st = _styles()
    footer_canvas = _make_footer_canvas(firm_name, period)

    frame = Frame(
        _MARGIN,
        _FRAME_BOTTOM,
        _PAGE_WIDTH - 2 * _MARGIN,
        _PAGE_HEIGHT - _MARGIN - _FRAME_BOTTOM,
        id="main",
    )
    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        title="Trust Account Exception Report",
        author=firm_name,
        subject=f"Trust Account Integrity Review — {period}",
        creator="Trust Account Integrity Engine",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    story: list = []

    # Cover block
    story.append(Paragraph("Trust Account Exception Report", st["title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Firm:</b> {firm_name}", st["cover"]))
    story.append(Paragraph(f"<b>Period:</b> {period}", st["cover"]))
    story.append(Paragraph(f"<b>Generated:</b> {date_str}", st["cover"]))
    story.append(Paragraph(
        f"<b>Total exceptions:</b> {total} ({n_critical} CRITICAL, {n_high} HIGH)",
        st["cover"],
    ))
    story.append(Spacer(1, 8 * mm))

    if total == 0:
        story.append(Paragraph("No exceptions found", st["critical_head"]))
        story.append(Paragraph(
            f"This trust account passed all integrity checks for {period}.",
            st["body"],
        ))
    else:
        critical_items = [v for v in violations if v["severity"] == "CRITICAL"]
        high_items     = [v for v in violations if v["severity"] == "HIGH"]

        if critical_items:
            story.append(Paragraph("CRITICAL Exceptions", st["critical_head"]))
            for i, v in enumerate(critical_items):
                if i > 0:
                    story.append(PageBreak())
                story.extend(_violation_block(v, st))

        if high_items:
            story.append(PageBreak())
            story.append(Paragraph("HIGH Exceptions", st["high_head"]))
            for i, v in enumerate(high_items):
                if i > 0:
                    story.append(PageBreak())
                story.extend(_violation_block(v, st))

        # Summary table
        story.append(PageBreak())
        story.append(Paragraph("Summary", st["critical_head"]))
        summary_rows = [
            [Paragraph("<b>Severity</b>", st["body"]), Paragraph("<b>Count</b>", st["body"])],
            [Paragraph("CRITICAL", st["body"]),         Paragraph(str(n_critical), st["body"])],
            [Paragraph("HIGH",     st["body"]),         Paragraph(str(n_high),     st["body"])],
            [Paragraph("<b>Total</b>", st["body"]),     Paragraph(f"<b>{total}</b>", st["body"])],
        ]
        tbl = Table(summary_rows, colWidths=[80 * mm, 40 * mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN",      (1, 0), (1, -1), "CENTER"),
            ("PADDING",    (0, 0), (-1, -1), 6),
        ]))
        story.append(tbl)

    doc.build(story, canvasmaker=footer_canvas)
    return output_path
