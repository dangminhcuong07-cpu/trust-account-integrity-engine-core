"""
R13_BANK_BALANCE_OVERDRAWN

Flag any trust bank statement line where the running balance
(running_balance_nzd) goes negative. This catches the specific entry
where the trust bank account first goes into deficit — even
intra-period, even if corrected by a later entry.

Checked per entry, not grouped by calendar date: firms process bank
feeds at varying cadences (daily, every second day, weekly), so
per-entry checking is the correct and simpler approach — the same
approach R01_OVERDRAWN_CLIENT_LEDGER uses for client_ledger.csv's
balance_after_nzd.

Regulation: LCA (Trust Account) Regulations 2008, Reg 6
Severity:   CRITICAL

Citation verified: 26 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).
"""

from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID  = "R13_BANK_BALANCE_OVERDRAWN"
NZLS_REF = "LCA (Trust Account) Regulations 2008, Reg 6"
SEVERITY = "CRITICAL"


def bank_balance_overdrawn(record: Record) -> TrustRuleResult:
    """
    Applied to each row of trust_bank_statement.csv.

    running_balance_nzd represents the trust bank account's running
    balance after this entry. A negative value means the trust account
    itself is in deficit at this point in time.
    """
    balance = record.data.get("running_balance_nzd")
    if balance is None:
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence="no running_balance_nzd field",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )
    if balance < 0.0:
        date = record.data.get("transaction_date", "?")
        return TrustRuleResult(
            rule_id=RULE_ID, passed=False, record_id=record.record_id,
            evidence=(
                f"trust bank account balance -${abs(balance):,.2f} NZD after entry "
                f"{record.record_id} dated {date} - trust account overdrawn"
            ),
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )
    return TrustRuleResult(
        rule_id=RULE_ID, passed=True, record_id=record.record_id,
        evidence=f"balance ${balance:,.2f} NZD",
        nzls_ref=NZLS_REF, severity=SEVERITY,
    )
