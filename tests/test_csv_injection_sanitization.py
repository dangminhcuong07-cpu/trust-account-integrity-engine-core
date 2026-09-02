"""
Tests for CSV/formula-injection defence (CWE-1236) — see
trust_domain/reports/sanitize.py and PROJECT_SNAPSHOT.md's security section.

Scope: a user-controlled ledger field (reference) that becomes the entire
content of a spreadsheet-openable cell (funds_trail.md's payments table)
must not be interpretable as a formula by Excel/Sheets. A value starting
with =, +, -, or @ must be neutralised — prefixed with a leading apostrophe
— when it is rendered into that table cell, while the underlying JSON
(funds_trail.json) keeps the true, unmutated value for audit purposes.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from integrity_engine.core.types import Record
from trust_domain.reports.funds_trail import build_funds_trail, write_funds_trail
from trust_domain.reports.sanitize import sanitize_for_spreadsheet

_REF_DATE = datetime.date(2026, 6, 25)

_MALICIOUS_VALUES = [
    "=1+1",
    "=CMD|'/C calc'!A1",
    "+1+1",
    "-1+1",
    "@SUM(1+1)",
]


def _ledger_fee(entry_id: str, matter_ref: str, payment: float, reference: str) -> Record:
    return Record(
        record_id=entry_id,
        data={
            "entry_id": entry_id,
            "matter_ref": matter_ref,
            "entry_date": "2026-06-01",
            "description": "Fee - legal services",
            "receipt_nzd": 0.0,
            "payment_nzd": payment,
            "reference": reference,
        },
    )


def _ledger_receipt(entry_id: str, matter_ref: str) -> Record:
    return Record(
        record_id=entry_id,
        data={
            "entry_id": entry_id,
            "matter_ref": matter_ref,
            "entry_date": "2026-06-01",
            "description": "Receipt - deposit",
            "receipt_nzd": 1000.0,
            "payment_nzd": 0.0,
            "reference": "",
        },
    )


def _bank(statement_id: str, credit: float, matched: str = "") -> Record:
    return Record(
        record_id=statement_id,
        data={
            "statement_id": statement_id,
            "transaction_date": "2026-06-24",
            "description": f"Credit - test {statement_id}",
            "credit_nzd": credit,
            "debit_nzd": 0.0,
            "matched_ledger_entry": matched,
        },
    )


def _alloc(bank_line_id: str, ledger_entry_id: str, amount: float) -> Record:
    return Record(
        record_id=bank_line_id,
        data={
            "bank_line_id": bank_line_id,
            "ledger_entry_id": ledger_entry_id,
            "amount_nzd": amount,
        },
    )


# ── unit tests for the sanitizer itself ─────────────────────────────────────────

class TestSanitizeForSpreadsheet:
    @pytest.mark.parametrize("value", _MALICIOUS_VALUES)
    def test_trigger_characters_get_apostrophe_prefixed(self, value):
        result = sanitize_for_spreadsheet(value)
        assert result == "'" + value
        assert not result.startswith(("=", "+", "-", "@"))

    def test_ordinary_value_passes_through_unchanged(self):
        assert sanitize_for_spreadsheet("INV-00237") == "INV-00237"
        assert sanitize_for_spreadsheet("Standard fee reference") == "Standard fee reference"

    def test_empty_and_none_pass_through(self):
        assert sanitize_for_spreadsheet("") == ""
        assert sanitize_for_spreadsheet(None) is None

    def test_leading_whitespace_before_trigger_char_is_still_neutralised(self):
        # Defensive: some parsers trim before checking; prefixing the whole
        # value with an apostrophe neutralises it either way.
        result = sanitize_for_spreadsheet("  =1+1")
        assert result.startswith("'")

    def test_original_value_is_fully_recoverable_after_the_prefix(self):
        # The mitigation must not be destructive — nothing about the
        # original value (including its leading character) is lost, only
        # its formula interpretation is neutralised.
        value = "=1+1"
        result = sanitize_for_spreadsheet(value)
        assert result[1:] == value


# ── integration: the actual funds_trail.md output ───────────────────────────────

class TestFundsTrailMarkdownNeutralisesInjection:
    @pytest.mark.parametrize("malicious", _MALICIOUS_VALUES)
    def test_malicious_reference_is_neutralised_in_rendered_markdown(self, tmp_path, malicious):
        ledger = [_ledger_fee("L900", "M900", 500.0, malicious)]
        write_funds_trail(
            bank_statement=[],
            allocations=[],
            client_ledger=ledger,
            invoice_register=None,
            firm_name="Test Firm",
            report_period="June 2026",
            generated_at=_REF_DATE,
            output_path=tmp_path / "funds_trail.md",
        )
        md = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")

        # The malicious value must appear ONLY in its neutralised
        # (apostrophe-prefixed) form — never as a table cell whose entire
        # content is the raw trigger character sequence.
        assert f"| {malicious} |" not in md
        assert f"'{malicious}" in md

    def test_ordinary_reference_is_unaffected(self, tmp_path):
        ledger = [_ledger_fee("L901", "M901", 500.0, "some free-text reference")]
        write_funds_trail(
            bank_statement=[], allocations=[], client_ledger=ledger,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        md = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "some free-text reference" in md
        assert "'some free-text reference" not in md

    def test_valid_invoice_reference_is_never_prefixed(self, tmp_path):
        # References that match ^INV-\d{5}$ can never start with a trigger
        # character (the format is fixed), so this must stay untouched —
        # a regression guard against over-sanitizing.
        ledger = [_ledger_fee("L902", "M902", 500.0, "INV-00237")]
        write_funds_trail(
            bank_statement=[], allocations=[], client_ledger=ledger,
            invoice_register=[Record(
                record_id="INV-00237",
                data={"invoice_id": "INV-00237", "matter_ref": "M902",
                      "amount_nzd": 500.0, "issue_date": "2026-06-01"},
            )],
            firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        md = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "| INV-00237 " in md
        assert "'INV-00237" not in md


class TestJsonAuditTrailKeepsRawValue:
    """The sanitizer is applied only at the spreadsheet-cell rendering
    boundary, never to the underlying data — funds_trail.json must keep
    the true, unmutated value a real auditor would need to see."""

    def test_funds_trail_json_is_not_mutated(self, tmp_path):
        malicious = "=1+1"
        ledger = [_ledger_fee("L903", "M903", 500.0, malicious)]
        write_funds_trail(
            bank_statement=[], allocations=[], client_ledger=ledger,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        trail = json.loads((tmp_path / "funds_trail.json").read_text(encoding="utf-8"))
        payment = trail["matters"]["M903"]["payments"][0]
        assert payment["reference"] == malicious  # raw, unprefixed

    def test_build_funds_trail_dict_is_not_mutated(self):
        malicious = "@SUM(1+1)"
        ledger = [_ledger_fee("L904", "M904", 500.0, malicious)]
        trail = build_funds_trail(
            bank_statement=[], allocations=[], client_ledger=ledger,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE,
        )
        assert trail["matters"]["M904"]["payments"][0]["reference"] == malicious


# ── record identifiers: known issue #6 (same shape as `reference`, not ──────────
# ── covered by the original fix) ─────────────────────────────────────────────────

class TestFundsTrailRecordIdentifiersNeutralised:
    """bank_line_id, ledger_entry_id (aka matched_ledger_entry), and entry_id
    are also raw, user-controlled CSV-sourced identifiers rendered directly
    into funds_trail.md table cells — PROJECT_SNAPSHOT.md known issue #6,
    left out of the original reference/description/notes-scoped fix."""

    @pytest.mark.parametrize("malicious", _MALICIOUS_VALUES)
    def test_malicious_bank_line_id_and_ledger_entry_id_neutralised_in_matter_receipts(
        self, tmp_path, malicious
    ):
        # Allocation path: attributes a receipt to a real matter section.
        bank_line_id = malicious
        ledger_entry_id = "+2+2"
        bank = _bank(bank_line_id, 1000.0)
        alloc = _alloc(bank_line_id, ledger_entry_id, 1000.0)
        ledger = [_ledger_receipt(ledger_entry_id, "M950")]
        write_funds_trail(
            bank_statement=[bank], allocations=[alloc], client_ledger=ledger,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        md = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert f"| {bank_line_id} " not in md
        assert f"'{bank_line_id}" in md
        assert f"| {ledger_entry_id} " not in md
        assert f"'{ledger_entry_id}" in md

    @pytest.mark.parametrize("malicious", _MALICIOUS_VALUES)
    def test_malicious_bank_line_id_and_matched_entry_neutralised_in_unattributed(
        self, tmp_path, malicious
    ):
        # No allocations, no client_ledger match -> lands in the
        # "Unattributed Credits" table instead of a per-matter section.
        bank = _bank(malicious, 750.0, matched=malicious)
        write_funds_trail(
            bank_statement=[bank], allocations=[], client_ledger=None,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        md = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert f"| {malicious} " not in md
        assert f"'{malicious}" in md

    @pytest.mark.parametrize("malicious", _MALICIOUS_VALUES)
    def test_malicious_entry_id_neutralised_in_payment_row(self, tmp_path, malicious):
        ledger = [_ledger_fee(malicious, "M951", 500.0, "not-an-invoice-ref")]
        write_funds_trail(
            bank_statement=[], allocations=[], client_ledger=ledger,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        md = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert f"| {malicious} " not in md
        assert f"'{malicious}" in md

    def test_ordinary_identifiers_pass_through_unprefixed(self, tmp_path):
        bank = _bank("B001", 1000.0)
        alloc = _alloc("B001", "L001", 1000.0)
        ledger = [_ledger_receipt("L001", "M001"),
                  _ledger_fee("L002", "M001", 200.0, "not-an-invoice-ref")]
        write_funds_trail(
            bank_statement=[bank], allocations=[alloc], client_ledger=ledger,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        md = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "| B001 " in md and "'B001" not in md
        assert "| L001 " in md and "'L001" not in md
        assert "| L002 " in md and "'L002" not in md

    def test_json_audit_trail_keeps_raw_identifiers_unmutated(self, tmp_path):
        malicious = "=1+1"
        bank = _bank(malicious, 1000.0)
        alloc = _alloc(malicious, malicious, 1000.0)
        ledger = [_ledger_receipt(malicious, "M952")]
        write_funds_trail(
            bank_statement=[bank], allocations=[alloc], client_ledger=ledger,
            invoice_register=None, firm_name="Test Firm", report_period="June 2026",
            generated_at=_REF_DATE, output_path=tmp_path / "funds_trail.md",
        )
        trail = json.loads((tmp_path / "funds_trail.json").read_text(encoding="utf-8"))
        receipt = trail["matters"]["M952"]["receipts"][0]
        assert receipt["bank_line_id"] == malicious
        assert receipt["ledger_entry_id"] == malicious
