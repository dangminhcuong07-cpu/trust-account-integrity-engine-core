"""
Tests for trust_domain/reports/generate_data_ts.py — Step 4.3

TDD RED: all tests written before implementation exists.
Spec interface: generate_data_ts(payload_path, output_path) -> Path
"""
import json
from pathlib import Path

import pytest

SAMPLE_PAYLOAD = {
    "violations": [
        {
            "id": "L021",
            "ruleId": "R01_OVERDRAWN_CLIENT_LEDGER",
            "ruleName": "Overdrawn client ledger entry",
            "severity": "CRITICAL",
            "evidence": "entry L021 balance -2500.00 NZD - client funds in deficit",
            "sourceRecordId": "L021",
            "sourceRecordType": "client_ledger",
            "description": "entry L021 balance -2500.00 NZD - client funds in deficit",
            "nzLawSocietyRule": "LCA Reg 12(6)(a)",
            "status": "UNRESOLVED",
            "dateIdentified": "2026-06-25",
            "actionTaken": None,
        }
    ],
    "complianceChecks": [
        {
            "id": "R01_OVERDRAWN_CLIENT_LEDGER",
            "name": "Overdrawn client ledger entry",
            "nzlsReference": "LCA Reg 12(6)(a)",
            "status": "failed",
            "resultCount": 1,
            "description": "Overdrawn client ledger entry — LCA Reg 12(6)(a)",
        }
    ],
    "summary": {
        "totalViolations": 1,
        "criticalCount": 1,
        "highCount": 0,
        "firmName": "Coastal Law Ltd",
        "period": "May 2026",
        "generatedAt": "2026-06-25",
    },
}


def _write_payload(tmp_path: Path) -> Path:
    p = tmp_path / "frontend_payload.json"
    p.write_text(json.dumps(SAMPLE_PAYLOAD, indent=2), encoding="utf-8")
    return p


class TestGenerateDataTs:
    def test_creates_data_ts_file(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        assert out.exists()

    def test_returns_output_path(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        result = generate_data_ts(payload_path, out)
        assert result == out

    def test_starts_with_auto_generated_comment(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        assert out.read_text(encoding="utf-8").startswith("// AUTO-GENERATED")

    def test_contains_generated_at_in_comment(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        assert "2026-06-25" in out.read_text(encoding="utf-8")

    def test_contains_import_from_types(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        assert "import { RuleViolation, ComplianceCheck } from './types'" in out.read_text(encoding="utf-8")

    def test_exports_violations_const(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        assert "export const violations: RuleViolation[]" in out.read_text(encoding="utf-8")

    def test_exports_compliance_checks_const(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        assert "export const complianceChecks: ComplianceCheck[]" in out.read_text(encoding="utf-8")

    def test_exports_report_summary_const(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        assert "export const reportSummary" in out.read_text(encoding="utf-8")

    def test_violation_data_embedded(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "data.ts"
        generate_data_ts(payload_path, out)
        content = out.read_text(encoding="utf-8")
        assert "Coastal Law Ltd" in content
        assert "L021" in content

    def test_creates_parent_dirs(self, tmp_path):
        from trust_domain.reports.generate_data_ts import generate_data_ts
        payload_path = _write_payload(tmp_path)
        out = tmp_path / "nested" / "dir" / "data.ts"
        generate_data_ts(payload_path, out)
        assert out.exists()
