"""
Output validation layer for the integrity engine.

Runs AFTER rules produce violations, BEFORE report generators write anything.
Valid format does not equal correct content — this module enforces content
correctness by checking produced figures against their source data.

Entry points
------------
validate_violations(violations, known_rule_ids=None) -> None
    Checks each violation object for internal consistency.

validate_report(report_dict, violations) -> None
    Checks the structured report dict's figures against the source violations.

validate_evidence_pack(pack_dict, violations, output_dir) -> None
    Checks the evidence pack dict's figures and verifies output files exist.
"""

from __future__ import annotations

from pathlib import Path


class ValidationError(Exception):
    """
    Raised when produced output does not match source records or figures.

    The message always includes the specific values that caused the failure
    and identifies which check or field triggered it.
    """


_VALID_SEVERITIES = frozenset({"CRITICAL", "HIGH"})


def validate_violations(
    violations: list,
    known_rule_ids: set[str] | None = None,
) -> None:
    """
    Validate each violation object before it enters a report.

    Parameters
    ----------
    violations      List of violation objects (RuleResult-like: must have
                    rule_id, record_id, evidence, severity attributes).
    known_rule_ids  Optional set of registered rule IDs. When provided,
                    any rule_id absent from this set raises ValidationError.
                    When None, the rule_id check is skipped.

    Raises
    ------
    ValidationError on the first violation that fails any check.
    Returns None if all violations pass.
    """
    for v in violations:
        rule_id   = getattr(v, "rule_id", "")
        record_id = getattr(v, "record_id", None)
        evidence  = getattr(v, "evidence", None)
        severity  = getattr(v, "severity", None)

        # 1a: record_id must be present and non-empty
        if not record_id:
            raise ValidationError(
                f"record_id mismatch: violation for rule '{rule_id}' has "
                f"empty or missing record_id — rule must set record_id from "
                f"the source record it evaluated"
            )

        # 1b: rule_id must appear in the known registry (when one is supplied)
        if known_rule_ids is not None and rule_id not in known_rule_ids:
            raise ValidationError(
                f"unregistered rule_id: '{rule_id}' is not in the known rule "
                f"registry (record_id='{record_id}', "
                f"registered={sorted(known_rule_ids)})"
            )

        # 1c: evidence must be non-empty — a violation with no evidence is unpublishable
        if not (evidence and evidence.strip()):
            raise ValidationError(
                f"missing evidence: rule_id='{rule_id}' record_id='{record_id}' "
                f"has empty evidence field — unpublishable without supporting detail"
            )

        # 1d: severity must be CRITICAL or HIGH
        if severity not in _VALID_SEVERITIES:
            raise ValidationError(
                f"invalid severity: rule_id='{rule_id}' record_id='{record_id}' "
                f"has severity='{severity}' — must be one of "
                f"{sorted(_VALID_SEVERITIES)}"
            )

    return None


def validate_report(report_dict: dict, violations: list) -> None:
    """
    Validate the structured report dict's figures against the source violations.

    Parameters
    ----------
    report_dict     The dict returned by write_report() / build_report_dict().
    violations      The source violations list that generated the report.

    Raises
    ------
    ValidationError on the first figure or record-id mismatch.
    Returns None if all checks pass.
    """
    expected_total    = len(violations)
    actual_total      = report_dict.get("total_violations")

    expected_critical = sum(
        1 for v in violations if getattr(v, "severity", None) == "CRITICAL"
    )
    expected_high     = sum(
        1 for v in violations if getattr(v, "severity", None) == "HIGH"
    )
    actual_critical   = report_dict.get("critical_count")
    actual_high       = report_dict.get("high_count")

    # 2a: total_violations
    if actual_total != expected_total:
        raise ValidationError(
            f"total_violations mismatch: report says {actual_total} but "
            f"violations list has {expected_total}"
        )

    # 2b: critical_count
    if actual_critical != expected_critical:
        raise ValidationError(
            f"critical_count mismatch: report says {actual_critical} but "
            f"violations list has {expected_critical} CRITICAL violations"
        )

    # 2c: high_count
    if actual_high != expected_high:
        raise ValidationError(
            f"high_count mismatch: report says {actual_high} but "
            f"violations list has {expected_high} HIGH violations"
        )

    # 2d: critical + high == total
    if actual_critical + actual_high != actual_total:
        raise ValidationError(
            f"count arithmetic mismatch: critical_count ({actual_critical}) + "
            f"high_count ({actual_high}) = {actual_critical + actual_high} "
            f"but total_violations = {actual_total}"
        )

    # 2e: record_ids in the report must exactly match the source violations
    source_ids = {getattr(v, "record_id") for v in violations}
    report_ids = {v["record_id"] for v in report_dict.get("violations", [])}

    extra   = report_ids - source_ids
    missing = source_ids - report_ids
    if extra or missing:
        raise ValidationError(
            f"record_id set mismatch in violations list: "
            f"extra={sorted(extra)}, missing={sorted(missing)}"
        )

    return None


def validate_evidence_pack(
    pack_dict: dict,
    violations: list,
    output_dir: Path,  # noqa: ARG001 — reserved for future path-root checks
) -> None:
    """
    Validate the evidence pack dict's figures and verify output files exist on disk.

    Parameters
    ----------
    pack_dict       The dict returned by generate_evidence_pack().
    violations      The source violations list used to generate the pack.
    output_dir      The directory where artefacts were written (unused in
                    current checks but kept for future path-root validation).

    Raises
    ------
    ValidationError on the first failed check.
    Returns None if all checks pass.
    """
    # 3a: total_records_checked must equal sum of records_checked across all rules_applied
    rules_applied      = pack_dict.get("rules_applied", [])
    expected_records   = sum(r["records_checked"] for r in rules_applied)
    actual_records     = pack_dict.get("total_records_checked")
    if actual_records != expected_records:
        raise ValidationError(
            f"total_records_checked mismatch: pack says {actual_records} but "
            f"sum of rules_applied.records_checked = {expected_records}"
        )

    # 3b: total_violations in pack must match the violations list
    expected_violations = len(violations)
    actual_violations   = pack_dict.get("total_violations")
    if actual_violations != expected_violations:
        raise ValidationError(
            f"total_violations mismatch in evidence pack: pack says {actual_violations} "
            f"but violations list has {expected_violations}"
        )

    # 3c: audit_log_path must exist on disk
    audit_log_path = Path(pack_dict.get("audit_log_path", ""))
    if not audit_log_path.exists():
        raise ValidationError(
            f"audit_log_path does not exist on disk: '{audit_log_path}'"
        )

    # 3d: exception_report_path must exist on disk
    exception_report_path = Path(pack_dict.get("exception_report_path", ""))
    if not exception_report_path.exists():
        raise ValidationError(
            f"exception_report_path does not exist on disk: '{exception_report_path}'"
        )

    return None
