"""
Tests for integrity_engine.consistency.
"""

import pytest
from integrity_engine.consistency.checker import ConsistencyChecker, ConsistencyViolation
from integrity_engine.core.types import Record


# ── Scaffold ──────────────────────────────────────────────────────────────────

def test_scaffold_importable():
    from integrity_engine.consistency import ConsistencyChecker, ConsistencyViolation
    assert ConsistencyChecker is not None


# ── Core behaviour ────────────────────────────────────────────────────────────

def test_no_violation_when_datasets_agree():
    checker = ConsistencyChecker()
    predicate = lambda r: r.data.get("eligible", False)
    r1 = Record(record_id="r1", data={"eligible": True})
    r2 = Record(record_id="r2", data={"eligible": False})

    violations = checker.check(
        predicate_id="ELIGIBLE",
        predicate=predicate,
        datasets={"path_a": [r1, r2], "path_b": [r1, r2]},
    )
    assert violations == []


def test_violation_when_datasets_diverge():
    """
    Replicates the _get_candidates / _get_recent_high_signals divergence:
    same predicate, different record sets → ConsistencyViolation raised.
    """
    checker = ConsistencyChecker()
    predicate = lambda r: r.data.get("eligible", False)
    r1 = Record(record_id="r1", data={"eligible": True})
    r2 = Record(record_id="r2", data={"eligible": True})

    violations = checker.check(
        predicate_id="ELIGIBLE",
        predicate=predicate,
        datasets={
            "path_a": [r1, r2],    # both pass
            "path_b": [r1],        # r2 missing — divergence
        },
    )
    assert len(violations) == 1
    assert violations[0].predicate_id == "ELIGIBLE"
    assert "r2" in violations[0].records_a   # r2 in A but not B


# ── Additional coverage ───────────────────────────────────────────────────────

def test_violation_carries_correct_path_labels():
    checker = ConsistencyChecker()
    predicate = lambda r: True
    r1 = Record(record_id="r1", data={})

    violations = checker.check(
        predicate_id="ALWAYS_PASS",
        predicate=predicate,
        datasets={"alpha": [r1], "beta": []},
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.path_a == "alpha"
    assert v.path_b == "beta"
    assert "r1" in v.records_a
    assert v.records_b == []


def test_records_failing_predicate_on_both_paths_no_violation():
    """Records that fail the predicate on every path are not a divergence."""
    checker = ConsistencyChecker()
    predicate = lambda r: r.data.get("eligible", False)
    r_fail = Record(record_id="fail1", data={"eligible": False})

    violations = checker.check(
        predicate_id="ELIGIBLE",
        predicate=predicate,
        datasets={"path_a": [r_fail], "path_b": [r_fail]},
    )
    assert violations == []


def test_three_paths_produces_pairwise_violations():
    """
    With three paths where each has a unique record, we get three pairwise
    violations (A×B, A×C, B×C).
    """
    checker = ConsistencyChecker()
    predicate = lambda r: True
    r1 = Record(record_id="r1", data={})
    r2 = Record(record_id="r2", data={})
    r3 = Record(record_id="r3", data={})

    violations = checker.check(
        predicate_id="ALWAYS_PASS",
        predicate=predicate,
        datasets={
            "path_a": [r1],
            "path_b": [r2],
            "path_c": [r3],
        },
    )
    assert len(violations) == 3


def test_empty_datasets_no_violation():
    checker = ConsistencyChecker()
    violations = checker.check(
        predicate_id="P",
        predicate=lambda r: True,
        datasets={"path_a": [], "path_b": []},
    )
    assert violations == []


def test_violation_detail_is_human_readable():
    checker = ConsistencyChecker()
    predicate = lambda r: True
    r1 = Record(record_id="r1", data={})

    violations = checker.check(
        predicate_id="P",
        predicate=predicate,
        datasets={"alpha": [r1], "beta": []},
    )
    assert len(violations) == 1
    assert "r1" in violations[0].detail
    assert "alpha" in violations[0].detail
