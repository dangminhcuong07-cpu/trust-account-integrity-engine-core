"""
Tests for integrity_engine.stats.
"""

import pytest
from integrity_engine.stats.bins import BinResult, ExceptionStats, elkan_threshold


# ── Scaffold ──────────────────────────────────────────────────────────────────

def test_scaffold_importable():
    from integrity_engine.stats import BinResult, ExceptionStats
    assert ExceptionStats is not None


# ── elkan_threshold ───────────────────────────────────────────────────────────

def test_elkan_threshold_formula():
    """Elkan formula is trivial and implemented immediately — no skip."""
    assert elkan_threshold(fp_cost=1.0, fn_cost=2.0) == pytest.approx(1 / 3)
    assert elkan_threshold(fp_cost=1.0, fn_cost=1.0) == pytest.approx(0.5)


# ── ExceptionStats.compute ────────────────────────────────────────────────────

def test_exception_rate_computed_per_bin():
    stats = ExceptionStats(bins=[
        ("0–10", 0.0, 10.0),
        ("10–20", 10.0, 20.0),
    ])
    records = [
        {"amount": 5.0, "has_exception": True},
        {"amount": 5.0, "has_exception": False},
        {"amount": 15.0, "has_exception": True},
    ]
    results = stats.compute(records, value_field="amount", exception_field="has_exception")
    assert len(results) == 2
    bin0 = results[0]
    assert bin0.count == 2
    assert bin0.exception_count == 1
    assert bin0.exception_rate == pytest.approx(0.5)
    bin1 = results[1]
    assert bin1.count == 1
    assert bin1.exception_rate == pytest.approx(1.0)


def test_empty_bin_has_none_exception_rate():
    """A bin with no records produces exception_rate=None, not a ZeroDivisionError."""
    stats = ExceptionStats(bins=[("0–10", 0.0, 10.0), ("10–20", 10.0, 20.0)])
    records = [{"amount": 5.0, "has_exception": False}]
    results = stats.compute(records, value_field="amount", exception_field="has_exception")
    assert results[0].count == 1
    assert results[1].count == 0
    assert results[1].exception_rate is None


def test_stale_field_excludes_records_from_count():
    """Stale records are counted in stale_count, not in count or exception_count."""
    stats = ExceptionStats(bins=[("0–10", 0.0, 10.0)])
    records = [
        {"amount": 5.0, "has_exception": True,  "is_stale": True},   # excluded
        {"amount": 5.0, "has_exception": True,  "is_stale": False},  # active, exception
        {"amount": 5.0, "has_exception": False, "is_stale": False},  # active, no exception
    ]
    results = stats.compute(
        records,
        value_field="amount",
        exception_field="has_exception",
        stale_field="is_stale",
    )
    b = results[0]
    assert b.count == 2
    assert b.exception_count == 1
    assert b.stale_count == 1
    assert b.exception_rate == pytest.approx(0.5)


def test_records_outside_all_bins_are_ignored():
    stats = ExceptionStats(bins=[("0–10", 0.0, 10.0)])
    records = [
        {"amount": 5.0,  "has_exception": True},   # in bin
        {"amount": 50.0, "has_exception": True},   # outside all bins
    ]
    results = stats.compute(records, value_field="amount", exception_field="has_exception")
    assert results[0].count == 1   # only the in-bin record counts


def test_bin_labels_and_bounds_preserved():
    stats = ExceptionStats(bins=[("low", 0.0, 5.0), ("high", 5.0, 10.0)])
    results = stats.compute([], value_field="v", exception_field="e")
    assert results[0].label == "low"
    assert results[0].lower == 0.0
    assert results[0].upper == 5.0
    assert results[1].label == "high"
