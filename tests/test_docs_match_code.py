"""Documentation must agree with the code it describes.

The rule count and severities drifted across README, .claude/CLAUDE.md and
outreach material (7, 11, 12, 13 and 14 rules; five wrong severities in
CLAUDE.md), and a wrong fact in CLAUDE.md is repeated by every Claude session
that reads it. These tests fail as soon as a documented rule table, or the
README's rule count, disagrees with RULE_METADATA.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from trust_domain.rules import RULE_METADATA

ROOT = Path(__file__).resolve().parent.parent
CODE = {rule_id[:3]: meta["severity"] for rule_id, meta in RULE_METADATA.items()}
DOCS_WITH_RULE_TABLES = ["README.md", ".claude/CLAUDE.md"]
_ROW = re.compile(r"^\|\s*(R\d\d)\s*\|[^|]*\|\s*(CRITICAL|HIGH)\s*\|", re.M)


@pytest.mark.parametrize("doc", DOCS_WITH_RULE_TABLES)
def test_rule_table_matches_code(doc):
    rows = dict(_ROW.findall((ROOT / doc).read_text(encoding="utf-8")))
    assert rows, f"no rule table found in {doc}"
    assert set(rows) == set(CODE), f"{doc} lists {sorted(rows)}, code has {sorted(CODE)}"
    wrong = {r: (rows[r], CODE[r]) for r in rows if rows[r] != CODE[r]}
    assert not wrong, f"{doc} severities (doc, code): {wrong}"


def test_readme_states_the_real_rule_count():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"evaluates {len(RULE_METADATA)} deterministic compliance rules" in readme
