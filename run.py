"""
run.py -- one-command runner for the Trust Account Integrity Engine.

Usage: python run.py --config trust_domain/config/coastal_law.toml
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from trust_domain.config import load_config, validate_config
from trust_domain.rules import load_trust_rules_from_config, RULE_METADATA
from trust_domain.ingestion.loader import load_file_mapped
from trust_domain.reports.exception_report import write_report
from trust_domain.reports.pdf_report import generate_pdf_report
from trust_domain.reports.evidence_pack import generate_evidence_pack
from trust_domain.reports.frontend_adapter import adapt_full_report
from trust_domain.reports.generate_data_ts import generate_data_ts
from trust_domain.reports.run_log import write_run_log
from trust_domain.reports.funds_trail import write_funds_trail

_DATASET_NAMES = [
    "matter_register",
    "client_ledger",
    "trust_bank_statement",
    "reconciliation_summary",
]

# Rules that require the invoice_register supplementary dataset
_INVOICE_RULES = frozenset({
    "R08_FEE_INVOICE_MISSING",
    "R09_FEE_EXCEEDS_INVOICE",
    "R10_INVOICE_POSTDATES_PAYMENT",
})

def _actual_input_path(name: str, in_dir: Path) -> str:
    """Return the posix path of the file that load_file_mapped will use."""
    for ext in (".csv", ".xlsx"):
        p = in_dir / f"{name}{ext}"
        if p.exists():
            return p.as_posix()
    return (in_dir / f"{name}.csv").as_posix()  # fallback; will error at load time


_OUTPUT_FILES = [
    "exception_report.md",
    "exception_report.json",
    "exception_report.pdf",
    "audit.log",
    "evidence_pack.md",
    "funds_trail.md",
    "funds_trail.json",
    "frontend_payload.json",
    "data.ts",
    "run_log.json",
]


def run_pipeline(
    config_path: Path,
    output_dir: Path | None = None,
    input_dir: Path | None = None,
    generated_at: datetime.datetime | None = None,
) -> dict:
    """
    Execute the full integrity engine pipeline.

    Parameters
    ----------
    config_path   Path to a .toml client config file.
    output_dir    Override the output directory from the config (used in tests).
    input_dir     Override the input directory from the config (used in tests).
    generated_at  Override the timestamp (used in tests for determinism).
                  Defaults to datetime.datetime.now() if None.

    Returns a dict with keys: violations, report_dict, pack_dict,
    run_log_data, output_dir, config.
    """
    config = load_config(config_path)
    warnings = validate_config(config)
    for w in warnings:
        print(f"WARNING: {w}")

    out_dir = output_dir if output_dir is not None else Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    in_dir = input_dir if input_dir is not None else Path(config.input_dir)

    if generated_at is None:
        generated_at = datetime.datetime.now()

    datasets = {name: load_file_mapped(name, in_dir, config.column_map) for name in _DATASET_NAMES}

    # Supplementary datasets — loaded lazily only when needed
    _invoice_register: list | None = None
    _allocations: list | None = None

    violations: list = []
    rule_summary: list = []

    for rule_id in config.enabled_rules:
        meta = RULE_METADATA[rule_id]
        records = datasets[meta["dataset"]]

        # Lazy-load supplementary datasets on first use
        if rule_id in _INVOICE_RULES and _invoice_register is None:
            _invoice_register = load_file_mapped("invoice_register", in_dir, config.column_map)
        if rule_id == "R12_BULK_DEPOSIT_UNALLOCATED" and _allocations is None:
            _allocations = load_file_mapped("allocations", in_dir, config.column_map)

        spec: dict = {"rule_id": rule_id}
        if rule_id == "R02_DORMANT_BALANCE":
            spec["dormancy_days"] = config.dormancy_threshold_days
        elif rule_id == "R04_UNMATCHED_BANK_LINE":
            spec["age_days"] = config.unmatched_bank_days
        elif rule_id == "R05_UNRECONCILED_AGEING":
            spec["age_days"] = config.unreconciled_age_days
        elif rule_id == "R06_FIT_OVERHELD":
            spec["fit_days"] = config.fit_transfer_days
        elif rule_id == "R12_BULK_DEPOSIT_UNALLOCATED":
            spec["bulk_min_nzd"] = config.bulk_min_nzd

        rule_fn = load_trust_rules_from_config(
            [spec],
            invoice_register=_invoice_register,
            allocations=_allocations,
            client_ledger=datasets.get("client_ledger"),
        )[0]
        results = [rule_fn(r) for r in records]
        rule_violations = [res for res in results if not res.passed]
        violations.extend(rule_violations)

        n_violations = len(rule_violations)
        rule_summary.append({
            "rule_id":          rule_id,
            "label":            meta["label"],
            "nzls_ref":         meta["nzls_ref"],
            "records_checked":  len(records),
            "violations_found": n_violations,
            "result":           "PASS" if n_violations == 0 else "VIOLATIONS FOUND",
        })

    report_dict = write_report(
        violations=violations,
        report_period=config.review_period,
        firm_name=config.firm_name,
        generated_at=generated_at.date(),
        output_path=out_dir / "exception_report.md",
    )

    generate_pdf_report(
        report_dict=report_dict,
        output_path=out_dir / "exception_report.pdf",
        generated_at=generated_at,
    )

    pack_dict = generate_evidence_pack(
        violations=violations,
        rule_summary=rule_summary,
        firm_name=config.firm_name,
        review_period=config.review_period,
        reviewed_by=config.reviewed_by,
        generated_at=generated_at,
        engine_version=config.engine_version,
        output_dir=out_dir,
    )

    trail_dict = write_funds_trail(
        bank_statement=datasets["trust_bank_statement"],
        allocations=_allocations or [],
        client_ledger=datasets.get("client_ledger"),
        invoice_register=_invoice_register,
        firm_name=config.firm_name,
        report_period=config.review_period,
        generated_at=generated_at.date(),
        output_path=out_dir / "funds_trail.md",
    )

    adapt_full_report(
        report_dict=report_dict,
        pack_dict=pack_dict,
        output_dir=out_dir,
        funds_trail_dict=trail_dict,
    )

    generate_data_ts(
        payload_path=out_dir / "frontend_payload.json",
        output_path=out_dir / "data.ts",
    )

    total_records = sum(len(ds) for ds in datasets.values())
    supplementary_names = []
    if _invoice_register is not None:
        supplementary_names.append("invoice_register")
    if _allocations is not None:
        supplementary_names.append("allocations")
    input_files = [
        _actual_input_path(name, in_dir)
        for name in _DATASET_NAMES + supplementary_names
    ]

    run_log_data = {
        "run_id":               f"RUN-{generated_at.strftime('%Y%m%d-%H%M%S')}",
        "generated_at":         generated_at.isoformat(),
        "engine_version":       config.engine_version,
        "firm_name":            config.firm_name,
        "review_period":        config.review_period,
        "input_files":          input_files,
        "rules_applied":        config.enabled_rules,
        "total_records":        total_records,
        "total_violations":     len(violations),
        "violation_record_ids": sorted(v.record_id for v in violations),
        "output_files":         _OUTPUT_FILES,
        "validation_passed":    True,
    }
    write_run_log(run_log_data, out_dir)

    return {
        "violations":   violations,
        "report_dict":  report_dict,
        "pack_dict":    pack_dict,
        "run_log_data": run_log_data,
        "output_dir":   out_dir,
        "config":       config,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Trust Account Integrity Engine."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to a .toml client config file.",
    )
    args = parser.parse_args()

    generated_at = datetime.datetime.now()
    result = run_pipeline(
        config_path=Path(args.config),
        generated_at=generated_at,
    )

    n   = result["run_log_data"]["total_violations"]
    c   = result["report_dict"]["critical_count"]
    h   = result["report_dict"]["high_count"]
    out = result["output_dir"]

    print(f"\nRun complete - {n} violations found ({c} CRITICAL, {h} HIGH)")
    print(f"Output written to: {out}")
    print(f"Exception report: {out}/exception_report.pdf")
    print(f"Evidence pack:    {out}/evidence_pack.md")
    print(f"Run log:          {out}/run_log.json")


if __name__ == "__main__":
    main()
