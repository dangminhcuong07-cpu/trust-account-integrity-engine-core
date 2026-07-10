"""
R02_DORMANT_BALANCE

Flag any client matter where:
  (a) current_balance_nzd > 0, AND
  (b) last_activity_date is more than `max_inactive_days` ago (default 365).

Dormancy threshold is a configurable internal-control default (do not hardcode); 365 days is not a statutory period. 

The legal anchor is Reg 12(7) (client statements at intervals of not more than 12 months) and LTAG June 2024 guidance on unexplained balances.

Regulation: LCA (Trust Account) Regulations 2008, Reg 12(7); LTAG June 2024 (guidance)
Severity:   HIGH

Citation verified: 10 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022) and NZLS Lawyers Trust Accounting
Guidelines, June 2024.
"""

from __future__ import annotations

import datetime
from integrity_engine.core.types import Record
from integrity_engine.flagging import StalenessChecker
from trust_domain.rules.types import TrustRuleResult

RULE_ID   = "R02_DORMANT_BALANCE"
NZLS_REF  = "LCA (Trust Account) Regulations 2008, Reg 12(7); LTAG June 2024 (guidance)"
SEVERITY  = "HIGH"


def make_dormant_rule(
    max_inactive_days: int = 365,
    reference_date: datetime.date | None = None,
):
    """
    Factory — returns a RuleProtocol for dormant-balance detection.

    reference_date defaults to datetime.date.today() at call time if None.
    Pass an explicit date only in tests for determinism.
    """
    checker = StalenessChecker(
        max_age_days=max_inactive_days,
        reference_date=reference_date,
    )

    def _rule(record: Record) -> TrustRuleResult:
        balance = record.data.get("current_balance_nzd")
        if balance is None or balance == 0.0:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="zero balance — dormancy not applicable",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        last_activity = record.data.get("last_activity_date", "")
        if not last_activity:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="no last_activity_date field",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        results = checker.check_age(
            [record.data], date_field="last_activity_date", id_field="matter_ref"
        )
        r = results[0]
        if r.is_stale:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"balance ${balance:,.2f} NZD; last activity {last_activity}; "
                    f"{r.reason}"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=r.reason or f"last activity within {max_inactive_days} days",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
