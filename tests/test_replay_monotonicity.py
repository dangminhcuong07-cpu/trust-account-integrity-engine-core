"""
CI monotonicity gate (Dream-RSI guarantee).

No rule update may reduce precision or recall below the baseline
established by the synthetic corpus at tests/replay_corpus/synthetic_nz_firm_01/.
This is the Dream-RSI monotonicity guarantee: selected policy >= prior
performance on fixed history.

If this test fails after a genuine, intentional rule-behaviour change, the
fix is to extend or correct the synthetic corpus to reflect the new correct
behaviour (see replay/engine.py's get_current_rule_set() docstring) — never
to lower the 0.95 thresholds below.
"""

from __future__ import annotations

from pathlib import Path

from replay.engine import ReplayCorpus, get_current_rule_set, run_replay

_CORPUS_PATH = Path(__file__).parent / "replay_corpus" / "synthetic_nz_firm_01"


def test_monotonicity_gate():
    corpus = ReplayCorpus.load(_CORPUS_PATH)
    result = run_replay(get_current_rule_set(), corpus)
    assert result.precision >= 0.95, (
        f"Monotonicity gate failed: precision {result.precision:.3f} < 0.95. "
        "Rule update regresses on synthetic corpus."
    )
    assert result.recall >= 0.95, (
        f"Monotonicity gate failed: recall {result.recall:.3f} < 0.95. "
        "Rule update regresses on synthetic corpus."
    )
