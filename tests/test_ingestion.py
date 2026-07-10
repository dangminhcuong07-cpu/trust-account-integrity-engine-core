"""Tests for trust_domain/ingestion/loader.py — Task 5.1."""
import csv
import pytest
from pathlib import Path

from trust_domain.ingestion.loader import load_file_mapped
from trust_domain.config.loader import ConfigError


# ── Helpers ────────────────────────────────────────────────────────────────────

_MATTER_HEADERS = [
    "matter_ref", "client_name", "matter_type", "status",
    "open_date", "last_activity_date", "current_balance_nzd",
]


def write_csv(path: Path, headers: list, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def write_xlsx(path: Path, headers: list, rows: list) -> None:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


# ── CSV tests ──────────────────────────────────────────────────────────────────

class TestCsvLoad:
    def test_loads_csv_records_and_casts_numerics(self, tmp_path):
        write_csv(
            tmp_path / "matter_register.csv",
            _MATTER_HEADERS,
            [["M001", "Alice", "Conv", "OPEN", "2025-01-01", "2026-05-01", "1000.00"],
             ["M002", "Bob",   "Lit",  "OPEN", "2025-02-01", "2026-05-02", ""]],
        )
        records = load_file_mapped("matter_register", tmp_path, {})
        assert len(records) == 2
        assert records[0].record_id == "M001"
        assert records[0].data["current_balance_nzd"] == 1000.0
        assert records[1].data["current_balance_nzd"] is None


# ── xlsx tests ─────────────────────────────────────────────────────────────────

class TestXlsxLoad:
    def test_loads_xlsx_records_and_casts_numerics(self, tmp_path):
        write_xlsx(
            tmp_path / "matter_register.xlsx",
            _MATTER_HEADERS,
            [["M001", "Alice", "Conv", "OPEN", "2025-01-01", "2026-05-01", 1000.0],
             ["M002", "Bob",   "Lit",  "OPEN", "2025-02-01", "2026-05-02", None]],
        )
        records = load_file_mapped("matter_register", tmp_path, {})
        assert len(records) == 2
        assert records[0].record_id == "M001"
        assert records[0].data["current_balance_nzd"] == 1000.0
        assert records[1].data["current_balance_nzd"] is None

    def test_skips_all_none_rows_in_xlsx(self, tmp_path):
        write_xlsx(
            tmp_path / "matter_register.xlsx",
            _MATTER_HEADERS,
            [["M001", "Alice", "Conv", "OPEN", "2025-01-01", "2026-05-01", 500.0],
             [None, None, None, None, None, None, None],
             ["M002", "Bob",   "Lit",  "OPEN", "2025-02-01", "2026-05-02", 200.0]],
        )
        records = load_file_mapped("matter_register", tmp_path, {})
        assert len(records) == 2

    def test_csv_preferred_over_xlsx_when_both_exist(self, tmp_path):
        write_csv(
            tmp_path / "matter_register.csv",
            _MATTER_HEADERS,
            [["M001", "CSV", "Conv", "OPEN", "2025-01-01", "2026-05-01", "1000.00"]],
        )
        write_xlsx(
            tmp_path / "matter_register.xlsx",
            _MATTER_HEADERS,
            [["M999", "XLSX", "Lit", "OPEN", "2025-01-01", "2026-05-01", 0.0]],
        )
        records = load_file_mapped("matter_register", tmp_path, {})
        assert records[0].data["client_name"] == "CSV"


# ── Column mapping tests ────────────────────────────────────────────────────────

class TestColumnMapping:
    def test_renames_client_columns_to_internal_names(self, tmp_path):
        write_csv(
            tmp_path / "matter_register.csv",
            ["Matter ID", "Client Full Name", "matter_type", "status",
             "open_date", "last_activity_date", "current_balance_nzd"],
            [["M001", "Alice", "Conv", "OPEN", "2025-01-01", "2026-05-01", "500.00"]],
        )
        column_map = {"matter_register": {"matter_ref": "Matter ID",
                                          "client_name": "Client Full Name"}}
        records = load_file_mapped("matter_register", tmp_path, column_map)
        assert records[0].record_id == "M001"
        assert records[0].data["client_name"] == "Alice"

    def test_missing_mapped_column_raises_config_error(self, tmp_path):
        write_csv(
            tmp_path / "matter_register.csv",
            _MATTER_HEADERS,
            [["M001", "Alice", "Conv", "OPEN", "2025-01-01", "2026-05-01", "500.00"]],
        )
        # Map asks for "Matter Reference" but file has "matter_ref"
        column_map = {"matter_register": {"matter_ref": "Matter Reference"}}
        with pytest.raises(ConfigError, match="Matter Reference"):
            load_file_mapped("matter_register", tmp_path, column_map)


# ── Error path tests ───────────────────────────────────────────────────────────

class TestErrorPaths:
    def test_xls_raises_config_error_with_xls_in_message(self, tmp_path):
        (tmp_path / "matter_register.xls").write_bytes(b"dummy")
        with pytest.raises(ConfigError, match=r"\.xls"):
            load_file_mapped("matter_register", tmp_path, {})

    def test_missing_file_raises_config_error_with_filename(self, tmp_path):
        with pytest.raises(ConfigError, match="matter_register"):
            load_file_mapped("matter_register", tmp_path, {})
