"""
Tests for trust_domain/reports/frontend_adapter.py — Step 4.3

TDD RED: all tests written before implementation exists.
Covers adapt_violations(), adapt_compliance_checks(), adapt_full_report().
"""
import json
from pathlib import Path

import pytest

# Realistic report_dict (from exception_report.json format)
REPORT_DICT = {
    "report_period": "May 2026",
    "firm_name": "Coastal Law Ltd",
    "generated_at": "2026-06-25",
    "total_violations": 4,
    "critical_count": 1,
    "high_count": 3,
    "violations": [
        {
            "rank": 1,
            "rule_id": "R01_OVERDRAWN_CLIENT_LEDGER",
            "severity": "CRITICAL",
            "nzls_ref": "LCA Reg 12(6)(a)",
            "label": "Overdrawn client ledger entry",
            "record_id": "L021",
            "evidence": "entry L021: balance -2500.00 NZD",
            "recommended_action": "ESCALATE",
        },
        {
            "rank": 2,
            "rule_id": "R04_UNMATCHED_BANK_LINE",
            "severity": "HIGH",
            "nzls_ref": "LCA Reg 11",
            "label": "Bank line with no matching ledger entry",
            "record_id": "B031",
            "evidence": "bank line B031 no matched ledger entry",
            "recommended_action": "REVIEW",
        },
        {
            "rank": 3,
            "rule_id": "R02_DORMANT_BALANCE",
            "severity": "HIGH",
            "nzls_ref": "NZLS Guidelines s4.3",
            "label": "Dormant balance",
            "record_id": "M017",
            "evidence": "matter M017 dormant 557 days",
            "recommended_action": "REVIEW",
        },
        {
            "rank": 4,
            "rule_id": "R03_RECON_BREAK",
            "severity": "HIGH",
            "nzls_ref": "LCA Reg 12(1)",
            "label": "Reconciliation break",
            "record_id": "R002",
            "evidence": "recon R002 break",
            "recommended_action": "REVIEW",
        },
    ],
}

# Realistic pack_dict (from evidence_pack / generate_evidence_pack format)
PACK_DICT = {
    "pack_id": "EP-20260625-103000",
    "firm_name": "Coastal Law Ltd",
    "review_period": "May 2026",
    "reviewed_by": "J. Smith (TAS)",
    "generated_at": "2026-06-25T10:30:00",
    "engine_version": "1.0.0",
    "rules_applied": [
        {
            "rule_id": "R01_OVERDRAWN_CLIENT_LEDGER",
            "label": "Overdrawn client ledger entry",
            "nzls_ref": "LCA Reg 12(6)(a)",
            "records_checked": 38,
            "violations_found": 1,
            "result": "VIOLATIONS FOUND",
        },
        {
            "rule_id": "R02_DORMANT_BALANCE",
            "label": "Dormant balance",
            "nzls_ref": "NZLS Guidelines s4.3",
            "records_checked": 21,
            "violations_found": 1,
            "result": "VIOLATIONS FOUND",
        },
        {
            "rule_id": "R03_RECON_BREAK",
            "label": "Reconciliation break",
            "nzls_ref": "LCA Reg 12(1)",
            "records_checked": 3,
            "violations_found": 1,
            "result": "VIOLATIONS FOUND",
        },
        {
            "rule_id": "R04_UNMATCHED_BANK_LINE",
            "label": "Bank line with no matching ledger entry",
            "nzls_ref": "LCA Reg 11",
            "records_checked": 40,
            "violations_found": 1,
            "result": "VIOLATIONS FOUND",
        },
        {
            "rule_id": "R07_FEE_WITHOUT_INVOICE",
            "label": "Fee or disbursement entry lacks valid invoice reference",
            "nzls_ref": "NZLS PMG s9",
            "records_checked": 38,
            "violations_found": 0,
            "result": "PASS",
        },
    ],
    "total_records_checked": 140,
    "total_violations": 4,
    "exception_report_path": "/output/exception_report.md",
    "audit_log_path": "/output/audit.log",
    "conclusion": "EXCEPTIONS FOUND — see report",
}


