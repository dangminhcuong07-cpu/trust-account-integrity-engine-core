"""
Exception report generator for NZ trust account integrity audits.

Accepts a list of TrustRuleResult violations (passed=False) produced by
the rule engine and renders them in two formats:

  - Structured dict  (machine-readable; suitable for further processing)
  - Markdown report  (human-readable; suitable for handing to a TAS)

No datetime.now() or date.today() is called here. The caller must inject
generated_at so the output is fully deterministic and testable.

Usage:
    from trust_domain.reports.exception_report import write_report

    result_dict = write_report(
        violations=violations,
        report_period="May 2026",
        firm_name="Coastal Law Ltd",
        generated_at=datetime.date(2026, 6, 25),
        output_path=Path("reports/may_2026_exceptions.md"),
    )
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from integrity_engine.validation.output_validator import (
    validate_report,
    validate_violations,
)
from trust_domain.rules import RULE_METADATA
from trust_domain.rules.types import TrustRuleResult

_SEVERITY_ORDER: dict[str, int] = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_RECOMMENDED_ACTION: dict[str, str] = {
    "CRITICAL": "ESCALATE",
    "HIGH":     "REVIEW",
    "MEDIUM":   "REVIEW",
    "LOW":      "REVIEW",
}

_ACTION_TEXT = (
    "Investigate and resolve immediately. "
    "Provide written explanation to TAS within 2 business days."
)


def _sort_key(result: TrustRuleResult) -> tuple[int, str]:
    return (_SEVERITY_ORDER.get(result.severity, 99), result.rule_id)


def build_report_dict(
    violations: list[TrustRuleResult],
    report_period: str,
    firm_name: str,
    generated_at: datetime.date,
) -> dict:
    """
    Build the machine-readable report dict from a list of violations.

    Violations are sorted CRITICAL first, then HIGH, then by rule_id
    alphabetically within each severity level. Ordering is deterministic.
    """
    sorted_violations = sorted(violations, key=_sort_key)
    critical_count = sum(1 for v in violations if v.severity == "CRITICAL")
    high_count     = sum(1 for v in violations if v.severity == "HIGH")

    violations_list = []
    for rank, v in enumerate(sorted_violations, start=1):
        meta  = RULE_METADATA.get(v.rule_id, {})
        label = v.label or meta.get("label", v.rule_id)
        violations_list.append({
            "rank":               rank,
            "rule_id":            v.rule_id,
            "severity":           v.severity,
            "nzls_ref":           v.nzls_ref,
            "label":              label,
            "record_id":          v.record_id,
            "evidence":           v.evidence,
            "recommended_action": _RECOMMENDED_ACTION.get(v.severity, "REVIEW"),
        })

    return {
        "report_period":    report_period,
        "firm_name":        firm_name,
        "generated_at":     generated_at.isoformat(),
        "total_violations": len(violations),
        "critical_count":   critical_count,
        "high_count":       high_count,
        "violations":       violations_list,
    }


def build_markdown(report_dict: dict) -> str:
    """Render the structured report dict as a Markdown string."""
    firm        = report_dict["firm_name"]
    period      = report_dict["report_period"]
    generated   = report_dict["generated_at"]
    total       = report_dict["total_violations"]
    n_critical  = report_dict["critical_count"]
    n_high      = report_dict["high_count"]
    violations  = report_dict["violations"]

    lines: list[str] = []
    lines.append("# Trust Account Exception Report")
    lines.append(f"**Firm:** {firm}")
    lines.append(f"**Period:** {period}")
    lines.append(f"**Generated:** {generated}")
    lines.append(f"**Total exceptions:** {total} ({n_critical} CRITICAL, {n_high} HIGH)")
    lines.append("")
    lines.append("---")

    if total == 0:
        lines.append("## No exceptions found")
        lines.append(
            f"This trust account passed all integrity checks for {period}."
        )
        return "\n".join(lines)

    critical_items = [v for v in violations if v["severity"] == "CRITICAL"]
    high_items     = [v for v in violations if v["severity"] == "HIGH"]

    if critical_items:
        lines.append(f"## CRITICAL Exceptions")
        for i, v in enumerate(critical_items, start=1):
            lines.append(f"### {i}. {v['label']}")
            lines.append(
                f"**Rule:** {v['rule_id']} | **Regulation:** {v['nzls_ref']}"
            )
            lines.append(f"**Record:** {v['record_id']}")
            lines.append(f"**Finding:** {v['evidence']}")
            lines.append(f"**Action required:** {_ACTION_TEXT}")
            lines.append("")

    lines.append("---")

    if high_items:
        lines.append(f"## HIGH Exceptions")
        for i, v in enumerate(high_items, start=1):
            lines.append(f"### {i}. {v['label']}")
            lines.append(
                f"**Rule:** {v['rule_id']} | **Regulation:** {v['nzls_ref']}"
            )
            lines.append(f"**Record:** {v['record_id']}")
            lines.append(f"**Finding:** {v['evidence']}")
            lines.append(f"**Action required:** {_ACTION_TEXT}")
            lines.append("")

    lines.append("---")
    lines.append("## Summary")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| CRITICAL | {n_critical} |")
    lines.append(f"| HIGH | {n_high} |")
    lines.append(f"| **Total** | {total} |")

    return "\n".join(lines)


def write_report(
    violations: list[TrustRuleResult],
    report_period: str,
    firm_name: str,
    generated_at: datetime.date,
    output_path: Path,
) -> dict:
    """
    Build the report dict, render markdown, write to output_path, return dict.

    The caller controls the output path. Parent directories are created
    automatically. The returned dict is the machine-readable report.

    Raises ValidationError (from integrity_engine.validation.output_validator)
    if any violation is malformed or if the produced dict's figures do not match
    the source violations.
    """
    validate_violations(violations)
    report_dict = build_report_dict(violations, report_period, firm_name, generated_at)
    validate_report(report_dict, violations)
    markdown = build_markdown(report_dict)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    output_path.with_suffix(".json").write_text(
        json.dumps(report_dict, indent=2), encoding="utf-8"
    )
    return report_dict
