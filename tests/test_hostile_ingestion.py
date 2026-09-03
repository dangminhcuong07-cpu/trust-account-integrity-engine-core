"""
Tests for defensive, tolerant CSV ingestion (trust_domain/ingestion/loader.py).

The engine had never processed data it didn't generate itself. These tests
lock in two things:

1. A full pipeline run against tests/fixtures/hostile_input/ — a real-world-
   quirky-but-ultimately-valid dataset (mixed DD/MM/YYYY and ISO dates,
   blank rows, extra unexpected columns, numeric formatting noise) —
   completes successfully with the correct violation count, proving the
   loader tolerates these quirks rather than crashing on them.

2. Every recognised bad-input failure mode raises trust_domain.config.loader
   .ConfigError with a message naming the exact file/row/column/value —
   never a bare exception (KeyError, ValueError, TypeError) escaping as a
   raw traceback.

Fixture-building follows the write_csv() convention already used in
test_ingestion.py: build the offending CSV inline via tmp_path so each test
is self-contained and the failure being tested is visible in the test body.
"""
from __future__ import annotations

import csv
import datetime
import sys
from pathlib import Path

import pytest

# run.py lives at the project root, one level above tests/
sys.path.insert(0, str(Path(__file__).parent.parent))
from run import run_pipeline

from trust_domain.ingestion.loader import load_file_mapped
from trust_domain.config.loader import ConfigError

_CONFIG_PATH = Path("trust_domain/config/coastal_law.toml")
_HOSTILE_FIXTURE = Path(__file__).parent / "fixtures" / "hostile_input"
_GENERATED_AT = datetime.datetime(2026, 6, 25, 10, 30, 0)


def write_csv(path: Path, headers: list, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


_LEDGER_HEADERS = [
    "entry_id", "matter_ref", "entry_date", "description",
    "receipt_nzd", "payment_nzd", "balance_after_nzd",
    "reconciled", "reconciled_date", "notes", "reference",
]

_LEDGER_ROW = [
    "L001", "M001", "2026-01-01", "Receipt",
    "100.00", "0.00", "100.00", "Y", "2026-01-05", "", "",
]


def _write_minimal_valid_ledger(tmp_path: Path) -> None:
    """A single well-formed client_ledger row, for tests that mutate one field."""
    write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS, [_LEDGER_ROW])


# ── 1. Full pipeline against the hostile-but-tolerant fixture ──────────────────

class TestHostileTolerantFixture:
    """The engine must process a file with realistic quirks, not just clean
    synthetic data — see tests/fixtures/hostile_input/README.md for what's
    deliberately wrong with these files."""

    @staticmethod
    @pytest.fixture(scope="class")
    def pipeline_result(tmp_path_factory):
        out = tmp_path_factory.mktemp("hostile_output")
        return run_pipeline(
            config_path=_CONFIG_PATH,
            output_dir=out,
            input_dir=_HOSTILE_FIXTURE,
            generated_at=_GENERATED_AT,
        )

    def test_hostile_tolerant_fixture_runs_clean(self, pipeline_result):
        # Same seeded violations as the clean synthetic sample at the time
        # this fixture was built (19 at the 2026-06-25 reference date; the
        # clean sample has since grown to 23 with the Phase 3 scenarios, but
        # this fixture was frozen before those were added) — mixed date
        # formats, blank rows, extra columns, and numeric formatting noise
        # must not change the result. Was asserted as 19 while R04 used the
        # wall clock; at the fixed reference date B048 (dated 2026-06-24) is
        # correctly below R04's 5-day threshold, so the true count is 18.
        assert len(pipeline_result["violations"]) == 18

    def test_r10_catches_violation_across_mixed_date_formats(self, pipeline_result):
        # INV-00237's issue_date is DD/MM/YYYY in this fixture while L041's
        # entry_date stays ISO. R10 compares the two as strings
        # (issue_date > entry_date) — that only gives the right answer if
        # both were normalised to the same format at ingestion. Before the
        # loader normalised dates, this exact input silently failed to flag
        # the violation (a wrong answer, not a crash) rather than raising
        # anything — the more dangerous failure mode for a compliance tool.
        r10 = [v for v in pipeline_result["violations"]
               if v.rule_id == "R10_INVOICE_POSTDATES_PAYMENT"]
        assert [v.record_id for v in r10] == ["L041"]
        assert "2026-06-15" in r10[0].evidence  # normalised, not "15/6/2026"

    def test_blank_rows_are_skipped_not_loaded_as_records(self, pipeline_result):
        # 66 real client_ledger data rows in the underlying synthetic sample;
        # the fixture adds one wholly-blank row on top, which must not
        # become a 67th record.
        config = pipeline_result["config"]
        records = load_file_mapped("client_ledger", _HOSTILE_FIXTURE, config.column_map)
        assert len(records) == 66


