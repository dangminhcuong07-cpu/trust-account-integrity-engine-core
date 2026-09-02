"""
trust_domain/ingestion/loader.py — format-agnostic dataset loader.

Replaces data/load_sample.py in the pipeline. Supports .csv and .xlsx input,
applies column renaming from a column_map dict, and returns list[Record] with
internal field names ready for rule evaluation.

Public API: load_file_mapped(filename, input_dir, column_map) -> list[Record]

This loader is the engine's one boundary with data it did not generate
itself (a real firm's CSV export). Every failure mode below must raise a
ConfigError with a clear, human-readable message naming the exact problem
(file, row, column, offending value) — never let a raw exception (KeyError,
ValueError, TypeError...) escape to the caller as a traceback.

Tolerated without error:
  - Blank rows (every field empty) — skipped, counted, reported via a
    WARNING print (consistent with run.py's own warning convention).
  - Extra columns not in the internal schema — carried through untouched;
    rules read fields with .get(), so unknown extras are simply ignored.
  - Dates in either ISO (YYYY-MM-DD) or NZ common (DD/MM/YYYY) format —
    normalised to ISO on the way in, so every downstream consumer (string
    comparison in R10, date.fromisoformat in StalenessChecker) sees one
    consistent format regardless of which format the source file used.
  - Thousands-separator commas and surrounding whitespace in numeric
    fields (e.g. "1,234.56", " 500.00 ").

Raised as ConfigError (never a bare exception):
  - A required column absent from the file (whether or not a column_map
    was configured for it).
  - A value in a numeric field that isn't a number once commas/whitespace
    are stripped.
  - A date value that isn't valid ISO or DD/MM/YYYY (including a
    calendar-invalid date such as 31/02/2026).
  - A row with some data but a blank value in the required identifier
    column (as opposed to a wholly blank row, which is just skipped).
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from integrity_engine.core.types import Record
from trust_domain.config.loader import ConfigError

# Internal field names that must be cast to float. Empty string or None -> None.
_FLOAT_FIELDS: dict[str, set[str]] = {
    "matter_register": {"current_balance_nzd"},
    "client_ledger": {"receipt_nzd", "payment_nzd", "balance_after_nzd"},
    "trust_bank_statement": {"credit_nzd", "debit_nzd", "running_balance_nzd"},
    "reconciliation_summary": {"ledger_total_nzd", "bank_balance_nzd", "difference_nzd"},
    "invoice_register": {"amount_nzd"},
    "allocations": {"amount_nzd"},
}

# Internal field names that hold a calendar date and should be normalised to
# ISO when present. Empty string or None is a legitimate "no date yet" value
# (e.g. closed_date on an open matter) and is passed through as "" rather
# than erroring. This is broader than _COMPUTED_DATE_FIELDS below — it also
# covers dates that only ever appear in evidence/report text, so those read
# consistently regardless of which format the source file used.
_DATE_FIELDS: dict[str, set[str]] = {
    "matter_register": {"opened_date", "closed_date", "last_activity_date"},
    "client_ledger": {"entry_date", "reconciled_date"},
    "trust_bank_statement": {"transaction_date"},
    "reconciliation_summary": {"period_end_date"},
    "invoice_register": {"issue_date"},
    "allocations": set(),
}

# Subset of _DATE_FIELDS actually used in date arithmetic or comparison by a
# rule (StalenessChecker age calculations, or R10's issue_date > entry_date
# comparison) — confirmed against every trust_domain/rules/*.py module.
# Only these are load-bearing enough to require: a missing opened_date or
# period_end_date changes nothing about rule correctness (nothing computes
# on them), so requiring them would reject files a real firm could legitimately
# submit. A missing entry_date or transaction_date, by contrast, would make a
# rule either silently skip records or blow up deep in StalenessChecker — so
# those are required, and named explicitly rather than failing quietly or
# with a raw traceback downstream.
_COMPUTED_DATE_FIELDS: dict[str, set[str]] = {
    "matter_register": {"last_activity_date"},
    "client_ledger": {"entry_date"},
    "trust_bank_statement": {"transaction_date"},
    "reconciliation_summary": set(),
    "invoice_register": {"issue_date"},
    "allocations": set(),
}

# The field that acts as Record.record_id per dataset.
_ID_FIELDS: dict[str, str] = {
    "matter_register": "matter_ref",
    "client_ledger": "entry_id",
    "trust_bank_statement": "statement_id",
    "reconciliation_summary": "recon_id",
    "invoice_register": "invoice_id",
    "allocations": "bank_line_id",
}

# Columns the engine actually depends on for correct rule evaluation: the
# record identifier, every numeric field (all are read into calculations),
# and every computed date field. A file missing one of these will silently
# mis-evaluate (e.g. a missing balance column reads as "no balance" rather
# than triggering R01) rather than crash, which is worse for a compliance
# tool — so these are validated up front and named explicitly rather than
# left to fail quietly, or with a raw traceback, downstream.
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    name: frozenset(
        {_ID_FIELDS[name]} | _FLOAT_FIELDS.get(name, set())
        | _COMPUTED_DATE_FIELDS.get(name, set())
    )
    for name in _ID_FIELDS
}

_ISO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ].*)?$")
_DMY_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _row_label(row_num: int) -> str:
    """1-indexed CSV/spreadsheet row number, matching what a user sees in Excel
    (row 1 = header, so the first data row is row 2)."""
    return f"row {row_num}"


def _is_blank_value(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    return False


def _is_blank_row(row: dict) -> bool:
    """True if every value in the row (ignoring the extras/`None` restkey) is blank."""
    return all(_is_blank_value(v) for k, v in row.items() if k is not None)


def _cast_numeric(v, *, filename: str, column: str, row_label: str):
    """Cast a value to float, tolerating thousands-separator commas and
    surrounding whitespace. Empty string or None -> None. Anything else that
    doesn't parse raises a ConfigError naming exactly where the bad value is."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        raise ConfigError(
            f"Could not read '{v}' as a number in column '{column}' ({row_label}) "
            f"of '{filename}'. Expected a plain number, e.g. 1234.56."
        )


