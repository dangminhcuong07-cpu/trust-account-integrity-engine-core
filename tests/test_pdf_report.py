"""
Tests for trust_domain/reports/pdf_report.py — Step 4.3

TDD RED: all tests written before implementation exists.
Spec interface: generate_pdf_report(report_dict, output_path, generated_at) -> Path
"""
import datetime
import re
from pathlib import Path

import pytest

FIRM = "Coastal Law Ltd"
PERIOD = "May 2026"
GENERATED_AT = datetime.datetime(2026, 6, 25, 10, 30, 0)

REPORT_DICT = {
    "report_period": "May 2026",
    "firm_name": "Coastal Law Ltd",
    "generated_at": "2026-06-25",
    "total_violations": 2,
    "critical_count": 1,
    "high_count": 1,
    "violations": [
        {
            "rank": 1,
            "rule_id": "R01_OVERDRAWN_CLIENT_LEDGER",
            "severity": "CRITICAL",
            "nzls_ref": "LCA (Trust Account) Regulations 2008, Reg 12(6)(a)",
            "label": "Overdrawn client ledger entry",
            "record_id": "L021",
            "evidence": "entry L021 (matter M016): balance -2500.00 NZD - client funds in deficit",
            "recommended_action": "ESCALATE",
        },
        {
            "rank": 2,
            "rule_id": "R05_UNRECONCILED_AGEING",
            "severity": "HIGH",
            "nzls_ref": "LCA (Trust Account) Regulations 2008, Reg 12(1)",
            "label": "Unreconciled ledger entry exceeds age threshold",
            "record_id": "L009",
            "evidence": "entry L009 open 89 days (threshold 30)",
            "recommended_action": "REVIEW",
        },
    ],
}

REPORT_DICT_ZERO = {
    "report_period": "May 2026",
    "firm_name": "Coastal Law Ltd",
    "generated_at": "2026-06-25",
    "total_violations": 0,
    "critical_count": 0,
    "high_count": 0,
    "violations": [],
}


