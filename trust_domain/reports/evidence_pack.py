"""
Evidence pack generator for NZ trust account integrity reviews.

Produces three artefacts in output_dir:
  exception_report.md  — human-readable list of what went wrong (via write_report)
  audit.log            — append-only record of every rule run, in execution order
  evidence_pack.md     — proof-of-diligence document for the NZLS Inspectorate

The evidence pack is NOT the exception report. The exception report lists violations.
The evidence pack proves the review happened: what was checked, in what order, what
was found, and that the process was systematic and documented.

The caller must inject generated_at so the output is fully deterministic and
testable. No time-of-call is sampled inside this module.

Usage:
    from trust_domain.reports.evidence_pack import generate_evidence_pack
    import datetime
    from pathlib import Path

    pack = generate_evidence_pack(
        violations=violations,
        rule_summary=rule_summary,
        firm_name="Coastal Law Ltd",
        review_period="May 2026",
        reviewed_by="J. Smith (TAS)",
        generated_at=datetime.datetime(2026, 6, 25, 10, 30, 0),
        engine_version="1.0.0",
        output_dir=Path("reports/may_2026"),
    )
"""

from __future__ import annotations

import datetime
from pathlib import Path

from integrity_engine.audit_trail.writer import AuditWriter
from integrity_engine.core.types import AuditEntry
from integrity_engine.validation.output_validator import validate_evidence_pack
from trust_domain.reports.exception_report import write_report

_STATEMENT_OF_DILIGENCE = """\
This review was conducted using the Trust Account Integrity Engine.
All checks were applied systematically to the trust account records
for {review_period}. This document constitutes evidence of a
structured integrity review conducted in accordance with the
Lawyers and Conveyancers Act (Trust Account) Regulations 2008
and the NZLS Lawyers Trust Accounting Guidelines (June 2024)."""


def generate_evidence_pack(
    violations: list,
    rule_summary: list,
    firm_name: str,
    review_period: str,
    reviewed_by: str,
    generated_at: datetime.datetime,
    engine_version: str,
    output_dir: Path,
) -> dict:
    """
    Generate an evidence pack proving a systematic trust account integrity review
    was conducted.

    Parameters
    ----------
    violations      List of TrustRuleResult objects with passed=False.
    rule_summary    List of dicts, one per rule run, with keys:
                      rule_id, label, nzls_ref, records_checked,
                      violations_found, result ("PASS" | "VIOLATIONS FOUND")
    firm_name       Law firm name for the cover page.
    review_period   Human-readable period string (e.g. "May 2026").
    reviewed_by     TAS name to appear on the cover page.
    generated_at    Injected by the caller — never sampled inside this function.
    engine_version  Version string (e.g. "1.0.0").
    output_dir      Directory where all three artefacts are written.

    Returns
    -------
    EvidencePack dict with all pack fields plus file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pack_id = f"EP-{generated_at.strftime('%Y%m%d-%H%M%S')}"
    timestamp_str = generated_at.isoformat()

    # 1. Write exception report
    exception_report_path = output_dir / "exception_report.md"
    write_report(
        violations=violations,
        report_period=review_period,
        firm_name=firm_name,
        generated_at=generated_at.date(),
        output_path=exception_report_path,
    )

    # 2. Write audit log — clear first so each call is idempotent
    audit_log_path = output_dir / "audit.log"
    if audit_log_path.exists():
        audit_log_path.unlink()

    writer = AuditWriter(output_dir=output_dir)
    n_rules = len(rule_summary)

    for seq, rule_entry in enumerate(rule_summary, start=1):
        entry = AuditEntry(
            entry_id=f"{pack_id}-{seq:02d}",
            source_record_id=rule_entry["rule_id"],
            event_type="RULE_RUN",
            timestamp=timestamp_str,
            detail=(
                f"checked {rule_entry['records_checked']} records "
                f"— {rule_entry['result']}"
            ),
        )
        writer.append_to_log(entry)

    total_violations = len(violations)
    final_entry = AuditEntry(
        entry_id=f"{pack_id}-{n_rules + 1:02d}",
        source_record_id="REVIEW",
        event_type="REVIEW_COMPLETE",
        timestamp=timestamp_str,
        detail=(
            f"{total_violations} violations found across {n_rules} rules "
            f"for {review_period}"
        ),
    )
    writer.append_to_log(final_entry)

    # 3. Build pack dict
    conclusion = "CLEAR" if total_violations == 0 else "EXCEPTIONS FOUND — see report"
    pack = {
        "pack_id":               pack_id,
        "firm_name":             firm_name,
        "review_period":         review_period,
        "reviewed_by":           reviewed_by,
        "generated_at":          timestamp_str,
        "engine_version":        engine_version,
        "rules_applied":         list(rule_summary),
        "total_records_checked": sum(r["records_checked"] for r in rule_summary),
        "total_violations":      total_violations,
        "exception_report_path": str(exception_report_path),
        "audit_log_path":        str(audit_log_path),
        "conclusion":            conclusion,
    }

    # 4. Write evidence pack markdown
    markdown = _build_markdown(pack, audit_log_path)
    evidence_pack_path = output_dir / "evidence_pack.md"
    evidence_pack_path.write_text(markdown, encoding="utf-8")

    validate_evidence_pack(pack, violations, output_dir)
    return pack


def _build_markdown(pack: dict, audit_log_path: Path) -> str:
    lines: list[str] = []

    lines.append("# Trust Account Integrity Review — Evidence Pack")
    lines.append(f"**Pack ID:** {pack['pack_id']}")
    lines.append(f"**Firm:** {pack['firm_name']}")
    lines.append(f"**Review period:** {pack['review_period']}")
    lines.append(f"**Reviewed by (TAS):** {pack['reviewed_by']}")
    lines.append(f"**Generated:** {pack['generated_at']}")
    lines.append(f"**Engine version:** {pack['engine_version']}")
    lines.append("")
    lines.append("---")
    lines.append("## Rules Applied")
    lines.append("| # | Rule ID | Regulation | Records checked | Violations |")
    lines.append("|---|---------|------------|-----------------|------------|")
    for i, rule in enumerate(pack["rules_applied"], start=1):
        lines.append(
            f"| {i} | {rule['rule_id']} | {rule['nzls_ref']} "
            f"| {rule['records_checked']} | {rule['violations_found']} |"
        )
    lines.append("")
    lines.append(
        f"**Total records reviewed across all rules:** {pack['total_records_checked']}"
    )
    lines.append("")
    lines.append("---")
    lines.append("## Conclusion")
    lines.append(f"**{pack['conclusion']}**")
    if pack["total_violations"] > 0:
        lines.append("")
        lines.append(
            "Full exception details: see attached exception report at exception_report.md"
        )
    lines.append("")
    lines.append("---")
    lines.append("## Audit Trail")
    if audit_log_path.exists():
        for log_line in audit_log_path.read_text(encoding="utf-8").splitlines():
            if log_line.strip():
                # log format: timestamp | event_type | source_record_id | detail
                # Strip the wall-clock timestamp so evidence_pack.md is deterministic
                parts = log_line.split(" | ", maxsplit=1)
                body = parts[1] if len(parts) == 2 else log_line
                lines.append(f"- {body}")
    lines.append("")
    lines.append("---")
    lines.append("## Statement of Diligence")
    lines.append(_STATEMENT_OF_DILIGENCE.format(review_period=pack["review_period"]))

    return "\n".join(lines)
