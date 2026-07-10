"""
Step 3.4 — Read-only / no-write guarantee tests.

Enforces the data-handling boundary documented in docs/DATA_HANDLING_BOUNDARY.md:
the engine must never modify, delete, or create any file in the source data
directories.  All output must go to the caller-specified output_dir.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

import pytest

# Source data directories — the engine must never write to these
SOURCE_DIR = Path("trust_domain/synthetic/sample")  # what the pipeline reads
LEGACY_DIR = Path("data/sample")                     # original sample data (Step 2.1)

SOURCE_FILES = [
    "matter_register.csv",
    "client_ledger.csv",
    "trust_bank_statement.csv",
    "reconciliation_summary.csv",
]

GENERATED_AT = datetime.datetime(2026, 6, 25, 10, 30, 0)
REF_DATE     = GENERATED_AT.date()
FIRM         = "Coastal Law Ltd"
PERIOD       = "May 2026"
REVIEWED_BY  = "J. Smith (TAS)"
VERSION      = "1.0.0"


@pytest.fixture(scope="session", autouse=True)
def trust_sample_data():
    from trust_domain.synthetic.generator import generate
    generate(SOURCE_DIR)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_hashes(directory: Path) -> dict[str, str]:
    return {fname: _sha256(directory / fname) for fname in SOURCE_FILES}


def _run_pipeline(output_dir: Path) -> dict:
    """Run the full trust-accounting integrity pipeline, return parsed run_log.json."""
    from data.load_sample import load_file
    import trust_domain.rules.r01_overdrawn_ledger as _r01
    import trust_domain.rules.r02_dormant_balance as _r02
    import trust_domain.rules.r03_reconciliation as _r03
    import trust_domain.rules.r04_unmatched_bank_line as _r04
    import trust_domain.rules.r05_unreconciled_ageing as _r05
    import trust_domain.rules.r06_fit_overheld as _r06
    import trust_domain.rules.r07_fee_without_invoice as _r07
    from trust_domain.rules import RULE_METADATA
    from trust_domain.reports.evidence_pack import generate_evidence_pack
    from trust_domain.reports.run_log import write_run_log

    ledger  = load_file("client_ledger",         SOURCE_DIR)
    matters = load_file("matter_register",        SOURCE_DIR)
    bank    = load_file("trust_bank_statement",   SOURCE_DIR)
    recon   = load_file("reconciliation_summary", SOURCE_DIR)

    RULES = [
        (_r01.overdrawn_ledger,                                           ledger,  "R01_OVERDRAWN_CLIENT_LEDGER"),
        (_r02.make_dormant_rule(reference_date=REF_DATE),                 matters, "R02_DORMANT_BALANCE"),
        (_r03.recon_break,                                                recon,   "R03_RECON_BREAK"),
        (_r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE), bank,  "R04_UNMATCHED_BANK_LINE"),
        (_r05.make_ageing_rule(max_days=30, reference_date=REF_DATE),     ledger,  "R05_UNRECONCILED_AGEING"),
        (_r06.make_fit_rule(max_days=14, reference_date=REF_DATE),        matters, "R06_FIT_OVERHELD"),
        (_r07.fee_without_invoice,                                        ledger,  "R07_FEE_WITHOUT_INVOICE"),
    ]

    violations = []
    rule_summary = []
    for rule_fn, records, rule_id in RULES:
        results = [rule_fn(r) for r in records]
        viols   = [res for res in results if not res.passed]
        violations.extend(viols)
        meta = RULE_METADATA[rule_id]
        rule_summary.append({
            "rule_id":          rule_id,
            "label":            meta["label"],
            "nzls_ref":         meta["nzls_ref"],
            "records_checked":  len(records),
            "violations_found": len(viols),
            "result":           "VIOLATIONS FOUND" if viols else "PASS",
        })

    generate_evidence_pack(
        violations=violations, rule_summary=rule_summary,
        firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
        generated_at=GENERATED_AT, engine_version=VERSION, output_dir=output_dir,
    )

    run_log_data = {
        "run_id":               "RUN-" + GENERATED_AT.strftime("%Y%m%d-%H%M%S"),
        "generated_at":         GENERATED_AT.isoformat(),
        "engine_version":       VERSION,
        "firm_name":            FIRM,
        "review_period":        PERIOD,
        "input_files": [
            str(SOURCE_DIR / "matter_register.csv"),
            str(SOURCE_DIR / "client_ledger.csv"),
            str(SOURCE_DIR / "trust_bank_statement.csv"),
            str(SOURCE_DIR / "reconciliation_summary.csv"),
        ],
        "rules_applied":        [rule_id for _, _, rule_id in RULES],
        "total_records":        sum(r["records_checked"] for r in rule_summary),
        "total_violations":     len(violations),
        "violation_record_ids": sorted(v.record_id for v in violations),
        "output_files": [
            "exception_report.md",
            "exception_report.json",
            "audit.log",
            "evidence_pack.md",
            "run_log.json",
        ],
        "validation_passed":    True,
    }
    log_path = write_run_log(run_log_data, output_dir)
    return json.loads(log_path.read_text(encoding="utf-8"))


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_engine_does_not_modify_input_files(tmp_path):
    """
    A full pipeline run must not modify any source CSV file and must not
    create any new file in either source data directory.
    """
    hashes_before        = _snapshot_hashes(SOURCE_DIR)
    names_in_source_before = {p.name for p in SOURCE_DIR.iterdir()}
    names_in_legacy_before = {p.name for p in LEGACY_DIR.iterdir()}

    _run_pipeline(tmp_path)

    # Every source CSV must have an identical SHA-256 hash after the run
    hashes_after = _snapshot_hashes(SOURCE_DIR)
    for fname in SOURCE_FILES:
        assert hashes_before[fname] == hashes_after[fname], (
            f"Read-only guarantee violated: pipeline modified source file '{fname}'"
        )

    # No new files may appear in the source directories
    new_in_source = {p.name for p in SOURCE_DIR.iterdir()} - names_in_source_before
    assert not new_in_source, (
        f"Pipeline created unexpected files in trust_domain/synthetic/sample/: "
        f"{sorted(new_in_source)}"
    )

    new_in_legacy = {p.name for p in LEGACY_DIR.iterdir()} - names_in_legacy_before
    assert not new_in_legacy, (
        f"Pipeline created unexpected files in data/sample/: "
        f"{sorted(new_in_legacy)}"
    )


def test_output_goes_to_output_dir_only(tmp_path):
    """
    Every file written by the pipeline must exist inside output_dir.
    data/sample/ must contain exactly the same files before and after the run.
    """
    names_in_legacy_before = {p.name for p in LEGACY_DIR.iterdir()}

    run_log = _run_pipeline(tmp_path)

    # Every entry in output_files must resolve to a file inside output_dir
    for fname in run_log["output_files"]:
        assert (tmp_path / fname).exists(), (
            f"output_file '{fname}' listed in run_log.json but not found in output_dir"
        )

    # data/sample/ must be unchanged
    names_in_legacy_after = {p.name for p in LEGACY_DIR.iterdir()}
    assert names_in_legacy_before == names_in_legacy_after, (
        f"data/sample/ changed after pipeline run — "
        f"before: {sorted(names_in_legacy_before)}, "
        f"after:  {sorted(names_in_legacy_after)}"
    )
