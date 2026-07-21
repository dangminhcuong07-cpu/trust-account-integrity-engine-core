"""
TDD tests for rules R08, R09, R10, R12.

Reference date throughout: 2026-06-25 (matches synthetic data scenario).

Seeded errors in synthetic corpus:
  ERR-8   L039  INV-99999 absent from invoice_register         -> R08
  ERR-9   L040  payment $5,000 > INV-00236 amount $3,000       -> R09
  ERR-10  L041  INV-00237 issue_date 2026-06-15 > entry 06-01  -> R10
  ERR-12a B046  allocations sum $7,500 < credit $9,000         -> R12
  ERR-12b B047  allocations sum $5,500 > credit $5,000         -> R12
  ERR-12c B048  zero allocations, no matched_ledger_entry       -> R12
  (B031 also caught by R12 — existing ERR-5 orphan credit)
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from integrity_engine.core.types import Record

import trust_domain.rules.r08_fee_invoice_missing as _r08
import trust_domain.rules.r09_fee_exceeds_invoice as _r09
import trust_domain.rules.r10_invoice_postdates_payment as _r10
import trust_domain.rules.r12_bulk_deposit_unallocated as _r12

SAMPLE_DIR = Path("trust_domain/synthetic/sample")


@pytest.fixture(scope="module", autouse=True)
def r08_r12_sample_data():
    """Ensure synthetic CSVs exist before tests run."""
    from trust_domain.synthetic.generator import generate
    generate(SAMPLE_DIR)


def _load(name: str) -> list[Record]:
    from data.load_sample import load_file
    return load_file(name, SAMPLE_DIR)


# ── Record builders ──────────────────────────────────────────────────────────

def _ledger(entry_id, matter_ref, entry_date, payment,
            description="Fee - legal services", reference="", receipt=0.0):
    return Record(
        record_id=entry_id,
        data={
            "entry_id":    entry_id,
            "matter_ref":  matter_ref,
            "entry_date":  entry_date,
            "description": description,
            "payment_nzd": float(payment),
            "receipt_nzd": float(receipt),
            "reference":   reference,
        },
    )


def _invoice(invoice_id, matter_ref, amount, issue_date, description=""):
    return Record(
        record_id=invoice_id,
        data={
            "invoice_id":  invoice_id,
            "matter_ref":  matter_ref,
            "amount_nzd":  float(amount),
            "issue_date":  issue_date,
            "description": description,
        },
    )


def _alloc(bank_line_id, ledger_entry_id, amount):
    return Record(
        record_id=bank_line_id,
        data={
            "bank_line_id":    bank_line_id,
            "ledger_entry_id": ledger_entry_id,
            "amount_nzd":      float(amount),
        },
    )


def _bank(statement_id, credit, matched="", transaction_date="2026-06-24"):
    return Record(
        record_id=statement_id,
        data={
            "statement_id":         statement_id,
            "credit_nzd":           float(credit),
            "debit_nzd":            0.0,
            "matched_ledger_entry": matched,
            "transaction_date":     transaction_date,
            "description":          "test credit",
        },
    )


def _client_ledger_record(entry_id, matter_ref="M001"):
    return Record(
        record_id=entry_id,
        data={"entry_id": entry_id, "matter_ref": matter_ref},
    )


# ── R08: Fee Invoice Missing ──────────────────────────────────────────────────

class TestR08FeeInvoiceMissing:

    def _make_rule(self, invoices=None):
        return _r08.make_fee_invoice_missing_rule(invoices or [])

    def test_not_fee_entry_passes(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-04-01", 1000,
                         description="Receipt - client funds"))
        assert r.passed
        assert r.rule_id == "R08_FEE_INVOICE_MISSING"

    def test_zero_payment_passes(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-04-01", 0,
                         description="Fee - legal services"))
        assert r.passed

    def test_reference_not_inv_format_skips(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-04-01", 500,
                         description="Fee - legal services", reference=""))
        assert r.passed

    def test_reference_wrong_format_skips(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-04-01", 500,
                         description="Fee - legal services", reference="BILL-999"))
        assert r.passed

    def test_invoice_not_in_register_fails(self):
        rule = self._make_rule(invoices=[])
        r = rule(_ledger("L039", "M004", "2026-06-10", 350,
                         description="Fee - legal services", reference="INV-99999"))
        assert not r.passed
        assert r.record_id == "L039"
        assert "INV-99999" in r.evidence

    def test_matter_mismatch_fails(self):
        inv = _invoice("INV-00100", "M099", 500, "2026-05-01")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L050", "M001", "2026-06-01", 500,
                         description="Fee - legal services", reference="INV-00100"))
        assert not r.passed
        assert "M099" in r.evidence or "M001" in r.evidence

    def test_valid_invoice_matching_matter_passes(self):
        inv = _invoice("INV-00234", "M013", 500, "2026-05-20")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L038", "M013", "2026-05-28", 500,
                         description="Fee - professional conveyancing services",
                         reference="INV-00234"))
        assert r.passed
        assert "INV-00234" in r.evidence

    def test_missing_description_field_passes(self):
        rule = self._make_rule()
        rec = Record(record_id="L999", data={"entry_id": "L999", "payment_nzd": 500.0})
        r = rule(rec)
        assert r.passed

    def test_result_has_nzls_ref(self):
        rule = self._make_rule()
        r = rule(_ledger("L039", "M004", "2026-06-10", 350,
                         description="Fee - legal services", reference="INV-99999"))
        assert r.nzls_ref == "LCA (Trust Account) Regulations 2008, Reg 9"

    def test_result_has_severity(self):
        rule = self._make_rule()
        r = rule(_ledger("L039", "M004", "2026-06-10", 350,
                         description="Fee - legal services", reference="INV-99999"))
        assert r.severity == "HIGH"

    def test_catches_err8_from_synthetic_data(self):
        invoices = _load("invoice_register")
        rule = _r08.make_fee_invoice_missing_rule(invoices)
        ledger = _load("client_ledger")
        failures = [rule(r) for r in ledger if not rule(r).passed]
        assert any(res.record_id == "L039" for res in failures), \
            "ERR-8 (L039) not caught by R08_FEE_INVOICE_MISSING"

    def test_only_one_violation_in_synthetic_data(self):
        invoices = _load("invoice_register")
        rule = _r08.make_fee_invoice_missing_rule(invoices)
        ledger = _load("client_ledger")
        failures = [rule(r) for r in ledger if not rule(r).passed]
        assert len(failures) == 1, \
            f"Expected 1 R08 violation, got: {[f.record_id for f in failures]}"


# ── R09: Fee Exceeds Invoice ──────────────────────────────────────────────────

class TestR09FeeExceedsInvoice:

    def _make_rule(self, invoices=None):
        return _r09.make_fee_exceeds_invoice_rule(invoices or [])

    def test_not_fee_entry_passes(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-04-01", 1000,
                         description="Receipt - client funds"))
        assert r.passed
        assert r.rule_id == "R09_FEE_EXCEEDS_INVOICE"

    def test_zero_payment_passes(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-04-01", 0,
                         description="Fee - legal services"))
        assert r.passed

    def test_no_matching_invoice_skips(self):
        rule = self._make_rule(invoices=[])
        r = rule(_ledger("L039", "M004", "2026-06-10", 350,
                         description="Fee - legal services", reference="INV-99999"))
        assert r.passed

    def test_payment_within_invoice_passes(self):
        inv = _invoice("INV-00100", "M001", 1000, "2026-05-01")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L050", "M001", "2026-06-01", 800,
                         description="Fee - legal services", reference="INV-00100"))
        assert r.passed

    def test_payment_equal_to_invoice_passes(self):
        inv = _invoice("INV-00100", "M001", 500, "2026-05-01")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L050", "M001", "2026-06-01", 500,
                         description="Fee - legal services", reference="INV-00100"))
        assert r.passed

    def test_payment_exceeds_invoice_fails(self):
        inv = _invoice("INV-00236", "M018", 3000, "2026-05-20")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L040", "M018", "2026-06-01", 5000,
                         description="Fee - professional legal services",
                         reference="INV-00236"))
        assert not r.passed
        assert r.record_id == "L040"
        assert "5,000.00" in r.evidence
        assert "3,000.00" in r.evidence

    def test_matter_mismatch_invoice_skips(self):
        inv = _invoice("INV-00100", "M099", 1000, "2026-05-01")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L050", "M001", "2026-06-01", 5000,
                         description="Fee - legal services", reference="INV-00100"))
        assert r.passed

    def test_result_has_nzls_ref(self):
        inv = _invoice("INV-00236", "M018", 3000, "2026-05-20")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L040", "M018", "2026-06-01", 5000,
                         description="Fee - legal services", reference="INV-00236"))
        assert r.nzls_ref == _r09.NZLS_REF

    def test_catches_err9_from_synthetic_data(self):
        invoices = _load("invoice_register")
        rule = _r09.make_fee_exceeds_invoice_rule(invoices)
        ledger = _load("client_ledger")
        failures = [rule(r) for r in ledger if not rule(r).passed]
        assert any(res.record_id == "L040" for res in failures), \
            "ERR-9 (L040) not caught by R09_FEE_EXCEEDS_INVOICE"

    def test_only_one_violation_in_synthetic_data(self):
        invoices = _load("invoice_register")
        rule = _r09.make_fee_exceeds_invoice_rule(invoices)
        ledger = _load("client_ledger")
        failures = [rule(r) for r in ledger if not rule(r).passed]
        assert len(failures) == 1, \
            f"Expected 1 R09 violation, got: {[f.record_id for f in failures]}"


# ── R10: Invoice Postdates Payment ───────────────────────────────────────────

class TestR10InvoicePostdatesPayment:

    def _make_rule(self, invoices=None):
        return _r10.make_invoice_postdates_rule(invoices or [])

    def test_not_fee_entry_passes(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-06-01", 1000,
                         description="Receipt - client funds"))
        assert r.passed
        assert r.rule_id == "R10_INVOICE_POSTDATES_PAYMENT"

    def test_zero_payment_passes(self):
        rule = self._make_rule()
        r = rule(_ledger("L001", "M001", "2026-06-01", 0,
                         description="Fee - legal services"))
        assert r.passed

    def test_no_matching_invoice_skips(self):
        rule = self._make_rule(invoices=[])
        r = rule(_ledger("L039", "M004", "2026-06-10", 350,
                         description="Fee - legal services", reference="INV-99999"))
        assert r.passed

    def test_invoice_before_payment_passes(self):
        inv = _invoice("INV-00234", "M013", 500, "2026-05-20")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L038", "M013", "2026-05-28", 500,
                         description="Fee - professional conveyancing services",
                         reference="INV-00234"))
        assert r.passed

    def test_invoice_same_day_as_payment_passes(self):
        inv = _invoice("INV-00100", "M001", 500, "2026-06-01")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L050", "M001", "2026-06-01", 500,
                         description="Fee - legal services", reference="INV-00100"))
        assert r.passed

    def test_invoice_after_payment_fails(self):
        inv = _invoice("INV-00237", "M015", 1000, "2026-06-15")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L041", "M015", "2026-06-01", 500,
                         description="Disbursement - search fee",
                         reference="INV-00237"))
        assert not r.passed
        assert r.record_id == "L041"
        assert "2026-06-15" in r.evidence
        assert "2026-06-01" in r.evidence

    def test_matter_mismatch_invoice_skips(self):
        inv = _invoice("INV-00100", "M099", 500, "2026-06-15")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L050", "M001", "2026-06-01", 500,
                         description="Fee - legal services", reference="INV-00100"))
        assert r.passed

    def test_result_has_nzls_ref_and_severity(self):
        inv = _invoice("INV-00237", "M015", 1000, "2026-06-15")
        rule = self._make_rule(invoices=[inv])
        r = rule(_ledger("L041", "M015", "2026-06-01", 500,
                         description="Disbursement - search fee",
                         reference="INV-00237"))
        assert r.nzls_ref == "LCA (Trust Account) Regulations 2008, Reg 9"
        assert r.severity == "HIGH"

    def test_catches_err10_from_synthetic_data(self):
        invoices = _load("invoice_register")
        rule = _r10.make_invoice_postdates_rule(invoices)
        ledger = _load("client_ledger")
        failures = [rule(r) for r in ledger if not rule(r).passed]
        assert any(res.record_id == "L041" for res in failures), \
            "ERR-10 (L041) not caught by R10_INVOICE_POSTDATES_PAYMENT"

    def test_only_one_violation_in_synthetic_data(self):
        invoices = _load("invoice_register")
        rule = _r10.make_invoice_postdates_rule(invoices)
        ledger = _load("client_ledger")
        failures = [rule(r) for r in ledger if not rule(r).passed]
        assert len(failures) == 1, \
            f"Expected 1 R10 violation, got: {[f.record_id for f in failures]}"


# ── R12: Bulk Deposit Unallocated ────────────────────────────────────────────

class TestR12BulkDepositUnallocated:

    def _make_rule(self, allocs=None, ledger_records=None, bulk_min_nzd=0.0):
        return _r12.make_bulk_deposit_rule(
            allocations=allocs or [],
            client_ledger=ledger_records,
            bulk_min_nzd=bulk_min_nzd,
        )

    def test_debit_line_passes(self):
        rule = self._make_rule()
        r = rule(Record(record_id="B010", data={
            "statement_id": "B010", "credit_nzd": 0.0, "debit_nzd": 482500.0,
            "matched_ledger_entry": "L010", "transaction_date": "2026-04-01",
            "description": "Debit",
        }))
        assert r.passed
        assert r.rule_id == "R12_BULK_DEPOSIT_UNALLOCATED"

    def test_below_threshold_passes(self):
        rule = self._make_rule(bulk_min_nzd=10000.0)
        r = rule(_bank("B044", credit=2500))
        assert r.passed

    def test_one_to_one_match_passes(self):
        rule = self._make_rule()
        r = rule(_bank("B045", credit=3000, matched="L048"))
        assert r.passed

    def test_fully_allocated_passes(self):
        allocs = [_alloc("B044", "L047", 2500)]
        rule = self._make_rule(allocs=allocs)
        r = rule(_bank("B044", credit=2500, matched="BULK-ALLOCATED"))
        assert r.passed

    def test_no_allocation_no_match_fails(self):
        rule = self._make_rule()
        r = rule(_bank("B031", credit=15000, matched=""))
        assert not r.passed
        assert r.record_id == "B031"

    def test_under_allocated_fails(self):
        allocs = [
            _alloc("B046", "L042", 3000),
            _alloc("B046", "L043", 2500),
            _alloc("B046", "L044", 2000),
        ]
        rule = self._make_rule(allocs=allocs)
        r = rule(_bank("B046", credit=9000, matched="BULK-MULTI"))
        assert not r.passed
        assert r.record_id == "B046"
        assert "7,500.00" in r.evidence
        assert "9,000.00" in r.evidence

    def test_over_allocated_fails(self):
        allocs = [
            _alloc("B047", "L045", 3000),
            _alloc("B047", "L046", 2500),
        ]
        rule = self._make_rule(allocs=allocs)
        r = rule(_bank("B047", credit=5000, matched="BULK-MULTI"))
        assert not r.passed
        assert r.record_id == "B047"
        assert "5,500.00" in r.evidence
        assert "5,000.00" in r.evidence

    def test_invalid_ledger_entry_in_allocation_fails(self):
        allocs = [_alloc("B050", "L999", 1000)]
        ledger = [_client_ledger_record("L001"), _client_ledger_record("L002")]
        rule = self._make_rule(allocs=allocs, ledger_records=ledger)
        r = rule(_bank("B050", credit=1000))
        assert not r.passed
        assert "L999" in r.evidence

    def test_result_has_critical_severity(self):
        rule = self._make_rule()
        r = rule(_bank("B031", credit=15000, matched=""))
        assert r.severity == "CRITICAL"
        assert r.nzls_ref == "LCA (Trust Account) Regulations 2008, Reg 11 / Reg 12(1)"

    def test_catches_err12a_b046_from_synthetic_data(self):
        allocs = _load("allocations")
        rule = _r12.make_bulk_deposit_rule(allocations=allocs)
        bank = _load("trust_bank_statement")
        failures = [rule(r) for r in bank if not rule(r).passed]
        assert any(res.record_id == "B046" for res in failures), \
            "ERR-12a (B046) not caught by R12_BULK_DEPOSIT_UNALLOCATED"

    def test_catches_err12b_b047_from_synthetic_data(self):
        allocs = _load("allocations")
        rule = _r12.make_bulk_deposit_rule(allocations=allocs)
        bank = _load("trust_bank_statement")
        failures = [rule(r) for r in bank if not rule(r).passed]
        assert any(res.record_id == "B047" for res in failures), \
            "ERR-12b (B047) not caught by R12_BULK_DEPOSIT_UNALLOCATED"

    def test_catches_err12c_b048_from_synthetic_data(self):
        allocs = _load("allocations")
        rule = _r12.make_bulk_deposit_rule(allocations=allocs)
        bank = _load("trust_bank_statement")
        failures = [rule(r) for r in bank if not rule(r).passed]
        assert any(res.record_id == "B048" for res in failures), \
            "ERR-12c (B048) not caught by R12_BULK_DEPOSIT_UNALLOCATED"

    def test_exactly_four_violations_in_synthetic_data(self):
        allocs = _load("allocations")
        ledger = _load("client_ledger")
        rule = _r12.make_bulk_deposit_rule(
            allocations=allocs,
            client_ledger=ledger,
        )
        bank = _load("trust_bank_statement")
        failures = [rule(r) for r in bank if not rule(r).passed]
        assert len(failures) == 4, (
            f"Expected 4 R12 violations (B031, B046, B047, B048), "
            f"got: {[f.record_id for f in failures]}"
        )

    def test_passes_b049_clean_fully_allocated_true_negative(self):
        allocs = _load("allocations")
        ledger = _load("client_ledger")
        rule = _r12.make_bulk_deposit_rule(
            allocations=allocs,
            client_ledger=ledger,
        )
        bank = _load("trust_bank_statement")
        b049 = next(r for r in bank if r.record_id == "B049")
        result = rule(b049)
        assert result.passed, (
            f"B049 ($12,000 bulk deposit fully allocated to L049/L050/L051) "
            f"should pass R12, but got: {result.evidence}"
        )
