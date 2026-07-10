"""
R01_OVERDRAWN_CLIENT_LEDGER

Flag any client ledger entry where the running balance (balance_after_nzd)
goes negative. This catches the specific entry where the overdraw first
occurs - even intra-month, even if corrected by a later entry.

Regulation: LCA (Trust Account) Regulations 2008, Reg 6 and Reg 12(6)(a)
Severity:   CRITICAL

Citation verified: 10 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).
"""

from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID   = "R01_OVERDRAWN_CLIENT_LEDGER"
NZLS_REF  = "LCA (Trust Account) Regulations 2008, Reg 6 and Reg 12(6)(a)"
SEVERITY  = "CRITICAL"


def overdrawn_ledger(record: Record) -> TrustRuleResult:
    """
    Applied to each row of client_ledger.csv.

    balance_after_nzd represents the running matter balance after this entry.
    A negative value means client funds are in deficit at this point in time.
    """
    balance = record.data.get("balance_after_nzd")
    if balance is None:
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence="no balance_after_nzd field",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )
    if balance < 0.0:
        matter = record.data.get("matter_ref", "?")
        date   = record.data.get("entry_date", "?")
        return TrustRuleResult(
            rule_id=RULE_ID, passed=False, record_id=record.record_id,
            evidence=(
                f"matter {matter} balance -${abs(balance):,.2f} NZD after entry "
                f"{record.record_id} dated {date} - client funds in deficit"
            ),
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )
    return TrustRuleResult(
        rule_id=RULE_ID, passed=True, record_id=record.record_id,
        evidence=f"balance ${balance:,.2f} NZD",
        nzls_ref=NZLS_REF, severity=SEVERITY,
    )
