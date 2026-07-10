"""
Run-log writer for the integrity engine.

Writes a structured JSON record of what went in and what came out of
each engine run, so any run can be reconstructed or audited.

The caller builds the data dict with all required fields and passes it
here.  This module never calls datetime.now() or date.today() — the
caller must inject 'generated_at' as an ISO string.

Required fields in the data dict:
    run_id               str   — "RUN-YYYYMMDD-HHMMSS" derived from generated_at
    generated_at         str   — ISO datetime (injected by caller)
    engine_version       str
    firm_name            str
    review_period        str
    input_files          list[str]  — CSV paths that were read
    rules_applied        list[str]  — rule_ids in execution order
    total_records        int
    total_violations     int
    violation_record_ids list[str]  — in deterministic (sorted) order
    output_files         list[str]  — files written this run
    validation_passed    bool

Usage:
    from trust_domain.reports.run_log import write_run_log
    path = write_run_log(data, output_dir)
"""

from __future__ import annotations

import json
from pathlib import Path


def write_run_log(data: dict, output_dir: Path) -> Path:
    """
    Write run-log data to run_log.json inside output_dir.

    Creates output_dir if it does not exist. Returns the path of the
    written file.  Never calls datetime.now() or date.today().
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "run_log.json"
    log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return log_path