class TestGeneratePdfReport:
    def test_creates_pdf_at_output_path(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "exception_report.pdf"
        generate_pdf_report(REPORT_DICT, out, GENERATED_AT)
        assert out.exists()

    def test_returns_output_path(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "exception_report.pdf"
        result = generate_pdf_report(REPORT_DICT, out, GENERATED_AT)
        assert result == out

    def test_pdf_has_valid_header(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "exception_report.pdf"
        generate_pdf_report(REPORT_DICT, out, GENERATED_AT)
        assert out.read_bytes()[:4] == b"%PDF"

    def test_pdf_contains_firm_name(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "exception_report.pdf"
        generate_pdf_report(REPORT_DICT, out, GENERATED_AT)
        # Firm name appears in uncompressed PDF metadata (Info dictionary)
        assert b"Coastal Law Ltd" in out.read_bytes()

    def test_same_inputs_produce_same_byte_length(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out1 = tmp_path / "run1.pdf"
        out2 = tmp_path / "run2.pdf"
        generate_pdf_report(REPORT_DICT, out1, GENERATED_AT)
        generate_pdf_report(REPORT_DICT, out2, GENERATED_AT)
        assert out1.stat().st_size == out2.stat().st_size

    def test_zero_violations_creates_pdf(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "exception_report.pdf"
        generate_pdf_report(REPORT_DICT_ZERO, out, GENERATED_AT)
        assert out.exists()
        assert out.read_bytes()[:4] == b"%PDF"

    def test_zero_violations_is_single_page(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "exception_report.pdf"
        generate_pdf_report(REPORT_DICT_ZERO, out, GENERATED_AT)
        # /Count N in the Pages dictionary gives total page count
        content = out.read_bytes()
        match = re.search(rb"/Count\s+(\d+)", content)
        assert match, "Could not find /Count in PDF"
        assert int(match.group(1)) == 1

    def test_creates_parent_dirs(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "nested" / "dir" / "exception_report.pdf"
        generate_pdf_report(REPORT_DICT, out, GENERATED_AT)
        assert out.exists()

    def test_pdf_is_nonempty(self, tmp_path):
        from trust_domain.reports.pdf_report import generate_pdf_report
        out = tmp_path / "exception_report.pdf"
        generate_pdf_report(REPORT_DICT, out, GENERATED_AT)
        assert out.stat().st_size > 1000


class TestFooterGeometry:
    """
    Regression guard for the footer-disclaimer/page-number overlap bug: the
    disclaimer line and "Page N of M" were drawn close enough together (and
    the disclaimer ran wide enough) that their rendered text visually
    overprinted on every page, confirmed by actual PDF rendering (PyMuPDF
    span/word extraction) during the fix.

    PyMuPDF is not a project dependency (see requirements.txt), so rather
    than add a render-and-parse dependency for a single test, this
    recomputes each string's bounding box analytically from the same inputs
    reportlab's Canvas uses to draw them: pdfmetrics.stringWidth() for the
    horizontal extent and pdfmetrics.getAscentDescent() for the vertical
    extent, anchored at the exact baseline coordinates _stamp_footer() uses
    (imported from pdf_report, not duplicated numbers). This is a
    conservative proxy — actual glyph rendering can be marginally taller
    than the nominal ascent/descent — but it pins the real coordinates and
    real string content so a future edit that shrinks the gap or widens the
    disclaimer text again will fail this test.
    """

    @staticmethod
    def _bbox(text: str, font_size: float, baseline_y: float, *, right_x: float | None = None):
        from reportlab.pdfbase import pdfmetrics
        from trust_domain.reports.pdf_report import _PAGE_WIDTH

        width = pdfmetrics.stringWidth(text, "Helvetica", font_size)
        ascent, descent = pdfmetrics.getAscentDescent("Helvetica", font_size)
        x0 = (right_x - width) if right_x is not None else (_PAGE_WIDTH / 2 - width / 2)
        return (x0, baseline_y + descent, x0 + width, baseline_y + ascent)

    @staticmethod
    def _overlaps(a: tuple, b: tuple) -> bool:
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    def test_disclaimer_bbox_does_not_overlap_page_number_bbox(self):
        from trust_domain.reports.pdf_report import (
            _DISCLAIMER_FONT_SIZE,
            _DISCLAIMER_LINE_1,
            _DISCLAIMER_LINE_2,
            _DISCLAIMER_Y1,
            _DISCLAIMER_Y2,
            _FOOTER_Y,
            _MARGIN,
            _PAGE_NUM_FONT_SIZE,
            _PAGE_WIDTH,
        )

        line_1 = self._bbox(_DISCLAIMER_LINE_1, _DISCLAIMER_FONT_SIZE, _DISCLAIMER_Y2)
        line_2 = self._bbox(_DISCLAIMER_LINE_2, _DISCLAIMER_FONT_SIZE, _DISCLAIMER_Y1)
        disclaimer_bbox = (
            min(line_1[0], line_2[0]), min(line_1[1], line_2[1]),
            max(line_1[2], line_2[2]), max(line_1[3], line_2[3]),
        )
        # Worst-case realistic page count (double digits on both sides).
        page_num_bbox = self._bbox(
            "Page 99 of 99", _PAGE_NUM_FONT_SIZE, _FOOTER_Y,
            right_x=_PAGE_WIDTH - _MARGIN,
        )

        assert not self._overlaps(disclaimer_bbox, page_num_bbox), (
            f"disclaimer bbox {disclaimer_bbox} overlaps "
            f"page-number bbox {page_num_bbox}"
        )

    def test_disclaimer_stays_within_page_margins(self):
        from trust_domain.reports.pdf_report import (
            _DISCLAIMER_FONT_SIZE,
            _DISCLAIMER_LINE_1,
            _DISCLAIMER_LINE_2,
            _DISCLAIMER_Y1,
            _DISCLAIMER_Y2,
            _MARGIN,
            _PAGE_WIDTH,
        )

        for text, y in ((_DISCLAIMER_LINE_1, _DISCLAIMER_Y2), (_DISCLAIMER_LINE_2, _DISCLAIMER_Y1)):
            x0, _, x1, _ = self._bbox(text, _DISCLAIMER_FONT_SIZE, y)
            assert x0 >= _MARGIN, f"{text!r} breaches left margin: x0={x0} < {_MARGIN}"
            assert x1 <= _PAGE_WIDTH - _MARGIN, f"{text!r} breaches right margin: x1={x1} > {_PAGE_WIDTH - _MARGIN}"
