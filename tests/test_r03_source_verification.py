"""
Tests for R03_RECON_BREAK source-verification (secondary bank-balance check).

The primary R03 check (stored_ledger ≠ stored_bank) is tested in
test_trust_rules.py.  This file covers the secondary check:

    When bank_statement records are supplied, make_recon_break_rule() verifies
    that the stored bank_balance_nzd matches the bank statement's own running
    balance at the period end.  If a matching pair of fabricated values was
    entered in both summary fields (primary check sees 0 and passes), the
    secondary check catches the discrepancy.

All tests use small inline Record lists so no CSV fixtures are needed.

NOTE on synthetic-data scope:
    The secondary check is intentionally not applied to the main synthetic
    sample (trust_domain/synthetic/sample/) because the reconciliation_summary
    stored totals in that fixture pre-date the ERR-14/15/16/19 bank entries
    (B052–B055); source-verification on that fixture would produce false
    positives on otherwise-clean periods.  The primary check (stored totals
    disagree) continues to flag ERR-4 and ERR-17 correctly.  Fixing the
    generator to derive summary totals from source data is deferred to a
    subsequent PR.
"""

from __future__ import annotations

import datetime

import pytest

from integrity_engine.core.types import Record
from trust_domain.rules.r03_reconciliation import make_recon_break_rule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _recon_record(
    recon_id: str,
    period_end: str,
    ledger_total: float,
    bank_balance: float,
    status: str = "AGREED",
) -> Record:
    return Record(
        record_id=recon_id,
        data={
            "recon_id":          recon_id,
            "period_end_date":   period_end,
            "ledger_total_nzd":  str(ledger_total),
            "bank_balance_nzd":  str(bank_balance),
            "difference_nzd":    str(ledger_total - bank_balance),
            "status":            status,
        },
    )


def _bank_record(
    stmt_id: str,
    txn_date: str,
    running_balance: float,
) -> Record:
    return Record(
        record_id=stmt_id,
        data={
            "statement_id":       stmt_id,
            "transaction_date":   txn_date,
            "running_balance_nzd": str(running_balance),
            "credit_nzd":         "0.00",
            "debit_nzd":          "0.00",
        },
    )


# ---------------------------------------------------------------------------
# Primary check (no bank_statement): existing behaviour unchanged
# ---------------------------------------------------------------------------

class TestPrimaryCheckUnchanged:
    """make_recon_break_rule with no bank_statement = same as recon_break."""

    def test_clean_period_passes(self):
        rule = make_recon_break_rule()
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed

    def test_stored_totals_disagree_flagged(self):
        rule = make_recon_break_rule()
        rec  = _recon_record("R002", "2026-04-30", 798_500.00, 798_750.00)
        result = rule(rec)
        assert not result.passed
        assert "bank exceeds ledger" in result.evidence

    def test_stirling_pattern_caught(self):
        """Status=AGREED and difference_nzd=0.00 do not prevent detection."""
        rule = make_recon_break_rule(bank_statement=None)
        rec  = _recon_record("R004", "2026-06-30", 425_300.00, 424_900.00)
        result = rule(rec)
        assert not result.passed
        assert "ledger exceeds bank" in result.evidence

    def test_in_progress_skipped(self):
        rule = make_recon_break_rule()
        rec  = Record(
            record_id="R003",
            data={"period_end_date": "2026-05-31", "status": "IN PROGRESS",
                  "ledger_total_nzd": "", "bank_balance_nzd": ""},
        )
        assert rule(rec).passed


# ---------------------------------------------------------------------------
# Secondary check: fabricated-matching-values gap
# ---------------------------------------------------------------------------

