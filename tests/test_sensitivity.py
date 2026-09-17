"""
Tests for the Phase F sensitivity dial (broad / standard / precise).

Sensitivity scales the engine's five configurable thresholds (dormancy,
unreconciled ageing, unmatched-bank-line age, FIT transfer days, bulk
deposit minimum) — it never changes which rules run. 'standard' must be
byte-for-byte identical to pre-Phase-F behaviour.
"""

from __future__ import annotations

import datetime

import pytest

from replay.engine import LedgerSnapshot, get_current_rule_set
from trust_domain.rules import SENSITIVITY_MODES, apply_sensitivity


class TestApplySensitivity:
    def test_standard_leaves_thresholds_unchanged(self):
        thresholds = {
            "dormancy_threshold_days": 365,
            "unreconciled_age_days": 30,
            "unmatched_bank_days": 5,
            "fit_transfer_days": 14,
            "bulk_min_nzd": 0.0,
        }
        assert apply_sensitivity(thresholds, "standard") == thresholds

    def test_broad_halves_age_thresholds(self):
        thresholds = {"dormancy_threshold_days": 365, "unreconciled_age_days": 30,
                       "unmatched_bank_days": 5, "fit_transfer_days": 14, "bulk_min_nzd": 0.0}
        scaled = apply_sensitivity(thresholds, "broad")
        assert scaled["dormancy_threshold_days"] < thresholds["dormancy_threshold_days"]
        assert scaled["unreconciled_age_days"] < thresholds["unreconciled_age_days"]

    def test_precise_raises_age_thresholds(self):
        thresholds = {"dormancy_threshold_days": 365, "unreconciled_age_days": 30,
                       "unmatched_bank_days": 5, "fit_transfer_days": 14, "bulk_min_nzd": 0.0}
        scaled = apply_sensitivity(thresholds, "precise")
        assert scaled["dormancy_threshold_days"] > thresholds["dormancy_threshold_days"]
        assert scaled["unreconciled_age_days"] > thresholds["unreconciled_age_days"]

    def test_invalid_sensitivity_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_sensitivity({"dormancy_threshold_days": 365}, "extreme")

    def test_sensitivity_modes_constant(self):
        assert SENSITIVITY_MODES == ("broad", "standard", "precise")


class TestGetCurrentRuleSetSensitivity:
    def test_default_is_standard(self):
        assert get_current_rule_set() == get_current_rule_set(sensitivity="standard")

    def test_broad_standard_precise_dormancy_days_are_ordered(self):
        def dormancy_days(sensitivity):
            specs = get_current_rule_set(sensitivity=sensitivity)
            spec = next(s for s in specs if s["rule_id"] == "R02_DORMANT_BALANCE")
            return spec["dormancy_days"]

        assert dormancy_days("broad") < dormancy_days("standard") < dormancy_days("precise")


class TestBreachCountsAcrossSensitivity:
    """
    Same snapshot, three sensitivity modes -> distinct breach counts.

    Three matters with dormancy ages of 200, 400, and 600 days as at the
    snapshot's period_end. Standard dormancy threshold is 365 days:
      - broad threshold (~183 days):   all three (200, 400, 600) are stale.
      - standard threshold (365 days): only 400 and 600 are stale.
      - precise threshold (~548 days): only 600 is stale.
    So broad=3, standard=2, precise=1 -- broad > standard > precise.
    """

    def _snapshot(self) -> LedgerSnapshot:
        period_end = datetime.date(2026, 6, 30)

        def stale_matter(ref, days_ago):
            last_activity = (period_end - datetime.timedelta(days=days_ago)).isoformat()
            return {
                "dataset": "matter_register",
                "matter_ref": ref,
                "client_name": "Client",
                "matter_type": "PROPERTY_PURCHASE",
                "opened_date": "2024-01-01",
                "last_activity_date": last_activity,
                "current_balance_nzd": 1000.0,
                "status": "OPEN",
            }

        return LedgerSnapshot(
            snapshot_id="sensitivity_fixture",
            period_end=period_end,
            ledger_entries=[
                stale_matter("M01", 200),
                stale_matter("M02", 400),
                stale_matter("M03", 600),
            ],
            expected_breaches=["R02_DORMANT_BALANCE"],
        )

    def test_broad_ge_standard_ge_precise_and_strictly_distinct(self):
        from trust_domain.rules import load_trust_rules_from_config

        def breach_count(sensitivity: str) -> int:
            specs = get_current_rule_set(sensitivity=sensitivity)
            spec = next(s for s in specs if s["rule_id"] == "R02_DORMANT_BALANCE")
            rule_fn = load_trust_rules_from_config(
                [spec], reference_date=datetime.date(2026, 6, 30)
            )[0]
            snap = self._snapshot()
            from integrity_engine.core.types import Record
            records = [
                Record(record_id=e["matter_ref"], data={k: v for k, v in e.items() if k != "dataset"})
                for e in snap.ledger_entries
            ]
            return sum(1 for r in records if not rule_fn(r).passed)

        broad = breach_count("broad")
        standard = breach_count("standard")
        precise = breach_count("precise")

        assert broad == 3
        assert standard == 2
        assert precise == 1
        assert broad >= standard >= precise


