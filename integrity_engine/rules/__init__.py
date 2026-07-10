"""Rule-evaluation loop and gate-enforcer pattern."""

from integrity_engine.rules.base import (
    GateError,
    RuleEngine,
    RuleProtocol,
    enforce_gates,
    load_rules_from_config,
)

__all__ = [
    "RuleProtocol",
    "RuleEngine",
    "GateError",
    "enforce_gates",
    "load_rules_from_config",
]
