"""
Cross-path consistency checker.

This is the generalisation of the _get_candidates() vs _get_recent_high_signals()
divergence documented in the trading system. Both functions were meant to apply
the same eligibility predicate, but they diverged on materiality scope and time
window without the engine noticing.

The pattern generalises to: "given a named predicate (rule), assert it holds
across every dataset or code path where it is supposed to apply."

In the trust-accounting domain this becomes: "given a compliance rule, assert
it is applied to every client account, every ledger entry type, every code path
that touches that account — not just the ones someone remembered to check."

A ConsistencyViolation is raised (or collected) when the same predicate
applied to two supposedly-equivalent datasets produces different results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from integrity_engine.core.types import Record


@dataclass
class ConsistencyViolation:
    """
    Records a case where the same predicate produced different results
    on two paths that were supposed to be equivalent.

    Attributes
    ----------
    predicate_id    Name of the rule / predicate being checked.
    path_a          Label for the first dataset / code path.
    path_b          Label for the second dataset / code path.
    detail          Human-readable explanation of what diverged.
    records_a       record_ids that pass on path_a but not path_b.
    records_b       record_ids that pass on path_b but not path_a.
    """
    predicate_id: str
    path_a: str
    path_b: str
    detail: str
    records_a: list[str] = None   # record_ids
    records_b: list[str] = None   # record_ids

    def __post_init__(self):
        self.records_a = self.records_a or []
        self.records_b = self.records_b or []


# Type alias: a predicate takes a Record, returns True if the record passes.
Predicate = Callable[[Record], bool]


class ConsistencyChecker:
    """
    Assert that a named predicate produces equivalent results across
    multiple datasets or query paths.

    Usage (illustrative):

        checker = ConsistencyChecker()
        violations = checker.check(
            predicate_id="HIGH_SIGNAL_ELIGIBLE",
            predicate=lambda r: r.data["materiality"] == "HIGH" and r.data["confidence"] >= 0.70,
            datasets={
                "log_trade._get_candidates":       candidates_records,
                "phase3b._get_recent_high_signals": recent_records,
            },
        )

    Any record that passes the predicate on one path but is absent or fails
    on another path is surfaced as a ConsistencyViolation.
    """

    def check(
        self,
        predicate_id: str,
        predicate: Predicate,
        datasets: dict[str, Sequence[Record]],
    ) -> list[ConsistencyViolation]:
        """
        Apply predicate to each dataset and surface records where results diverge.

        For each pair of paths (A, B):
        - records_a: record_ids that pass on A but are absent or fail on B
        - records_b: record_ids that pass on B but are absent or fail on A

        Returns a (possibly empty) list of ConsistencyViolation. An empty list
        means the predicate produced consistent results across all datasets.
        """
        # Build passing-record-id set per path
        passing: dict[str, set[str]] = {
            path_name: {r.record_id for r in records if predicate(r)}
            for path_name, records in datasets.items()
        }

        path_names = list(passing.keys())
        violations: list[ConsistencyViolation] = []

        for i in range(len(path_names)):
            for j in range(i + 1, len(path_names)):
                name_a = path_names[i]
                name_b = path_names[j]
                set_a = passing[name_a]
                set_b = passing[name_b]

                only_in_a = sorted(set_a - set_b)
                only_in_b = sorted(set_b - set_a)

                if not only_in_a and not only_in_b:
                    continue

                parts: list[str] = []
                if only_in_a:
                    parts.append(
                        f"{len(only_in_a)} record(s) pass on '{name_a}' but not '{name_b}': {only_in_a}"
                    )
                if only_in_b:
                    parts.append(
                        f"{len(only_in_b)} record(s) pass on '{name_b}' but not '{name_a}': {only_in_b}"
                    )

                violations.append(ConsistencyViolation(
                    predicate_id=predicate_id,
                    path_a=name_a,
                    path_b=name_b,
                    detail="; ".join(parts),
                    records_a=only_in_a,
                    records_b=only_in_b,
                ))

        return violations
