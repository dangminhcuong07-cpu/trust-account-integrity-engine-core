"""
Tests for integrity_engine.validation.output_validator — Step 3.2.

Coverage:
  validate_violations()      — checks 1a (record_id), 1b (registry), 1c (evidence),
                               1d (severity), and the happy path
  validate_report()          — checks 2a-2e and the happy path
  validate_evidence_pack()   — checks 3a (records total), 3b (violations total),
                               3c/3d (paths exist), and the happy path
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from integrity_engine.validation.output_validator import (
    ValidationError,
    validate_evidence_pack,
    validate_report,
    validate_violations,
)


# ── Test fixture: minimal violation object ────────────────────────────────────

@dataclass
class _V:
    rule_id: str
    record_id: str
    evidence: str
    severity: str
    passed: bool = False


def _valid_violation(
    rule_id="R01", record_id="REC-1",
    evidence="some finding", severity="HIGH",
):
    return _V(rule_id=rule_id, record_id=record_id,
               evidence=evidence, severity=severity)


KNOWN_RULES = {"R01", "R02", "R03"}


# ── Helpers for report and pack dicts ─────────────────────────────────────────

def _make_report_dict(
    violations: list[_V],
    total_override=None,
    critical_override=None,
    high_override=None,
    extra_record_id: str | None = None,
) -> dict:
    n_critical = sum(1 for v in violations if v.severity == "CRITICAL")
    n_high     = sum(1 for v in violations if v.severity == "HIGH")
    viol_list  = [{"record_id": v.record_id, "rule_id": v.rule_id} for v in violations]
    if extra_record_id:
        viol_list.append({"record_id": extra_record_id, "rule_id": "R01"})
    return {
        "total_violations": total_override if total_override is not None else len(violations),
        "critical_count":   critical_override if critical_override is not None else n_critical,
        "high_count":       high_override if high_override is not None else n_high,
        "violations":       viol_list,
    }


def _make_pack_dict(
    violations: list[_V],
    rules_applied: list[dict] | None = None,
    total_records_override: int | None = None,
    total_violations_override: int | None = None,
    audit_log_path: str = "/nonexistent/audit.log",
    exception_report_path: str = "/nonexistent/report.md",
) -> dict:
    if rules_applied is None:
        rules_applied = [
            {"rule_id": "R01", "records_checked": 10},
            {"rule_id": "R02", "records_checked": 20},
        ]
    computed_total = sum(r["records_checked"] for r in rules_applied)
    return {
        "total_violations":      total_violations_override
                                 if total_violations_override is not None
                                 else len(violations),
        "total_records_checked": total_records_override
                                 if total_records_override is not None
                                 else computed_total,
        "rules_applied":         rules_applied,
        "audit_log_path":        audit_log_path,
        "exception_report_path": exception_report_path,
    }


# ── validate_violations ───────────────────────────────────────────────────────

class TestValidateViolations:

    def test_valid_violations_returns_none(self):
        v = _valid_violation()
        assert validate_violations([v], known_rule_ids=KNOWN_RULES) is None

    def test_empty_violations_list_returns_none(self):
        assert validate_violations([]) is None

    # 1a — record_id must not be empty
    def test_empty_record_id_raises(self):
        v = _valid_violation(record_id="")
        with pytest.raises(ValidationError) as exc_info:
            validate_violations([v])
        msg = str(exc_info.value)
        assert "record_id" in msg
        assert "R01" in msg   # rule_id of the bad violation must be in message

    # 1b — rule_id must be registered (when registry provided)
    def test_unregistered_rule_id_raises(self):
        v = _valid_violation(rule_id="R99_UNKNOWN")
        with pytest.raises(ValidationError) as exc_info:
            validate_violations([v], known_rule_ids=KNOWN_RULES)
        msg = str(exc_info.value)
        assert "R99_UNKNOWN" in msg
        assert "rule_id" in msg

    def test_known_rule_id_passes_registry_check(self):
        v = _valid_violation(rule_id="R01")
        assert validate_violations([v], known_rule_ids=KNOWN_RULES) is None

    def test_no_registry_skips_rule_id_check(self):
        v = _valid_violation(rule_id="ANYTHING_GOES")
        assert validate_violations([v], known_rule_ids=None) is None

    # 1c — evidence must not be empty
    def test_empty_evidence_raises(self):
        v = _valid_violation(evidence="")
        with pytest.raises(ValidationError) as exc_info:
            validate_violations([v])
        msg = str(exc_info.value)
        assert "evidence" in msg
        assert "R01" in msg   # rule_id in message
        assert "REC-1" in msg  # record_id in message

    def test_whitespace_only_evidence_raises(self):
        v = _valid_violation(evidence="   ")
        with pytest.raises(ValidationError):
            validate_violations([v])

    # 1d — severity must be CRITICAL or HIGH
    def test_invalid_severity_raises(self):
        v = _valid_violation(severity="MEDIUM")
        with pytest.raises(ValidationError) as exc_info:
            validate_violations([v])
        msg = str(exc_info.value)
        assert "MEDIUM" in msg
        assert "severity" in msg

    def test_critical_severity_is_valid(self):
        v = _valid_violation(severity="CRITICAL")
        assert validate_violations([v]) is None

    def test_high_severity_is_valid(self):
        v = _valid_violation(severity="HIGH")
        assert validate_violations([v]) is None

    def test_low_severity_raises(self):
        v = _valid_violation(severity="LOW")
        with pytest.raises(ValidationError) as exc_info:
            validate_violations([v])
        assert "LOW" in str(exc_info.value)


# ── validate_report ───────────────────────────────────────────────────────────

class TestValidateReport:

    def test_valid_report_returns_none(self):
        violations = [_valid_violation(record_id="REC-1", severity="HIGH")]
        report = _make_report_dict(violations)
        assert validate_report(report, violations) is None

    def test_valid_report_mixed_severities_returns_none(self):
        violations = [
            _valid_violation(record_id="REC-1", severity="CRITICAL"),
            _valid_violation(record_id="REC-2", severity="HIGH"),
        ]
        report = _make_report_dict(violations)
        assert validate_report(report, violations) is None

    # 2a — total_violations
    def test_total_violations_mismatch_raises(self):
        violations = [_valid_violation()]
        report = _make_report_dict(violations, total_override=99)
        with pytest.raises(ValidationError) as exc_info:
            validate_report(report, violations)
        msg = str(exc_info.value)
        assert "total_violations" in msg
        assert "99" in msg
        assert "1" in msg

    # 2b — critical_count
    def test_critical_count_mismatch_raises(self):
        violations = [_valid_violation(severity="HIGH")]
        report = _make_report_dict(violations, critical_override=5)
        with pytest.raises(ValidationError) as exc_info:
            validate_report(report, violations)
        msg = str(exc_info.value)
        assert "critical_count" in msg
        assert "5" in msg

    # 2c — high_count
    def test_high_count_mismatch_raises(self):
        violations = [_valid_violation(severity="CRITICAL")]
        report = _make_report_dict(violations, high_override=3)
        with pytest.raises(ValidationError) as exc_info:
            validate_report(report, violations)
        msg = str(exc_info.value)
        assert "high_count" in msg
        assert "3" in msg

    # 2d — critical + high == total
    def test_count_arithmetic_mismatch_raises(self):
        violations = [
            _valid_violation(record_id="REC-1", severity="CRITICAL"),
            _valid_violation(record_id="REC-2", severity="HIGH"),
        ]
        # Override so critical+high=3 but total=2
        report = _make_report_dict(violations, critical_override=2, high_override=1)
        with pytest.raises(ValidationError) as exc_info:
            validate_report(report, violations)
        msg = str(exc_info.value)
        assert "arithmetic" in msg or "mismatch" in msg

    # 2e — record_ids must match exactly
    def test_extra_record_id_in_report_raises(self):
        violations = [_valid_violation(record_id="REC-1")]
        report = _make_report_dict(violations, extra_record_id="PHANTOM-99")
        with pytest.raises(ValidationError) as exc_info:
            validate_report(report, violations)
        msg = str(exc_info.value)
        assert "PHANTOM-99" in msg
        assert "record_id" in msg

    def test_missing_record_id_in_report_raises(self):
        violations = [
            _valid_violation(record_id="REC-1"),
            _valid_violation(record_id="REC-2"),
        ]
        # Report only has REC-1
        report = {
            "total_violations": 2,
            "critical_count": 0,
            "high_count": 2,
            "violations": [{"record_id": "REC-1", "rule_id": "R01"}],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_report(report, violations)
        msg = str(exc_info.value)
        assert "REC-2" in msg


# ── validate_evidence_pack ────────────────────────────────────────────────────

class TestValidateEvidencePack:

    def test_valid_pack_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit_log = tmp / "audit.log"
            report_md = tmp / "report.md"
            audit_log.write_text("log", encoding="utf-8")
            report_md.write_text("report", encoding="utf-8")

            violations = [_valid_violation()]
            pack = _make_pack_dict(
                violations,
                rules_applied=[{"rule_id": "R01", "records_checked": 10}],
                audit_log_path=str(audit_log),
                exception_report_path=str(report_md),
            )
            assert validate_evidence_pack(pack, violations, tmp) is None

    # 3a — total_records_checked
    def test_total_records_checked_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit_log = tmp / "audit.log"
            report_md = tmp / "report.md"
            audit_log.write_text("log", encoding="utf-8")
            report_md.write_text("report", encoding="utf-8")

            violations = [_valid_violation()]
            pack = _make_pack_dict(
                violations,
                rules_applied=[{"rule_id": "R01", "records_checked": 10}],
                total_records_override=999,   # wrong
                audit_log_path=str(audit_log),
                exception_report_path=str(report_md),
            )
            with pytest.raises(ValidationError) as exc_info:
                validate_evidence_pack(pack, violations, tmp)
            msg = str(exc_info.value)
            assert "total_records_checked" in msg
            assert "999" in msg
            assert "10" in msg

    # 3b — total_violations in pack
    def test_total_violations_mismatch_in_pack_raises(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit_log = tmp / "audit.log"
            report_md = tmp / "report.md"
            audit_log.write_text("log", encoding="utf-8")
            report_md.write_text("report", encoding="utf-8")

            violations = [_valid_violation()]
            pack = _make_pack_dict(
                violations,
                total_violations_override=42,   # wrong
                audit_log_path=str(audit_log),
                exception_report_path=str(report_md),
            )
            with pytest.raises(ValidationError) as exc_info:
                validate_evidence_pack(pack, violations, tmp)
            msg = str(exc_info.value)
            assert "total_violations" in msg
            assert "42" in msg

    # 3c — audit_log_path must exist
    def test_missing_audit_log_raises(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            report_md = tmp / "report.md"
            report_md.write_text("report", encoding="utf-8")

            violations = []
            pack = _make_pack_dict(
                violations,
                rules_applied=[{"rule_id": "R01", "records_checked": 5}],
                audit_log_path=str(tmp / "nonexistent_audit.log"),
                exception_report_path=str(report_md),
            )
            with pytest.raises(ValidationError) as exc_info:
                validate_evidence_pack(pack, violations, tmp)
            msg = str(exc_info.value)
            assert "audit_log_path" in msg
            assert "nonexistent_audit.log" in msg

    # 3d — exception_report_path must exist
    def test_missing_exception_report_raises(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit_log = tmp / "audit.log"
            audit_log.write_text("log", encoding="utf-8")

            violations = []
            pack = _make_pack_dict(
                violations,
                rules_applied=[{"rule_id": "R01", "records_checked": 5}],
                audit_log_path=str(audit_log),
                exception_report_path=str(tmp / "nonexistent_report.md"),
            )
            with pytest.raises(ValidationError) as exc_info:
                validate_evidence_pack(pack, violations, tmp)
            msg = str(exc_info.value)
            assert "exception_report_path" in msg
            assert "nonexistent_report.md" in msg
