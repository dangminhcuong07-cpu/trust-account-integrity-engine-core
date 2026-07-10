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
