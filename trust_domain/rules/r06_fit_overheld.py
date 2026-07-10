"""
R06_FIT_OVERHELD

Flag any matter with matter_type="FIT" where the balance has not been transferred to the office account within `max_days` (default 14).

The 14-day default is a configurable firm-policy threshold, NOT a statutory deadline. 

Statutory basis: LCA 2006 s110 and Reg 8/Reg 9 (fees must be properly invoiced and promptly transferred; the FIT ledger must never be overdrawn).

Regulation: LCA 2006, s110; LCA (Trust Account) Regulations 2008, Reg 8/Reg 9
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

RULE_ID   = "R06_FIT_OVERHELD"
NZLS_REF  = "LCA 2006, s110; LCA (Trust Account) Regulations 2008, Reg 8/Reg 9"
SEVERITY  = "HIGH"


def make_fit_rule(
    max_days: int = 14,
    reference_date: datetime.date | None = None,
):
    """
    Factory - returns a RuleProtocol for FIT overheld detection.

    reference_date defaults to datetime.date.today() if None.
    """
    checker = StalenessChecker(max_age_days=max_days, reference_date=reference_date)

    def _rule(record: Record) -> TrustRuleResult:
        if record.data.get("matter_type") != "FIT":
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="not a FIT matter - rule not applicable",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        balance = record.data.get("current_balance_nzd")
        if balance is None or balance == 0.0:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="FIT balance is zero - no outstanding transfer required",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        last_activity = record.data.get("last_activity_date", "")
        if not last_activity:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="no last_activity_date - cannot determine FIT age",
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
                    f"FIT balance ${balance:,.2f} NZD credited {last_activity}; "
                    f"{r.reason} - transfer to office account overdue"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=f"FIT balance ${balance:,.2f} NZD - within {max_days}-day transfer deadline",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