def _normalize_date(v, *, filename: str, column: str, row_label: str) -> str:
    """Normalise a date value to ISO 'YYYY-MM-DD'. Accepts ISO (optionally with
    a time component, which is discarded) and DD/MM/YYYY. Empty/None -> "".
    Anything else — including a calendar-invalid date like 31/02/2026 — raises
    a ConfigError naming exactly where the bad value is."""
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if _is_blank_value(v):
        return ""

    s = str(v).strip()

    m = _ISO_DATE_RE.match(s)
    if m:
        try:
            return dt.date.fromisoformat(m.group(1)).isoformat()
        except ValueError:
            raise ConfigError(
                f"'{v}' in column '{column}' ({row_label}) of '{filename}' looks like an "
                f"ISO date but is not a valid calendar date."
            )

    m = _DMY_DATE_RE.match(s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(year, month, day).isoformat()
        except ValueError:
            raise ConfigError(
                f"'{v}' in column '{column}' ({row_label}) of '{filename}' looks like a "
                f"DD/MM/YYYY date but is not a valid calendar date "
                f"(day={day}, month={month}, year={year})."
            )

    raise ConfigError(
        f"Could not read '{v}' as a date in column '{column}' ({row_label}) of "
        f"'{filename}'. Expected ISO format (YYYY-MM-DD) or DD/MM/YYYY."
    )


def _cast_row(row: dict, *, filename: str, float_fields: set[str], date_fields: set[str],
              row_label: str) -> dict:
    out = {}
    for k, v in row.items():
        if k is None:
            continue  # extra unnamed columns from a ragged CSV row — dropped, not fatal
        if k in float_fields:
            out[k] = _cast_numeric(v, filename=filename, column=k, row_label=row_label)
        elif k in date_fields:
            out[k] = _normalize_date(v, filename=filename, column=k, row_label=row_label)
        else:
            out[k] = v
    return out


def _load_csv_raw(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames
    if not headers:
        raise ConfigError(
            f"'{path.name}' has no header row (the file appears to be empty). "
            f"Add a header row with the required column names before retrying."
        )
    return list(headers), rows


def _load_xlsx_raw(path: Path) -> tuple[list[str], list[dict]]:
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
        raise ConfigError(
            f"'{path.name}' has no header row (the file appears to be empty). "
            f"Add a header row with the required column names before retrying."
        )
    headers = [cell.value for cell in all_rows[0]]
    if any(h is None or str(h).strip() == "" for h in headers):
        raise ConfigError(
            f"'{path.name}' has a blank column heading in its header row: {headers!r}. "
            f"Every column must be named before the file can be read."
        )
    result: list[dict] = []
    for row in all_rows[1:]:
        values = [cell.value for cell in row]
        if all(v is None for v in values):
            continue  # skip merged-cell spacer rows and trailing empty rows
        result.append(dict(zip(headers, values)))
    return list(headers), result


def _validate_columns(available: list[str], *, dataset: str, source_name: str,
                       file_map: dict) -> None:
    """
    Raise ConfigError, naming the exact problem, if:
      - a client-side column named in column_map is absent from the file, or
      - a column the engine depends on (id field, numeric fields, date
        fields) is absent from the file after column_map renaming is applied.

    dataset:     logical dataset name (e.g. "client_ledger") — used to look
                 up which columns are required.
    source_name: the actual file name on disk (e.g. "client_ledger.csv") —
                 used only in error messages, so the user can find the file.
    """
    available_set = set(available)

    for internal_name, client_name in file_map.items():
        if client_name not in available_set:
            raise ConfigError(
                f"Mapped column '{client_name}' (for internal field '{internal_name}') "
                f"not found in '{source_name}'. Available columns: {sorted(available_set)}"
            )

    reverse = {client: internal for internal, client in file_map.items()}
    available_internal = {reverse.get(c, c) for c in available_set}
    missing = _REQUIRED_FIELDS.get(dataset, frozenset()) - available_internal
    if missing:
        hint = (
            "Add a column_map entry in your client config to point at the right column, "
            "or add the column to the file."
        )
        raise ConfigError(
            f"'{source_name}' is missing required column(s): {sorted(missing)}. "
            f"Available columns: {sorted(available_set)}. {hint}"
        )


def _apply_column_map(rows: list[dict], file_map: dict) -> list[dict]:
    """Rename client-side column names to internal field names."""
    if not file_map:
        return rows
    reverse = {client: internal for internal, client in file_map.items()}
    return [{reverse.get(k, k): v for k, v in row.items()} for row in rows]


def load_file_mapped(filename: str, input_dir: Path, column_map: dict) -> list[Record]:
    """
    Load a dataset file (CSV or .xlsx), apply column renaming, cast numerics,
    normalise dates, and skip blank rows.

    filename:   logical dataset name — e.g. "client_ledger" (no extension)
    input_dir:  directory containing the files
    column_map: full column_map dict from ClientConfig; the sub-dict for
                this filename is extracted internally. Empty dict = no rename.

    File format precedence: .csv tried first, then .xlsx.
    .xls raises ConfigError immediately — not supported.

    Raises ConfigError (never a bare exception) with a message naming the
    file, row, and column for every recognised failure mode: missing file,
    missing/mismatched column, unparseable date, non-numeric value, or a
    data row missing its required identifier.
    """
    csv_path  = input_dir / f"{filename}.csv"
    xlsx_path = input_dir / f"{filename}.xlsx"
    xls_path  = input_dir / f"{filename}.xls"

    float_fields = _FLOAT_FIELDS.get(filename, set())
    date_fields  = _DATE_FIELDS.get(filename, set())
    id_field     = _ID_FIELDS[filename]
    file_map     = column_map.get(filename, {})

    if csv_path.exists():
        source_name = csv_path.name
        headers, raw = _load_csv_raw(csv_path)
    elif xlsx_path.exists():
        source_name = xlsx_path.name
        headers, raw = _load_xlsx_raw(xlsx_path)
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

    _validate_columns(headers, dataset=filename, source_name=source_name, file_map=file_map)
    mapped = _apply_column_map(raw, file_map)

    records: list[Record] = []
    blank_rows_skipped = 0
    for i, row in enumerate(mapped):
        row_num = i + 2  # header is row 1; first data row is row 2, matching Excel
        label = _row_label(row_num)

        if _is_blank_row(row):
            blank_rows_skipped += 1
            continue

        cast = _cast_row(
            row, filename=source_name, float_fields=float_fields,
            date_fields=date_fields, row_label=label,
        )

        record_id = cast.get(id_field)
        if _is_blank_value(record_id):
            raise ConfigError(
                f"{label.capitalize()} of '{source_name}' is missing a value for "
                f"'{id_field}', the required identifier column for {filename}. "
                f"Every row must have a non-blank {id_field}."
            )

        records.append(Record(record_id=record_id, data=cast))

    if blank_rows_skipped:
        print(f"WARNING: skipped {blank_rows_skipped} blank row(s) in '{source_name}'.")

    return records
