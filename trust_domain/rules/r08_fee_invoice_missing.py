"""
R08_FEE_INVOICE_MISSING

Flag any client ledger entry where:
  (a) description (case-insensitive) contains "fee" or "disbursement",
  (b) payment_nzd > 0,
  (c) reference field matches ^INV-\\d{5}$ (format is valid), AND
  (d) the invoice_id is absent from invoice_register, OR the matter_ref
      of the matching invoice does not match the ledger entry's matter_ref.

This rule does NOT check reference format (that is R07's domain). Any entry
where the reference is empty or does not match INV-format is skipped here.

Citation verified: 20 Jul 2026 against legislation.govt.nz
(reprint as at 1 Jul 2022).

Scope note: this rule checks only the invoice path of Reg 9(1)(a). Reg 9(1)(b)
permits an alternative basis — a signed, dated client authority — which this rule
cannot currently detect because the ledger schema has no field for it. A debit
properly authorised under 9(1)(b) with no invoice will be a false positive under
this rule until that field is added.

Regulation: LCA (Trust Account) Regulations 2008, Reg 9
Severity:   HIGH
"""

from __future__ import annotations

import re
from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

RULE_ID  = "R08_FEE_INVOICE_MISSING"
NZLS_REF = "LCA (Trust Account) Regulations 2008, Reg 9"
SEVERITY = "HIGH"

_INVOICE_RE = re.compile(r"^INV-\d{5}$")
_FEE_TERMS  = ("fee", "disbursement")


def make_fee_invoice_missing_rule(invoice_register: list[Record]):
    """
    Factory - returns a RuleProtocol for fee invoice existence checking.

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
                evidence=f"reference {reference!r} not in INV-format - format check is R07's domain",
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        inv = _inv_by_id.get(reference)
        matter = record.data.get("matter_ref", "?")

        if inv is None:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"entry {record.record_id} (matter {matter}): "
                    f"reference={reference!r}, payment=${payment:,.2f} - "
                    f"invoice {reference} not found in invoice register (Reg 9 breach)"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        inv_matter = inv.data.get("matter_ref", "?")
        if inv_matter != matter:
            return TrustRuleResult(
                rule_id=RULE_ID, passed=False, record_id=record.record_id,
                evidence=(
                    f"entry {record.record_id} (matter {matter}): "
                    f"reference={reference!r} - invoice matter {inv_matter!r} "
                    f"does not match entry matter {matter!r} (Reg 9 breach)"
                ),
                nzls_ref=NZLS_REF, severity=SEVERITY,
            )

        return TrustRuleResult(
            rule_id=RULE_ID, passed=True, record_id=record.record_id,
            evidence=f"invoice {reference} verified in register for matter {matter}",
            nzls_ref=NZLS_REF, severity=SEVERITY,
        )

    return _rule