class TestAdaptViolations:
    """adapt_violations(violations_list, generated_at) -> list"""

    def test_renames_record_id_to_id(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert result[0]["id"] == "L021"
        assert "record_id" not in result[0]

    def test_renames_rule_id_to_ruleId(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert result[0]["ruleId"] == "R01_OVERDRAWN_CLIENT_LEDGER"

    def test_renames_label_to_ruleName(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert result[0]["ruleName"] == "Overdrawn client ledger entry"

    def test_renames_nzls_ref_to_nzLawSocietyRule(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert result[0]["nzLawSocietyRule"] == "LCA Reg 12(6)(a)"

    def test_critical_severity_stays_critical(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        critical = next(v for v in result if v["ruleId"] == "R01_OVERDRAWN_CLIENT_LEDGER")
        assert critical["severity"] == "CRITICAL"

    def test_high_severity_maps_to_warning(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        high_violations = [v for v in result if v["ruleId"] != "R01_OVERDRAWN_CLIENT_LEDGER"]
        assert all(v["severity"] == "WARNING" for v in high_violations), (
            f"Expected all HIGH to map to WARNING, got: "
            f"{[v['severity'] for v in high_violations]}"
        )

    def test_status_always_unresolved(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert all(v["status"] == "UNRESOLVED" for v in result)

    def test_source_record_type_b_prefix(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        bank = next(v for v in result if v["id"] == "B031")
        assert bank["sourceRecordType"] == "bank_statement"

    def test_source_record_type_l_prefix(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        ledger = next(v for v in result if v["id"] == "L021")
        assert ledger["sourceRecordType"] == "client_ledger"

    def test_source_record_type_m_prefix(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        matter = next(v for v in result if v["id"] == "M017")
        assert matter["sourceRecordType"] == "matter_register"

    def test_source_record_type_r_prefix(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        recon = next(v for v in result if v["id"] == "R002")
        assert recon["sourceRecordType"] == "reconciliation"

    def test_source_record_id_equals_id(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert all(v["sourceRecordId"] == v["id"] for v in result)

    def test_description_equals_evidence(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert all(v["description"] == v["evidence"] for v in result)

    def test_date_identified_from_generated_at(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert all(v["dateIdentified"] == "2026-06-25" for v in result)

    def test_action_taken_is_null(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert all(v["actionTaken"] is None for v in result)

    def test_rank_and_recommended_action_dropped(self):
        from trust_domain.reports.frontend_adapter import adapt_violations
        result = adapt_violations(REPORT_DICT["violations"], REPORT_DICT["generated_at"])
        assert all("rank" not in v for v in result)
        assert all("recommended_action" not in v for v in result)


class TestAdaptComplianceChecks:
    """adapt_compliance_checks(rules_applied) -> list"""

    def test_renames_rule_id_to_id(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        assert result[0]["id"] == "R01_OVERDRAWN_CLIENT_LEDGER"

    def test_renames_label_to_name(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        assert result[0]["name"] == "Overdrawn client ledger entry"

    def test_renames_nzls_ref_to_nzlsReference(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        assert result[0]["nzlsReference"] == "LCA Reg 12(6)(a)"

    def test_pass_result_maps_to_passed_status(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        passing = next(r for r in result if r["id"] == "R07_FEE_WITHOUT_INVOICE")
        assert passing["status"] == "passed"

    def test_violations_found_result_maps_to_failed_status(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        failing = next(r for r in result if r["id"] == "R01_OVERDRAWN_CLIENT_LEDGER")
        assert failing["status"] == "failed"

    def test_result_count_from_violations_found(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        assert result[0]["resultCount"] == 1
        passing = next(r for r in result if r["id"] == "R07_FEE_WITHOUT_INVOICE")
        assert passing["resultCount"] == 0

    def test_description_combines_label_and_nzls_ref(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        assert result[0]["description"] == (
            "Overdrawn client ledger entry — LCA Reg 12(6)(a)"
        )

    def test_records_checked_is_dropped(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks
        result = adapt_compliance_checks(PACK_DICT["rules_applied"])
        assert all("records_checked" not in r for r in result)


class TestAdaptFullReport:
    """adapt_full_report(report_dict, pack_dict, output_dir) -> dict"""

    def test_has_violations_key(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert "violations" in payload
        assert len(payload["violations"]) == 4

    def test_has_compliance_checks_key(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert "complianceChecks" in payload
        assert len(payload["complianceChecks"]) == 5

    def test_summary_total_violations(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert payload["summary"]["totalViolations"] == 4

    def test_summary_critical_count(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert payload["summary"]["criticalCount"] == 1

    def test_summary_high_count(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert payload["summary"]["highCount"] == 3

    def test_summary_firm_name(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert payload["summary"]["firmName"] == "Coastal Law Ltd"

    def test_summary_period(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert payload["summary"]["period"] == "May 2026"

    def test_summary_generated_at(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert payload["summary"]["generatedAt"] == "2026-06-25"

    def test_writes_frontend_payload_json(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        assert (tmp_path / "frontend_payload.json").exists()

    def test_frontend_payload_json_is_valid(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        data = json.loads((tmp_path / "frontend_payload.json").read_text(encoding="utf-8"))
        assert data["summary"]["totalViolations"] == 4

    def test_high_severity_maps_to_warning_in_payload(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        payload = adapt_full_report(REPORT_DICT, PACK_DICT, tmp_path)
        high_vs = [v for v in payload["violations"] if v["ruleId"] != "R01_OVERDRAWN_CLIENT_LEDGER"]
        assert all(v["severity"] == "WARNING" for v in high_vs)

    def test_creates_output_dir_if_missing(self, tmp_path):
        from trust_domain.reports.frontend_adapter import adapt_full_report
        nested = tmp_path / "new" / "dir"
        adapt_full_report(REPORT_DICT, PACK_DICT, nested)
        assert (nested / "frontend_payload.json").exists()
