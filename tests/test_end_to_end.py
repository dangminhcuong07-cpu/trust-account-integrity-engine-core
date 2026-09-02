"""
End-to-end test for the full integrity engine pipeline.

Calls run_pipeline() directly (no subprocess). Uses trust_domain/synthetic/sample
as input_dir so the violation count is deterministic (exactly 23 seeded errors
across the 12 enabled rules, measured as at the injected generated_at date —
see test_exception_report_total_violations_is_23 for the per-rule breakdown).
coastal_law.toml supplies all other config (firm name, thresholds, rules).
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pytest

# run.py lives at the project root, one level above tests/
sys.path.insert(0, str(Path(__file__).parent.parent))
from run import run_pipeline

_CONFIG_PATH = Path("trust_domain/config/coastal_law.toml")
_SYNTHETIC_SAMPLE = Path("trust_domain/synthetic/sample")
_GENERATED_AT = datetime.datetime(2026, 6, 25, 10, 30, 0)

_EXPECTED_OUTPUT_FILES = [
    "exception_report.json",
    "exception_report.md",
    "exception_report.pdf",
    "evidence_pack.md",
    "funds_trail.md",
    "funds_trail.json",
    "frontend_payload.json",
    "run_log.json",
    "data.ts",
]


@pytest.fixture(scope="module", autouse=True)
def generate_synthetic_sample():
    """Ensure trust_domain/synthetic/sample CSVs exist before any test runs."""
    from trust_domain.synthetic.generator import generate
    generate(_SYNTHETIC_SAMPLE)


@pytest.fixture(scope="module")
def pipeline_result(tmp_path_factory):
    out = tmp_path_factory.mktemp("e2e_output")
    return run_pipeline(
        config_path=_CONFIG_PATH,
        output_dir=out,
        input_dir=_SYNTHETIC_SAMPLE,
        generated_at=_GENERATED_AT,
    )


def test_all_output_files_exist(pipeline_result):
    out = pipeline_result["output_dir"]
    for fname in _EXPECTED_OUTPUT_FILES:
        assert (out / fname).exists(), f"Missing output file: {fname}"


def test_run_log_validation_passed(pipeline_result):
    out = pipeline_result["output_dir"]
    run_log = json.loads((out / "run_log.json").read_text(encoding="utf-8"))
    assert run_log["validation_passed"] is True


def test_exception_report_total_violations_is_23(pipeline_result):
    # All ageing rules (R02/R04/R05/R06) are measured "as at" _GENERATED_AT
    # (2026-06-25), the same reference date the per-rule unit tests in
    # test_trust_rules.py use — run.py now passes generated_at.date() as
    # reference_date. Before that fix these rules used the wall clock, so
    # this total silently depended on the calendar date the suite ran on.
    #
    # R01:  L021, L053, L061, L071, L072, L073 (6) — L053 is ERR-14a (Nguy
    #       cross-matter), L061 is ERR-15 (Ms M gradual deficit via 4 smaller
    #       transfers), L071/L072/L073 are ERR-19 (David Small persistent
    #       uncorrected overdraw)
    # R02:  M017 (1)
    # R03:  R002, R004 (2) — R004 is ERR-17 (Stirling false certification)
    # R04:  B031 (1) — B048 (the orphan bulk credit) is dated 2026-06-24, so
    #       at the 2026-06-25 reference date it is 1 day old and correctly
    #       BELOW R04's 5-day threshold. It is still caught by R12. The old
    #       expectation "R04: B031, B048 (2)" was only ever true because the
    #       wall clock had drifted ≥5 days past 2026-06-24 — and it
    #       contradicted test_trust_rules.py::TestR04UnmatchedBankLine::
    #       test_only_one_violation_in_synthetic_data, which asserts exactly
    #       one R04 hit at REF_DATE.
    # R05:  L009 (1)
    # R06:  M021 (1)
    # R07:  L037 (1)
    # R08:  L039, L068 (2) — L068 is ERR-18 (Kejriwal phantom invoice)
    # R09:  L040 (1)
    # R10:  L041 (1)
    # R12:  B031, B046, B047, B048 (4)
    # R13:  B050, B055 (2) — B055 is ERR-16 (Ms M gradual deficit, bank side)
    # Total = 23
    out = pipeline_result["output_dir"]
    report = json.loads((out / "exception_report.json").read_text(encoding="utf-8"))
    assert report["total_violations"] == 23, (
        f"Expected 23 violations, got {report['total_violations']}"
    )


def test_violation_count_does_not_depend_on_wall_clock(tmp_path, monkeypatch):
    # Regression guard for PROJECT_SNAPSHOT.md known issue #3: the ageing
    # rules (R02/R04/R05/R06) used to fall back to date.today() when run via
    # run.py, so the same input produced different findings on different
    # calendar days. Every ageing rule reaches the clock through
    # StalenessChecker, so pretending "today" is years in the future must
    # change nothing when generated_at is injected.
    import integrity_engine.flagging.staleness as staleness

    class _FarFutureDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2031, 1, 1)

    monkeypatch.setattr(staleness, "date", _FarFutureDate)
    result = run_pipeline(
        config_path=_CONFIG_PATH,
        output_dir=tmp_path / "wallclock",
        input_dir=_SYNTHETIC_SAMPLE,
        generated_at=_GENERATED_AT,
    )
    assert len(result["violations"]) == 23, (
        "Ageing rules are still reading the wall clock instead of the "
        "injected generated_at reference date"
    )


def test_no_files_written_to_data_sample(pipeline_result):
    data_sample = Path("data/sample")
    if not data_sample.exists():
        return
    actual_names = {f.name for f in data_sample.iterdir()}
    expected_names = {
        "matter_register.csv",
        "client_ledger.csv",
        "trust_bank_statement.csv",
        "reconciliation_summary.csv",
        "invoice_register.csv",
        "allocations.csv",
    }
    assert actual_names == expected_names, (
        f"Unexpected files appeared in data/sample/: "
        f"{actual_names - expected_names}"
    )


def test_data_ts_starts_with_autogenerated_comment(pipeline_result):
    out = pipeline_result["output_dir"]
    content = (out / "data.ts").read_text(encoding="utf-8")
    assert content.startswith("// AUTO-GENERATED by Trust Account Integrity Engine"), (
        "data.ts does not start with the expected auto-generated comment"
    )


def test_cli_as_at_flag_gives_reproducible_count(monkeypatch, capsys):
    # `python run.py --config ... --as-at 2026-06-25` must match the
    # injected-generated_at result above (23), regardless of today's date.
    import run as run_module
    monkeypatch.setattr(
        sys, "argv",
        ["run.py", "--config", str(_CONFIG_PATH), "--as-at", "2026-06-25"],
    )
    run_module.main()
    out = capsys.readouterr().out
    assert "Run complete - 23 violations found" in out, out
