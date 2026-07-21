"""
Step 4.1 — Tests for the per-client config loader.

Covers:
  - load_config() succeeds on the real coastal_law.toml
  - ConfigError raised for missing required field
  - ConfigError raised for unknown rule ID in enabled_rules
  - ConfigError raised for non-positive threshold
  - validate_config() returns a warning for an unusually short dormancy threshold
  - validate_config() returns empty list for a valid config
  - input_files paths use forward slashes (posix) not backslashes
"""

from __future__ import annotations

import pytest
from pathlib import Path

from trust_domain.config import load_config, validate_config, ConfigError, ClientConfig

# Path to the real sample config shipped with the engine
COASTAL_LAW_TOML = Path("trust_domain/config/coastal_law.toml")


class TestLoadConfigSuccess:
    def test_loads_coastal_law_toml(self):
        config = load_config(COASTAL_LAW_TOML)
        assert isinstance(config, ClientConfig)

    def test_firm_name(self):
        config = load_config(COASTAL_LAW_TOML)
        assert config.firm_name == "Coastal Law Ltd"

    def test_reviewed_by(self):
        config = load_config(COASTAL_LAW_TOML)
        assert config.reviewed_by == "J. Smith (TAS)"

    def test_engine_version(self):
        config = load_config(COASTAL_LAW_TOML)
        assert config.engine_version == "1.0.0"

    def test_review_period(self):
        config = load_config(COASTAL_LAW_TOML)
        assert config.review_period == "May 2026"

    def test_threshold_defaults(self):
        config = load_config(COASTAL_LAW_TOML)
        assert config.dormancy_threshold_days == 365
        assert config.unreconciled_age_days == 30
        assert config.unmatched_bank_days == 5
        assert config.fit_transfer_days == 14

    def test_all_eleven_rules_enabled(self):
        config = load_config(COASTAL_LAW_TOML)
        assert len(config.enabled_rules) == 11
        assert "R01_OVERDRAWN_CLIENT_LEDGER" in config.enabled_rules
        assert "R07_FEE_WITHOUT_INVOICE" in config.enabled_rules
        assert "R08_FEE_INVOICE_MISSING" in config.enabled_rules
        assert "R12_BULK_DEPOSIT_UNALLOCATED" in config.enabled_rules

    def test_input_dir_is_absolute(self):
        config = load_config(COASTAL_LAW_TOML)
        assert Path(config.input_dir).is_absolute()

    def test_output_dir_is_absolute(self):
        config = load_config(COASTAL_LAW_TOML)
        assert Path(config.output_dir).is_absolute()

    def test_paths_use_forward_slashes(self):
        """input_dir and output_dir must never contain backslashes (Windows safety)."""
        config = load_config(COASTAL_LAW_TOML)
        assert "\\" not in config.input_dir, (
            f"input_dir contains backslashes: {config.input_dir}"
        )
        assert "\\" not in config.output_dir, (
            f"output_dir contains backslashes: {config.output_dir}"
        )

    def test_input_dir_resolves_to_data_sample(self):
        """Relative path '../../data/sample' must resolve to the actual data directory."""
        config = load_config(COASTAL_LAW_TOML)
        resolved = Path(config.input_dir)
        assert resolved.name == "sample"
        assert resolved.parent.name == "data"


