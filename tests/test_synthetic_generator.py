"""
Tests for trust_domain/synthetic/generator.py.

The generator has one public function: generate(output_dir: Path) -> None.
It always writes the same hardcoded dataset (14 seeded error records across
12 rule types: R01-R10, R12, R13).
There is no seed_errors parameter and no ground_truth.json output.
Tests verify: file creation, row counts, seeded-error records present,
and false-positive prevention (key differences from data/sample/).
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Run generate() once into a temp dir; return the dir."""
    from trust_domain.synthetic.generator import generate
    out = tmp_path_factory.mktemp("synthetic")
    generate(out)
    return out


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Group 1 — All four CSV files are created
# ---------------------------------------------------------------------------

class TestFilesCreated:
    def test_matter_register_exists(self, generated):
        assert (generated / "matter_register.csv").exists()

    def test_client_ledger_exists(self, generated):
        assert (generated / "client_ledger.csv").exists()

    def test_trust_bank_statement_exists(self, generated):
        assert (generated / "trust_bank_statement.csv").exists()

    def test_reconciliation_summary_exists(self, generated):
        assert (generated / "reconciliation_summary.csv").exists()

    def test_invoice_register_exists(self, generated):
        assert (generated / "invoice_register.csv").exists()

    def test_allocations_exists(self, generated):
        assert (generated / "allocations.csv").exists()

    def test_no_extra_files_written(self, generated):
        expected = {
            "matter_register.csv",
            "client_ledger.csv",
            "trust_bank_statement.csv",
            "reconciliation_summary.csv",
            "invoice_register.csv",
            "allocations.csv",
        }
        actual = {f.name for f in generated.iterdir()}
        assert actual == expected


# ---------------------------------------------------------------------------
# Group 2 — Row counts match the spec (21 / 38 / 40 / 3)
# ---------------------------------------------------------------------------

