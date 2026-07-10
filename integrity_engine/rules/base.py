"""
Rule-evaluation loop and gate-enforcer pattern.

Two complementary patterns extracted from the trading system:

1. RuleEngine — evaluates a list of rules against a record, short-circuits
   on first failure, returns (passed, RuleResult). Generalises filters.py's
   should_skip() / filter_batch() pattern. Rules are config-driven: each rule
   is a callable that receives a Record and returns a RuleResult.

2. GateError / enforce_gates — pre-condition checks that must ALL pass before
   any write is committed. Generalises paper_trade.py's AuditGateError pattern.
   Raises GateError with the failing gate's id; nothing is written on failure.
"""

from __future__ import annotations

from typing import Callable, Sequence

from integrity_engine.core.types import Flag, Record, RuleResult


class GateError(Exception):
    """Raised when a pre-condition gate fails. Always names the failing gate."""


# Type alias: a rule is any callable that takes a Record and returns a RuleResult.
RuleProtocol = Callable[[Record], RuleResult]


class RuleEngine:
    """
    Evaluates an ordered list of rules against records.

    Rules are loaded from config (a list of RuleProtocol callables) rather
    than hardcoded. Per-domain rule sets are config; the evaluation loop is engine.
    """

    def __init__(self, rules: Sequence[RuleProtocol]) -> None:
        self._rules = list(rules)

    def evaluate_one(self, record: Record) -> tuple[bool, RuleResult | None]:
        """
        Run all rules against a single record. Short-circuits on first failure.

        Returns (True, None) if all rules pass.
        Returns (False, RuleResult) with the failing result if any rule fails.
        """
        for rule in self._rules:
            result = rule(record)
            if not result.passed:
                return (False, result)
        return (True, None)

    def evaluate_batch(
        self, records: list[Record]
    ) -> tuple[list[Record], list[tuple[Record, RuleResult]]]:
        """
        Filter a list of records through the rule set.

        Returns (passed, failed) where failed is [(record, result), ...].
        """
        passed_records: list[Record] = []
        failed_records: list[tuple[Record, RuleResult]] = []
        for record in records:
            ok, result = self.evaluate_one(record)
            if ok:
                passed_records.append(record)
            else:
                failed_records.append((record, result))
        return (passed_records, failed_records)

    def evaluate_all(self, record: Record) -> list[RuleResult]:
        """
        Run ALL rules against a record without short-circuiting.
        Returns every RuleResult (pass and fail alike).

        Use this when you want a complete picture of all violations,
        not just the first one (e.g. for exception reports).
        """
        return [rule(record) for rule in self._rules]


def enforce_gates(
    gates: Sequence[tuple[str, Callable[[], None]]],
) -> None:
    """
    Run a sequence of named pre-condition checks.

    Each gate is (gate_id, callable). The callable should raise GateError
    if the condition is not met. Gates run in order; the first failure
    raises GateError immediately and nothing further runs.

    If a gate raises GateError without its gate_id in the message, the
    gate_id is prepended so the failing gate is always identifiable.

    This is the pattern from paper_trade.py's 5-gate enforcer, generalised
    so the gate list is config rather than hardcoded.
    """
    for gate_id, check in gates:
        try:
            check()
        except GateError as exc:
            if gate_id not in str(exc):
                raise GateError(f"{gate_id}: {exc}") from exc
            raise


# ── Built-in example rules (trivial; used by load_rules_from_config) ─────────

def _builtin_always_pass(record: Record) -> RuleResult:
    return RuleResult(rule_id="builtin.always_pass", passed=True, record_id=record.record_id)


def _builtin_always_fail(record: Record) -> RuleResult:
    return RuleResult(
        rule_id="builtin.always_fail",
        passed=False,
        record_id=record.record_id,
        evidence="built-in always-fail rule",
    )


_RULE_REGISTRY: dict[str, RuleProtocol] = {
    "builtin.always_pass": _builtin_always_pass,
    "builtin.always_fail": _builtin_always_fail,
}


def load_rules_from_config(config: list[dict]) -> list[RuleProtocol]:
    """
    Build a list of RuleProtocol callables from a list of rule specs.

    Each spec is a dict with at least "rule_id" matching a registered rule.
    Rules are data, not hardcoded; callers provide the config.

    Example:
        load_rules_from_config([{"rule_id": "builtin.always_pass"}])
    """
    return [_RULE_REGISTRY[spec["rule_id"]] for spec in config]
