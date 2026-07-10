"""
Tests for integrity_engine.rules.
"""

import pytest
from integrity_engine.core.types import Record, RuleResult
from integrity_engine.rules.base import GateError, RuleEngine


def _always_pass(record: Record) -> RuleResult:
    return RuleResult(rule_id="ALWAYS_PASS", passed=True, record_id=record.record_id)


def _always_fail(record: Record) -> RuleResult:
    return RuleResult(
        rule_id="ALWAYS_FAIL", passed=False,
        record_id=record.record_id, evidence="forced failure",
    )


# ── Scaffold smoke test ───────────────────────────────────────────────────────

def test_scaffold_importable():
    """Package structure is importable before any logic is migrated."""
    from integrity_engine.rules import GateError, RuleEngine, RuleProtocol
    assert RuleEngine is not None


# ── evaluate_one ─────────────────────────────────────────────────────────────

def test_rule_engine_passes_all_rules():
    engine = RuleEngine(rules=[_always_pass])
    record = Record(record_id="r1", data={})
    passed, result = engine.evaluate_one(record)
    assert passed is True
    assert result is None


def test_rule_engine_short_circuits_on_first_failure():
    called = []

    def _track(record: Record) -> RuleResult:
        called.append("track")
        return RuleResult(rule_id="TRACK", passed=True, record_id=record.record_id)

    engine = RuleEngine(rules=[_always_fail, _track])
    record = Record(record_id="r1", data={})
    passed, result = engine.evaluate_one(record)
    assert passed is False
    assert result.rule_id == "ALWAYS_FAIL"
    assert "track" not in called   # second rule never ran


# ── evaluate_all ─────────────────────────────────────────────────────────────

def test_evaluate_all_returns_all_results_without_short_circuit():
    """evaluate_all must visit every rule even after a failure."""
    engine = RuleEngine(rules=[_always_fail, _always_pass])
    record = Record(record_id="r1", data={})
    results = engine.evaluate_all(record)
    assert len(results) == 2
    assert results[0].rule_id == "ALWAYS_FAIL"
    assert results[0].passed is False
    assert results[1].rule_id == "ALWAYS_PASS"
    assert results[1].passed is True


# ── enforce_gates ─────────────────────────────────────────────────────────────

def test_gate_error_names_failing_gate():
    from integrity_engine.rules.base import enforce_gates

    def _bad_gate():
        raise GateError("GATE_TEST FAIL: something wrong")

    with pytest.raises(GateError, match="GATE_TEST"):
        enforce_gates([("GATE_TEST", _bad_gate)])


def test_enforce_gates_prepends_gate_id_when_missing():
    """If the GateError message omits the gate_id, enforce_gates adds it."""
    from integrity_engine.rules.base import enforce_gates

    def _silent_gate():
        raise GateError("something went wrong without an id")

    with pytest.raises(GateError, match="MY_GATE"):
        enforce_gates([("MY_GATE", _silent_gate)])


def test_enforce_gates_passes_when_all_gates_ok():
    from integrity_engine.rules.base import enforce_gates

    enforce_gates([("GATE_OK", lambda: None)])  # must not raise


# ── load_rules_from_config ────────────────────────────────────────────────────

def test_load_rules_from_config_produces_working_engine():
    """Config-loaded rules evaluate correctly via RuleEngine."""
    from integrity_engine.rules.base import load_rules_from_config

    config = [{"rule_id": "builtin.always_pass"}]
    rules = load_rules_from_config(config)
    engine = RuleEngine(rules=rules)
    record = Record(record_id="r1", data={})
    passed, result = engine.evaluate_one(record)
    assert passed is True
    assert result is None


def test_load_rules_from_config_fail_rule():
    """Config-loaded always-fail rule causes evaluate_one to return failure."""
    from integrity_engine.rules.base import load_rules_from_config

    config = [{"rule_id": "builtin.always_fail"}]
    rules = load_rules_from_config(config)
    engine = RuleEngine(rules=rules)
    record = Record(record_id="r2", data={})
    passed, result = engine.evaluate_one(record)
    assert passed is False
    assert result is not None
    assert result.rule_id == "builtin.always_fail"
