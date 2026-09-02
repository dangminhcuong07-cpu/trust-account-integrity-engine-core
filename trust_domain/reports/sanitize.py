"""
CSV/formula-injection defence (CWE-1236) for report output.

Any field sourced from an ingested CSV (a ledger's `description`, `notes`,
or `reference` column) is user-controlled data, not engine-generated text.
If such a value is written verbatim as the entire content of a spreadsheet
cell — a markdown table cell that a user copies into Excel, or a literal
CSV cell — and it starts with =, +, -, or @, Excel (and most spreadsheet
apps) may interpret it as a formula rather than literal text on open or
paste. A malicious or merely careless entry like `=1+1` in a ledger's
reference field would then execute as a formula for whoever opens the
report, rather than displaying as the text it is.

This module provides one function, used at the point a raw field value
becomes the entire content of a spreadsheet-openable cell — never applied
to the underlying JSON/audit data itself, which must stay a faithful,
unmutated record of what was actually ingested.
"""
from __future__ import annotations

_TRIGGER_CHARS = ("=", "+", "-", "@")


def sanitize_for_spreadsheet(value: str) -> str:
    """
    Neutralise a value that would otherwise be interpreted as a formula if
    it became the entire content of a spreadsheet cell.

    Prefixes a leading apostrophe when the first non-whitespace character
    is =, +, -, or @ — the standard, non-destructive mitigation (Excel
    displays the apostrophe-prefixed cell as plain text, and the original
    value, including the prefix character, is still fully visible and
    auditable — nothing is stripped or lost).

    Empty/None values pass through unchanged. Values that don't start with
    a trigger character pass through unchanged.
    """
    if not value:
        return value
    stripped = value.lstrip()
    if stripped and stripped[0] in _TRIGGER_CHARS:
        return "'" + value
    return value
