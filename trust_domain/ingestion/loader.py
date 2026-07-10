"""
trust_domain/ingestion/loader.py — format-agnostic dataset loader.

Replaces data/load_sample.py in the pipeline. Supports .csv and .xlsx input,
applies column renaming from a column_map dict, and returns list[Record] with
internal field names ready for rule evaluation.

Public API: load_file_mapped(filename, input_dir, column_map) -> list[Record]
"""
from __future__ import annotations

import csv
from pathlib import Path

from integrity_engine.core.types import Record
from trust_domain.config.loader import ConfigError

# Internal field names that must be cast to float. Empty string or None -> None.
_FLOAT_FIELDS: dict[str, set[str]] = {
    "matter_register": {"current_balance_nzd"},
    "client_ledger": {"receipt_nzd", "payment_nzd", "balance_after_nzd"},
    "trust_bank_statement": {"credit_nzd", "debit_nzd", "running_balance_nzd"},
    "reconciliation_summary": {"ledger_total_nzd", "bank_balance_nzd", "difference_nzd"},
}

# The field that acts as Record.record_id per dataset.
_ID_FIELDS: dict[str, str] = {
    "matter_register": "matter_ref",
    "client_ledger": "entry_id",
    "trust_bank_statement": "statement_id",
    "reconciliation_summary": "recon_id",
}


def _cast_numeric(v) -> float | None:
    """Cast a value to float, returning None for empty string or None."""
    if v is None or v == "":
        return None
    return float(v)


def _cast_row(row: dict, float_fields: set[str]) -> dict:
    return {k: (_cast_numeric(v) if k in float_fields else v) for k, v in row.items()}


def _load_csv_raw(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_xlsx_raw(path: Path) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise ConfigError(
            "openpyxl is required to read .xlsx files. Run: pip install openpyxl"
        )
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.rows)
    wb.close()
    if not all_rows:
        return []
    headers = [cell.value for cell in all_rows[0]]
    result: list[dict] = []
    for row in all_rows[1:]:
        values = [cell.value for cell in row]
        if all(v is None for v in values):
            continue  # skip merged-cell spacer rows and trailing empty rows
        result.append(dict(zip(headers, values)))
    return result


def _validate_mapped_columns(rows: list[dict], file_map: dict) -> None:
    """Raise ConfigError if a mapped client-side column is absent from the file."""
    if not rows or not file_map:
        return
    available = set(rows[0].keys())
    for internal_name, client_name in file_map.items():
        if client_name not in available:
            raise ConfigError(
                f"Mapped column '{client_name}' (for internal field '{internal_name}') "
                f"not found in file. Available columns: {sorted(available)}"
            )


def _apply_column_map(rows: list[dict], file_map: dict) -> list[dict]:
    """Rename client-side column names to internal field names."""
    if not file_map:
        return rows
    reverse = {client: internal for internal, client in file_map.items()}
    return [{reverse.get(k, k): v for k, v in row.items()} for row in rows]


def load_file_mapped(filename: str, input_dir: Path, column_map: dict) -> list[Record]:
    """
    Load a dataset file (CSV or .xlsx), apply column renaming, cast numerics.

    filename:   logical dataset name — e.g. "client_ledger" (no extension)
    input_dir:  directory containing the files
    column_map: full column_map dict from ClientConfig; the sub-dict for
                this filename is extracted internally. Empty dict = no rename.

    File format precedence: .csv tried first, then .xlsx.
    .xls raises ConfigError immediately — not supported.
    """
    csv_path  = input_dir / f"{filename}.csv"
    xlsx_path = input_dir / f"{filename}.xlsx"
    xls_path  = input_dir / f"{filename}.xls"

    float_fields = _FLOAT_FIELDS.get(filename, set())
    id_field     = _ID_FIELDS[filename]
    file_map     = column_map.get(filename, {})

    if csv_path.exists():
        raw = _load_csv_raw(csv_path)
    elif xlsx_path.exists():
        raw = _load_xlsx_raw(xlsx_path)
    elif xls_path.exists():
        raise ConfigError(
            f"Legacy .xls format is not supported. "
            f"Please save '{filename}.xls' as .xlsx and try again."
        )
    else:
        raise ConfigError(
            f"No input file found for '{filename}'. "
            f"Tried: '{csv_path}' and '{xlsx_path}'."
        )

    _validate_mapped_columns(raw, file_map)
    rows = _apply_column_map(raw, file_map)
    return [
        Record(record_id=row[id_field], data=_cast_row(row, float_fields))
        for row in rows
    ]
