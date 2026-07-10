"""
Exception-rate statistics and bin analysis.

Repurposed from calibrator.py's compute_bins() and elkan_threshold().

In the trading system, bins measured classifier accuracy per confidence band.
Here, bins measure exception rates per stratum of a numeric field — for example:
  - "what fraction of client balances in the $0–$10k band are unreconciled?"
  - "what fraction of trust ledger entries aged 0–30 days have exceptions?"

The Elkan threshold formula is retained as a domain-agnostic tool for
recommending an action threshold given asymmetric error costs:
    tau* = FP_cost / (FP_cost + FN_cost)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass
class BinResult:
    """Statistics for one stratum (bin) of a numeric field."""
    label: str              # e.g. "0–30 days"
    lower: float
    upper: float
    count: int              # non-stale records in this bin
    exception_count: int    # non-stale records in this bin with a flag
    exception_rate: float | None   # exception_count / count, or None if count=0
    stale_count: int = 0    # records excluded because they are stale/invalid
    recommended_action: str = ""


class ExceptionStats:
    """
    Bin records by a numeric field and compute per-bin exception rates.

    Parameters
    ----------
    bins    List of (label, lower_inclusive, upper_exclusive) tuples defining strata.
    """

    def __init__(self, bins: list[tuple[str, float, float]]) -> None:
        self._bins = bins

    def compute(
        self,
        records: Sequence[dict],
        value_field: str,
        exception_field: str,
        stale_field: str | None = None,
    ) -> list[BinResult]:
        """
        Compute per-bin exception rates.

        Parameters
        ----------
        records         The records to analyse.
        value_field     Numeric field used to assign records to bins.
        exception_field Boolean/int field; truthy = this record has an exception.
        stale_field     Optional field; truthy = record excluded from counts
                        (tracked in stale_count but not in count or exception_count).

        Records whose value_field falls outside all bins are ignored.
        Returns a BinResult per bin, ordered as defined in __init__.
        """
        results = []
        for label, lower, upper in self._bins:
            in_bin = [
                r for r in records
                if lower <= (r.get(value_field) or 0.0) < upper
            ]

            if stale_field:
                stale = [r for r in in_bin if r.get(stale_field)]
                active = [r for r in in_bin if not r.get(stale_field)]
            else:
                stale = []
                active = in_bin

            count = len(active)
            exception_count = sum(1 for r in active if r.get(exception_field))
            exception_rate = (exception_count / count) if count > 0 else None

            results.append(BinResult(
                label=label,
                lower=lower,
                upper=upper,
                count=count,
                exception_count=exception_count,
                exception_rate=exception_rate,
                stale_count=len(stale),
            ))
        return results


def elkan_threshold(fp_cost: float = 1.0, fn_cost: float = 2.0) -> float:
    """
    Elkan (2001) optimal decision threshold.

        tau* = FP_cost / (FP_cost + FN_cost)

    With FP=1, FN=2: tau* ≈ 0.333
    """
    return fp_cost / (fp_cost + fn_cost)