class TestRunPipelineSensitivity:
    """
    Integration tests against the real coastal_law sample data. Standard
    sensitivity must be byte-for-byte unchanged from pre-Phase-F behaviour
    (23 violations: 14 CRITICAL, 9 HIGH, as documented in CLAUDE.md).
    """

    CONFIG = "trust_domain/config/coastal_law.toml"
    AS_AT = datetime.datetime(2026, 6, 25)

    def _run(self, tmp_path, sensitivity):
        from pathlib import Path
        from run import run_pipeline
        return run_pipeline(
            config_path=Path(self.CONFIG),
            output_dir=tmp_path / sensitivity,
            generated_at=self.AS_AT,
            sensitivity=sensitivity,
        )

    def test_standard_matches_pre_phase_f_baseline(self, tmp_path):
        result = self._run(tmp_path, "standard")
        assert result["run_log_data"]["total_violations"] == 23
        assert result["report_dict"]["critical_count"] == 14
        assert result["report_dict"]["high_count"] == 9

    def test_broad_flags_at_least_as_many_as_standard(self, tmp_path):
        standard_total = self._run(tmp_path, "standard")["run_log_data"]["total_violations"]
        broad_total = self._run(tmp_path, "broad")["run_log_data"]["total_violations"]
        assert broad_total >= standard_total

    def test_precise_flags_at_most_as_many_as_standard(self, tmp_path):
        standard_total = self._run(tmp_path, "standard")["run_log_data"]["total_violations"]
        precise_total = self._run(tmp_path, "precise")["run_log_data"]["total_violations"]
        assert precise_total <= standard_total

    def test_invalid_sensitivity_raises(self, tmp_path):
        with pytest.raises(ValueError):
            self._run(tmp_path, "extreme")

    def test_report_dict_records_sensitivity(self, tmp_path):
        result = self._run(tmp_path, "broad")
        assert result["report_dict"]["sensitivity"] == "broad"

    def test_run_log_records_sensitivity(self, tmp_path):
        result = self._run(tmp_path, "precise")
        assert result["run_log_data"]["sensitivity"] == "precise"


class TestCLISensitivityFlag:
    def test_parser_accepts_sensitivity_choices(self):
        from run import _build_arg_parser
        parser = _build_arg_parser()
        args = parser.parse_args([
            "--config", "trust_domain/config/coastal_law.toml",
            "--sensitivity", "broad",
        ])
        assert args.sensitivity == "broad"

    def test_parser_defaults_sensitivity_to_standard(self):
        from run import _build_arg_parser
        parser = _build_arg_parser()
        args = parser.parse_args(["--config", "trust_domain/config/coastal_law.toml"])
        assert args.sensitivity == "standard"

    def test_parser_rejects_invalid_sensitivity(self):
        from run import _build_arg_parser
        parser = _build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([
                "--config", "trust_domain/config/coastal_law.toml",
                "--sensitivity", "extreme",
            ])