class TestRowCounts:
    def test_matter_register_row_count(self, generated):
        rows = _read_csv(generated / "matter_register.csv")
        assert len(rows) == 21, f"Expected 21 matters, got {len(rows)}"

    def test_client_ledger_row_count(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        assert len(rows) == 51, f"Expected 51 ledger entries, got {len(rows)}"

    def test_trust_bank_statement_row_count(self, generated):
        rows = _read_csv(generated / "trust_bank_statement.csv")
        assert len(rows) == 51, f"Expected 51 bank lines, got {len(rows)}"

    def test_reconciliation_summary_row_count(self, generated):
        rows = _read_csv(generated / "reconciliation_summary.csv")
        assert len(rows) == 3, f"Expected 3 recon rows, got {len(rows)}"

    def test_invoice_register_row_count(self, generated):
        rows = _read_csv(generated / "invoice_register.csv")
        assert len(rows) == 3, f"Expected 3 invoice rows, got {len(rows)}"

    def test_allocations_row_count(self, generated):
        rows = _read_csv(generated / "allocations.csv")
        assert len(rows) == 9, f"Expected 9 allocation rows, got {len(rows)}"


# ---------------------------------------------------------------------------
# Group 3 — Each of the 7 seeded error records is present
# ---------------------------------------------------------------------------

class TestSeededErrorRecordsPresent:
    """
    Confirms each ERR-N record exists in the correct file with its
    expected identifying field value. Does not re-run rule logic.
    """

    def test_err1_l009_unreconciled(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L009"), None)
        assert entry is not None, "L009 not found in client_ledger.csv"
        assert entry["reconciled"] == "N", "L009 must have reconciled=N (ERR-1)"

    def test_err2_l021_overdrawn(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L021"), None)
        assert entry is not None, "L021 not found in client_ledger.csv"
        assert float(entry["balance_after_nzd"]) < 0, (
            "L021 must have negative balance_after_nzd (ERR-2)"
        )

    def test_err3_m017_dormant(self, generated):
        rows = _read_csv(generated / "matter_register.csv")
        matter = next((r for r in rows if r["matter_ref"] == "M017"), None)
        assert matter is not None, "M017 not found in matter_register.csv"
        assert matter["last_activity_date"] == "2024-12-15", (
            "M017 must have last_activity_date=2024-12-15 (ERR-3)"
        )
        assert float(matter["current_balance_nzd"]) > 0, (
            "M017 must have positive balance (ERR-3)"
        )

    def test_err4_r002_recon_break(self, generated):
        rows = _read_csv(generated / "reconciliation_summary.csv")
        recon = next((r for r in rows if r["recon_id"] == "R002"), None)
        assert recon is not None, "R002 not found in reconciliation_summary.csv"
        ledger = float(recon["ledger_total_nzd"])
        bank = float(recon["bank_balance_nzd"])
        assert ledger != bank, (
            f"R002 must have ledger_total != bank_balance (ERR-4); got {ledger} == {bank}"
        )

    def test_err5_b031_unmatched_bank_line(self, generated):
        rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in rows if r["statement_id"] == "B031"), None)
        assert line is not None, "B031 not found in trust_bank_statement.csv"
        assert line["matched_ledger_entry"] == "", (
            "B031 must have empty matched_ledger_entry (ERR-5)"
        )

    def test_err6_m021_fit_overheld(self, generated):
        rows = _read_csv(generated / "matter_register.csv")
        matter = next((r for r in rows if r["matter_ref"] == "M021"), None)
        assert matter is not None, "M021 not found in matter_register.csv"
        assert matter["matter_type"] == "FIT", (
            "M021 must have matter_type=FIT (ERR-6)"
        )
        assert float(matter["current_balance_nzd"]) > 0, (
            "M021 must have positive FIT balance (ERR-6)"
        )

    def test_err7_l037_fee_without_invoice(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L037"), None)
        assert entry is not None, "L037 not found in client_ledger.csv"
        assert entry.get("reference", "") == "", (
            "L037 must have empty reference (ERR-7)"
        )
        assert float(entry["payment_nzd"]) > 0, (
            "L037 must have payment > 0 (ERR-7)"
        )


# ---------------------------------------------------------------------------
# Group 4 — False-positive prevention: key differences from data/sample/
# ---------------------------------------------------------------------------

class TestFalsePositivePrevention:
    """
    Confirms the specific changes made in Step 2.2 that prevent the
    spurious R04 and R07 violations that appear when running rules against
    data/sample/ (which lacks the reference column and has B009/B022 unmatched).
    """

    def test_b009_has_matched_ledger_entry(self, generated):
        rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in rows if r["statement_id"] == "B009"), None)
        assert line is not None
        assert line["matched_ledger_entry"] != "", (
            "B009 must have matched_ledger_entry set to prevent spurious R04 flag"
        )

    def test_b022_has_matched_ledger_entry(self, generated):
        rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in rows if r["statement_id"] == "B022"), None)
        assert line is not None
        assert line["matched_ledger_entry"] != "", (
            "B022 must have matched_ledger_entry set to prevent spurious R04 flag"
        )

    def test_l011_description_has_no_disbursement_keyword(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L011"), None)
        assert entry is not None
        assert "disbursement" not in entry["description"].lower(), (
            "L011 description must not contain 'disbursement' (prevents spurious R07 flag)"
        )

    def test_l021_description_has_no_disbursement_keyword(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L021"), None)
        assert entry is not None
        assert "disbursement" not in entry["description"].lower(), (
            "L021 description must not contain 'disbursement' (prevents spurious R07 flag)"
        )

    def test_l035_description_has_no_disbursement_keyword(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L035"), None)
        assert entry is not None
        assert "disbursement" not in entry["description"].lower(), (
            "L035 description must not contain 'disbursement' (prevents spurious R07 flag)"
        )

    def test_l037_disbursement_with_empty_reference_is_the_only_r07_trigger(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        flaggable = [
            r for r in rows
            if any(t in r["description"].lower() for t in ("fee", "disbursement"))
            and float(r.get("payment_nzd") or 0) > 0
            and not r.get("reference", "").strip().startswith("INV-")
        ]
        assert len(flaggable) == 1, (
            f"Expected exactly 1 R07-flaggable entry (L037), got: "
            f"{[r['entry_id'] for r in flaggable]}"
        )
        assert flaggable[0]["entry_id"] == "L037"

    def test_l038_has_valid_invoice_reference(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L038"), None)
        assert entry is not None, "L038 (clean fee counterpart) not found"
        assert entry.get("reference", "").startswith("INV-"), (
            "L038 must have a valid INV-XXXXX reference (clean counterpart to L037)"
        )


# ---------------------------------------------------------------------------
# Group 5 — ERR-8/9/10/12 seeded error records present
# ---------------------------------------------------------------------------

class TestNewSeededErrorRecordsPresent:
    """
    Confirms the ERR-8 through ERR-12 records exist with the right field
    values. Does not run rule logic.
    """

    def test_err8_l039_fee_with_missing_invoice(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L039"), None)
        assert entry is not None, "L039 not found in client_ledger.csv"
        assert entry["reference"] == "INV-99999", (
            "L039 must reference INV-99999 (well-formed but absent from invoice_register)"
        )
        assert float(entry["payment_nzd"]) > 0, "L039 must have payment > 0"

    def test_err8_inv99999_absent_from_invoice_register(self, generated):
        rows = _read_csv(generated / "invoice_register.csv")
        ids = {r["invoice_id"] for r in rows}
        assert "INV-99999" not in ids, (
            "INV-99999 must NOT appear in invoice_register (ERR-8: missing invoice)"
        )

    def test_err9_l040_payment_exceeds_invoice(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L040"), None)
        assert entry is not None, "L040 not found in client_ledger.csv"
        assert entry["reference"] == "INV-00236", "L040 must reference INV-00236"
        inv_rows = _read_csv(generated / "invoice_register.csv")
        inv = next((r for r in inv_rows if r["invoice_id"] == "INV-00236"), None)
        assert inv is not None, "INV-00236 must exist in invoice_register"
        assert float(entry["payment_nzd"]) > float(inv["amount_nzd"]), (
            f"L040 payment {entry['payment_nzd']} must exceed INV-00236 amount {inv['amount_nzd']} (ERR-9)"
        )

    def test_err10_l041_payment_before_invoice_issue(self, generated):
        rows = _read_csv(generated / "client_ledger.csv")
        entry = next((r for r in rows if r["entry_id"] == "L041"), None)
        assert entry is not None, "L041 not found in client_ledger.csv"
        assert entry["reference"] == "INV-00237", "L041 must reference INV-00237"
        inv_rows = _read_csv(generated / "invoice_register.csv")
        inv = next((r for r in inv_rows if r["invoice_id"] == "INV-00237"), None)
        assert inv is not None, "INV-00237 must exist in invoice_register"
        assert entry["entry_date"] < inv["issue_date"], (
            f"L041 entry_date {entry['entry_date']} must be before INV-00237 "
            f"issue_date {inv['issue_date']} (ERR-10)"
        )

    def test_err12a_b046_under_allocated(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B046"), None)
        assert line is not None, "B046 not found in trust_bank_statement.csv"
        credit = float(line["credit_nzd"])
        alloc_rows = _read_csv(generated / "allocations.csv")
        alloc_sum = sum(float(r["amount_nzd"]) for r in alloc_rows if r["bank_line_id"] == "B046")
        assert alloc_sum < credit, (
            f"B046: allocations sum {alloc_sum} must be less than credit {credit} (ERR-12a)"
        )

    def test_err12b_b047_over_allocated(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B047"), None)
        assert line is not None, "B047 not found in trust_bank_statement.csv"
        credit = float(line["credit_nzd"])
        alloc_rows = _read_csv(generated / "allocations.csv")
        alloc_sum = sum(float(r["amount_nzd"]) for r in alloc_rows if r["bank_line_id"] == "B047")
        assert alloc_sum > credit, (
            f"B047: allocations sum {alloc_sum} must exceed credit {credit} (ERR-12b)"
        )

    def test_err12c_b048_no_allocations(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B048"), None)
        assert line is not None, "B048 not found in trust_bank_statement.csv"
        assert float(line["credit_nzd"]) > 0, "B048 must be a credit line"
        alloc_rows = _read_csv(generated / "allocations.csv")
        b048_allocs = [r for r in alloc_rows if r["bank_line_id"] == "B048"]
        assert len(b048_allocs) == 0, (
            f"B048 must have zero allocation rows (ERR-12c), got {len(b048_allocs)}"
        )

    def test_b044_clean_fully_allocated(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B044"), None)
        assert line is not None, "B044 not found in trust_bank_statement.csv"
        credit = float(line["credit_nzd"])
        alloc_rows = _read_csv(generated / "allocations.csv")
        alloc_sum = sum(float(r["amount_nzd"]) for r in alloc_rows if r["bank_line_id"] == "B044")
        assert alloc_sum == credit, (
            f"B044 clean case: allocations sum {alloc_sum} must equal credit {credit}"
        )

    def test_b045_clean_one_to_one_match(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B045"), None)
        assert line is not None, "B045 not found in trust_bank_statement.csv"
        assert line["matched_ledger_entry"] == "L048", (
            "B045 clean 1:1 case must have matched_ledger_entry=L048"
        )

    def test_b049_clean_true_negative_fully_allocated(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B049"), None)
        assert line is not None, "B049 not found in trust_bank_statement.csv"
        credit = float(line["credit_nzd"])
        assert credit > 10000, f"B049 must be > $10,000, got ${credit:,.2f}"
        alloc_rows = _read_csv(generated / "allocations.csv")
        alloc_sum = sum(float(r["amount_nzd"]) for r in alloc_rows if r["bank_line_id"] == "B049")
        assert alloc_sum == credit, (
            f"B049 true-negative: allocations sum {alloc_sum} must equal credit {credit}"
        )
        ledger_rows = _read_csv(generated / "client_ledger.csv")
        ledger_ids = {r["entry_id"] for r in ledger_rows}
        b049_ledger_refs = [r["ledger_entry_id"] for r in alloc_rows if r["bank_line_id"] == "B049"]
        for ref in b049_ledger_refs:
            assert ref in ledger_ids, (
                f"B049 allocation ledger_entry_id {ref!r} not found in client_ledger.csv"
            )


# ---------------------------------------------------------------------------
# Group 6 — ERR-13 seeded error record present (bank balance overdrawn)
# ---------------------------------------------------------------------------

class TestErr13SeededRecords:
    def test_err13_b050_negative_running_balance(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B050"), None)
        assert line is not None, "B050 not found in trust_bank_statement.csv"
        assert float(line["running_balance_nzd"]) < 0, (
            "B050 must have negative running_balance_nzd (ERR-13)"
        )

    def test_b051_clean_positive_running_balance(self, generated):
        bank_rows = _read_csv(generated / "trust_bank_statement.csv")
        line = next((r for r in bank_rows if r["statement_id"] == "B051"), None)
        assert line is not None, "B051 not found in trust_bank_statement.csv"
        assert float(line["running_balance_nzd"]) > 0, (
            "B051 (clean complement) must have positive running_balance_nzd"
        )
