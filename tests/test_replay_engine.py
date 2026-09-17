"""
Tests for replay/engine.py — LedgerSnapshot, ReplayCorpus, run_replay.

Fixtures here are small and hand-built (not the 12-month synthetic corpus
in tests/replay_corpus/, which is covered separately by
test_replay_monotonicity.py). These tests exercise the replay mechanics in
isolation: serialisation round-trip, corpus loading, and the three
precision/recall scenarios the Phase F spec calls out explicitly.
"""

from __future__ import annotations

import datetime
import json

from replay.engine import (
    LedgerSnapshot,
    ReplayCorpus,
    ReplayResult,
    get_current_rule_set,
    run_replay,
)


def _entry(dataset: str, **fields) -> dict:
    return {"dataset": dataset, **fields}


class TestLedgerSnapshotSerialisation:
    def test_json_round_trip_preserves_all_fields(self):
        snap = LedgerSnapshot(
            snapshot_id="test_2026-01",
            period_end=datetime.date(2026, 1, 31),
            ledger_entries=[_entry("client_ledger", entry_id="L001", matter_ref="M001")],
            expected_breaches=["R01_OVERDRAWN_CLIENT_LEDGER"],
            metadata={"firm_size": "small"},
        )
        restored = LedgerSnapshot.from_json(snap.to_json())
        assert restored == snap

    def test_to_dict_serialises_period_end_as_iso_string(self):
        snap = LedgerSnapshot(
            snapshot_id="test_2026-02",
            period_end=datetime.date(2026, 2, 28),
            ledger_entries=[],
            expected_breaches=[],
        )
        d = snap.to_dict()
        assert d["period_end"] == "2026-02-28"
        # must be plain JSON — no date objects left over
        json.dumps(d)


class TestReplayCorpusLoad:
    def test_load_reads_every_json_file_in_directory(self, tmp_path):
        for month in ("2026-01", "2026-02"):
            snap = LedgerSnapshot(
                snapshot_id=f"firm_{month}",
                period_end=datetime.date.fromisoformat(f"{month}-01"),
                ledger_entries=[],
                expected_breaches=[],
            )
            (tmp_path / f"{month}.json").write_text(snap.to_json(), encoding="utf-8")

        corpus = ReplayCorpus.load(tmp_path)

        assert len(corpus.snapshots) == 2
        assert {s.snapshot_id for s in corpus.snapshots} == {"firm_2026-01", "firm_2026-02"}

    def test_load_missing_directory_raises(self, tmp_path):
        import pytest
        with pytest.raises(FileNotFoundError):
            ReplayCorpus.load(tmp_path / "does_not_exist")


