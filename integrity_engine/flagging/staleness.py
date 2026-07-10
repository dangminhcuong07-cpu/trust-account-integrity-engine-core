"""
Staleness and invalidity flagging.

Two patterns extracted from the trading system:

1. Age-based staleness — phase3b_runner._annotate_open_trades():
   "record open for more than N calendar days is stale."
   Generalised: any record older than a configurable threshold is flagged.

2. Change-log invalidation — invalidate_stale_labels.py:
   "a human judgment made against a since-changed upstream record is no
   longer valid; preserve the original value for audit, record why."
   Generalised: given a set of upstream IDs that have changed,
   find all dependent records and flag them as stale.

Both patterns share a principle: the original record is preserved for audit
(never deleted); only the validity flag is cleared, and a reason is recorded
explaining why, with a source reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence


@dataclass
class InvalidationResult:
    """
    Result of a staleness check on one record.

    Attributes
    ----------
    record_id       The source record examined.
    is_stale        True if this record is now stale / invalid.
    reason          Human-readable explanation; required when is_stale=True.
    source_ref      ID of the upstream change that caused staleness (if any).
    original_value  The value that was valid before; preserved for audit.
    """
    record_id: str
    is_stale: bool
    reason: str = ""
    source_ref: str = ""
    original_value: Any = None


class StalenessChecker:
    """
    Flags records as stale using one or both strategies.

    Parameters
    ----------
    max_age_days    Records open longer than this many calendar days are stale.
                    None disables age-based checking.
    reference_date  Date to measure age from. Defaults to today.
    """

    def __init__(
        self,
        max_age_days: int | None = None,
        reference_date: date | None = None,
    ) -> None:
        self._max_age_days = max_age_days
        self._reference_date = reference_date or date.today()

    def check_age(
        self,
        records: Sequence[dict],
        date_field: str,
        id_field: str,
    ) -> list[InvalidationResult]:
        """
        Flag records where (reference_date - date_field) > max_age_days.

        When max_age_days is None all records are returned as non-stale
        (age-based checking is disabled).
        """
        results = []
        for record in records:
            record_id = record[id_field]

            if self._max_age_days is None:
                results.append(InvalidationResult(record_id=record_id, is_stale=False))
                continue

            record_date = date.fromisoformat(record[date_field])
            age_days = (self._reference_date - record_date).days
            is_stale = age_days > self._max_age_days

            results.append(InvalidationResult(
                record_id=record_id,
                is_stale=is_stale,
                reason=(
                    f"open {age_days} days (threshold {self._max_age_days})"
                    if is_stale else ""
                ),
            ))
        return results

    def check_upstream_changes(
        self,
        records: Sequence[dict],
        id_field: str,
        upstream_changed_ids: set[str],
        upstream_id_field: str,
        validity_field: str,
        note_field: str,
        invalidation_note: str,
    ) -> list[InvalidationResult]:
        """
        Flag records whose upstream record has changed.

        For each record whose upstream_id_field value is in upstream_changed_ids,
        the record is stale: original_value captures the validity_field value
        before invalidation (for audit), source_ref captures the upstream ID
        that triggered the invalidation.

        Records not linked to a changed upstream are returned as non-stale.
        This method does NOT mutate the input records — callers apply the
        returned results to their persistence layer as they see fit.
        """
        results = []
        for record in records:
            record_id = record[id_field]
            upstream_id = str(record.get(upstream_id_field, ""))
            is_stale = upstream_id in upstream_changed_ids

            results.append(InvalidationResult(
                record_id=record_id,
                is_stale=is_stale,
                reason=invalidation_note if is_stale else "",
                source_ref=upstream_id if is_stale else "",
                original_value=record.get(validity_field) if is_stale else None,
            ))
        return results
