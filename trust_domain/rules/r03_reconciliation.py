"""
R03_RECON_BREAK

For each monthly period in reconciliation_summary.csv, recompute the
difference as (ledger_total_nzd - bank_balance_nzd) and flag if it is
non-zero.  The stored difference_nzd field is NOT trusted — the rule
recomputes independently from the source figures and flags any mismatch.

Secondary check (when bank_statement records are supplied):
  The stored bank_balance_nzd is verified against the running_balance_nzd
  of the chronologically-last bank statement entry on or before period_end.
  This catches the fabrication pattern where an operator types matching
  values in both ledger_total_nzd and bank_balance_nzd — which the
  primary comparison would miss — but the bank statement's own running
  balance contradicts the stored figure.

  NOTE: this secondary check requires the bank_statement records to carry
  correct running_balance_nzd values (i.e. computed in date order, not
  insertion order).  Call make_recon_break_rule() with bank_statement=[],
  or use the bare recon_break callable, to disable it.

Periods with status=IN PROGRESS (fields blank) are skipped.

Regulation: LCA (Trust Account) Regulations 2008, Reg 17 (with Reg 11)
Severity:   CRITICAL

Citation verified: 10 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).
"""

from __future__ import annotations

import datetime
from typing import Callable

from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID   = "R03_RECON_BREAK"
NZLS_REF  = "LCA (Trust Account) Regulations 2008, Reg 17 (with Reg 11)"
SEVERITY  = "CRITICAL"

# Absolute tolerance for floating-point comparison of running balances.
# Real bank statement figures are always 2-decimal-place NZD; any
# discrepancy above 1 cent is genuine.
_BALANCE_TOLERANCE_NZD = 0.01


def _parse_date(s: str) -> datetime.date | None:
    """Parse ISO or DD/MM/YYYY date strings; return None on failure."""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def make_recon_break_rule(
    bank_statement: list[Record] | None = None,
) -> Callable[[Record], TrustRuleResult]:
    """
    Return a recon_break rule callable.

    Parameters
    ----------
    bank_statement
        Records from trust_bank_statement.  When non-empty, enables the
        secondary bank-balance cross-check (see module docstring).
        Pass None or [] to disable; behaviour is then identical to the
        bare recon_break function.
    """
    _bank = bank_statement or []

    # Pre-sort bank entries by date so look-ups are O(n) at call time.
    _sorted_bank: list[tuple[datetime.date, float]] = []
    for b in _bank:
        d = _parse_date(b.data.get("transaction_date", ""))
        raw = b.data.get("running_balance_nzd", "")
        if d is not None and raw not in (None, ""):
            try:
                _sorted_bank.append((d, float(str(raw).replace(",", "").strip())))
            except (ValueError, TypeError):
                pass
    _sorted_bank.sort(key=lambda x: x[0])

    def _last_bank_running_balance(period_end: datetime.date) -> float | None:
        """Return running_balance_nzd of last bank entry on/before period_end."""
        result: float | None = None
        for d, bal in _sorted_bank:
            if d <= period_end:
                result = bal
            else:
                break
        return result

    def _rule(record: Record) -> TrustRuleResult:
        status    = record.data.get("status", "")
        ledger_raw = record.data.get("ledger_total_nzd")
        bank_raw   = record.data.get("bank_balance_nzd")
        period_str = record.data.get("period_end_date", "?")

        # Skip periods not yet finalised
        if status == "IN PROGRESS" or ledger_raw in (None, "") or bank_raw in (None, ""):
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence=f"period {period_str} not yet finalised",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        ledger_total = float(str(ledger_raw).replace(",", "").strip())
        bank_balance = float(str(bank_raw).replace(",", "").strip())
        computed_diff = ledger_total - bank_balance

        # --- Primary check: stored totals disagree with each other ----------
        if computed_diff != 0.0:
            gap = abs(computed_diff)
            direction = (
                f"bank exceeds ledger by ${gap:.2f} NZD"
                if computed_diff < 0
                else f"ledger exceeds bank by ${gap:.2f} NZD"
            )
            evidence = (
                f"period {period_str}: "
                f"ledger_total=${ledger_total:,.2f} "
                f"bank_balance=${bank_balance:,.2f} — {direction}"
            )
            # Augment with source-bank discrepancy if bank_statement available
            period_end = _parse_date(period_str)
            if period_end is not None and _sorted_bank:
                src_bal = _last_bank_running_balance(period_end)
                if src_bal is not None and abs(src_bal - bank_balance) > _BALANCE_TOLERANCE_NZD:
                    evidence += (
                        f"; bank statement running balance at period end "
                        f"=${src_bal:,.2f} (stored ${bank_balance:,.2f}, "
                        f"Δ={src_bal - bank_balance:+,.2f})"
                    )
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=evidence,
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        # --- Secondary check: stored totals agree but contradict bank stmt --
        # Catches the fabrication pattern: operator enters matching values in
        # both fields, primary comparison sees 0 and passes, but the bank
        # statement's own running balance tells a different story.
        period_end = _parse_date(period_str)
        if period_end is not None and _sorted_bank:
            src_bal = _last_bank_running_balance(period_end)
            if src_bal is not None and abs(src_bal - bank_balance) > _BALANCE_TOLERANCE_NZD:
                gap = abs(src_bal - bank_balance)
                direction = (
                    f"bank statement running balance ${src_bal:,.2f} "
                    f"exceeds stored bank_balance_nzd ${bank_balance:,.2f}"
                    if src_bal > bank_balance
                    else f"stored bank_balance_nzd ${bank_balance:,.2f} "
                    f"exceeds bank statement running balance ${src_bal:,.2f}"
                )
                return TrustRuleResult(
                    rule_id=RULE_ID, passed=False, record_id=record.record_id,
                    evidence=(
                        f"period {period_str}: stored totals agree "
                        f"(ledger=bank=${bank_balance:,.2f}, diff=0) but "
                        f"bank statement running balance contradicts stored figure — "
                        f"{direction}; Δ=${gap:,.2f}. "
                        f"Possible fabrication: matching values entered in both "
                        f"ledger_total_nzd and bank_balance_nzd fields."
                    ),
                    nzls_ref=NZLS_REF, severity=SEVERITY,
                )

        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=f"period {period_str} reconciled: difference=0.00",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule


# ---------------------------------------------------------------------------
# Bare callable — backward-compatible; secondary check disabled.
# Used by _TRUST_RULE_REGISTRY as the default (no supplementary datasets).
# ---------------------------------------------------------------------------
recon_break: Callable[[Record], TrustRuleResult] = make_recon_break_rule()
