"""
R03_RECON_BREAK

For each monthly period in reconciliation_summary.csv, recompute the
difference as (ledger_total_nzd - bank_balance_nzd) and flag if it is
non-zero. The stored difference_nzd field is NOT trusted - the rule
recomputes independently from the source figures and flags any mismatch.

Periods with status=IN PROGRESS (fields blank) are skipped.

Regulation: LCA (Trust Account) Regulations 2008, Reg 17 (with Reg 11)
Severity:   CRITICAL

Citation verified: 10 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).
"""

from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID   = "R03_RECON_BREAK"
NZLS_REF  = "LCA (Trust Account) Regulations 2008, Reg 17 (with Reg 11)"
SEVERITY  = "CRITICAL"


def recon_break(record: Record) -> TrustRuleResult:
    """Applied to each row of reconciliation_summary.csv."""
    status = record.data.get("status", "")
    ledger_raw = record.data.get("ledger_total_nzd")
    bank_raw   = record.data.get("bank_balance_nzd")

    # Skip periods not yet finalised
    if status == "IN PROGRESS" or ledger_raw in (None, "") or bank_raw in (None, ""):
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=f"period {record.data.get('period_end_date', '?')} not yet finalised",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    ledger_total = float(ledger_raw)
    bank_balance = float(bank_raw)
    computed_diff = ledger_total - bank_balance

    if computed_diff != 0.0:
        gap = abs(computed_diff)
        if computed_diff < 0:
            direction = f"bank exceeds ledger by ${gap:.2f} NZD"
        else:
            direction = f"ledger exceeds bank by ${gap:.2f} NZD"
        return TrustRuleResult(
            rule_id=RULE_ID, passed=False, record_id=record.record_id,
            evidence=(
                f"period {record.data.get('period_end_date', '?')}: "
                f"ledger_total=${ledger_total:,.2f} bank_balance=${bank_balance:,.2f} - "
                f"{direction}"
            ),
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return TrustRuleResult(
        rule_id=RULE_ID, passed=True, record_id=record.record_id,
        evidence=f"period {record.data.get('period_end_date', '?')} reconciled: difference=0.00",
        nzls_ref=NZLS_REF, severity=SEVERITY,
    )
