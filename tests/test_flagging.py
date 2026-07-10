"""
Tests for integrity_engine.flagging.
"""

import pytest
from datetime import date
from integrity_engine.flagging.staleness import InvalidationResult, StalenessChecker


# ── Scaffold ──────────────────────────────────────────────────────────────────

def test_scaffold_importable():
    from integrity_engine.flagging import InvalidationResult, StalenessChecker
    assert StalenessChecker is not None


# ── check_age ─────────────────────────────────────────────────────────────────

def test_age_based_staleness_flags_old_records():
    checker = StalenessChecker(max_age_days=10, reference_date=date(2026, 6, 22))
    records = [
        {"id": "r1", "opened_date": "2026-06-01"},   # 21 days — stale
        {"id": "r2", "opened_date": "2026-06-20"},   # 2 days — OK
    ]
    results = checker.check_age(records, date_field="opened_date", id_field="id")
    stale = [r for r in results if r.is_stale]
    ok    = [r for r in results if not r.is_stale]
    assert len(stale) == 1 and stale[0].record_id == "r1"
    assert len(ok)    == 1 and ok[0].record_id    == "r2"


def test_check_age_reason_includes_day_count():
    checker = StalenessChecker(max_age_days=5, reference_date=date(2026, 6, 22))
    records = [{"id": "r1", "opened_date": "2026-06-10"}]   # 12 days — stale
    results = checker.check_age(records, date_field="opened_date", id_field="id")
    assert results[0].is_stale is True
    assert "12" in results[0].reason


def test_check_age_record_at_exactly_threshold_is_not_stale():
    """Record open exactly max_age_days days is not stale (> not >=)."""
    checker = StalenessChecker(max_age_days=10, reference_date=date(2026, 6, 22))
    records = [{"id": "r1", "opened_date": "2026-06-12"}]   # exactly 10 days
    results = checker.check_age(records, date_field="opened_date", id_field="id")
    assert results[0].is_stale is False


def test_check_age_none_max_age_all_clean():
    """When max_age_days is None, age checking is disabled — nothing is stale."""
    checker = StalenessChecker(max_age_days=None, reference_date=date(2026, 6, 22))
    records = [{"id": "r1", "opened_date": "2020-01-01"}]   # ancient — but disabled
    results = checker.check_age(records, date_field="opened_date", id_field="id")
    assert results[0].is_stale is False


# ── check_upstream_changes ────────────────────────────────────────────────────

def test_upstream_change_invalidates_dependent_record():
    checker = StalenessChecker()
    records = [
        {"obs_id": "o1", "announcement_id": "ann42", "valid": 1, "notes": ""},
        {"obs_id": "o2", "announcement_id": "ann99", "valid": 1, "notes": ""},
    ]
    results = checker.check_upstream_changes(
        records=records,
        id_field="obs_id",
        upstream_changed_ids={"ann42"},
        upstream_id_field="announcement_id",
        validity_field="valid",
        note_field="notes",
        invalidation_note="upstream reclassified",
    )
    stale = [r for r in results if r.is_stale]
    assert len(stale) == 1
    assert stale[0].record_id == "o1"
    assert stale[0].original_value == 1    # original validity preserved


def test_upstream_change_leaves_unaffected_records_clean():
    checker = StalenessChecker()
    records = [
        {"obs_id": "o1", "announcement_id": "ann42", "valid": 1, "notes": ""},
        {"obs_id": "o2", "announcement_id": "ann99", "valid": 1, "notes": ""},
    ]
    results = checker.check_upstream_changes(
        records=records,
        id_field="obs_id",
        upstream_changed_ids={"ann42"},
        upstream_id_field="announcement_id",
        validity_field="valid",
        note_field="notes",
        invalidation_note="upstream reclassified",
    )
    clean = [r for r in results if not r.is_stale]
    assert len(clean) == 1
    assert clean[0].record_id == "o2"
    assert clean[0].original_value is None


def test_upstream_change_source_ref_set_to_upstream_id():
    checker = StalenessChecker()
    records = [{"id": "r1", "ann_id": "ann42", "valid": 1, "notes": ""}]
    results = checker.check_upstream_changes(
        records=records,
        id_field="id",
        upstream_changed_ids={"ann42"},
        upstream_id_field="ann_id",
        validity_field="valid",
        note_field="notes",
        invalidation_note="changed",
    )
    assert results[0].source_ref == "ann42"


def test_upstream_change_does_not_mutate_input_records():
    """check_upstream_changes must not modify the source dicts."""
    checker = StalenessChecker()
    records = [{"id": "r1", "ann_id": "ann42", "valid": 1, "notes": ""}]
    original_valid = records[0]["valid"]
    checker.check_upstream_changes(
        records=records,
        id_field="id",
        upstream_changed_ids={"ann42"},
        upstream_id_field="ann_id",
        validity_field="valid",
        note_field="notes",
        invalidation_note="changed",
    )
    assert records[0]["valid"] == original_valid   # unchanged
