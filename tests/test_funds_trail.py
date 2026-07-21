"""
Tests for trust_domain/reports/funds_trail.py.

Covers build_funds_trail() (unit + integration) and write_funds_trail()
(file output). The new per-matter structure with two legs is verified:
  - receipt leg: bank credits attributed to matters via allocations /
    matched_ledger_entry, with bank-line allocation status
  - payment leg: client_ledger fee/disbursement entries with invoice
    status (R08 / R09 / R10 / PROVEN / NO_INVOICE_REF / UNCHECKED)
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from integrity_engine.core.types import Record
from trust_domain.reports.funds_trail import build_funds_trail, write_funds_trail

_SAMPLE_DIR = Path("trust_domain/synthetic/sample")
_REF_DATE = datetime.date(2026, 6, 25)


# ── fixtures / helpers ────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _generate_sample():
    from trust_domain.synthetic.generator import generate
    generate(_SAMPLE_DIR)


def _bank(
    statement_id: str,
    credit: float,
    matched: str = "",
    date: str = "2026-06-24",
) -> Record:
    return Record(
        record_id=statement_id,
        data={
            "statement_id": statement_id,
            "transaction_date": date,
            "description": f"Credit - test {statement_id}",
            "credit_nzd": credit,
            "debit_nzd": 0.0,
            "matched_ledger_entry": matched,
        },
    )


def _debit(statement_id: str, amount: float) -> Record:
    return Record(
        record_id=statement_id,
        data={
            "statement_id": statement_id,
            "transaction_date": "2026-06-24",
            "description": f"Debit - test {statement_id}",
            "credit_nzd": 0.0,
            "debit_nzd": amount,
            "matched_ledger_entry": "L001",
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


def _ledger_fee(
    entry_id: str,
    matter_ref: str,
    payment: float,
    reference: str,
    entry_date: str = "2026-06-01",
    description: str = "Fee - legal services",
) -> Record:
    return Record(
        record_id=entry_id,
        data={
            "entry_id": entry_id,
            "matter_ref": matter_ref,
            "entry_date": entry_date,
            "description": description,
            "receipt_nzd": 0.0,
            "payment_nzd": payment,
            "reference": reference,
        },
    )


def _invoice(
    invoice_id: str,
    matter_ref: str,
    amount: float,
    issue_date: str,
) -> Record:
    return Record(
        record_id=invoice_id,
        data={
            "invoice_id": invoice_id,
            "matter_ref": matter_ref,
            "amount_nzd": amount,
            "issue_date": issue_date,
        },
    )


def _load(name: str) -> list[Record]:
    from data.load_sample import load_file
    return load_file(name, _SAMPLE_DIR)


# ── top-level structure ───────────────────────────────────────────────────────

class TestTopLevelStructure:
    def test_returns_expected_keys(self):
        trail = build_funds_trail([], [])
        for key in (
            "firm_name", "report_period", "generated_at",
            "receipt_summary", "payment_summary",
            "matters", "unattributed_receipts",
        ):
            assert key in trail, f"Missing top-level key {key!r}"

    def test_receipt_summary_keys(self):
        trail = build_funds_trail([], [])
        for key in ("total", "proven", "untraced", "mismatch"):
            assert key in trail["receipt_summary"]

    def test_payment_summary_keys(self):
        trail = build_funds_trail([], [])
        for key in ("total", "proven", "exception"):
            assert key in trail["payment_summary"]

    def test_empty_input_produces_zero_counts(self):
        trail = build_funds_trail([], [])
        assert trail["receipt_summary"]["total"] == 0
        assert trail["payment_summary"]["total"] == 0
        assert trail["matters"] == {}
        assert trail["unattributed_receipts"] == []

    def test_generated_at_isoformat(self):
        trail = build_funds_trail([], [], generated_at=_REF_DATE)
        assert trail["generated_at"] == "2026-06-25"

    def test_generated_at_none_is_empty_string(self):
        trail = build_funds_trail([], [], generated_at=None)
        assert trail["generated_at"] == ""


# ── receipt leg — debit exclusion ─────────────────────────────────────────────

class TestDebitExclusion:
    def test_debit_only_line_not_counted(self):
        trail = build_funds_trail([_debit("BD01", 500.0)], [])
        assert trail["receipt_summary"]["total"] == 0
        assert trail["unattributed_receipts"] == []

    def test_debit_does_not_appear_in_matters(self):
        ledger = [_ledger_receipt("L001", "M001")]
        trail = build_funds_trail([_debit("BD01", 500.0)], [], client_ledger=ledger)
        assert "M001" not in trail["matters"]


# ── receipt leg — attribution to matters ─────────────────────────────────────

class TestReceiptAttribution:
    def test_one_to_one_match_attributed_to_matter(self):
        bank = [_bank("BC01", 5000.0, matched="L001")]
        ledger = [_ledger_receipt("L001", "M001")]
        trail = build_funds_trail(bank, [], client_ledger=ledger)
        assert "M001" in trail["matters"]
        receipts = trail["matters"]["M001"]["receipts"]
        assert len(receipts) == 1
        assert receipts[0]["bank_line_id"] == "BC01"
        assert receipts[0]["bank_line_status"] == "PROVEN"
        assert receipts[0]["amount_nzd"] == 5000.0

    def test_untraced_credit_goes_to_unattributed(self):
        bank = [_bank("BC01", 15000.0, matched="")]
        trail = build_funds_trail(bank, [])
        assert trail["unattributed_receipts"][0]["bank_line_status"] == "UNTRACED"
        assert trail["matters"] == {}

    def test_sentinel_matched_entry_goes_to_unattributed(self):
        bank = [_bank("BC01", 250.0, matched="BANK-INTEREST")]
        trail = build_funds_trail(bank, [])
        assert len(trail["unattributed_receipts"]) == 1
        row = trail["unattributed_receipts"][0]
        assert row["bank_line_status"] == "PROVEN"
        assert row["ledger_entry_id"] == "BANK-INTEREST"

    def test_allocation_distributes_to_multiple_matters(self):
        bank = [_bank("BC01", 12000.0)]
        allocs = [
            _alloc("BC01", "L049", 4000.0),
            _alloc("BC01", "L050", 5000.0),
            _alloc("BC01", "L051", 3000.0),
        ]
        ledger = [
            _ledger_receipt("L049", "M003"),
            _ledger_receipt("L050", "M008"),
            _ledger_receipt("L051", "M012"),
        ]
        trail = build_funds_trail(bank, allocs, client_ledger=ledger)
        assert "M003" in trail["matters"]
        assert "M008" in trail["matters"]
        assert "M012" in trail["matters"]
        assert trail["matters"]["M003"]["receipts"][0]["amount_nzd"] == 4000.0
        assert trail["matters"]["M008"]["receipts"][0]["amount_nzd"] == 5000.0
        assert trail["matters"]["M012"]["receipts"][0]["amount_nzd"] == 3000.0

    def test_allocation_amount_vs_bank_line_credit_fields(self):
        bank = [_bank("BC01", 12000.0)]
        allocs = [_alloc("BC01", "L049", 4000.0), _alloc("BC01", "L050", 8000.0)]
        ledger = [_ledger_receipt("L049", "M001"), _ledger_receipt("L050", "M002")]
        trail = build_funds_trail(bank, allocs, client_ledger=ledger)
        row = trail["matters"]["M001"]["receipts"][0]
        assert row["amount_nzd"] == 4000.0
        assert row["bank_line_credit_nzd"] == 12000.0

    def test_allocation_without_client_ledger_goes_to_unattributed(self):
        bank = [_bank("BC01", 5000.0)]
        allocs = [_alloc("BC01", "L001", 5000.0)]
        trail = build_funds_trail(bank, allocs, client_ledger=None)
        assert len(trail["unattributed_receipts"]) == 1

    def test_receipt_summary_proven_count(self):
        bank = [
            _bank("BC01", 1000.0, matched="L001"),
            _bank("BC02", 2000.0, matched=""),
        ]
        ledger = [_ledger_receipt("L001", "M001")]
        trail = build_funds_trail(bank, [], client_ledger=ledger)
        assert trail["receipt_summary"]["proven"] == 1
        assert trail["receipt_summary"]["untraced"] == 1

    def test_receipt_summary_total_excludes_debits(self):
        bank = [_bank("BC01", 1000.0, matched="L001"), _debit("BD01", 500.0)]
        trail = build_funds_trail(bank, [])
        assert trail["receipt_summary"]["total"] == 1


# ── receipt leg — bank-line status ───────────────────────────────────────────

class TestReceiptBankLineStatus:
    def test_fully_allocated_is_proven(self):
        bank = [_bank("BC01", 12000.0)]
        allocs = [_alloc("BC01", "L001", 12000.0)]
        ledger = [_ledger_receipt("L001", "M001")]
        trail = build_funds_trail(bank, allocs, client_ledger=ledger)
        assert trail["matters"]["M001"]["receipts"][0]["bank_line_status"] == "PROVEN"

    def test_under_allocated_status(self):
        bank = [_bank("BC01", 9000.0)]
        allocs = [_alloc("BC01", "L001", 7500.0)]
        ledger = [_ledger_receipt("L001", "M001")]
        trail = build_funds_trail(bank, allocs, client_ledger=ledger)
        assert trail["matters"]["M001"]["receipts"][0]["bank_line_status"] == "UNDER_ALLOCATED"
        assert trail["receipt_summary"]["mismatch"] == 1

    def test_over_allocated_status(self):
        bank = [_bank("BC01", 5000.0)]
        allocs = [_alloc("BC01", "L001", 5500.0)]
        ledger = [_ledger_receipt("L001", "M001")]
        trail = build_funds_trail(bank, allocs, client_ledger=ledger)
        assert trail["matters"]["M001"]["receipts"][0]["bank_line_status"] == "OVER_ALLOCATED"

    def test_invalid_ledger_ref_status(self):
        bank = [_bank("BC01", 5000.0)]
        allocs = [_alloc("BC01", "L999", 5000.0)]
        ledger = [_ledger_receipt("L001", "M001")]
        trail = build_funds_trail(bank, allocs, client_ledger=ledger)
        # L999 not in ledger_ids → INVALID_LEDGER_REF; no matter_ref → unattributed
        assert trail["unattributed_receipts"][0]["bank_line_status"] == "INVALID_LEDGER_REF"


# ── payment leg — invoice classification ─────────────────────────────────────

class TestPaymentClassification:
    def test_no_invoice_ref_status(self):
        ledger = [_ledger_fee("L037", "M012", 200.0, reference="")]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=[])
        assert trail["matters"]["M012"]["payments"][0]["status"] == "NO_INVOICE_REF"
        assert trail["matters"]["M012"]["payments"][0]["rule_id"] is None

    def test_r08_missing_invoice(self):
        ledger = [_ledger_fee("L039", "M004", 350.0, "INV-99999")]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=[])
        p = trail["matters"]["M004"]["payments"][0]
        assert p["status"] == "EXCEPTION"
        assert p["rule_id"] == "R08_FEE_INVOICE_MISSING"
        assert p["invoice_id"] == "INV-99999"

    def test_r08_matter_mismatch(self):
        ledger = [_ledger_fee("LX01", "M001", 500.0, "INV-00001")]
        invoices = [_invoice("INV-00001", "M002", 500.0, "2026-05-01")]  # wrong matter
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=invoices)
        p = trail["matters"]["M001"]["payments"][0]
        assert p["status"] == "EXCEPTION"
        assert p["rule_id"] == "R08_FEE_INVOICE_MISSING"

    def test_r09_payment_exceeds_invoice(self):
        ledger = [_ledger_fee("L040", "M018", 5000.0, "INV-00236")]
        invoices = [_invoice("INV-00236", "M018", 3000.0, "2026-05-20")]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=invoices)
        p = trail["matters"]["M018"]["payments"][0]
        assert p["status"] == "EXCEPTION"
        assert p["rule_id"] == "R09_FEE_EXCEEDS_INVOICE"
        assert p["invoice_amount_nzd"] == 3000.0

    def test_r10_invoice_postdates_payment(self):
        ledger = [_ledger_fee("L041", "M015", 500.0, "INV-00237", entry_date="2026-06-01")]
        invoices = [_invoice("INV-00237", "M015", 1000.0, "2026-06-15")]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=invoices)
        p = trail["matters"]["M015"]["payments"][0]
        assert p["status"] == "EXCEPTION"
        assert p["rule_id"] == "R10_INVOICE_POSTDATES_PAYMENT"
        assert p["invoice_issue_date"] == "2026-06-15"

    def test_proven_payment(self):
        ledger = [_ledger_fee("L038", "M013", 500.0, "INV-00234", entry_date="2026-05-28")]
        invoices = [_invoice("INV-00234", "M013", 500.0, "2026-05-20")]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=invoices)
        p = trail["matters"]["M013"]["payments"][0]
        assert p["status"] == "PROVEN"
        assert p["rule_id"] is None

    def test_unchecked_when_no_invoice_register(self):
        ledger = [_ledger_fee("LX01", "M001", 500.0, "INV-00001")]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=None)
        p = trail["matters"]["M001"]["payments"][0]
        assert p["status"] == "UNCHECKED"

    def test_non_fee_entry_excluded_from_payments(self):
        ledger = [
            _ledger_fee("LX01", "M001", 500.0, "INV-00001"),
            Record(
                record_id="LY01",
                data={
                    "entry_id": "LY01",
                    "matter_ref": "M001",
                    "entry_date": "2026-06-01",
                    "description": "Payment - vendor proceeds",
                    "payment_nzd": 50000.0,
                    "receipt_nzd": 0.0,
                    "reference": "",
                },
            ),
        ]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=[])
        payments = trail["matters"]["M001"]["payments"]
        assert len(payments) == 1
        assert payments[0]["entry_id"] == "LX01"

    def test_zero_payment_excluded(self):
        ledger = [
            _ledger_fee("LX01", "M001", 0.0, "INV-00001"),
        ]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=[])
        assert trail["payment_summary"]["total"] == 0

    def test_payment_summary_proven_and_exception_counts(self):
        ledger = [
            _ledger_fee("L038", "M013", 500.0, "INV-00234", entry_date="2026-05-28"),
            _ledger_fee("L039", "M004", 350.0, "INV-99999"),
            _ledger_fee("L040", "M018", 5000.0, "INV-00236"),
        ]
        invoices = [
            _invoice("INV-00234", "M013", 500.0, "2026-05-20"),
            _invoice("INV-00236", "M018", 3000.0, "2026-05-20"),
            # INV-99999 absent
        ]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=invoices)
        assert trail["payment_summary"]["total"] == 3
        assert trail["payment_summary"]["proven"] == 1
        assert trail["payment_summary"]["exception"] == 2

    def test_payment_row_has_expected_keys(self):
        ledger = [_ledger_fee("LX01", "M001", 500.0, "INV-00001")]
        trail = build_funds_trail([], [], client_ledger=ledger, invoice_register=[])
        p = trail["matters"]["M001"]["payments"][0]
        for key in (
            "entry_id", "entry_date", "description", "payment_nzd",
            "reference", "invoice_id", "invoice_amount_nzd", "invoice_issue_date",
            "status", "rule_id", "notes",
        ):
            assert key in p, f"Payment row missing key {key!r}"


# ── integration tests against synthetic sample data ───────────────────────────

class TestFundsTrailSyntheticData:
    def _trail(self):
        bank = _load("trust_bank_statement")
        allocs = _load("allocations")
        ledger = _load("client_ledger")
        invoices = _load("invoice_register")
        return build_funds_trail(
            bank, allocs,
            client_ledger=ledger,
            invoice_register=invoices,
            firm_name="Coastal Law Ltd",
            report_period="Jun 2026",
            generated_at=_REF_DATE,
        )

    def test_l039_exception_r08_in_m004(self):
        trail = self._trail()
        payments = trail["matters"]["M004"]["payments"]
        row = next((p for p in payments if p["entry_id"] == "L039"), None)
        assert row is not None, "L039 not found in M004 payments"
        assert row["status"] == "EXCEPTION", f"Expected EXCEPTION, got {row['status']}"
        assert row["rule_id"] == "R08_FEE_INVOICE_MISSING"
        assert row["invoice_id"] == "INV-99999"

    def test_l040_exception_r09_in_m018(self):
        trail = self._trail()
        payments = trail["matters"]["M018"]["payments"]
        row = next((p for p in payments if p["entry_id"] == "L040"), None)
        assert row is not None, "L040 not found in M018 payments"
        assert row["status"] == "EXCEPTION"
        assert row["rule_id"] == "R09_FEE_EXCEEDS_INVOICE"
        assert row["invoice_amount_nzd"] == 3000.0
        assert row["payment_nzd"] == 5000.0

    def test_l041_exception_r10_in_m015(self):
        trail = self._trail()
        payments = trail["matters"]["M015"]["payments"]
        row = next((p for p in payments if p["entry_id"] == "L041"), None)
        assert row is not None, "L041 not found in M015 payments"
        assert row["status"] == "EXCEPTION"
        assert row["rule_id"] == "R10_INVOICE_POSTDATES_PAYMENT"
        assert row["invoice_issue_date"] == "2026-06-15"

    def test_l038_proven_payment_in_m013(self):
        trail = self._trail()
        payments = trail["matters"]["M013"]["payments"]
        row = next((p for p in payments if p["entry_id"] == "L038"), None)
        assert row is not None, "L038 not found in M013 payments"
        assert row["status"] == "PROVEN"

    def test_l037_no_invoice_ref_in_m012(self):
        trail = self._trail()
        payments = trail["matters"]["M012"]["payments"]
        row = next((p for p in payments if p["entry_id"] == "L037"), None)
        assert row is not None, "L037 not found in M012 payments"
        assert row["status"] == "NO_INVOICE_REF"

    def test_b049_proven_portions_in_m003_m008_m012(self):
        trail = self._trail()
        for matter_ref, expected_amount in (("M003", 4000.0), ("M008", 5000.0), ("M012", 3000.0)):
            receipts = trail["matters"][matter_ref]["receipts"]
            row = next(
                (r for r in receipts if r["bank_line_id"] == "B049"), None
            )
            assert row is not None, f"B049 portion not found in matter {matter_ref}"
            assert row["bank_line_status"] == "PROVEN", (
                f"{matter_ref} B049 receipt should be PROVEN"
            )
            assert row["amount_nzd"] == expected_amount
            assert row["bank_line_credit_nzd"] == 12000.0

    def test_b046_over_allocated_portions_attributed(self):
        trail = self._trail()
        # B046 (UNDER_ALLOCATED) portions go to M004/M005/M007
        for matter_ref in ("M004", "M005", "M007"):
            receipts = trail["matters"][matter_ref]["receipts"]
            row = next((r for r in receipts if r["bank_line_id"] == "B046"), None)
            assert row is not None, f"B046 portion missing from {matter_ref}"
            assert row["bank_line_status"] == "UNDER_ALLOCATED"

    def test_b047_over_allocated_portions_attributed(self):
        trail = self._trail()
        for matter_ref in ("M015", "M018"):
            receipts = trail["matters"][matter_ref]["receipts"]
            row = next((r for r in receipts if r["bank_line_id"] == "B047"), None)
            assert row is not None, f"B047 portion missing from {matter_ref}"
            assert row["bank_line_status"] == "OVER_ALLOCATED"

    def test_b031_and_b048_are_unattributed(self):
        trail = self._trail()
        unattr_ids = {r["bank_line_id"] for r in trail["unattributed_receipts"]}
        assert "B031" in unattr_ids, "B031 should be in unattributed_receipts"
        assert "B048" in unattr_ids, "B048 should be in unattributed_receipts"

    def test_b031_and_b048_are_untraced(self):
        trail = self._trail()
        for bid in ("B031", "B048"):
            row = next(r for r in trail["unattributed_receipts"] if r["bank_line_id"] == bid)
            assert row["bank_line_status"] == "UNTRACED", (
                f"{bid} should be UNTRACED in unattributed_receipts"
            )

    def test_m018_receipt_from_b032(self):
        trail = self._trail()
        receipts = trail["matters"]["M018"]["receipts"]
        row = next((r for r in receipts if r["bank_line_id"] == "B032"), None)
        assert row is not None, "B032 not found in M018 receipts"
        assert row["bank_line_status"] == "PROVEN"
        assert row["amount_nzd"] == 40000.0

    def test_payment_summary_totals(self):
        trail = self._trail()
        ps = trail["payment_summary"]
        assert ps["total"] == 5, f"Expected 5 fee/disbursement entries, got {ps['total']}"
        assert ps["proven"] == 1, f"Expected 1 proven payment, got {ps['proven']}"
        assert ps["exception"] == 3, f"Expected 3 exception payments, got {ps['exception']}"

    def test_receipt_summary_totals(self):
        trail = self._trail()
        rs = trail["receipt_summary"]
        assert rs["proven"] + rs["untraced"] + rs["mismatch"] == rs["total"]


# ── write_funds_trail — file output ──────────────────────────────────────────

class TestWriteFundsTrail:
    def test_creates_md_and_json(self, tmp_path):
        write_funds_trail(
            bank_statement=[_bank("BX01", 1000.0, matched="L001")],
            allocations=[],
            client_ledger=[_ledger_receipt("L001", "M001")],
            output_path=tmp_path / "funds_trail.md",
        )
        assert (tmp_path / "funds_trail.md").exists()
        assert (tmp_path / "funds_trail.json").exists()

    def test_json_matches_returned_dict(self, tmp_path):
        trail = write_funds_trail(
            bank_statement=[],
            allocations=[],
            firm_name="Test Firm",
            output_path=tmp_path / "funds_trail.md",
        )
        written = json.loads((tmp_path / "funds_trail.json").read_text(encoding="utf-8"))
        assert written == trail

    def test_markdown_contains_firm_name(self, tmp_path):
        write_funds_trail(
            bank_statement=[],
            allocations=[],
            firm_name="Test Firm Ltd",
            output_path=tmp_path / "funds_trail.md",
        )
        content = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "Test Firm Ltd" in content

    def test_markdown_renders_matter_section(self, tmp_path):
        write_funds_trail(
            bank_statement=[_bank("BX01", 1000.0, matched="L001")],
            allocations=[],
            client_ledger=[_ledger_receipt("L001", "M001")],
            output_path=tmp_path / "funds_trail.md",
        )
        content = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "## Matter M001" in content

    def test_markdown_renders_payment_table_for_matter(self, tmp_path):
        write_funds_trail(
            bank_statement=[],
            allocations=[],
            client_ledger=[_ledger_fee("LX01", "M001", 500.0, "INV-00001")],
            invoice_register=[],
            output_path=tmp_path / "funds_trail.md",
        )
        content = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "Fee / Disbursement Payments" in content
        assert "LX01" in content

    def test_markdown_shows_exception_rule_id(self, tmp_path):
        write_funds_trail(
            bank_statement=[],
            allocations=[],
            client_ledger=[_ledger_fee("L039", "M004", 350.0, "INV-99999")],
            invoice_register=[],
            output_path=tmp_path / "funds_trail.md",
        )
        content = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "R08_FEE_INVOICE_MISSING" in content
        assert "EXCEPTION" in content

    def test_synthetic_markdown_contains_r09_and_r10(self, tmp_path):
        bank = _load("trust_bank_statement")
        allocs = _load("allocations")
        ledger = _load("client_ledger")
        invoices = _load("invoice_register")
        write_funds_trail(
            bank_statement=bank,
            allocations=allocs,
            client_ledger=ledger,
            invoice_register=invoices,
            firm_name="Coastal Law Ltd",
            report_period="Jun 2026",
            generated_at=_REF_DATE,
            output_path=tmp_path / "funds_trail.md",
        )
        content = (tmp_path / "funds_trail.md").read_text(encoding="utf-8")
        assert "R08_FEE_INVOICE_MISSING" in content
        assert "R09_FEE_EXCEEDS_INVOICE" in content
        assert "R10_INVOICE_POSTDATES_PAYMENT" in content
        assert "## Matter M018" in content
        assert "L040" in content
