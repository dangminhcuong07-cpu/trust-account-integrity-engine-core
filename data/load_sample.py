"""
Sample data loader — reads generated CSV files into engine Record objects.

The loader is intentionally thin: it reads rows, converts numeric fields to
float where expected, and wraps each row in a Record.  Domain-specific
validation (balance checks, age checks, etc.) is left to the rule layer.

Usage:
    from data.load_sample import load_all
    datasets = load_all()            # dict[str, list[Record]]
    ledger_records = datasets["client_ledger"]
"""

import csv
from pathlib import Path

from integrity_engine.core.types import Record

_DEFAULT_DIR = Path(__file__).parent / "sample"

# Numeric fields that should be cast to float (empty string → None).
_FLOAT_FIELDS: dict[str, set[str]] = {
    "matter_register": {"current_balance_nzd"},
    "client_ledger": {"receipt_nzd", "payment_nzd", "balance_after_nzd"},
    # trust_account_number and matched_ledger_entry are strings — not cast
    "trust_bank_statement": {"credit_nzd", "debit_nzd", "running_balance_nzd"},
    "reconciliation_summary": {
        "ledger_total_nzd", "bank_balance_nzd", "difference_nzd"
    },
}

# The field that acts as the unique identifier per file.
_ID_FIELDS: dict[str, str] = {
    "matter_register": "matter_ref",
    "client_ledger": "entry_id",
    "trust_bank_statement": "statement_id",
    "reconciliation_summary": "recon_id",
}


def _cast_row(row: dict, float_fields: set[str]) -> dict:
    out = {}
    for k, v in row.items():
        if k in float_fields:
            out[k] = float(v) if v != "" else None
        else:
            out[k] = v
    return out


def load_file(name: str, sample_dir: Path = _DEFAULT_DIR) -> list[Record]:
    """Load one CSV file by logical name (e.g. "client_ledger")."""
    path = sample_dir / f"{name}.csv"
    id_field = _ID_FIELDS[name]
    float_fields = _FLOAT_FIELDS.get(name, set())
    records = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            data = _cast_row(row, float_fields)
            records.append(Record(record_id=data[id_field], data=data))
    return records


def load_all(sample_dir: Path = _DEFAULT_DIR) -> dict[str, list[Record]]:
    """Load all four sample CSV files, returning a dict keyed by file name."""
    return {name: load_file(name, sample_dir) for name in _ID_FIELDS}
