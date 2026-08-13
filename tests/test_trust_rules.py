"""
TDD tests for the NZ trust-accounting domain rules that need no
supplementary dataset or factory parameters (Step 2.2, plus R13 added
later in the same style).

Reference date used throughout: 2026-06-25 (matches synthetic data scenario).

Seeded errors:
  ERR-1  L009  reconciled=N, entry_date=2026-03-28 (89 days)    → R05_UNRECONCILED_AGEING
  ERR-2  L021  balance_after_nzd=-2500.00                        → R01_OVERDRAWN_CLIENT_LEDGER
  ERR-3  M017  last_activity=2024-12-15, bal=8500 (557 days)    → R02_DORMANT_BALANCE
  ERR-4  R002  ledger=798500 vs bank=798750 (diff=-250)          → R03_RECON_BREAK
  ERR-5  B031  matched_ledger_entry="" (34 days old)             → R04_UNMATCHED_BANK_LINE
  ERR-6  M021  FIT balance 24 days old (threshold=14)           → R06_FIT_OVERHELD
  ERR-7  L037  disbursement payment, reference="" (no INV-#)     → R07_FEE_WITHOUT_INVOICE
  ERR-13 B050  running_balance_nzd=-14175.00                     → R13_BANK_BALANCE_OVERDRAWN
  ERR-14a L053  balance_after_nzd=-1800.00 (Nguy cross-matter)    → R01_OVERDRAWN_CLIENT_LEDGER
  ERR-14b L055  unexplained credit, correlated with L053          → NOT caught by R01 (by design)
  ERR-15  L061  balance_after_nzd=-400.00 (Ms M gradual, 4 txns)  → R01_OVERDRAWN_CLIENT_LEDGER
  ERR-16  B055  running_balance_nzd=-575.00 (Ms M gradual, bank)  → R13_BANK_BALANCE_OVERDRAWN
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from integrity_engine.core.types import Record

import trust_domain.rules.r01_overdrawn_ledger as _r01
import trust_domain.rules.r02_dormant_balance as _r02
import trust_domain.rules.r03_reconciliation as _r03
import trust_domain.rules.r04_unmatched_bank_line as _r04
import trust_domain.rules.r05_unreconciled_ageing as _r05
import trust_domain.rules.r06_fit_overheld as _r06
import trust_domain.rules.r07_fee_without_invoice as _r07
import trust_domain.rules.r13_bank_balance_overdrawn as _r13
from trust_domain.rules import TrustRuleResult

REF_DATE  = datetime.date(2026, 6, 25)
SAMPLE_DIR = Path("trust_domain/synthetic/sample")


# ── Generate synthetic data before any test runs ─────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def trust_sample_data():
    from trust_domain.synthetic.generator import generate
    generate(SAMPLE_DIR)


def _load(name: str) -> list[Record]:
    from data.load_sample import load_file
    return load_file(name, SAMPLE_DIR)


# ── Helpers to build minimal test records ────────────────────────────────────

def _ledger_record(entry_id, matter_ref, entry_date, receipt, payment,
                   balance_after, reconciled="Y", reference="", description=""):
    return Record(
        record_id=entry_id,
        data={
            "entry_id":          entry_id,
            "matter_ref":        matter_ref,
            "entry_date":        entry_date,
            "description":       description,
            "receipt_nzd":       float(receipt),
            "payment_nzd":       float(payment),
            "balance_after_nzd": float(balance_after),
            "reconciled":        reconciled,
            "reconciled_date":   "",
            "notes":             "",
            "reference":         reference,
        },
    )


def _matter_record(matter_ref, balance, last_activity, matter_type="PROPERTY_PURCHASE"):
    return Record(
        record_id=matter_ref,
        data={
            "matter_ref":          matter_ref,
            "current_balance_nzd": float(balance),
            "last_activity_date":  last_activity,
            "matter_type":         matter_type,
        },
    )


def _recon_record(recon_id, status, ledger_total, bank_balance, difference, period):
    return Record(
        record_id=recon_id,
        data={
            "recon_id":          recon_id,
            "status":            status,
            "ledger_total_nzd":  ledger_total,
            "bank_balance_nzd":  bank_balance,
            "difference_nzd":    difference,
            "period_end_date":   period,
        },
    )


def _bank_record(statement_id, transaction_date, credit, debit, matched,
                  running_balance_nzd=0.0):
    return Record(
        record_id=statement_id,
        data={
            "statement_id":         statement_id,
            "transaction_date":     transaction_date,
            "credit_nzd":           credit,
            "debit_nzd":            debit,
            "matched_ledger_entry": matched,
            "description":          "test",
            "running_balance_nzd":  float(running_balance_nzd),
        },
    )


# ── R01: Overdrawn client ledger ──────────────────────────────────────────────

class TestR01OverdrawnLedger:

    def test_positive_balance_passes(self):
        r = _r01.overdrawn_ledger(
            _ledger_record("L004", "M001", "2026-03-01", 80000, 0, 80000)
        )
        assert r.passed
        assert r.rule_id == "R01_OVERDRAWN_CLIENT_LEDGER"

    def test_zero_balance_passes(self):
        r = _r01.overdrawn_ledger(
            _ledger_record("L014", "M001", "2026-04-15", 0, 725000, 0)
        )
        assert r.passed

    def test_negative_balance_fails(self):
        r = _r01.overdrawn_ledger(
            _ledger_record("L021", "M016", "2026-04-28", 0, 97500, -2500)
        )
        assert not r.passed
        assert r.record_id == "L021"

    def test_evidence_contains_balance(self):
        r = _r01.overdrawn_ledger(
            _ledger_record("L021", "M016", "2026-04-28", 0, 97500, -2500)
        )
        assert "-$2,500.00" in r.evidence

    def test_nzls_ref_present(self):
        r = _r01.overdrawn_ledger(
            _ledger_record("L021", "M016", "2026-04-28", 0, 97500, -2500)
        )
        assert r.nzls_ref != ""

    def test_severity_present(self):
        r = _r01.overdrawn_ledger(
            _ledger_record("L021", "M016", "2026-04-28", 0, 97500, -2500)
        )
        assert r.severity != ""

    def test_catches_err2_from_synthetic_data(self):
        records = _load("client_ledger")
        results = [_r01.overdrawn_ledger(r) for r in records]
        failures = [res for res in results if not res.passed]
        assert any(res.record_id == "L021" for res in failures), \
            "ERR-2 (L021) not caught by R01_OVERDRAWN_CLIENT_LEDGER"

    def test_catches_err14a_cross_matter_deficit_from_synthetic_data(self):
        """ERR-14a: modeled on the NZLS Nguy decision (cross-matter correlation,
        deficit side). Confirms R01 catches the deficit even though the pattern
        also involves a correlated unexplained credit elsewhere (L055/M023)."""
        records = _load("client_ledger")
        failures = [res for res in [_r01.overdrawn_ledger(r) for r in records]
                    if not res.passed]
        assert any(res.record_id == "L053" for res in failures), \
            "ERR-14a (L053) not caught by R01_OVERDRAWN_CLIENT_LEDGER"

    def test_err14b_unexplained_credit_not_caught_by_r01(self):
        """ERR-14b: the correlated unexplained credit (L055/M023) has a positive
        balance, so R01 does not and should not flag it - only the deficit side
        (L053) is structurally visible to this rule. Detecting the cross-matter
        correlation itself would require a new rule tracing money between
        matters; out of scope here."""
        records = _load("client_ledger")
        l055 = next(r for r in records if r.record_id == "L055")
        assert _r01.overdrawn_ledger(l055).passed, \
            "L055 (unexplained credit, positive balance) should pass R01 - " \
            "R01 only detects the deficit side of the Nguy pattern"

    def test_catches_err15_gradual_deficit_from_synthetic_data(self):
        """ERR-15: modeled on the NZLS 'Ms M' decision (gradual deficit via 4
        smaller transfers over consecutive months, disguised among normal
        transaction volume). Confirms R01 catches the deficit even though it
        emerged gradually rather than as one large overdraw."""
        records = _load("client_ledger")
        failures = [res for res in [_r01.overdrawn_ledger(r) for r in records]
                    if not res.passed]
        assert any(res.record_id == "L061" for res in failures), \
            "ERR-15 (L061) not caught by R01_OVERDRAWN_CLIENT_LEDGER"

    def test_m026_clean_complement_never_overdrawn(self):
        """Clean complement to ERR-15: 4 smaller legitimate disbursements over
        consecutive months, balance never goes negative."""
        records = _load("client_ledger")
        m026_entries = [r for r in records if r.data.get("matter_ref") == "M026"]
        failures = [res for res in [_r01.overdrawn_ledger(r) for r in m026_entries]
                    if not res.passed]
        assert failures == [], f"M026 (clean complement) should never overdraw, got: {[f.record_id for f in failures]}"

    def test_only_three_violations_in_synthetic_data(self):
        records = _load("client_ledger")
        failures = [res for res in [_r01.overdrawn_ledger(r) for r in records]
                    if not res.passed]
        assert len(failures) == 3, f"Expected 3 violations, got: {[f.record_id for f in failures]}"
        assert {f.record_id for f in failures} == {"L021", "L053", "L061"}


# ── R02: Dormant balance ──────────────────────────────────────────────────────

class TestR02DormantBalance:

    def test_active_matter_passes(self):
        rule = _r02.make_dormant_rule(reference_date=REF_DATE)
        r = rule(_matter_record("M004", 30000, "2026-04-08"))
        assert r.passed

    def test_zero_balance_passes_regardless_of_age(self):
        rule = _r02.make_dormant_rule(reference_date=REF_DATE)
        r = rule(_matter_record("M999", 0, "2020-01-01"))
        assert r.passed

    def test_dormant_matter_fails(self):
        rule = _r02.make_dormant_rule(reference_date=REF_DATE)
        r = rule(_matter_record("M017", 8500, "2024-12-15"))
        assert not r.passed
        assert r.record_id == "M017"

    def test_evidence_contains_day_count(self):
        rule = _r02.make_dormant_rule(reference_date=REF_DATE)
        r = rule(_matter_record("M017", 8500, "2024-12-15"))
        assert "557" in r.evidence

    def test_exactly_at_threshold_is_not_dormant(self):
        rule = _r02.make_dormant_rule(max_inactive_days=365, reference_date=REF_DATE)
        exactly_365 = datetime.date(2025, 6, 25)
        r = rule(_matter_record("M999", 1000, exactly_365.isoformat()))
        assert r.passed

    def test_nzls_ref_present(self):
        rule = _r02.make_dormant_rule(reference_date=REF_DATE)
        r = rule(_matter_record("M017", 8500, "2024-12-15"))
        assert r.nzls_ref != ""

    def test_catches_err3_from_synthetic_data(self):
        rule = _r02.make_dormant_rule(reference_date=REF_DATE)
        records = _load("matter_register")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert any(res.record_id == "M017" for res in failures), \
            "ERR-3 (M017) not caught by R02_DORMANT_BALANCE"

    def test_only_one_violation_in_synthetic_data(self):
        rule = _r02.make_dormant_rule(reference_date=REF_DATE)
        records = _load("matter_register")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert len(failures) == 1, f"Expected 1 violation, got: {[f.record_id for f in failures]}"


# ── R03: Reconciliation break ─────────────────────────────────────────────────

class TestR03ReconBreak:

    def test_zero_difference_passes(self):
        r = _r03.recon_break(
            _recon_record("R001", "AGREED", "1508500.00", "1508500.00", "0.00", "2026-03-31")
        )
        assert r.passed

    def test_in_progress_passes(self):
        r = _r03.recon_break(
            _recon_record("R003", "IN PROGRESS", "", "", "", "2026-05-31")
        )
        assert r.passed

    def test_discrepancy_fails(self):
        r = _r03.recon_break(
            _recon_record("R002", "DISCREPANCY", "798500.00", "798750.00", "-250.00", "2026-04-30")
        )
        assert not r.passed
        assert r.record_id == "R002"

    def test_evidence_contains_computed_difference(self):
        r = _r03.recon_break(
            _recon_record("R002", "DISCREPANCY", "798500.00", "798750.00", "-250.00", "2026-04-30")
        )
        assert "250" in r.evidence and "bank exceeds ledger" in r.evidence

    def test_nzls_ref_present(self):
        r = _r03.recon_break(
            _recon_record("R002", "DISCREPANCY", "798500.00", "798750.00", "-250.00", "2026-04-30")
        )
        assert r.nzls_ref != ""

    def test_catches_err4_from_synthetic_data(self):
        records = _load("reconciliation_summary")
        failures = [res for res in [_r03.recon_break(r) for r in records] if not res.passed]
        assert any(res.record_id == "R002" for res in failures), \
            "ERR-4 (R002) not caught by R03_RECON_BREAK"

    def test_only_one_violation_in_synthetic_data(self):
        records = _load("reconciliation_summary")
        failures = [res for res in [_r03.recon_break(r) for r in records] if not res.passed]
        assert len(failures) == 1, f"Expected 1 violation, got: {[f.record_id for f in failures]}"


# ── R04: Unmatched bank line ──────────────────────────────────────────────────

class TestR04UnmatchedBankLine:

    def test_matched_line_passes(self):
        rule = _r04.make_unmatched_rule(reference_date=REF_DATE)
        r = rule(_bank_record("B001", "2024-12-15", "8500.00", "0.00", "L001"))
        assert r.passed

    def test_recent_unmatched_passes_within_window(self):
        rule = _r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
        r = rule(_bank_record("B999", "2026-06-22", "100.00", "0.00", ""))
        assert r.passed

    def test_old_unmatched_fails(self):
        rule = _r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
        r = rule(_bank_record("B031", "2026-05-22", "15000.00", "0.00", ""))
        assert not r.passed
        assert r.record_id == "B031"

    def test_evidence_contains_bank_line_id(self):
        rule = _r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
        r = rule(_bank_record("B031", "2026-05-22", "15000.00", "0.00", ""))
        assert "B031" in r.evidence

    def test_b009_passes_with_match(self):
        rule = _r04.make_unmatched_rule(reference_date=REF_DATE)
        records = _load("trust_bank_statement")
        b009 = next(r for r in records if r.record_id == "B009")
        assert _r04.make_unmatched_rule(reference_date=REF_DATE)(b009).passed, \
            "B009 should pass (matched_ledger_entry='L009')"

    def test_b022_passes_with_match(self):
        rule = _r04.make_unmatched_rule(reference_date=REF_DATE)
        records = _load("trust_bank_statement")
        b022 = next(r for r in records if r.record_id == "B022")
        assert rule(b022).passed, "B022 should pass (matched_ledger_entry='BANK-INTEREST')"

    def test_nzls_ref_present(self):
        rule = _r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
        r = rule(_bank_record("B031", "2026-05-22", "15000.00", "0.00", ""))
        assert r.nzls_ref != ""

    def test_catches_err5_from_synthetic_data(self):
        rule = _r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
        records = _load("trust_bank_statement")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert any(res.record_id == "B031" for res in failures), \
            "ERR-5 (B031) not caught by R04_UNMATCHED_BANK_LINE"

    def test_only_one_violation_in_synthetic_data(self):
        rule = _r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
        records = _load("trust_bank_statement")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert len(failures) == 1, f"Expected 1 violation, got: {[f.record_id for f in failures]}"


# ── R05: Unreconciled ageing ──────────────────────────────────────────────────

class TestR05UnreconciledAgeing:

    def test_reconciled_entry_passes(self):
        rule = _r05.make_ageing_rule(reference_date=REF_DATE)
        r = rule(_ledger_record("L001", "M017", "2024-12-15", 8500, 0, 8500, reconciled="Y"))
        assert r.passed

    def test_recent_unreconciled_passes(self):
        rule = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
        r = rule(_ledger_record("L999", "M001", "2026-06-10", 1000, 0, 1000, reconciled="N"))
        assert r.passed

    def test_old_unreconciled_fails(self):
        rule = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
        r = rule(_ledger_record("L009", "M008", "2026-03-28", 120000, 0, 120000, reconciled="N"))
        assert not r.passed
        assert r.record_id == "L009"

    def test_evidence_contains_day_count(self):
        rule = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
        r = rule(_ledger_record("L009", "M008", "2026-03-28", 120000, 0, 120000, reconciled="N"))
        assert "89" in r.evidence

    def test_exactly_at_threshold_is_not_stale(self):
        rule = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
        exactly_30 = datetime.date(2026, 5, 26)
        r = rule(_ledger_record("L999", "M001", exactly_30.isoformat(), 1000, 0, 1000, reconciled="N"))
        assert r.passed

    def test_nzls_ref_present(self):
        rule = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
        r = rule(_ledger_record("L009", "M008", "2026-03-28", 120000, 0, 120000, reconciled="N"))
        assert r.nzls_ref != ""

    def test_catches_err1_from_synthetic_data(self):
        rule = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
        records = _load("client_ledger")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert any(res.record_id == "L009" for res in failures), \
            "ERR-1 (L009) not caught by R05_UNRECONCILED_AGEING"

    def test_only_one_violation_in_synthetic_data(self):
        rule = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
        records = _load("client_ledger")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert len(failures) == 1, f"Expected 1 violation, got: {[f.record_id for f in failures]}"


# ── R06: FIT overheld ─────────────────────────────────────────────────────────

class TestR06FitOverheld:

    def test_non_fit_matter_passes(self):
        rule = _r06.make_fit_rule(reference_date=REF_DATE)
        r = rule(_matter_record("M001", 80000, "2026-04-15", matter_type="PROPERTY_PURCHASE"))
        assert r.passed

    def test_fit_zero_balance_passes(self):
        rule = _r06.make_fit_rule(reference_date=REF_DATE)
        r = rule(_matter_record("M099", 0, "2026-06-01", matter_type="FIT"))
        assert r.passed

    def test_fit_within_deadline_passes(self):
        rule = _r06.make_fit_rule(max_days=14, reference_date=REF_DATE)
        r = rule(_matter_record("M099", 200, "2026-06-15", matter_type="FIT"))
        assert r.passed

    def test_fit_overheld_fails(self):
        rule = _r06.make_fit_rule(max_days=14, reference_date=REF_DATE)
        r = rule(_matter_record("M021", 125, "2026-06-01", matter_type="FIT"))
        assert not r.passed
        assert r.record_id == "M021"

    def test_evidence_contains_balance(self):
        rule = _r06.make_fit_rule(max_days=14, reference_date=REF_DATE)
        r = rule(_matter_record("M021", 125, "2026-06-01", matter_type="FIT"))
        assert "125" in r.evidence

    def test_nzls_ref_present(self):
        rule = _r06.make_fit_rule(max_days=14, reference_date=REF_DATE)
        r = rule(_matter_record("M021", 125, "2026-06-01", matter_type="FIT"))
        assert r.nzls_ref != ""

    def test_catches_err6_from_synthetic_data(self):
        rule = _r06.make_fit_rule(max_days=14, reference_date=REF_DATE)
        records = _load("matter_register")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert any(res.record_id == "M021" for res in failures), \
            "ERR-6 (M021) not caught by R06_FIT_OVERHELD"

    def test_only_one_violation_in_synthetic_data(self):
        rule = _r06.make_fit_rule(max_days=14, reference_date=REF_DATE)
        records = _load("matter_register")
        failures = [res for res in [rule(r) for r in records] if not res.passed]
        assert len(failures) == 1, f"Expected 1 violation, got: {[f.record_id for f in failures]}"


# ── R07: Fee without invoice ──────────────────────────────────────────────────

class TestR07FeeWithoutInvoice:

    def test_receipt_entry_passes(self):
        r = _r07.fee_without_invoice(
            _ledger_record("L009", "M008", "2026-03-28", 120000, 0, 120000)
        )
        assert r.passed

    def test_payment_without_fee_keyword_passes(self):
        r = _r07.fee_without_invoice(
            _ledger_record("L014", "M001", "2026-04-15", 0, 725000, 0)
        )
        assert r.passed

    def test_fee_entry_with_valid_invoice_passes(self):
        r = _r07.fee_without_invoice(
            _ledger_record("L038", "M013", "2026-05-28", 0, 500, 109500, reference="INV-00234")
        )
        assert r.passed

    def test_disbursement_without_invoice_fails(self):
        r = _r07.fee_without_invoice(
            _ledger_record("L037", "M012", "2026-05-28", 0, 200, 54800,
                           reference="", description="Disbursement - LINZ title search fee")
        )
        assert not r.passed
        assert r.record_id == "L037"

    def test_evidence_contains_missing_reference(self):
        r = _r07.fee_without_invoice(
            _ledger_record("L037", "M012", "2026-05-28", 0, 200, 54800,
                           reference="", description="Disbursement - LINZ title search fee")
        )
        assert "INV" in r.evidence

    def test_nzls_ref_present(self):
        r = _r07.fee_without_invoice(
            _ledger_record("L037", "M012", "2026-05-28", 0, 200, 54800, reference="")
        )
        assert r.nzls_ref != ""

    def test_severity_present(self):
        r = _r07.fee_without_invoice(
            _ledger_record("L037", "M012", "2026-05-28", 0, 200, 54800, reference="")
        )
        assert r.severity != ""

    def test_catches_err7_from_synthetic_data(self):
        records = _load("client_ledger")
        failures = [res for res in [_r07.fee_without_invoice(r) for r in records]
                    if not res.passed]
        assert any(res.record_id == "L037" for res in failures), \
            "ERR-7 (L037) not caught by R07_FEE_WITHOUT_INVOICE"

    def test_l038_clean_fee_passes(self):
        records = _load("client_ledger")
        l038 = next(r for r in records if r.record_id == "L038")
        assert _r07.fee_without_invoice(l038).passed, "L038 (valid invoice) should pass R07"

    def test_only_one_violation_in_synthetic_data(self):
        records = _load("client_ledger")
        failures = [res for res in [_r07.fee_without_invoice(r) for r in records]
                    if not res.passed]
        assert len(failures) == 1, f"Expected 1 violation, got: {[f.record_id for f in failures]}"


# ── R13: Bank balance overdrawn ────────────────────────────────────────────────

class TestR13BankBalanceOverdrawn:

    def test_positive_balance_passes(self):
        r = _r13.bank_balance_overdrawn(
            _bank_record("B004", "2026-03-01", 80000, 0, "L004", running_balance_nzd=553500.00)
        )
        assert r.passed
        assert r.rule_id == "R13_BANK_BALANCE_OVERDRAWN"

    def test_zero_balance_passes(self):
        r = _r13.bank_balance_overdrawn(
            _bank_record("B014", "2026-04-15", 0, 725000, "L014", running_balance_nzd=0.00)
        )
        assert r.passed

    def test_negative_balance_fails(self):
        r = _r13.bank_balance_overdrawn(
            _bank_record("B050", "2026-06-25", 0, 700000, "BANK-ERROR", running_balance_nzd=-14175.00)
        )
        assert not r.passed
        assert r.record_id == "B050"

    def test_evidence_contains_balance(self):
        r = _r13.bank_balance_overdrawn(
            _bank_record("B050", "2026-06-25", 0, 700000, "BANK-ERROR", running_balance_nzd=-14175.00)
        )
        assert "-$14,175.00" in r.evidence

    def test_nzls_ref_present(self):
        r = _r13.bank_balance_overdrawn(
            _bank_record("B050", "2026-06-25", 0, 700000, "BANK-ERROR", running_balance_nzd=-14175.00)
        )
        assert r.nzls_ref != ""

    def test_severity_present(self):
        r = _r13.bank_balance_overdrawn(
            _bank_record("B050", "2026-06-25", 0, 700000, "BANK-ERROR", running_balance_nzd=-14175.00)
        )
        assert r.severity != ""

    def test_catches_err13_from_synthetic_data(self):
        records = _load("trust_bank_statement")
        results = [_r13.bank_balance_overdrawn(r) for r in records]
        failures = [res for res in results if not res.passed]
        assert any(res.record_id == "B050" for res in failures), \
            "ERR-13 (B050) not caught by R13_BANK_BALANCE_OVERDRAWN"

    def test_b051_clean_complement_passes(self):
        records = _load("trust_bank_statement")
        b051 = next(r for r in records if r.record_id == "B051")
        assert _r13.bank_balance_overdrawn(b051).passed, \
            "B051 (balance restored positive) should pass R13"

    def test_catches_err16_gradual_deficit_from_synthetic_data(self):
        """ERR-16: modeled on the NZLS 'Ms M' decision (same pattern as ERR-15,
        applied to the trust bank statement instead of the client ledger) - a
        series of 4 smaller unauthorised-looking debits disguised among normal
        transaction volume. Confirms R13 catches the deficit even though it
        emerged gradually rather than as one dramatic overdraw like ERR-13."""
        records = _load("trust_bank_statement")
        failures = [res for res in [_r13.bank_balance_overdrawn(r) for r in records]
                    if not res.passed]
        assert any(res.record_id == "B055" for res in failures), \
            "ERR-16 (B055) not caught by R13_BANK_BALANCE_OVERDRAWN"

    def test_b056_clean_complement_passes(self):
        records = _load("trust_bank_statement")
        b056 = next(r for r in records if r.record_id == "B056")
        assert _r13.bank_balance_overdrawn(b056).passed, \
            "B056 (balance restored positive) should pass R13"

    def test_only_two_violations_in_synthetic_data(self):
        records = _load("trust_bank_statement")
        failures = [res for res in [_r13.bank_balance_overdrawn(r) for r in records]
                    if not res.passed]
        assert len(failures) == 2, f"Expected 2 violations, got: {[f.record_id for f in failures]}"
        assert {f.record_id for f in failures} == {"B050", "B055"}


# ── TrustRuleResult contract ──────────────────────────────────────────────────

class TestTrustRuleResultContract:

    def test_is_subclass_of_rule_result(self):
        from integrity_engine.core.types import RuleResult
        r = _r01.overdrawn_ledger(
            _ledger_record("L021", "M016", "2026-04-28", 0, 97500, -2500)
        )
        assert isinstance(r, RuleResult)
        assert isinstance(r, TrustRuleResult)

    def test_all_violations_have_nzls_ref(self):
        violations = _collect_all_violations()
        for v in violations:
            assert v.nzls_ref != "", f"{v.rule_id} / {v.record_id} missing nzls_ref"

    def test_all_violations_have_severity(self):
        violations = _collect_all_violations()
        for v in violations:
            assert v.severity != "", f"{v.rule_id} / {v.record_id} missing severity"

    def test_all_violations_have_evidence(self):
        violations = _collect_all_violations()
        for v in violations:
            assert v.evidence != "", f"{v.rule_id} / {v.record_id} missing evidence"


# ── Integration: exactly 7 violations ────────────────────────────────────────

def _collect_all_violations() -> list[TrustRuleResult]:
    ledger   = _load("client_ledger")
    matters  = _load("matter_register")
    bank     = _load("trust_bank_statement")
    recon    = _load("reconciliation_summary")

    r01 = _r01.overdrawn_ledger
    r02 = _r02.make_dormant_rule(reference_date=REF_DATE)
    r03 = _r03.recon_break
    r04 = _r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
    r05 = _r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
    r06 = _r06.make_fit_rule(max_days=14, reference_date=REF_DATE)
    r07 = _r07.fee_without_invoice

    all_results: list[TrustRuleResult] = []
    for rec in ledger:
        all_results.extend([r01(rec), r05(rec), r07(rec)])
    for rec in matters:
        all_results.extend([r02(rec), r06(rec)])
    for rec in bank:
        all_results.append(r04(rec))
    for rec in recon:
        all_results.append(r03(rec))

    return [res for res in all_results if not res.passed]


class TestIntegration:

    def test_exactly_9_violations_total(self):
        violations = _collect_all_violations()
        ids = [(v.rule_id, v.record_id) for v in violations]
        assert len(violations) == 9, f"Expected 9 violations, got {len(violations)}: {ids}"

    def test_violation_record_ids_match_expected_errors(self):
        violations = _collect_all_violations()
        by_rule = {(v.rule_id, v.record_id) for v in violations}
        expected = {
            ("R01_OVERDRAWN_CLIENT_LEDGER",   "L021"),
            ("R01_OVERDRAWN_CLIENT_LEDGER",   "L053"),
            ("R01_OVERDRAWN_CLIENT_LEDGER",   "L061"),
            ("R02_DORMANT_BALANCE",            "M017"),
            ("R03_RECON_BREAK",                "R002"),
            ("R04_UNMATCHED_BANK_LINE",        "B031"),
            ("R05_UNRECONCILED_AGEING",        "L009"),
            ("R06_FIT_OVERHELD",               "M021"),
            ("R07_FEE_WITHOUT_INVOICE",        "L037"),
        }
        assert by_rule == expected, f"Violation set mismatch:\n  got:      {sorted(by_rule)}\n  expected: {sorted(expected)}"
