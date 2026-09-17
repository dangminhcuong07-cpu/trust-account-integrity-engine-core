"""
replay/engine.py

Deterministic replay of the trust-domain rule engine against fixed,
version-controlled synthetic ledger snapshots ("golden" firm-months).

Purpose: give the CI monotonicity gate (tests/test_replay_monotonicity.py)
a fixed history to measure precision/recall against, so a future rule
change can be checked for regression before it ships — the Dream-RSI
guarantee: selected policy >= prior performance on fixed history.

No network calls. No filesystem writes (ReplayCorpus.load only reads). No
mutation of caller-supplied rule_set/corpus objects — run_replay is a pure
read -> evaluate -> report function and produces identical results on
every call with the same inputs.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path

from integrity_engine.core.types import Record
from trust_domain.rules import RULE_METADATA, apply_sensitivity, load_trust_rules_from_config
from trust_domain.rules.r14_reconciliation_timing import dataset_has_column

# The field that identifies a record within each dataset. Mirrors
# trust_domain/ingestion/loader.py's _ID_FIELDS — the real CSV ingestion
# path uses the same convention, so a snapshot entry's own natural id field
# (e.g. "entry_id" for client_ledger) doubles as its Record.record_id;
# no separate "record_id" key is needed in the JSON.
_ID_FIELDS: dict[str, str] = {
    "matter_register": "matter_ref",
    "client_ledger": "entry_id",
    "trust_bank_statement": "statement_id",
    "reconciliation_summary": "recon_id",
    "invoice_register": "invoice_id",
    "allocations": "bank_line_id",
}

# Rules that require a supplementary dataset beyond their primary one.
_INVOICE_RULES = frozenset({
    "R08_FEE_INVOICE_MISSING", "R09_FEE_EXCEEDS_INVOICE", "R10_INVOICE_POSTDATES_PAYMENT",
})

# Standard (unscaled) default thresholds — mirrors ClientConfig's field
# defaults in trust_domain/config/schema.py. Duplicated rather than
# imported because ClientConfig requires several unrelated identity fields
# to construct; this mirrors the same duplication already present in
# app.py's _build_toml() defaults.
_STANDARD_THRESHOLDS: dict[str, int | float] = {
    "dormancy_threshold_days": 365,
    "unreconciled_age_days": 30,
    "unmatched_bank_days": 5,
    "fit_transfer_days": 14,
    "bulk_min_nzd": 0.0,
}


@dataclass
class LedgerSnapshot:
    """
    One firm-month of (synthetic) trust-ledger records, plus the rule IDs a
    correct engine run is expected to flag against it.

    Attributes
    ----------
    snapshot_id         Stable identifier, e.g. "synthetic_nz_firm_01_2025-07".
    period_end          The reconciliation period this snapshot represents.
    ledger_entries       Flat list of records across all datasets. Each dict
                         must carry a "dataset" key — one of "matter_register",
                         "client_ledger", "trust_bank_statement",
                         "reconciliation_summary", "invoice_register", or
                         "allocations" — plus that dataset's own internal
                         field names (see docs/DATA_HANDLING_BOUNDARY.md),
                         including its natural id field (e.g. "entry_id" for
                         client_ledger), which doubles as the record's id.
    expected_breaches    Rule IDs (e.g. ["R01_OVERDRAWN_CLIENT_LEDGER"]) a
                         correct engine run must flag at least once against
                         this snapshot.
    metadata             Anonymised context only — firm size category and
                         relative-amount descriptors. Never real names, and
                         never dollar amounts precise enough to identify a
                         real firm.
    """
    snapshot_id: str
    period_end: datetime.date
    ledger_entries: list[dict]
    expected_breaches: list[str]
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "period_end": self.period_end.isoformat(),
            "ledger_entries": self.ledger_entries,
            "expected_breaches": list(self.expected_breaches),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LedgerSnapshot":
        return cls(
            snapshot_id=data["snapshot_id"],
            period_end=datetime.date.fromisoformat(data["period_end"]),
            ledger_entries=list(data["ledger_entries"]),
            expected_breaches=list(data["expected_breaches"]),
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "LedgerSnapshot":
        return cls.from_dict(json.loads(text))


class ReplayCorpus:
    """A named, ordered collection of LedgerSnapshots loaded from a directory."""

    def __init__(self, snapshots: list[LedgerSnapshot]) -> None:
        self._snapshots = list(snapshots)

    @property
    def snapshots(self) -> list[LedgerSnapshot]:
        return list(self._snapshots)

    @classmethod
    def load(cls, path: str | Path) -> "ReplayCorpus":
        """
        Load every *.json file in `path` as a LedgerSnapshot, sorted by
        filename so corpus order is deterministic regardless of the
        filesystem's directory-listing order.
        """
        directory = Path(path)
        if not directory.is_dir():
            raise FileNotFoundError(f"replay corpus directory not found: {directory}")
        files = sorted(directory.glob("*.json"))
        if not files:
            raise FileNotFoundError(f"no snapshot JSON files found in {directory}")
        snapshots = [LedgerSnapshot.from_json(f.read_text(encoding="utf-8")) for f in files]
        return cls(snapshots)

    def __len__(self) -> int:
        return len(self._snapshots)


@dataclass
class ReplayResult:
    """
    Outcome of running a rule set against a ReplayCorpus.

    Attributes
    ----------
    precision         Fraction of flagged rule-breaches that were expected:
                       TP / (TP + FP) across the whole corpus. 1.0 when
                       nothing was flagged at all (no false positives to
                       divide by, vacuously precise).
    recall            Fraction of expected rule-breaches that were flagged:
                       TP / (TP + FN) across the whole corpus. 1.0 when
                       nothing was expected at all.
    false_positives   One entry per snapshot with unexpected fires:
                       {"snapshot_id": ..., "rule_ids": [...]}.
    false_negatives   One entry per snapshot with missed expected breaches:
                       {"snapshot_id": ..., "rule_ids": [...]}.
    per_snapshot      Full breakdown for every snapshot, in corpus order:
                       {"snapshot_id", "expected", "fired", "true_positives",
                       "false_positives", "false_negatives"}.
    """
    precision: float
    recall: float
    false_positives: list[dict]
    false_negatives: list[dict]
    per_snapshot: list[dict]


def _group_entries_by_dataset(entries: list[dict]) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = {name: [] for name in _ID_FIELDS}
    for entry in entries:
        dataset = entry["dataset"]
        id_field = _ID_FIELDS[dataset]
        data = {k: v for k, v in entry.items() if k != "dataset"}
        grouped.setdefault(dataset, []).append(Record(record_id=data[id_field], data=data))
    return grouped


def _fired_rule_ids(rule_set: list[dict], grouped: dict[str, list[Record]],
                     period_end: datetime.date) -> set[str]:
    """Run every rule in rule_set against its dataset; return the rule_ids
    that produced at least one violation. Builds fresh rule callables on
    every call — no shared/mutable state between snapshots or between
    separate run_replay() calls."""
    invoice_register = grouped.get("invoice_register", [])
    allocations = grouped.get("allocations", [])
    client_ledger = grouped.get("client_ledger", [])

    fired: set[str] = set()
    for spec in rule_set:
        rule_id = spec["rule_id"]
        meta = RULE_METADATA[rule_id]
        records = grouped.get(meta["dataset"], [])

        if rule_id == "R14_RECONCILIATION_TIMING" and not dataset_has_column(
            records, "reconciliation_date"
        ):
            continue

        rule_fn = load_trust_rules_from_config(
            [spec],
            invoice_register=invoice_register if rule_id in _INVOICE_RULES else None,
            allocations=allocations if rule_id == "R12_BULK_DEPOSIT_UNALLOCATED" else None,
            client_ledger=client_ledger,
            bank_statement=None,
            reference_date=period_end,
        )[0]

        if any(not rule_fn(r).passed for r in records):
            fired.add(rule_id)

    return fired


def run_replay(rule_set: list[dict], corpus: ReplayCorpus) -> ReplayResult:
    """
    Run `rule_set` (a list of rule-spec dicts, as accepted by
    trust_domain.rules.load_trust_rules_from_config) against every snapshot
    in `corpus`, and score the result against each snapshot's
    expected_breaches.

    Deterministic and side-effect free: neither `rule_set` nor `corpus` is
    mutated, no global state is touched, and no file is written. Calling
    this twice with the same arguments always returns an equal result.
    """
    total_tp = 0
    total_fp = 0
    total_fn = 0
    false_positives: list[dict] = []
    false_negatives: list[dict] = []
    per_snapshot: list[dict] = []

    for snapshot in corpus.snapshots:
        expected = set(snapshot.expected_breaches)
        grouped = _group_entries_by_dataset(snapshot.ledger_entries)
        fired = _fired_rule_ids(rule_set, grouped, snapshot.period_end)

        true_positives = fired & expected
        snap_fp = fired - expected
        snap_fn = expected - fired

        total_tp += len(true_positives)
        total_fp += len(snap_fp)
        total_fn += len(snap_fn)

        if snap_fp:
            false_positives.append({
                "snapshot_id": snapshot.snapshot_id,
                "rule_ids": sorted(snap_fp),
            })
        if snap_fn:
            false_negatives.append({
                "snapshot_id": snapshot.snapshot_id,
                "rule_ids": sorted(snap_fn),
            })

        per_snapshot.append({
            "snapshot_id": snapshot.snapshot_id,
            "expected": sorted(expected),
            "fired": sorted(fired),
            "true_positives": sorted(true_positives),
            "false_positives": sorted(snap_fp),
            "false_negatives": sorted(snap_fn),
        })

    flagged_total = total_tp + total_fp
    expected_total = total_tp + total_fn
    precision = 1.0 if flagged_total == 0 else total_tp / flagged_total
    recall = 1.0 if expected_total == 0 else total_tp / expected_total

    return ReplayResult(
        precision=precision,
        recall=recall,
        false_positives=false_positives,
        false_negatives=false_negatives,
        per_snapshot=per_snapshot,
    )


def get_current_rule_set(sensitivity: str = "standard") -> list[dict]:
    """
    The rule-spec list representing the engine's shipped rule set (all
    R01-R14, at the given sensitivity mode's thresholds) — what
    tests/test_replay_monotonicity.py checks for regressions against.

    sensitivity: "broad" | "standard" (default) | "precise" — see
    trust_domain.rules.apply_sensitivity. Update the underlying thresholds
    only when a rule's default intentionally changes; never edit them just
    to make the monotonicity gate pass.
    """
    scaled = apply_sensitivity(_STANDARD_THRESHOLDS, sensitivity)
    specs: list[dict] = []
    for rule_id in RULE_METADATA:
        spec: dict = {"rule_id": rule_id}
        if rule_id == "R02_DORMANT_BALANCE":
            spec["dormancy_days"] = scaled["dormancy_threshold_days"]
        elif rule_id == "R04_UNMATCHED_BANK_LINE":
            spec["age_days"] = scaled["unmatched_bank_days"]
        elif rule_id == "R05_UNRECONCILED_AGEING":
            spec["age_days"] = scaled["unreconciled_age_days"]
        elif rule_id == "R06_FIT_OVERHELD":
            spec["fit_days"] = scaled["fit_transfer_days"]
        elif rule_id == "R12_BULK_DEPOSIT_UNALLOCATED":
            spec["bulk_min_nzd"] = scaled["bulk_min_nzd"]
        specs.append(spec)
    return specs
