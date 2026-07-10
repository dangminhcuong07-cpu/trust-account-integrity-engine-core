"""
R07_FEE_WITHOUT_INVOICE

Flag any client ledger entry where:
  (a) description (case-insensitive) contains "fee" or "disbursement", AND
  (b) the `reference` field is absent or does not match the firm's
      invoice format ^INV-\\d{5}$.

Payment entries without a proper invoice reference indicate a fee or
disbursement has been drawn from trust without a compliant billing record,
in breach of LCA (Trust Account) Regulations 2008, Reg 9.

Regulation: LCA (Trust Account) Regulations 2008, Reg 9
Severity:   HIGH

Citation verified: 10 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).
"""

from __future__ import annotations

import re
from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID       = "R07_FEE_WITHOUT_INVOICE"
NZLS_REF      = "LCA (Trust Account) Regulations 2008, Reg 9"
SEVERITY      = "HIGH"

_INVOICE_RE   = re.compile(r"^INV-\d{5}$")
_FEE_TERMS    = ("fee", "disbursement")


def fee_without_invoice(record: Record) -> TrustRuleResult:
    """Applied to each row of client_ledger.csv."""
    description = record.data.get("description", "")
    desc_lower  = description.lower()
    if not any(t in desc_lower for t in _FEE_TERMS):
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence="not a fee or disbursement entry - rule not applicable",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    payment = record.data.get("payment_nzd", 0.0) or 0.0
    if float(payment) == 0.0:
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence="description matches but payment=0.00 - not a debit entry",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    reference = (record.data.get("reference") or "").strip()
    if _INVOICE_RE.match(reference):
        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=f"invoice reference {reference!r} - valid",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    matter = record.data.get("matter_ref", "?")
    return TrustRuleResult(
        rule_id=RULE_ID, passed=False, record_id=record.record_id,
        evidence=(
            f"entry {record.record_id} (matter {matter}): "
            f"description={description!r}, payment=${float(payment):,.2f}, "
            f"reference={reference!r} - no INV-XXXXX invoice reference found (Reg 9 breach)"
        ),
        nzls_ref=NZLS_REF, severity=SEVERITY,
    )
