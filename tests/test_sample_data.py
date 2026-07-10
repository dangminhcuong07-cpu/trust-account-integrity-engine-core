"""
Tests for the synthetic trust ledger generator and loader.

Verifies:
  1. Generator runs and produces all four CSV files.
  2. Each file has the expected headers.
  3. All five seeded errors are present in the data.
  4. Running balances are internally consistent (every matter's balance
     equals its receipts minus payments as computed from ledger entries).
  5. The loader produces Record objects with the correct id and data fields.
"""

import csv
import subprocess
import sys
from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).parent.parent / "data" / "sample"
GENERATE_SCRIPT = Path(__file__).parent.parent / "data" / "generate_sample.py"


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Run the generator into a temporary directory; return that path."""
    out = tmp_path_factory.mktemp("sample")
    result = subprocess.run(
        [sys.executable, str(GENERATE_SCRIPT), "--output-dir", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Generator failed:\n{result.stderr}"
    return out


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ── File presence and headers ─────────────────────────────────────────────────

def test_all_four_files_created(generated):
    for name in ("matter_register", "client_ledger", "trust_bank_statement",
                 "reconciliation_summary"):
        assert (generated / f"{name}.csv").exists()


def test_matter_register_headers(generated):
    rows = _read(generated / "matter_register.csv")
    assert "matter_ref" in rows[0]
    assert "current_balance_nzd" in rows[0]
    assert "status" in rows[0]


def test_client_ledger_headers(generated):
    rows = _read(generated / "client_ledger.csv")
    assert "entry_id" in rows[0]
    assert "receipt_nzd" in rows[0]
    assert "reconciled" in rows[0]


def test_bank_statement_headers(generated):
    rows = _read(generated / "trust_bank_statement.csv")
    assert "statement_id" in rows[0]
    assert "matched_ledger_entry" in rows[0]


def test_reconciliation_headers(generated):
    rows = _read(generated / "reconciliation_summary.csv")
    assert "recon_id" in rows[0]
    assert "difference_nzd" in rows[0]
    assert "status" in rows[0]


# ── Row counts sanity ─────────────────────────────────────────────────────────

def test_matter_register_has_twenty_matters(generated):
    rows = _read(generated / "matter_register.csv")
    assert len(rows) == 20


def test_client_ledger_has_at_least_thirty_entries(generated):
    rows = _read(generated / "client_ledger.csv")
    assert len(rows) >= 30


# ── Seeded error presence ─────────────────────────────────────────────────────

def test_err1_unreconciled_entry_exists(generated):
    """ERR-1: at least one ledger entry with reconciled=N."""
    rows = _read(generated / "client_ledger.csv")
    unreconciled = [r for r in rows if r["reconciled"] == "N"]
    assert len(unreconciled) >= 1, "No unreconciled ledger entry found"


def test_err1_unreconciled_entry_is_on_matter_m008(generated):
    """ERR-1: the specific unreconciled entry belongs to M008 (Schmidt)."""
    rows = _read(generated / "client_ledger.csv")
    unreconciled_m008 = [
        r for r in rows if r["reconciled"] == "N" and r["matter_ref"] == "M008"
    ]
    assert len(unreconciled_m008) >= 1


def test_err2_overdrawn_matter_exists(generated):
    """ERR-2: at least one matter has a negative current_balance_nzd."""
    rows = _read(generated / "matter_register.csv")
    overdrawn = [r for r in rows if float(r["current_balance_nzd"]) < 0]
    assert len(overdrawn) >= 1, "No overdrawn matter found"


def test_err2_overdrawn_matter_is_m016(generated):
    matters = {r["matter_ref"]: r for r in _read(generated / "matter_register.csv")}
    assert float(matters["M016"]["current_balance_nzd"]) < 0


def test_err3_dormant_matter_exists(generated):
    """ERR-3: at least one matter with status=DORMANT and a non-zero balance."""
    rows = _read(generated / "matter_register.csv")
    dormant = [
        r for r in rows
        if r["status"] == "DORMANT" and float(r["current_balance_nzd"]) != 0
    ]
    assert len(dormant) >= 1, "No dormant matter with non-zero balance"


def test_err3_dormant_matter_is_m017(generated):
    matters = {r["matter_ref"]: r for r in _read(generated / "matter_register.csv")}
    assert matters["M017"]["status"] == "DORMANT"
    assert float(matters["M017"]["current_balance_nzd"]) > 0


def test_err4_reconciliation_discrepancy_exists(generated):
    """ERR-4: at least one reconciliation row with status=DISCREPANCY."""
    rows = _read(generated / "reconciliation_summary.csv")
    discrepancies = [r for r in rows if r["status"] == "DISCREPANCY"]
    assert len(discrepancies) >= 1


def test_err4_discrepancy_has_nonzero_difference(generated):
    rows = _read(generated / "reconciliation_summary.csv")
    discrepancies = [r for r in rows if r["status"] == "DISCREPANCY"]
    for r in discrepancies:
        assert r["difference_nzd"] not in ("", "0.00", "0")


def test_err5_orphan_bank_entry_exists(generated):
    """ERR-5: at least one bank statement entry with no matched_ledger_entry."""
    rows = _read(generated / "trust_bank_statement.csv")
    # Exclude the ERR-1 bank entry (B009) which also has no match but for a
    # different reason.  ERR-5 specifically involves a credit (not a debit).
    orphan_credits = [
        r for r in rows
        if r["matched_ledger_entry"] == ""
        and float(r["credit_nzd"]) > 0
        and r["statement_id"] != "B009"
    ]
    assert len(orphan_credits) >= 1, "No orphan bank credit entry found"


# ── Balance consistency ───────────────────────────────────────────────────────

def test_matter_balance_equals_ledger_net(generated):
    """
    For each matter, the current_balance_nzd in matter_register must equal
    sum(receipt_nzd) - sum(payment_nzd) from client_ledger entries.
    """
    matters = {r["matter_ref"]: float(r["current_balance_nzd"])
               for r in _read(generated / "matter_register.csv")}
    ledger = _read(generated / "client_ledger.csv")

    computed: dict[str, float] = {}
    for row in ledger:
        ref = row["matter_ref"]
        net = float(row["receipt_nzd"]) - float(row["payment_nzd"])
        computed[ref] = computed.get(ref, 0.0) + net

    for ref, stated in matters.items():
        calc = computed.get(ref, 0.0)
        assert abs(stated - calc) < 0.01, (
            f"{ref}: matter_register says {stated:.2f}, "
            f"ledger computes {calc:.2f}"
        )


# ── Bank account number fields ────────────────────────────────────────────────

import re as _re
_NZ_BANK_RE = _re.compile(r"^\d{2}-\d{4}-\d{7}-\d{2}$")


def test_trust_account_number_field_exists_in_bank_statement(generated):
    rows = _read(generated / "trust_bank_statement.csv")
    assert "trust_account_number" in rows[0], \
        "trust_bank_statement.csv missing trust_account_number column"


def test_trust_account_number_format_on_every_row(generated):
    """Every bank statement row must carry a valid NZ bank account number."""
    rows = _read(generated / "trust_bank_statement.csv")
    for row in rows:
        acct = row["trust_account_number"]
        assert _NZ_BANK_RE.match(acct), \
            f"{row['statement_id']}: trust_account_number {acct!r} does not match XX-XXXX-XXXXXXX-XX"


def test_trust_account_number_is_same_for_all_rows(generated):
    """All rows belong to one trust account — the number must be uniform."""
    rows = _read(generated / "trust_bank_statement.csv")
    numbers = {r["trust_account_number"] for r in rows}
    assert len(numbers) == 1, f"Expected 1 unique trust account number, got {numbers}"


def test_client_bank_account_field_exists_in_matter_register(generated):
    rows = _read(generated / "matter_register.csv")
    assert "client_bank_account" in rows[0], \
        "matter_register.csv missing client_bank_account column"


def test_client_bank_account_format_on_every_row(generated):
    """Every matter row must carry a valid NZ bank account number for the client."""
    rows = _read(generated / "matter_register.csv")
    for row in rows:
        acct = row["client_bank_account"]
        assert _NZ_BANK_RE.match(acct), \
            f"{row['matter_ref']}: client_bank_account {acct!r} does not match XX-XXXX-XXXXXXX-XX"


# ── Loader integration ────────────────────────────────────────────────────────

def test_loader_produces_records(generated):
    """load_file returns Record objects with correct record_id and data."""
    from data.load_sample import load_file
    records = load_file("matter_register", sample_dir=generated)
    assert len(records) == 20
    assert records[0].record_id == "M001"
    assert isinstance(records[0].data["current_balance_nzd"], float)


def test_loader_load_all_returns_four_datasets(generated):
    from data.load_sample import load_all
    datasets = load_all(sample_dir=generated)
    assert set(datasets.keys()) == {
        "matter_register", "client_ledger",
        "trust_bank_statement", "reconciliation_summary",
    }
    for name, records in datasets.items():
        assert len(records) > 0, f"{name} dataset is empty"
