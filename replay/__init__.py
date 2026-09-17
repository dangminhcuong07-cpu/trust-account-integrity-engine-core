"""
replay — deterministic replay infrastructure for the trust-domain rule engine.

Public API:
    LedgerSnapshot      One firm-month of synthetic ledger records plus the
                        rule IDs a correct engine run must flag.
    ReplayCorpus        A directory of LedgerSnapshot JSON files.
    run_replay          Evaluate a rule set against a corpus; returns
                        precision/recall and false positive/negative detail.
    ReplayResult        The result of a run_replay() call.
    get_current_rule_set  The rule-spec list the engine currently ships,
                        at a given sensitivity mode — what the monotonicity
                        gate (tests/test_replay_monotonicity.py) checks
                        for regressions.
"""

from __future__ import annotations

from replay.engine import (
    LedgerSnapshot,
    ReplayCorpus,
    ReplayResult,
    get_current_rule_set,
    run_replay,
)

__all__ = [
    "LedgerSnapshot",
    "ReplayCorpus",
    "ReplayResult",
    "get_current_rule_set",
    "run_replay",
]
