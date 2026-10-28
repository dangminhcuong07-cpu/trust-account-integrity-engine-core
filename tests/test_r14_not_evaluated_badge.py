"""
Phase E.1 — R14 must not render as a false PASS when it was never evaluated.

Root cause: run.py's R14-skip dispatch branch (when the input has no
reconciliation_date column) appended a rule_summary entry with
"result": "PASS" — indistinguishable, downstream, from a rule that ran and
found nothing wrong. This flows unchanged through evidence_pack.py's
rules_applied -> frontend_adapter.adapt_compliance_checks() -> the web UI's
green PASS badge.

Fix: add a distinct "status": "NOT_EVALUATED" key to that rule_summary
entry (the existing "result": "PASS" is left untouched — audit.log and
evidence_pack.md read `result`, and the task requires the CLI-facing output
format stay unchanged). adapt_compliance_checks() and the web UI template
branch on that new key.
"""

from __future__ import annotations

import datetime
import io
from pathlib import Path

import pytest

SAMPLE_DIR = Path("data/sample")  # reconciliation_summary.csv here has no
                                   # reconciliation_date column (Phase F baseline)


class TestRunPipelineMarksR14NotEvaluated:
    def test_r14_rule_summary_entry_has_not_evaluated_status(self):
        from run import run_pipeline

        result = run_pipeline(
            config_path=Path("trust_domain/config/coastal_law.toml"),
            generated_at=datetime.datetime(2026, 6, 25),
        )
        rules_applied = result["pack_dict"]["rules_applied"]
        r14 = next(r for r in rules_applied if r["rule_id"] == "R14_RECONCILIATION_TIMING")

        assert r14["status"] == "NOT_EVALUATED"

    def test_r14_result_field_unchanged_for_cli_evidence_pack_output(self):
        """CLI-facing artefacts (audit.log, evidence_pack.md) read `result`,
        not `status` — this must stay "PASS" so their output format is
        unchanged by this UI-layer fix."""
        from run import run_pipeline

        result = run_pipeline(
            config_path=Path("trust_domain/config/coastal_law.toml"),
            generated_at=datetime.datetime(2026, 6, 25),
        )
        rules_applied = result["pack_dict"]["rules_applied"]
        r14 = next(r for r in rules_applied if r["rule_id"] == "R14_RECONCILIATION_TIMING")

        assert r14["result"] == "PASS"

    def test_evaluated_rules_carry_no_status_key(self):
        """A rule that actually ran must not get the not-evaluated marker."""
        from run import run_pipeline

        result = run_pipeline(
            config_path=Path("trust_domain/config/coastal_law.toml"),
            generated_at=datetime.datetime(2026, 6, 25),
        )
        rules_applied = result["pack_dict"]["rules_applied"]
        r01 = next(r for r in rules_applied if r["rule_id"] == "R01_OVERDRAWN_CLIENT_LEDGER")

        assert "status" not in r01 or r01["status"] != "NOT_EVALUATED"


class TestFrontendAdapterNotEvaluatedStatus:
    def test_not_evaluated_status_maps_to_not_evaluated_not_passed(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks

        rules_applied = [{
            "rule_id": "R14_RECONCILIATION_TIMING",
            "label": "Reconciliation not certified within statutory deadline "
                     "(not evaluated — no reconciliation_date column in input)",
            "nzls_ref": "Regulation 14 — Lawyers and Conveyancers Act (Trust Account) Regulations 2008",
            "records_checked": 0,
            "violations_found": 0,
            "result": "PASS",
            "status": "NOT_EVALUATED",
        }]
        checks = adapt_compliance_checks(rules_applied)
        assert checks[0]["status"] == "not_evaluated"

    def test_normal_pass_entry_without_status_key_still_maps_to_passed(self):
        """Backward compatibility: every existing rule_summary entry has no
        "status" key at all — must keep mapping PASS -> "passed"."""
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks

        rules_applied = [{
            "rule_id": "R01_OVERDRAWN_CLIENT_LEDGER",
            "label": "Overdrawn client ledger entry",
            "nzls_ref": "LCA (Trust Account) Regulations 2008, Reg 6 and Reg 12(6)(a)",
            "records_checked": 10,
            "violations_found": 0,
            "result": "PASS",
        }]
        checks = adapt_compliance_checks(rules_applied)
        assert checks[0]["status"] == "passed"

    def test_normal_failed_entry_still_maps_to_failed(self):
        from trust_domain.reports.frontend_adapter import adapt_compliance_checks

        rules_applied = [{
            "rule_id": "R01_OVERDRAWN_CLIENT_LEDGER",
            "label": "Overdrawn client ledger entry",
            "nzls_ref": "LCA (Trust Account) Regulations 2008, Reg 6 and Reg 12(6)(a)",
            "records_checked": 10,
            "violations_found": 2,
            "result": "VIOLATIONS FOUND",
        }]
        checks = adapt_compliance_checks(rules_applied)
        assert checks[0]["status"] == "failed"


@pytest.fixture()
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def _upload_files() -> dict:
    files = {}
    for name in ["matter_register", "client_ledger", "trust_bank_statement",
                 "reconciliation_summary", "invoice_register", "allocations"]:
        content = (SAMPLE_DIR / f"{name}.csv").read_bytes()
        files[name] = (io.BytesIO(content), f"{name}.csv")
    return files


class TestWebUIShowsNotEvaluatedBadge:
    def test_r14_renders_na_badge_not_pass_when_column_absent(self, client):
        data = {
            "firm_name": "Test Firm",
            "review_period": "June 2026",
            "as_at": "2026-06-25",
            **_upload_files(),
        }
        resp = client.post("/run", data=data, content_type="multipart/form-data",
                            follow_redirects=True)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        r14_idx = html.index("R14_RECONCILIATION_TIMING")
        row = html[r14_idx: r14_idx + 700]
        assert "N/A" in row
        assert "PASS" not in row