class TestSecondaryBankBalanceCheck:
    """
    The gap: operator enters matching values in both summary fields
    (ledger_total = bank_balance = X).  Primary check sees diff=0 and passes.
    Secondary check compares stored bank_balance against the bank statement's
    own running balance.
    """

    def _make_bank(self, period_end: str, running_balance: float) -> list[Record]:
        """One bank entry on the period_end date with the given running balance."""
        return [_bank_record("B001", period_end, running_balance)]

    def test_fabricated_matching_values_caught(self):
        """
        Both summary fields are set to 500_000 (primary check passes).
        Bank statement running balance is 480_000.
        Secondary check must flag this as a violation.
        """
        bank = self._make_bank("2026-03-31", 480_000.00)
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        result = rule(rec)
        assert not result.passed, (
            "R03 should catch fabricated matching values when bank statement "
            "running balance contradicts the stored figure"
        )
        assert "fabrication" in result.evidence.lower()
        assert "480,000.00" in result.evidence
        assert "500,000.00" in result.evidence

    def test_clean_period_with_matching_source_passes(self):
        """Stored values match AND match bank statement → clean pass."""
        bank = self._make_bank("2026-03-31", 500_000.00)
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed

    def test_penny_rounding_does_not_trigger(self):
        """Differences of ≤ 1 cent are within floating-point tolerance."""
        bank = self._make_bank("2026-03-31", 500_000.009)
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed

    def test_secondary_check_uses_last_entry_before_period_end(self):
        """
        Bank statement has two entries.  Only the one on or before period_end
        (closer to the end) is used.  A later entry (after period_end) is ignored.
        """
        bank = [
            _bank_record("B001", "2026-03-15", 400_000.00),
            _bank_record("B002", "2026-03-28", 500_000.00),  # last before 2026-03-31
            _bank_record("B003", "2026-04-15", 999_999.00),  # after period_end, ignored
        ]
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed  # B002 running_balance matches stored bank

    def test_secondary_check_bank_exceeds_stored(self):
        """Bank running balance > stored bank_balance is also a violation."""
        bank = self._make_bank("2026-03-31", 520_000.00)
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        result = rule(rec)
        assert not result.passed
        assert "520,000.00" in result.evidence

    def test_primary_failure_includes_source_info_in_evidence(self):
        """
        If primary check already fails, source discrepancy is appended to
        evidence (not a separate violation — count stays at 1 per period).
        """
        bank = self._make_bank("2026-04-30", 800_000.00)
        rule = make_recon_break_rule(bank_statement=bank)
        # stored_bank=798_750, stored_ledger=798_500 → primary fails (-250)
        # source_bank=800_000 ≠ stored_bank → secondary info appended
        rec = _recon_record("R002", "2026-04-30", 798_500.00, 798_750.00)
        result = rule(rec)
        assert not result.passed
        assert "bank exceeds ledger" in result.evidence  # primary message
        assert "800,000.00" in result.evidence            # secondary augmentation

    def test_no_bank_entries_before_period_end_does_not_crash(self):
        """If all bank entries are after period_end, secondary check is silently skipped."""
        bank = [_bank_record("B001", "2026-05-01", 500_000.00)]  # after Mar 31
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed

    def test_empty_bank_statement_disables_secondary_check(self):
        """Supplying an empty list is equivalent to not supplying bank_statement."""
        rule = make_recon_break_rule(bank_statement=[])
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed

    def test_unparseable_bank_date_skipped_gracefully(self):
        """A bank record with an unparseable date is ignored without crashing."""
        bank = [
            _bank_record("B000", "NOT-A-DATE", 999_999.00),
            _bank_record("B001", "2026-03-31", 500_000.00),
        ]
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed  # B001 matches stored; B000 ignored

    def test_dd_mm_yyyy_bank_dates_parsed(self):
        """Bank statement dates in DD/MM/YYYY format are handled correctly."""
        bank = [_bank_record("B001", "31/03/2026", 500_000.00)]
        rule = make_recon_break_rule(bank_statement=bank)
        rec  = _recon_record("R001", "2026-03-31", 500_000.00, 500_000.00)
        assert rule(rec).passed