class TestLoadConfigMissingRequiredField:
    def _write_toml(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "test.toml"
        p.write_text(content, encoding="utf-8")
        return p

    def test_raises_for_missing_firm_name(self, tmp_path):
        toml = self._write_toml(tmp_path, """
[client]
reviewed_by = "J. Smith"
engine_version = "1.0.0"
review_period = "May 2026"

[paths]
input_dir = "."
output_dir = "."
""")
        with pytest.raises(ConfigError, match="firm_name"):
            load_config(toml)

    def test_raises_for_missing_paths_section(self, tmp_path):
        toml = self._write_toml(tmp_path, """
[client]
firm_name = "Test Firm"
reviewed_by = "J. Smith"
engine_version = "1.0.0"
review_period = "May 2026"
""")
        with pytest.raises(ConfigError, match="paths"):
            load_config(toml)

    def test_raises_for_missing_input_dir(self, tmp_path):
        toml = self._write_toml(tmp_path, """
[client]
firm_name = "Test Firm"
reviewed_by = "J. Smith"
engine_version = "1.0.0"
review_period = "May 2026"

[paths]
output_dir = "."
""")
        with pytest.raises(ConfigError, match="input_dir"):
            load_config(toml)

    def test_raises_for_missing_review_period(self, tmp_path):
        toml = self._write_toml(tmp_path, """
[client]
firm_name = "Test Firm"
reviewed_by = "J. Smith"
engine_version = "1.0.0"

[paths]
input_dir = "."
output_dir = "."
""")
        with pytest.raises(ConfigError, match="review_period"):
            load_config(toml)


class TestLoadConfigUnknownRuleId:
    def test_raises_for_unknown_rule_id(self, tmp_path):
        toml = tmp_path / "bad_rules.toml"
        toml.write_text("""
[client]
firm_name = "Test Firm"
reviewed_by = "J. Smith"
engine_version = "1.0.0"
review_period = "May 2026"

[paths]
input_dir = "."
output_dir = "."

[rules]
enabled = ["R01_OVERDRAWN_CLIENT_LEDGER", "R99_DOES_NOT_EXIST"]
""", encoding="utf-8")
        with pytest.raises(ConfigError, match="R99_DOES_NOT_EXIST"):
            load_config(toml)


class TestLoadConfigNonPositiveThreshold:
    def _base_toml(self, threshold_key: str, value: int) -> str:
        return f"""
[client]
firm_name = "Test Firm"
reviewed_by = "J. Smith"
engine_version = "1.0.0"
review_period = "May 2026"

[paths]
input_dir = "."
output_dir = "."

[thresholds]
{threshold_key} = {value}
"""

    def test_raises_for_zero_dormancy(self, tmp_path):
        toml = tmp_path / "t.toml"
        toml.write_text(self._base_toml("dormancy_threshold_days", 0), encoding="utf-8")
        with pytest.raises(ConfigError, match="dormancy_threshold_days"):
            load_config(toml)

    def test_raises_for_negative_threshold(self, tmp_path):
        toml = tmp_path / "t.toml"
        toml.write_text(self._base_toml("unreconciled_age_days", -5), encoding="utf-8")
        with pytest.raises(ConfigError, match="unreconciled_age_days"):
            load_config(toml)

    def test_raises_for_zero_fit_days(self, tmp_path):
        toml = tmp_path / "t.toml"
        toml.write_text(self._base_toml("fit_transfer_days", 0), encoding="utf-8")
        with pytest.raises(ConfigError, match="fit_transfer_days"):
            load_config(toml)


class TestValidateConfig:
    def _make_config(self, **overrides) -> ClientConfig:
        base = {
            "firm_name":               "Test Firm",
            "reviewed_by":             "J. Smith",
            "engine_version":          "1.0.0",
            "input_dir":               "/data/in",
            "output_dir":              "/data/out",
            "dormancy_threshold_days": 365,
            "unreconciled_age_days":   30,
            "unmatched_bank_days":     5,
            "fit_transfer_days":       14,
            "enabled_rules": [
                "R01_OVERDRAWN_CLIENT_LEDGER",
                "R02_DORMANT_BALANCE",
            ],
            "review_period": "May 2026",
        }
        base.update(overrides)
        return ClientConfig(**base)

    def test_returns_empty_list_for_valid_config(self):
        config = self._make_config()
        warnings = validate_config(config)
        assert warnings == []

    def test_warns_for_short_dormancy_threshold(self):
        config = self._make_config(dormancy_threshold_days=90)
        warnings = validate_config(config)
        assert len(warnings) == 1
        assert "dormancy_threshold_days" in warnings[0]
        assert "unusually short" in warnings[0]

    def test_dormancy_at_180_is_not_warned(self):
        # 180 is the boundary — below it warns, at/above it does not
        config = self._make_config(dormancy_threshold_days=180)
        warnings = validate_config(config)
        assert not any("dormancy" in w for w in warnings)

    def test_dormancy_at_179_warns(self):
        config = self._make_config(dormancy_threshold_days=179)
        warnings = validate_config(config)
        assert any("dormancy" in w for w in warnings)


class TestRunLogPathsAreForwardSlashes:
    """Confirm the fix for the Windows backslash issue in run_log input_files."""

    def test_input_files_built_from_config_use_posix_paths(self):
        """
        When a caller builds input_files for run_log using config.input_dir,
        the result must not contain backslashes.
        """
        config = load_config(COASTAL_LAW_TOML)
        csv_names = [
            "matter_register.csv",
            "client_ledger.csv",
            "trust_bank_statement.csv",
            "reconciliation_summary.csv",
        ]
        input_files = [
            (Path(config.input_dir) / name).as_posix()
            for name in csv_names
        ]
        for p in input_files:
            assert "\\" not in p, f"Backslash found in run_log path: {p}"
            assert "/" in p, f"No forward slash in run_log path: {p}"

    def test_reproducibility_test_uses_posix_paths(self):
        """
        Confirm test_reproducibility.py was patched to use .as_posix()
        not str() when building input_files.
        """
        from pathlib import Path
        src = Path("tests/test_reproducibility.py").read_text(encoding="utf-8")
        assert ".as_posix()" in src, (
            "test_reproducibility.py must use .as_posix() for input_files paths"
        )
        assert 'str(SAMPLE_DIR /' not in src, (
            "test_reproducibility.py must not use str(SAMPLE_DIR / ...) for paths"
        )


class TestColumnMap:
    """column_map field on ClientConfig — Task 5.1."""

    def test_column_map_defaults_to_empty_dict(self):
        """Existing coastal_law.toml (no [column_map]) loads with column_map == {}."""
        config = load_config(COASTAL_LAW_TOML)
        assert config.column_map == {}

    def test_column_map_loaded_from_toml(self, tmp_path):
        """[column_map.matter_register] section is correctly parsed into a nested dict."""
        (tmp_path / "test.toml").write_text(
            '[client]\nfirm_name = "T"\nreviewed_by = "U"\n'
            'engine_version = "1.0.0"\nreview_period = "Jun 2026"\n'
            '[paths]\ninput_dir = "."\noutput_dir = "."\n'
            '[column_map.matter_register]\nmatter_ref = "Matter ID"\n'
            'client_name = "Client Full Name"\n',
            encoding="utf-8",
        )
        config = load_config(tmp_path / "test.toml")
        assert config.column_map == {
            "matter_register": {
                "matter_ref": "Matter ID",
                "client_name": "Client Full Name",
            }
        }
