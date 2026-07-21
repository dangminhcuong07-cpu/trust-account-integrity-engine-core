"""
R12_BULK_DEPOSIT_UNALLOCATED

Flag any bank statement credit line where:
  (a) credit_nzd > 0 and credit_nzd >= bulk_min_nzd (default 0.0), AND one of:
    (b1) allocation rows exist and their amounts do not sum to credit_nzd, OR
    (b2) allocation rows exist and any ledger_entry_id is absent from
         client_ledger (only checked when client_ledger is supplied), OR
    (b3) no allocation rows AND matched_ledger_entry is empty.

Pass conditions:
  - Debit-only lines (credit_nzd == 0): not applicable.
  - credit_nzd < bulk_min_nzd: below threshold, not applicable.
  - 1:1 case: zero allocations AND matched_ledger_entry is non-empty.
  - Fully allocated: allocation amounts sum to credit_nzd AND all
    ledger_entry_ids in allocations exist in client_ledger (when provided).

Citation status: PROVISIONAL - pending verification against legislation.govt.nz
by the maintainer.

Regulation: LCA (Trust Account) Regulations 2008, Reg 11 / Reg 12(1)
Severity:   CRITICAL
"""

from __future__ import annotations

from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID  = "R12_BULK_DEPOSIT_UNALLOCATED"
NZLS_REF = "LCA (Trust Account) Regulations 2008, Reg 11 / Reg 12(1)"
SEVERITY = "CRITICAL"


def make_bulk_deposit_rule(
    allocations: list[Record],
    client_ledger: list[Record] | None = None,
    bulk_min_nzd: float = 0.0,
):
    """
    Factory - returns a RuleProtocol for bulk deposit allocation checking.

    allocations:   all records from allocations.csv (bank_line_id, ledger_entry_id, amount_nzd)
    client_ledger: optional list of client_ledger Records used to verify that
                   ledger_entry_ids in allocations exist. Pass None to skip.
    bulk_min_nzd:  minimum credit amount to check (0.0 = check all credit lines).
    """
    # Group allocations by bank_line_id
    _alloc_by_line: dict[str, list[Record]] = {}
    for rec in allocations:
        bid = rec.data.get("bank_line_id", rec.record_id)
        _alloc_by_line.setdefault(bid, []).append(rec)

    # Build ledger entry_id set for existence checks
    _ledger_ids: set[str] | None = (
        {r.record_id for r in client_ledger} if client_ledger is not None else None
    )

    def _rule(record: Record) -> TrustRuleResult:
        credit = float(record.data.get("credit_nzd", 0.0) or 0.0)

        if credit == 0.0:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="debit-only line - rule not applicable",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        if bulk_min_nzd > 0.0 and credit < bulk_min_nzd:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence=(
                    f"credit ${credit:,.2f} below bulk threshold "
                    f"${bulk_min_nzd:,.2f} - rule not applicable"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        alloc_records = _alloc_by_line.get(record.record_id, [])

        if not alloc_records:
            matched = record.data.get("matched_ledger_entry", "")
            if matched:
                return TrustRuleResult(
                    rule_id=RULE_ID, passed=True, record_id=record.record_id,
                    evidence=f"1:1 deposit - matched to ledger entry {matched!r}",
                    nzls_ref=NZLS_REF, severity=SEVERITY,
                )
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"bank line {record.record_id} "
                    f"({record.data.get('transaction_date', '?')}): "
                    f"credit=${credit:,.2f} NZD - zero allocations and no matched "
                    f"ledger entry (Reg 11 / Reg 12(1) breach)"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        # Check for invalid ledger_entry_ids
        if _ledger_ids is not None:
            invalid = [
                r.data.get("ledger_entry_id", "?")
                for r in alloc_records
                if r.data.get("ledger_entry_id", "?") not in _ledger_ids
            ]
            if invalid:
                return TrustRuleResult(
                    rule_id=RULE_ID, passed=False, record_id=record.record_id,
                    evidence=(
                        f"bank line {record.record_id}: "
                        f"credit=${credit:,.2f} NZD - "
                        f"allocation ledger_entry_id(s) not found in client ledger: "
                        f"{invalid} (Reg 11 / Reg 12(1) breach)"
                    ),
                    nzls_ref=NZLS_REF, severity=SEVERITY,
                )

        alloc_sum = round(
            sum(float(r.data.get("amount_nzd", 0.0) or 0.0) for r in alloc_records),
            2,
        )
        credit_rounded = round(credit, 2)

        if alloc_sum != credit_rounded:
            direction = "under" if alloc_sum < credit_rounded else "over"
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"bank line {record.record_id} "
                    f"({record.data.get('transaction_date', '?')}): "
                    f"credit=${credit_rounded:,.2f} NZD, "
                    f"allocations sum=${alloc_sum:,.2f} NZD ({len(alloc_records)} rows) - "
                    f"{direction}-allocated (Reg 11 / Reg 12(1) breach)"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=(
                f"credit ${credit_rounded:,.2f} NZD fully allocated "
                f"across {len(alloc_records)} ledger entr"
                f"{'y' if len(alloc_records) == 1 else 'ies'}"
            ),
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
