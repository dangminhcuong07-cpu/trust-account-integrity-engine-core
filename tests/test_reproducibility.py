"""
Step 3.3 — Reproducibility test.

Same inputs must produce byte-for-byte identical outputs on every run.
The full pipeline is executed twice with an identical fixed generated_at
and all factory rules receive an explicit reference_date so no wall-clock
value enters the computation.

Files compared (must be identical):
    exception_report.json  — structured report dict serialised as JSON
    exception_report.md    — human-readable exception report
    evidence_pack.md       — proof-of-diligence markdown
    run_log.json           — structured run record

File deliberately excluded from comparison:
    audit.log              — contains wall-clock timestamps stamped by
                             append_to_log() at the moment each RULE_RUN
                             entry is written (Step 3.1 Part B).  Two runs
                             at different real-world times will always
                             differ in those timestamps by design — the log
                             records *when* each event actually occurred,
                             not the injected generated_at.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

GENERATED_AT = datetime.datetime(2026, 6, 25, 10, 30, 0)
REF_DATE     = GENERATED_AT.date()
SAMPLE_DIR   = Path("trust_domain/synthetic/sample")
FIRM         = "Coastal Law Ltd"
PERIOD       = "May 2026"
REVIEWED_BY  = "J. Smith (TAS)"
VERSION      = "1.0.0"


@pytest.fixture(scope="session", autouse=True)
def trust_sample_data():
    from trust_domain.synthetic.generator import generate
    generate(SAMPLE_DIR)


def _run_full_pipeline(output_dir: Path) -> None:
    """Execute the complete trust-accounting integrity pipeline into output_dir."""
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

    ledger  = load_file("client_ledger",         SAMPLE_DIR)
    matters = load_file("matter_register",        SAMPLE_DIR)
    bank    = load_file("trust_bank_statement",   SAMPLE_DIR)
    recon   = load_file("reconciliation_summary", SAMPLE_DIR)

    # Each factory rule receives an explicit reference_date so no wall-clock
    # value enters the violation computation.
    RULES = [
        (_r01.overdrawn_ledger,                                        ledger,  "R01_OVERDRAWN_CLIENT_LEDGER"),
        (_r02.make_dormant_rule(reference_date=REF_DATE),              matters, "R02_DORMANT_BALANCE"),
        (_r03.recon_break,                                             recon,   "R03_RECON_BREAK"),
        (_r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE), bank, "R04_UNMATCHED_BANK_LINE"),
        (_r05.make_ageing_rule(max_days=30, reference_date=REF_DATE),  ledger,  "R05_UNRECONCILED_AGEING"),
        (_r06.make_fit_rule(max_days=14, reference_date=REF_DATE),     matters, "R06_FIT_OVERHELD"),
        (_r07.fee_without_invoice,                                     ledger,  "R07_FEE_WITHOUT_INVOICE"),
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
        violations=violations,
        rule_summary=rule_summary,
        firm_name=FIRM,
        review_period=PERIOD,
        reviewed_by=REVIEWED_BY,
        generated_at=GENERATED_AT,
        engine_version=VERSION,
        output_dir=output_dir,
    )

    # output_files uses filenames only (no directory prefix) so that the
    # run_log.json is byte-for-byte identical across runs writing to
    # different output directories.
    run_log_data = {
        "run_id":               f"RUN-{GENERATED_AT.strftime('%Y%m%d-%H%M%S')}",
        "generated_at":         GENERATED_AT.isoformat(),
        "engine_version":       VERSION,
        "firm_name":            FIRM,
        "review_period":        PERIOD,
        "input_files": [
            (SAMPLE_DIR / "matter_register.csv").as_posix(),
            (SAMPLE_DIR / "client_ledger.csv").as_posix(),
            (SAMPLE_DIR / "trust_bank_statement.csv").as_posix(),
            (SAMPLE_DIR / "reconciliation_summary.csv").as_posix(),
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
    write_run_log(run_log_data, output_dir)


def test_identical_output_on_two_runs(tmp_path):
    """
    The full pipeline run twice with identical inputs must produce
    byte-for-byte identical output files.

    If any deterministic output differs between run 1 and run 2, the
    test fails with a message naming the file that differed.
    """
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"

    _run_full_pipeline(dir1)
    _run_full_pipeline(dir2)

    # These four files must be byte-for-byte identical between runs.
    deterministic_files = [
        "exception_report.json",  # structured dict serialised as JSON
        "exception_report.md",
        "evidence_pack.md",
        "run_log.json",
    ]
    for fname in deterministic_files:
        content1 = (dir1 / fname).read_bytes()
        content2 = (dir2 / fname).read_bytes()
        assert content1 == content2, (
            f"Reproducibility failure: '{fname}' differs between run 1 and run 2"
        )

    # audit.log is intentionally excluded: it contains wall-clock timestamps
    # stamped by append_to_log() at the moment each RULE_RUN entry is written
    # (Step 3.1 Part B).  Two separate runs at different real-world times will
    # always differ in those timestamps by design — the log records *when* each
    # event actually occurred, not the injected generated_at.
