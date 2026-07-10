"""
Trust-domain result type, separated to avoid circular imports.

All rule modules import TrustRuleResult from here, not from __init__.
"""

from __future__ import annotations

from dataclasses import dataclass
from integrity_engine.core.types import RuleResult


@dataclass
class TrustRuleResult(RuleResult):
    """
    RuleResult extended with NZ trust-accounting metadata.

    nzls_ref  Regulation / guideline that mandates this check.
    severity  CRITICAL | HIGH | MEDIUM | LOW
    label     Human-readable rule name (populated by report layer from RULE_METADATA)
    """
    nzls_ref: str = ""
    severity: str = ""
    label:    str = ""
