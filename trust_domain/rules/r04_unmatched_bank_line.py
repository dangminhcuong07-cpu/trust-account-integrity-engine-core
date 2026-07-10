"""
R04_UNMATCHED_BANK_LINE

Flag any bank statement line where:
  (a) matched_ledger_entry is empty (no ledger counterpart identified), AND
  (b) transaction_date is more than `max_age_days` calendar days ago
      (default 5 - gives the firm a short window to post incoming items).

Age is computed from transaction_date to datetime.date.today() unless an
explicit reference_date is provided (for deterministic testing only).

Regulation: LCA (Trust Account) Regulations 2008, Reg 11
Severity:   HIGH

Citation verified: 10 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).
"""

from __future__ import annotations

import datetime
from integrity_engine.core.types import Record
from integrity_engine.flagging import StalenessChecker
from trust_domain.rules.types import TrustRuleResult

RULE_ID   = "R04_UNMATCHED_BANK_LINE"
NZLS_REF  = "LCA (Trust Account) Regulations 2008, Reg 11"
SEVERITY  = "HIGH"


def make_unmatched_rule(
    max_age_days: int = 5,
    reference_date: datetime.date | None = None,
):
    """
    Factory - returns a RuleProtocol for unmatched bank line detection.

    reference_date defaults to datetime.date.today() if None.
    """
    checker = StalenessChecker(
        max_age_days=max_age_days,
        reference_date=reference_date,
    )

    def _rule(record: Record) -> TrustRuleResult:
        matched = record.data.get("matched_ledger_entry", "")
        if matched:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence=f"matched to ledger entry {matched}",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        # No match - check whether it is old enough to be a real problem
        results = checker.check_age(
            [record.data], date_field="transaction_date", id_field="statement_id"
        )
        r = results[0]
        if r.is_stale:
            desc       = record.data.get("description", "")
            credit_raw = record.data.get("credit_nzd", 0.0)
            debit_raw  = record.data.get("debit_nzd",  0.0)
            credit     = f"${float(credit_raw):,.2f}"
            debit      = f"${float(debit_raw):,.2f}"
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"bank line {record.record_id} "
                    f"({record.data.get('transaction_date', '?')}): "
                    f"credit={credit} debit={debit} - {desc!r} - "
                    f"no matched ledger entry; {r.reason}"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=f"unmatched but within {max_age_days}-day posting window",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
