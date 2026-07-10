"""
R05_UNRECONCILED_AGEING

Flag any client ledger entry where:
  (a) reconciled field is "N", AND
  (b) entry_date is more than `max_days` calendar days ago (default 30).

Ageing threshold is configurable via rule config.

Regulation: LCA (Trust Account) Regulations 2008, Reg 11 / Reg 17
Severity:   HIGH

Citation verified: 10 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).
"""

from __future__ import annotations

import datetime
from integrity_engine.core.types import Record
from integrity_engine.flagging import StalenessChecker
from trust_domain.rules.types import TrustRuleResult

RULE_ID   = "R05_UNRECONCILED_AGEING"
NZLS_REF  = "LCA (Trust Account) Regulations 2008, Reg 11 / Reg 17"
SEVERITY  = "HIGH"


def make_ageing_rule(
    max_days: int = 30,
    reference_date: datetime.date | None = None,
):
    """
    Factory - returns a RuleProtocol for unreconciled-item ageing.

    reference_date defaults to datetime.date.today() if None.
    """
    checker = StalenessChecker(max_age_days=max_days, reference_date=reference_date)

    def _rule(record: Record) -> TrustRuleResult:
        if record.data.get("reconciled") != "N":
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="reconciled=Y - ageing not applicable",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        results = checker.check_age(
            [record.data], date_field="entry_date", id_field="entry_id"
        )
        r = results[0]
        if r.is_stale:
            matter = record.data.get("matter_ref", "?")
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"entry {record.record_id} (matter {matter}) "
                    f"dated {record.data.get('entry_date', '?')} is unreconciled; "
                    f"{r.reason}"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=f"unreconciled but within {max_days}-day limit",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