# ── 2. Unparseable dates ────────────────────────────────────────────────────────

class TestUnparseableDates:
    def test_garbage_date_raises_config_error_naming_row_and_column(self, tmp_path):
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS,
                   [["L001", "M001", "yesterday", "Receipt",
                     "100.00", "0.00", "100.00", "Y", "", "", ""]])
        with pytest.raises(ConfigError, match=r"entry_date.*row 2"):
            load_file_mapped("client_ledger", tmp_path, {})

    def test_invalid_calendar_date_raises_config_error(self, tmp_path):
        # 31 February doesn't exist in any calendar — must be caught even
        # though it matches the DD/MM/YYYY shape.
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS,
                   [["L001", "M001", "31/02/2026", "Receipt",
                     "100.00", "0.00", "100.00", "Y", "", "", ""]])
        with pytest.raises(ConfigError, match="not a valid calendar date"):
            load_file_mapped("client_ledger", tmp_path, {})

    def test_iso_and_dmy_dates_both_normalise_to_the_same_iso_value(self, tmp_path):
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS,
                   [["L001", "M001", "2026-03-04", "ISO",
                     "100.00", "0.00", "100.00", "Y", "", "", ""],
                    ["L002", "M001", "4/3/2026", "DD/MM/YYYY",
                     "100.00", "0.00", "100.00", "Y", "", "", ""]])
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert records[0].data["entry_date"] == "2026-03-04"
        assert records[1].data["entry_date"] == "2026-03-04"

    def test_blank_date_on_optional_field_is_tolerated(self, tmp_path):
        # reconciled_date is not a computed field (nothing does date
        # arithmetic on it) and is legitimately blank for an unreconciled
        # entry — must not error.
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS,
                   [["L001", "M001", "2026-01-01", "Receipt",
                     "100.00", "0.00", "100.00", "N", "", "", ""]])
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert records[0].data["reconciled_date"] == ""


# ── 3. Non-numeric values in numeric fields ─────────────────────────────────────

class TestNonNumericValues:
    def test_garbage_in_amount_field_raises_config_error(self, tmp_path):
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS,
                   [["L001", "M001", "2026-01-01", "Receipt",
                     "N/A", "0.00", "100.00", "Y", "", "", ""]])
        with pytest.raises(ConfigError, match=r"receipt_nzd.*row 2"):
            load_file_mapped("client_ledger", tmp_path, {})

    def test_thousands_separator_and_whitespace_are_tolerated(self, tmp_path):
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS,
                   [["L001", "M001", "2026-01-01", "Receipt",
                     " 8,500.00 ", "0.00", "8500.00", "Y", "", "", ""]])
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert records[0].data["receipt_nzd"] == 8500.00


# ── 4. Missing / mismatched columns ─────────────────────────────────────────────

