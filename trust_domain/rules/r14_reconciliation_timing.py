"""
R14_RECONCILIATION_TIMING

Flag any reconciliation_summary record where reconciliation_date is later
than the statutory deadline for that period:

  - deadline = 10th working day of the month following period_end_date's
    month, in the same year
  - EXCEPT: if the following month is January, deadline = 15th working day
    of that January (in the next year)
  - working day = Monday-Friday only. v1 SIMPLIFICATION: no NZ public
    holiday calendar is applied, so a deadline that lands on a public
    holiday is not pushed forward. This is a known conservative gap
    (flags nothing that wouldn't already be late, but could mark a firm
    late-by-one-day on a deadline that actually fell on a holiday).

If the reconciliation_date column is absent from the input entirely, this
rule is skipped for the whole dataset before it ever runs (see run.py's
rule-dispatch loop) - not handled inside this module, since a per-record
callable has no way to know "no row anywhere has this column."

If reconciliation_date is present but blank for a given row, that row
passes (treated the same way R03 treats a not-yet-finalised period: no
data to judge means no violation).

Regulation: LCA (Trust Account) Regulations 2008, Reg 14
Severity:   HIGH

Citation verified: 17 Sep 2026 against the NZLS Lawyers Trust Accounting
Guidelines (June 2024), section 18.1 ("regulation 14" governs the duty to
regularly reconcile trust account records) - see
docs/superpowers/specs/2026-09-17-phase-e-regulatory-accuracy-design.md
for the full verification trail (also cross-checked against section 18.9
and the NZLS trust-account-certificates FAQ page).
"""

from __future__ import annotations

import datetime

from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID  = "R14_RECONCILIATION_TIMING"
NZLS_REF = "LCA (Trust Account) Regulations 2008, Reg 14"
SEVERITY = "HIGH"


def dataset_has_column(records: list[Record], column_name: str) -> bool:
    """
    True if ANY record in the dataset has `column_name` as a key in .data —
    i.e. the CSV genuinely had that column (even if blank for some rows).
    False for an empty dataset or when no record carries the key at all.

    Used by run.py to decide whether to run this rule at all: a per-record
    rule callable has no way to know "does any row anywhere have this
    column," since it only ever sees one record at a time.
    """
    return any(column_name in r.data for r in records)


def _parse_date(s: str) -> datetime.date | None:
    """Parse ISO or DD/MM/YYYY date strings; return None on failure/blank."""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _nth_working_day(year: int, month: int, n: int) -> datetime.date:
    """Return the date of the nth Mon-Fri day of (year, month), counting from
    the 1st. No public holiday calendar - see module docstring."""
    d = datetime.date(year, month, 1)
    count = 0
    while True:
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            count += 1
            if count == n:
                return d
        d += datetime.timedelta(days=1)


def _deadline_for_period(period_end: datetime.date) -> datetime.date:
    """10th working day of the following month; 15th working day of January
    if the following month is January."""
    if period_end.month == 12:
        return _nth_working_day(period_end.year + 1, 1, 15)
    return _nth_working_day(period_end.year, period_end.month + 1, 10)


def make_reconciliation_timing_rule():
    """Factory - returns a RuleProtocol for reconciliation-timing checking."""

    def _rule(record: Record) -> TrustRuleResult:
        period_str = record.data.get("period_end_date", "?")
        period_end = _parse_date(period_str)
        recon_str  = record.data.get("reconciliation_date", "")
        recon_date = _parse_date(recon_str)

        if period_end is None or recon_date is None:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence=f"period {period_str}: no reconciliation_date to check",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        deadline = _deadline_for_period(period_end)
        if recon_date > deadline:
            month_label = period_end.strftime("%B %Y")
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"Trust account reconciliation for {month_label} was "
                    f"certified on {recon_date.isoformat()}, exceeding the "
                    f"statutory deadline under Regulation 14. "
                    f"Deadline was {deadline.isoformat()}."
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=(
                f"period {period_str}: reconciled {recon_date.isoformat()}, "
                f"within deadline {deadline.isoformat()}"
            ),
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
