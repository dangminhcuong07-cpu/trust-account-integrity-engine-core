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
}

# Default callable registry (parameterizable rules use date.today() defaults).
_TRUST_RULE_REGISTRY: dict[str, RuleProtocol] = {
    "R01_OVERDRAWN_CLIENT_LEDGER": _r01.overdrawn_ledger,
    "R02_DORMANT_BALANCE":         _r02.make_dormant_rule(),
    "R03_RECON_BREAK":             _r03.recon_break,
    "R04_UNMATCHED_BANK_LINE":     _r04.make_unmatched_rule(),
    "R05_UNRECONCILED_AGEING":     _r05.make_ageing_rule(),
    "R06_FIT_OVERHELD":            _r06.make_fit_rule(),
    "R07_FEE_WITHOUT_INVOICE":     _r07.fee_without_invoice,
}


def load_trust_rules_from_config(config: list[dict]) -> list[RuleProtocol]:
    """
    Build trust-domain rule callables from a list of rule-spec dicts.

    Each spec must have "rule_id". Optional keys:
      "dormancy_days"   (R02) override inactivity threshold
      "age_days"        (R05) override ageing threshold
      "fit_days"        (R06) override FIT transfer deadline
      "age_days"        (R04) override bank-line age threshold

    Example:
        load_trust_rules_from_config([
            {"rule_id": "R02_DORMANT_BALANCE", "dormancy_days": 180},
        ])
    """
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
        else:
            rules.append(_TRUST_RULE_REGISTRY[rid])
    return rules
