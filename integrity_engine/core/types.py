"""
Core shared types for the integrity engine.

These are plain dataclasses with no domain knowledge. Every submodule
speaks in these terms so domain layers can be swapped without touching
engine internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Record:
    """One row of source data, as a dict plus its stable identifier."""
    record_id: str
    data: dict[str, Any]


@dataclass
class RuleResult:
    """
    Outcome of evaluating one rule against one record.

    Attributes
    ----------
    rule_id     Stable identifier for the rule (e.g. "R01_RECON_COMPLETE").
    passed      True if the record satisfies the rule.
    record_id   The source record this result applies to.
    evidence    Human-readable explanation; required when passed=False.
    """
    rule_id: str
    passed: bool
    record_id: str
    evidence: str = ""


@dataclass
class Flag:
    """
    An exception surfaced by the engine.

    Every Flag must carry the record_id and rule_id that produced it —
    no anonymous flags ever leave the engine.
    """
    rule_id: str
    record_id: str
    evidence: str
    severity: str = "ERROR"    # ERROR | WARN | INFO
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditEntry:
    """
    One timestamped entry in the audit trail.

    The trail is append-only: state changes produce new entries rather
    than modifying old ones. The source_record_id links every entry
    back to the row that triggered it — no anonymous audit entries.
    """
    entry_id: str
    source_record_id: str
    event_type: str        # e.g. "RULE_EVALUATED", "FLAG_RAISED", "STATE_CHANGED"
    timestamp: str         # ISO-8601
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