class TestMissingColumns:
    def test_missing_required_unmapped_column_raises_config_error(self, tmp_path):
        # entry_date dropped entirely, no column_map configured — this must
        # be caught at ingestion, not surface later as a KeyError deep in
        # rule evaluation (StalenessChecker.check_age).
        headers = [h for h in _LEDGER_HEADERS if h != "entry_date"]
        row = [v for h, v in zip(_LEDGER_HEADERS, _LEDGER_ROW) if h != "entry_date"]
        write_csv(tmp_path / "client_ledger.csv", headers, [row])
        with pytest.raises(ConfigError, match=r"entry_date"):
            load_file_mapped("client_ledger", tmp_path, {})

    def test_missing_optional_column_does_not_raise(self, tmp_path):
        # reconciled_date is descriptive only (nothing computes on it) — a
        # file that omits it entirely must still load.
        headers = [h for h in _LEDGER_HEADERS if h != "reconciled_date"]
        row = [v for h, v in zip(_LEDGER_HEADERS, _LEDGER_ROW) if h != "reconciled_date"]
        write_csv(tmp_path / "client_ledger.csv", headers, [row])
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert records[0].record_id == "L001"

    def test_missing_mapped_column_names_the_client_side_column(self, tmp_path):
        _write_minimal_valid_ledger(tmp_path)
        column_map = {"client_ledger": {"entry_date": "Transaction Date"}}
        with pytest.raises(ConfigError, match="Transaction Date"):
            load_file_mapped("client_ledger", tmp_path, column_map)

    def test_completely_empty_file_raises_config_error(self, tmp_path):
        (tmp_path / "client_ledger.csv").write_text("")
        with pytest.raises(ConfigError, match="no header row"):
            load_file_mapped("client_ledger", tmp_path, {})

    def test_xlsx_blank_column_heading_raises_config_error(self, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["matter_ref", "client_name", None, "status",
                   "open_date", "last_activity_date", "current_balance_nzd"])
        ws.append(["M001", "Alice", "x", "OPEN", "2025-01-01", "2026-05-01", 1000.0])
        wb.save(tmp_path / "matter_register.xlsx")
        with pytest.raises(ConfigError, match="blank column heading"):
            load_file_mapped("matter_register", tmp_path, {})


# ── 5. Blank rows ────────────────────────────────────────────────────────────────

class TestBlankRows:
    def test_wholly_blank_row_is_skipped_not_loaded(self, tmp_path, capsys):
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS,
                   [_LEDGER_ROW, [""] * len(_LEDGER_HEADERS)])
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert len(records) == 1
        assert records[0].record_id == "L001"
        assert "skipped 1 blank row" in capsys.readouterr().out

    def test_row_with_data_but_blank_id_raises_config_error(self, tmp_path):
        # Not a blank row (every other field is populated) — silently
        # dropping it would lose a real transaction, and a None/blank
        # record_id would later break `sorted(v.record_id for v in
        # violations)` in run.py with a TypeError. Must raise clearly instead.
        row = list(_LEDGER_ROW)
        row[0] = ""  # entry_id
        write_csv(tmp_path / "client_ledger.csv", _LEDGER_HEADERS, [row])
        with pytest.raises(ConfigError, match=r"Row 2.*entry_id"):
            load_file_mapped("client_ledger", tmp_path, {})


# ── 6. Extra unexpected columns ─────────────────────────────────────────────────

class TestExtraColumns:
    def test_extra_named_column_is_ignored(self, tmp_path):
        headers = _LEDGER_HEADERS + ["internal_pms_flag"]
        row = _LEDGER_ROW + ["X"]
        write_csv(tmp_path / "client_ledger.csv", headers, [row])
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert records[0].record_id == "L001"
        assert records[0].data["internal_pms_flag"] == "X"

    def test_ragged_row_with_more_fields_than_header_does_not_crash(self, tmp_path):
        # A row with trailing extra commas beyond the header count — csv's
        # DictReader files these under the `None` restkey, which must be
        # dropped rather than blowing up when the row is later cast.
        with (tmp_path / "client_ledger.csv").open("w", newline="", encoding="utf-8") as f:
            f.write(",".join(_LEDGER_HEADERS) + "\n")
            f.write(",".join(_LEDGER_ROW) + ",EXTRA1,EXTRA2\n")
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert records[0].record_id == "L001"
        assert None not in records[0].data

    def test_short_row_with_fewer_fields_than_header_does_not_crash(self, tmp_path):
        with (tmp_path / "client_ledger.csv").open("w", newline="", encoding="utf-8") as f:
            f.write(",".join(_LEDGER_HEADERS) + "\n")
            f.write("L002,M002,2026-01-02,Receipt short row,50.00\n")
        records = load_file_mapped("client_ledger", tmp_path, {})
        assert records[0].record_id == "L002"
        assert records[0].data["balance_after_nzd"] is None