class TestRunReplay:
    def test_all_expected_breaches_fire(self):
        """A snapshot whose only entry is a genuine R01 violation, checked
        against a rule set that includes R01, must be fully matched."""
        snap = LedgerSnapshot(
            snapshot_id="firm_2026-03",
            period_end=datetime.date(2026, 3, 31),
            ledger_entries=[
                _entry(
                    "client_ledger", entry_id="L001", matter_ref="M001",
                    entry_date="2026-03-05", description="Payment",
                    receipt_nzd=0.0, payment_nzd=500.0,
                    balance_after_nzd=-500.0, reconciled="Y", reference="",
                ),
            ],
            expected_breaches=["R01_OVERDRAWN_CLIENT_LEDGER"],
        )
        corpus = ReplayCorpus([snap])
        rule_set = [{"rule_id": "R01_OVERDRAWN_CLIENT_LEDGER"}]

        result = run_replay(rule_set, corpus)

        assert isinstance(result, ReplayResult)
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.false_positives == []
        assert result.false_negatives == []

    def test_no_unexpected_breaches_fire(self):
        """A snapshot with clean data must not be flagged by a rule not in
        expected_breaches — precision stays perfect."""
        snap = LedgerSnapshot(
            snapshot_id="firm_2026-04",
            period_end=datetime.date(2026, 4, 30),
            ledger_entries=[
                _entry(
                    "client_ledger", entry_id="L002", matter_ref="M002",
                    entry_date="2026-04-05", description="Receipt",
                    receipt_nzd=500.0, payment_nzd=0.0,
                    balance_after_nzd=500.0, reconciled="Y", reference="",
                ),
            ],
            expected_breaches=[],
        )
        corpus = ReplayCorpus([snap])
        rule_set = [{"rule_id": "R01_OVERDRAWN_CLIENT_LEDGER"}]

        result = run_replay(rule_set, corpus)

        assert result.precision == 1.0
        assert result.false_positives == []

    def test_precision_recall_calculation_across_snapshots(self):
        """
        Snapshot A: expects R01, data fires R01 only -> TP=1.
        Snapshot B: expects R02, data fires R01 (unexpected) and never
        triggers R02 (dormant matter with zero balance, so R02 can't fire)
        -> FP=1 (R01), FN=1 (R02).

        Aggregate: TP=1, flagged=2 -> precision=0.5; expected=2 -> recall=0.5.
        """
        snap_a = LedgerSnapshot(
            snapshot_id="firm_A",
            period_end=datetime.date(2026, 5, 31),
            ledger_entries=[
                _entry(
                    "client_ledger", entry_id="L003", matter_ref="M003",
                    entry_date="2026-05-05", description="Payment",
                    receipt_nzd=0.0, payment_nzd=100.0,
                    balance_after_nzd=-100.0, reconciled="Y", reference="",
                ),
            ],
            expected_breaches=["R01_OVERDRAWN_CLIENT_LEDGER"],
        )
        snap_b = LedgerSnapshot(
            snapshot_id="firm_B",
            period_end=datetime.date(2026, 6, 30),
            ledger_entries=[
                _entry(
                    "client_ledger", entry_id="L004", matter_ref="M004",
                    entry_date="2026-06-05", description="Payment",
                    receipt_nzd=0.0, payment_nzd=100.0,
                    balance_after_nzd=-100.0, reconciled="Y", reference="",
                ),
                _entry(
                    "matter_register", matter_ref="M004", client_name="X",
                    matter_type="PROPERTY_PURCHASE", opened_date="2020-01-01",
                    last_activity_date="2020-01-01", current_balance_nzd=0.0,
                    status="OPEN",
                ),
            ],
            expected_breaches=["R02_DORMANT_BALANCE"],
        )
        corpus = ReplayCorpus([snap_a, snap_b])
        rule_set = [
            {"rule_id": "R01_OVERDRAWN_CLIENT_LEDGER"},
            {"rule_id": "R02_DORMANT_BALANCE"},
        ]

        result = run_replay(rule_set, corpus)

        assert result.precision == 0.5
        assert result.recall == 0.5
        assert len(result.false_positives) == 1
        assert len(result.false_negatives) == 1
        assert result.false_positives[0]["snapshot_id"] == "firm_B"
        assert "R01_OVERDRAWN_CLIENT_LEDGER" in result.false_positives[0]["rule_ids"]
        assert result.false_negatives[0]["snapshot_id"] == "firm_B"
        assert "R02_DORMANT_BALANCE" in result.false_negatives[0]["rule_ids"]

    def test_run_replay_does_not_mutate_corpus_or_rule_set(self):
        """Determinism guarantee: calling run_replay twice with the same
        corpus/rule_set objects must not change their contents or the
        result between calls."""
        snap = LedgerSnapshot(
            snapshot_id="firm_repeat",
            period_end=datetime.date(2026, 7, 31),
            ledger_entries=[
                _entry(
                    "client_ledger", entry_id="L005", matter_ref="M005",
                    entry_date="2026-07-05", description="Payment",
                    receipt_nzd=0.0, payment_nzd=100.0,
                    balance_after_nzd=-100.0, reconciled="Y", reference="",
                ),
            ],
            expected_breaches=["R01_OVERDRAWN_CLIENT_LEDGER"],
        )
        corpus = ReplayCorpus([snap])
        rule_set = [{"rule_id": "R01_OVERDRAWN_CLIENT_LEDGER"}]
        rule_set_copy = [dict(r) for r in rule_set]

        result1 = run_replay(rule_set, corpus)
        result2 = run_replay(rule_set, corpus)

        assert rule_set == rule_set_copy
        assert len(corpus.snapshots) == 1
        assert result1.precision == result2.precision
        assert result1.recall == result2.recall


class TestGetCurrentRuleSet:
    def test_returns_a_spec_for_every_shipped_rule(self):
        specs = get_current_rule_set()
        rule_ids = {s["rule_id"] for s in specs}
        assert rule_ids == {
            "R01_OVERDRAWN_CLIENT_LEDGER", "R02_DORMANT_BALANCE", "R03_RECON_BREAK",
            "R04_UNMATCHED_BANK_LINE", "R05_UNRECONCILED_AGEING", "R06_FIT_OVERHELD",
            "R07_FEE_WITHOUT_INVOICE", "R08_FEE_INVOICE_MISSING", "R09_FEE_EXCEEDS_INVOICE",
            "R10_INVOICE_POSTDATES_PAYMENT", "R12_BULK_DEPOSIT_UNALLOCATED",
            "R13_BANK_BALANCE_OVERDRAWN", "R14_RECONCILIATION_TIMING",
        }
