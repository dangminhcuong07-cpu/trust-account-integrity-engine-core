"""
R09_FEE_EXCEEDS_INVOICE

Flag any client ledger entry where:
  (a) description (case-insensitive) contains "fee" or "disbursement",
  (b) payment_nzd > 0,
  (c) reference matches ^INV-\\d{5}$,
  (d) a matching invoice exists in invoice_register with the same matter_ref, AND
  (e) payment_nzd > invoice amount_nzd.

Scope: per-entry check only. Does not aggregate multiple payments against one
invoice. Skip when no matching same-matter invoice is found in invoice_register
(that absence is R08's domain).

Citation status: PROVISIONAL - pending verification against legislation.govt.nz
by the maintainer.

Regulation: LCA (Trust Account) Regulations 2008, Reg 9
Severity:   HIGH
"""

from __future__ import annotations

import re
from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID  = "R09_FEE_EXCEEDS_INVOICE"
NZLS_REF = "LCA (Trust Account) Regulations 2008, Reg 9"
SEVERITY = "HIGH"

_INVOICE_RE = re.compile(r"^INV-\d{5}$")
_FEE_TERMS  = ("fee", "disbursement")


def make_fee_exceeds_invoice_rule(invoice_register: list[Record]):
    """
    Factory - returns a RuleProtocol for fee-exceeds-invoice checking.

    invoice_register: all records loaded from invoice_register.csv
    """
    _inv_by_id: dict[str, Record] = {r.record_id: r for r in invoice_register}

    def _rule(record: Record) -> TrustRuleResult:
        description = record.data.get("description", "")
        if not any(t in description.lower() for t in _FEE_TERMS):
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="not a fee or disbursement entry - rule not applicable",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        payment = float(record.data.get("payment_nzd", 0.0) or 0.0)
        if payment == 0.0:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence="payment=0.00 - not a debit entry",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        reference = (record.data.get("reference") or "").strip()
        if not _INVOICE_RE.match(reference):
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence=f"reference {reference!r} not in INV-format - rule not applicable",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        inv = _inv_by_id.get(reference)
        matter = record.data.get("matter_ref", "?")

        if inv is None or inv.data.get("matter_ref") != matter:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=True, record_id=record.record_id,
                evidence=f"no matching same-matter invoice for {reference!r} - R08's domain",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        inv_amount = float(inv.data.get("amount_nzd", 0.0) or 0.0)
        if payment > inv_amount:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"entry {record.record_id} (matter {matter}): "
                    f"reference={reference!r}, payment=${payment:,.2f} "
                    f"exceeds invoice amount ${inv_amount:,.2f} - "
                    f"fee drawn exceeds authorised invoice (Reg 9 breach)"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=(
                f"payment ${payment:,.2f} within invoice {reference!r} "
                f"amount ${inv_amount:,.2f}"
            ),
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
