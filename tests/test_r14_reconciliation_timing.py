"""
Tests for R14_RECONCILIATION_TIMING.

Deadline: 10th working day of the month following period_end_date's month
(15th working day of January if that following month is January).
Working day = Mon-Fri only; no public holiday calendar in v1 (see the rule
module's docstring for the simplification note).

Fixture dates were computed directly (Mon-Fri counting from the 1st of the
month), not eyeballed from a calendar:
  - 10th working day of April 2026  = 2026-04-14
  - 10th working day of July 2026   = 2026-07-14
  - 15th working day of January 2027 = 2027-01-21
"""

from __future__ import annotations

from integrity_engine.core.types import Record
from trust_domain.rules.r14_reconciliation_timing import (
    dataset_has_column,
    make_reconciliation_timing_rule,
)


def _recon_record(recon_id: str, period_end: str, reconciliation_date: str) -> Record:
    return Record(
        record_id=recon_id,
        data={
            "recon_id": recon_id,
            "period_end_date": period_end,
            "reconciliation_date": reconciliation_date,
        },
    )


class TestOnTime:
    def test_on_time_standard_month_passes(self):
        rule = make_reconciliation_timing_rule()
        # Period end March 2026 -> deadline is 10th working day of April 2026 = 2026-04-14
        rec = _recon_record("R101", "2026-03-31", "2026-04-10")
        result = rule(rec)
        assert result.passed


class TestLateStandardMonth:
    def test_late_standard_month_violation(self):
        rule = make_reconciliation_timing_rule()
        # Period end June 2026 -> deadline is 10th working day of July 2026 = 2026-07-14
        rec = _recon_record("R102", "2026-06-30", "2026-07-20")
        result = rule(rec)
        assert not result.passed
        assert "Regulation 14" in result.evidence
        assert "2026-07-20" in result.evidence
        assert "2026-07-14" in result.evidence


class TestJanuaryEdgeCase:
    def test_late_december_to_january_violation(self):
        rule = make_reconciliation_timing_rule()
        # Period end December 2026 -> deadline is 15th working day of January 2027 = 2027-01-21
        rec = _recon_record("R103", "2026-12-31", "2027-01-25")
        result = rule(rec)
        assert not result.passed
        assert "2027-01-21" in result.evidence

    def test_on_time_december_to_january_passes(self):
        rule = make_reconciliation_timing_rule()
        rec = _recon_record("R104", "2026-12-31", "2027-01-15")
        result = rule(rec)
        assert result.passed


class TestColumnPresenceHelper:
    def test_column_absent_returns_false(self):
        records = [
            Record(record_id="R1", data={"recon_id": "R1", "period_end_date": "2026-03-31"}),
            Record(record_id="R2", data={"recon_id": "R2", "period_end_date": "2026-04-30"}),
        ]
        assert dataset_has_column(records, "reconciliation_date") is False

    def test_column_present_returns_true_even_if_blank_on_some_rows(self):
        records = [
            Record(record_id="R1", data={"recon_id": "R1", "reconciliation_date": ""}),
            Record(record_id="R2", data={"recon_id": "R2", "reconciliation_date": "2026-04-10"}),
        ]
        assert dataset_has_column(records, "reconciliation_date") is True

    def test_empty_dataset_returns_false(self):
        assert dataset_has_column([], "reconciliation_date") is False


class TestBlankValueOnPresentColumn:
    def test_blank_reconciliation_date_on_one_row_passes(self):
        rule = make_reconciliation_timing_rule()
        rec = _recon_record("R105", "2026-03-31", "")
        result = rule(rec)
        assert result.passed
