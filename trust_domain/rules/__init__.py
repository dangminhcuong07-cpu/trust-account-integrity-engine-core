"""
Trust-accounting domain rule registry.

Extends the engine's base registry without touching integrity_engine internals.

Usage:
    from trust_domain.rules import load_trust_rules_from_config, RULE_METADATA
    rules = load_trust_rules_from_config([{"rule_id": "R01_OVERDRAWN_CLIENT_LEDGER"}])
"""

from __future__ import annotations

from integrity_engine.rules.base import RuleProtocol
from trust_domain.rules.types import TrustRuleResult  # re-exported for callers

import trust_domain.rules.r01_overdrawn_ledger as _r01
import trust_domain.rules.r02_dormant_balance as _r02
import trust_domain.rules.r03_reconciliation as _r03
import trust_domain.rules.r04_unmatched_bank_line as _r04
import trust_domain.rules.r05_unreconciled_ageing as _r05
import trust_domain.rules.r06_fit_overheld as _r06
import trust_domain.rules.r07_fee_without_invoice as _r07
import trust_domain.rules.r08_fee_invoice_missing as _r08
import trust_domain.rules.r09_fee_exceeds_invoice as _r09
import trust_domain.rules.r10_invoice_postdates_payment as _r10
import trust_domain.rules.r12_bulk_deposit_unallocated as _r12

__all__ = ["TrustRuleResult", "RULE_METADATA", "load_trust_rules_from_config"]


# Per-rule metadata (used when building a config-driven pipeline).
RULE_METADATA: dict[str, dict] = {
    "R01_OVERDRAWN_CLIENT_LEDGER": {
        "rule_id":   "R01_OVERDRAWN_CLIENT_LEDGER",
        "label":     "Overdrawn client ledger entry",
        "nzls_ref":  _r01.NZLS_REF,
        "severity":  _r01.SEVERITY,
        "dataset":   "client_ledger",
        "mode":      "evaluate_all",
    },
    "R02_DORMANT_BALANCE": {
        "rule_id":   "R02_DORMANT_BALANCE",
        "label":     "Dormant balance — no activity exceeds threshold",
        "nzls_ref":  _r02.NZLS_REF,
        "severity":  _r02.SEVERITY,
        "dataset":   "matter_register",
        "mode":      "evaluate_all",
    },
    "R03_RECON_BREAK": {
        "rule_id":   "R03_RECON_BREAK",
        "label":     "Reconciliation break — ledger does not equal bank balance",
        "nzls_ref":  _r03.NZLS_REF,
        "severity":  _r03.SEVERITY,
        "dataset":   "reconciliation_summary",
        "mode":      "evaluate_all",
    },
    "R04_UNMATCHED_BANK_LINE": {
        "rule_id":   "R04_UNMATCHED_BANK_LINE",
        "label":     "Bank line with no matching ledger entry",
        "nzls_ref":  _r04.NZLS_REF,
        "severity":  _r04.SEVERITY,
        "dataset":   "trust_bank_statement",
        "mode":      "evaluate_all",
    },
    "R05_UNRECONCILED_AGEING": {
        "rule_id":   "R05_UNRECONCILED_AGEING",
        "label":     "Unreconciled ledger entry exceeds age threshold",
        "nzls_ref":  _r05.NZLS_REF,
        "severity":  _r05.SEVERITY,
        "dataset":   "client_ledger",
        "mode":      "evaluate_all",
    },
    "R06_FIT_OVERHELD": {
        "rule_id":   "R06_FIT_OVERHELD",
        "label":     "FIT balance held beyond transfer deadline",
        "nzls_ref":  _r06.NZLS_REF,
        "severity":  _r06.SEVERITY,
        "dataset":   "matter_register",
        "mode":      "evaluate_all",
    },
    "R07_FEE_WITHOUT_INVOICE": {
        "rule_id":   "R07_FEE_WITHOUT_INVOICE",
        "label":     "Fee or disbursement entry lacks valid invoice reference",
        "nzls_ref":  _r07.NZLS_REF,
        "severity":  _r07.SEVERITY,
        "dataset":   "client_ledger",
        "mode":      "evaluate_all",
    },
    "R08_FEE_INVOICE_MISSING": {
        "rule_id":   "R08_FEE_INVOICE_MISSING",
        "label":     "Fee invoice reference not found in invoice register",
        "nzls_ref":  _r08.NZLS_REF,
        "severity":  _r08.SEVERITY,
        "dataset":   "client_ledger",
        "mode":      "evaluate_all",
    },
    "R09_FEE_EXCEEDS_INVOICE": {
        "rule_id":   "R09_FEE_EXCEEDS_INVOICE",
        "label":     "Fee payment exceeds authorised invoice amount",
        "nzls_ref":  _r09.NZLS_REF,
        "severity":  _r09.SEVERITY,
        "dataset":   "client_ledger",
        "mode":      "evaluate_all",
    },
    "R10_INVOICE_POSTDATES_PAYMENT": {
        "rule_id":   "R10_INVOICE_POSTDATES_PAYMENT",
        "label":     "Invoice issue date is after the fee payment date",
        "nzls_ref":  _r10.NZLS_REF,
        "severity":  _r10.SEVERITY,
        "dataset":   "client_ledger",
        "mode":      "evaluate_all",
    },
    "R12_BULK_DEPOSIT_UNALLOCATED": {
        "rule_id":   "R12_BULK_DEPOSIT_UNALLOCATED",
        "label":     "Bulk bank deposit not fully allocated to client ledger entries",
        "nzls_ref":  _r12.NZLS_REF,
        "severity":  _r12.SEVERITY,
        "dataset":   "trust_bank_statement",
        "mode":      "evaluate_all",
    },
}

