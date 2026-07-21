"""
Frontend schema adapter for the trust account integrity engine.

Transforms the engine's exception_report.json and evidence pack
into the shape expected by the LedgerSandbox React frontend.

No datetime.now() called here. generated_at is always taken from the
report_dict header field, which was injected by the caller.

Usage:
    from trust_domain.reports.frontend_adapter import adapt_full_report
    payload = adapt_full_report(report_dict, pack_dict, output_dir)
"""

from __future__ import annotations

import json
from pathlib import Path

_SOURCE_RECORD_TYPE: dict[str, str] = {
    "B": "bank_statement",
    "L": "client_ledger",
    "M": "matter_register",
    "R": "reconciliation",
}

_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "CRITICAL",
    "HIGH": "WARNING",
}


def adapt_violations(violations_list: list, generated_at: str) -> list:
    """
    Map violations from exception_report.json to frontend RuleViolation shape.

    Field mapping (engine -> frontend):
        record_id           -> id, sourceRecordId
        rule_id             -> ruleId
        label               -> ruleName
        nzls_ref            -> nzLawSocietyRule
        severity            -> severity  (CRITICAL stays; HIGH -> WARNING)
        evidence            -> evidence, description
        record_id prefix    -> sourceRecordType  (B/L/M/R)
        (fixed)             -> status = "UNRESOLVED"
        generated_at        -> dateIdentified
        (null)              -> actionTaken = null
        rank, recommended_action -> dropped
    """
    result = []
    for v in violations_list:
        record_id = v["record_id"]
        prefix = record_id[0].upper() if record_id else ""
        result.append({
            "id":               record_id,
            "ruleId":           v["rule_id"],
            "ruleName":         v["label"],
            "nzLawSocietyRule": v["nzls_ref"],
            "severity":         _SEVERITY_MAP.get(v["severity"], v["severity"]),
            "evidence":         v["evidence"],
            "sourceRecordId":   record_id,
            "sourceRecordType": _SOURCE_RECORD_TYPE.get(prefix, "unknown"),
            "description":      v["evidence"],
            "status":           "UNRESOLVED",
            "dateIdentified":   generated_at,
            "actionTaken":      None,
        })
    return result


def adapt_compliance_checks(rules_applied: list) -> list:
    """
    Map rules_applied from the evidence pack to frontend ComplianceCheck shape.

    Field mapping (engine -> frontend):
        rule_id          -> id
        label            -> name
        nzls_ref         -> nzlsReference
        result           -> status  ("PASS" -> "passed"; "VIOLATIONS FOUND" -> "failed")
        violations_found -> resultCount
        label + nzls_ref -> description  ("{label} — {nzls_ref}")
        records_checked  -> dropped
    """
    result = []
    for r in rules_applied:
        status = "passed" if r["result"] == "PASS" else "failed"
        result.append({
            "id":            r["rule_id"],
            "name":          r["label"],
            "nzlsReference": r["nzls_ref"],
            "status":        status,
            "resultCount":   r["violations_found"],
            "description":   f"{r['label']} — {r['nzls_ref']}",
        })
    return result


def adapt_full_report(
    report_dict: dict,
    pack_dict: dict,
    output_dir: Path,
    funds_trail_dict: dict | None = None,
) -> dict:
    """
    Build the complete frontend payload and write frontend_payload.json.

    Returns the payload dict.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "violations": adapt_violations(
            report_dict["violations"],
            report_dict["generated_at"],
        ),
        "complianceChecks": adapt_compliance_checks(
            pack_dict["rules_applied"]
        ),
        "summary": {
            "totalViolations": report_dict["total_violations"],
            "criticalCount":   report_dict["critical_count"],
            "highCount":       report_dict["high_count"],
            "firmName":        report_dict["firm_name"],
            "period":          report_dict["report_period"],
            "generatedAt":     report_dict["generated_at"],
        },
    }

    if funds_trail_dict is not None:
        payload["fundsTrail"] = funds_trail_dict

    (output_dir / "frontend_payload.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    return payload