# Default callable registry (parameterizable rules use date.today() defaults).
# R08/R09/R10/R12 require supplementary datasets; use load_trust_rules_from_config
# rather than this registry directly for those rules.
_TRUST_RULE_REGISTRY: dict[str, RuleProtocol] = {
    "R01_OVERDRAWN_CLIENT_LEDGER": _r01.overdrawn_ledger,
    "R02_DORMANT_BALANCE":         _r02.make_dormant_rule(),
    "R03_RECON_BREAK":             _r03.recon_break,
    "R04_UNMATCHED_BANK_LINE":     _r04.make_unmatched_rule(),
    "R05_UNRECONCILED_AGEING":     _r05.make_ageing_rule(),
    "R06_FIT_OVERHELD":            _r06.make_fit_rule(),
    "R07_FEE_WITHOUT_INVOICE":     _r07.fee_without_invoice,
    # R08-R12 defaults (empty datasets — callers must pass datasets via load_trust_rules_from_config)
    "R08_FEE_INVOICE_MISSING":     _r08.make_fee_invoice_missing_rule([]),
    "R09_FEE_EXCEEDS_INVOICE":     _r09.make_fee_exceeds_invoice_rule([]),
    "R10_INVOICE_POSTDATES_PAYMENT": _r10.make_invoice_postdates_rule([]),
    "R12_BULK_DEPOSIT_UNALLOCATED":  _r12.make_bulk_deposit_rule([]),
}


def load_trust_rules_from_config(
    config: list[dict],
    *,
    invoice_register: list | None = None,
    allocations: list | None = None,
    client_ledger: list | None = None,
) -> list[RuleProtocol]:
    """
    Build trust-domain rule callables from a list of rule-spec dicts.

    Each spec must have "rule_id". Optional keys:
      "dormancy_days"   (R02) override inactivity threshold
      "age_days"        (R04, R05) override bank-line / ledger age threshold
      "fit_days"        (R06) override FIT transfer deadline
      "bulk_min_nzd"    (R12) minimum credit amount to check

    Supplementary datasets (keyword-only):
      invoice_register  required for R08/R09/R10; defaults to empty list
      allocations       required for R12; defaults to empty list
      client_ledger     optional for R12 ledger-entry existence checks

    Example:
        load_trust_rules_from_config(
            [{"rule_id": "R02_DORMANT_BALANCE", "dormancy_days": 180}],
        )
    """
    _inv_reg = invoice_register or []
    _allocs  = allocations or []

    rules: list[RuleProtocol] = []
    for spec in config:
        rid = spec["rule_id"]
        if rid == "R02_DORMANT_BALANCE":
            rules.append(_r02.make_dormant_rule(
                max_inactive_days=spec.get("dormancy_days", 365)
            ))
        elif rid == "R04_UNMATCHED_BANK_LINE":
            rules.append(_r04.make_unmatched_rule(
                max_age_days=spec.get("age_days", 5)
            ))
        elif rid == "R05_UNRECONCILED_AGEING":
            rules.append(_r05.make_ageing_rule(
                max_days=spec.get("age_days", 30)
            ))
        elif rid == "R06_FIT_OVERHELD":
            rules.append(_r06.make_fit_rule(
                max_days=spec.get("fit_days", 14)
            ))
        elif rid == "R08_FEE_INVOICE_MISSING":
            rules.append(_r08.make_fee_invoice_missing_rule(_inv_reg))
        elif rid == "R09_FEE_EXCEEDS_INVOICE":
            rules.append(_r09.make_fee_exceeds_invoice_rule(_inv_reg))
        elif rid == "R10_INVOICE_POSTDATES_PAYMENT":
            rules.append(_r10.make_invoice_postdates_rule(_inv_reg))
        elif rid == "R12_BULK_DEPOSIT_UNALLOCATED":
            rules.append(_r12.make_bulk_deposit_rule(
                allocations=_allocs,
                client_ledger=client_ledger,
                bulk_min_nzd=spec.get("bulk_min_nzd", 0.0),
            ))
        else:
            rules.append(_TRUST_RULE_REGISTRY[rid])
    return rules
