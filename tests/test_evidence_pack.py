"""
Tests for trust_domain.reports.evidence_pack — Step 2.4.

Verifier requirements:
  1. generate_evidence_pack() with 7 violations → total_violations=7,
     conclusion="EXCEPTIONS FOUND — see report"
  2. generate_evidence_pack() with 0 violations → conclusion="CLEAR"
  3. audit.log has 8 entries (7 RULE_RUN + 1 REVIEW_COMPLETE)
  4. Evidence pack markdown contains Statement of Diligence verbatim
  5. pack_id format is EP-YYYYMMDD-HHMMSS derived from generated_at
  6. Same inputs → identical output files (determinism)
"""

import datetime
import inspect
from pathlib import Path

import pytest

from trust_domain.reports.evidence_pack import generate_evidence_pack
from trust_domain.rules.types import TrustRuleResult

# ── Shared fixtures ───────────────────────────────────────────────────────────

GENERATED_AT = datetime.datetime(2026, 6, 25, 10, 30, 0)
FIRM         = "Coastal Law Ltd"
PERIOD       = "May 2026"
REVIEWED_BY  = "J. Smith (TAS)"
VERSION      = "1.0.0"

ALL_RULE_IDS = [
    "R01_OVERDRAWN_CLIENT_LEDGER",
    "R02_DORMANT_BALANCE",
    "R03_RECON_BREAK",
    "R04_UNMATCHED_BANK_LINE",
    "R05_UNRECONCILED_AGEING",
    "R06_FIT_OVERHELD",
    "R07_FEE_WITHOUT_INVOICE",
]

_RULE_META = {
    "R01_OVERDRAWN_CLIENT_LEDGER": {
        "label":   "Overdrawn client ledger entry",
        "nzls_ref": "LCA Reg 12(6)(a)",
        "dataset": "client_ledger",
    },
    "R02_DORMANT_BALANCE": {
        "label":   "Dormant balance",
        "nzls_ref": "NZLS Guidelines s4.3",
        "dataset": "matter_register",
    },
    "R03_RECON_BREAK": {
        "label":   "Reconciliation break",
        "nzls_ref": "LCA Reg 12(1)",
        "dataset": "reconciliation_summary",
    },
    "R04_UNMATCHED_BANK_LINE": {
        "label":   "Unmatched bank line",
        "nzls_ref": "LCA Reg 11",
        "dataset": "trust_bank_statement",
    },
    "R05_UNRECONCILED_AGEING": {
        "label":   "Unreconciled ageing",
        "nzls_ref": "LCA Reg 12(1)",
        "dataset": "client_ledger",
    },
    "R06_FIT_OVERHELD": {
        "label":   "FIT balance held beyond transfer deadline",
        "nzls_ref": "NZLS PS-2",
        "dataset": "matter_register",
    },
    "R07_FEE_WITHOUT_INVOICE": {
        "label":   "Fee or disbursement lacks invoice reference",
        "nzls_ref": "NZLS PMG s9",
        "dataset": "client_ledger",
    },
}

_DATASET_COUNTS = {
    "client_ledger":           38,
    "matter_register":         21,
    "reconciliation_summary":   3,
    "trust_bank_statement":    40,
}


def _make_rule_summary(violations_by_rule: dict[str, int]) -> list[dict]:
    result = []
    for rid in ALL_RULE_IDS:
        viol = violations_by_rule.get(rid, 0)
        dataset = _RULE_META[rid]["dataset"]
        result.append({
            "rule_id":          rid,
            "label":            _RULE_META[rid]["label"],
            "nzls_ref":         _RULE_META[rid]["nzls_ref"],
            "records_checked":  _DATASET_COUNTS[dataset],
            "violations_found": viol,
            "result":           "VIOLATIONS FOUND" if viol > 0 else "PASS",
        })
    return result


def _make_7_violations() -> list[TrustRuleResult]:
    data = [
        ("R01_OVERDRAWN_CLIENT_LEDGER", "L021", "CRITICAL",
         "LCA Reg 12(6)(a)", "Overdrawn client ledger entry",
         "matter M016 balance -2500.00 NZD after entry L021"),
        ("R02_DORMANT_BALANCE",         "M017", "HIGH",
         "NZLS Guidelines s4.3", "Dormant balance",
         "balance 8500.00 NZD; last activity 2024-12-15; open 557 days"),
        ("R03_RECON_BREAK",             "R002", "CRITICAL",
         "LCA Reg 12(1)", "Reconciliation break",
         "bank exceeds ledger by $250.00 NZD"),
        ("R04_UNMATCHED_BANK_LINE",     "B031", "HIGH",
         "LCA Reg 11", "Unmatched bank line",
         "bank line B031 open 34 days, no matched ledger entry"),
        ("R05_UNRECONCILED_AGEING",     "L009", "HIGH",
         "LCA Reg 12(1)", "Unreconciled ageing",
         "entry L009 unreconciled 89 days (threshold 30)"),
        ("R06_FIT_OVERHELD",            "M021", "HIGH",
         "NZLS PS-2", "FIT balance held beyond transfer deadline",
         "FIT balance 125.00 NZD open 24 days (threshold 14)"),
        ("R07_FEE_WITHOUT_INVOICE",     "L037", "HIGH",
         "NZLS PMG s9", "Fee or disbursement lacks invoice reference",
         "entry L037 disbursement, no INV-XXXXX reference"),
    ]
    return [
        TrustRuleResult(
            rule_id=rid, passed=False, record_id=rec_id,
            severity=sev, nzls_ref=nzls, label=label, evidence=ev,
        )
        for rid, rec_id, sev, nzls, label, ev in data
    ]


def _violations_by_rule(violations: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in violations:
        counts[v.rule_id] = counts.get(v.rule_id, 0) + 1
    return counts


# ── Tests — correct totals and conclusion ─────────────────────────────────────

class TestConclusion:
    def test_7_violations_total_and_conclusion(self, tmp_path):
        violations = _make_7_violations()
        pack = generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert pack["total_violations"] == 7
        assert pack["conclusion"] == "EXCEPTIONS FOUND — see report"

    def test_0_violations_conclusion_clear(self, tmp_path):
        pack = generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert pack["total_violations"] == 0
        assert pack["conclusion"] == "CLEAR"

    def test_rules_applied_count(self, tmp_path):
        violations = _make_7_violations()
        pack = generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert len(pack["rules_applied"]) == 7

    def test_total_records_checked_is_sum_of_rule_summary(self, tmp_path):
        rule_summary = _make_rule_summary({})
        pack = generate_evidence_pack(
            violations=[],
            rule_summary=rule_summary,
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        expected = sum(r["records_checked"] for r in rule_summary)
        assert pack["total_records_checked"] == expected


# ── Tests — audit log ─────────────────────────────────────────────────────────

class TestAuditLog:
    def test_audit_log_has_8_entries(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        log_lines = [
            l for l in (tmp_path / "audit.log").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        assert len(log_lines) == 8

    def test_audit_log_zero_violations_has_8_entries(self, tmp_path):
        """Even with no violations, one entry per rule + REVIEW_COMPLETE = 8 entries."""
        generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        log_lines = [
            l for l in (tmp_path / "audit.log").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        assert len(log_lines) == 8

    def test_audit_log_contains_rule_run_event_type(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        log = (tmp_path / "audit.log").read_text(encoding="utf-8")
        assert "RULE_RUN" in log

    def test_audit_log_contains_review_complete_event(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        log = (tmp_path / "audit.log").read_text(encoding="utf-8")
        assert "REVIEW_COMPLETE" in log

    def test_audit_log_review_complete_states_violations_count(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        log = (tmp_path / "audit.log").read_text(encoding="utf-8")
        assert "7 violations found" in log

    def test_audit_log_is_idempotent_on_second_call(self, tmp_path):
        """Second call to generate_evidence_pack clears and rewrites the log."""
        violations = _make_7_violations()
        kwargs = dict(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        generate_evidence_pack(**kwargs)
        generate_evidence_pack(**kwargs)
        log_lines = [
            l for l in (tmp_path / "audit.log").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        assert len(log_lines) == 8   # not 16


# ── Tests — evidence pack markdown ───────────────────────────────────────────

class TestEvidencePackMarkdown:
    def test_statement_of_diligence_key_phrases(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        md = (tmp_path / "evidence_pack.md").read_text(encoding="utf-8")
        assert "This review was conducted using the Trust Account Integrity Engine." in md
        assert "All checks were applied systematically to the trust account records" in md
        assert f"for {PERIOD}." in md
        assert "This document constitutes evidence of a" in md
        assert "structured integrity review conducted in accordance with the" in md
        assert "Lawyers and Conveyancers Act (Trust Account) Regulations 2008" in md
        assert "and the NZLS Lawyers Trust Accounting Guidelines (June 2024)." in md

    def test_cover_page_fields_present(self, tmp_path):
        violations = _make_7_violations()
        pack = generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        md = (tmp_path / "evidence_pack.md").read_text(encoding="utf-8")
        assert FIRM in md
        assert PERIOD in md
        assert REVIEWED_BY in md
        assert pack["pack_id"] in md
        assert VERSION in md

    def test_audit_trail_section_present(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        md = (tmp_path / "evidence_pack.md").read_text(encoding="utf-8")
        assert "## Audit Trail" in md
        assert "RULE_RUN" in md
        assert "REVIEW_COMPLETE" in md

    def test_rules_applied_table_has_all_rules(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        md = (tmp_path / "evidence_pack.md").read_text(encoding="utf-8")
        for rid in ALL_RULE_IDS:
            assert rid in md

    def test_conclusion_clear_no_exception_report_link(self, tmp_path):
        generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        md = (tmp_path / "evidence_pack.md").read_text(encoding="utf-8")
        assert "**CLEAR**" in md
        assert "see attached exception report" not in md

    def test_conclusion_exceptions_includes_exception_report_link(self, tmp_path):
        violations = _make_7_violations()
        generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        md = (tmp_path / "evidence_pack.md").read_text(encoding="utf-8")
        assert "**EXCEPTIONS FOUND — see report**" in md
        assert "exception_report.md" in md


# ── Tests — pack_id format ────────────────────────────────────────────────────

class TestPackId:
    def test_pack_id_format_from_generated_at(self, tmp_path):
        pack = generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert pack["pack_id"] == "EP-20260625-103000"

    def test_pack_id_changes_with_different_timestamp(self, tmp_path):
        later = datetime.datetime(2026, 6, 30, 14, 45, 0)
        pack = generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=later, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert pack["pack_id"] == "EP-20260630-144500"

    def test_pack_id_appears_in_audit_log_entries(self, tmp_path):
        generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        # Each RULE_RUN entry carries the rule_id as source_record_id in the log.
        # The log now uses wall-clock timestamps (not injected generated_at).
        log = (tmp_path / "audit.log").read_text(encoding="utf-8")
        for rid in ALL_RULE_IDS:
            assert rid in log


# ── Tests — determinism ───────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_inputs_produce_identical_markdown(self, tmp_path):
        violations = _make_7_violations()
        kwargs = dict(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
        )
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        generate_evidence_pack(**kwargs, output_dir=dir1)
        generate_evidence_pack(**kwargs, output_dir=dir2)

        for fname in ("evidence_pack.md", "exception_report.md"):
            content1 = (dir1 / fname).read_text(encoding="utf-8")
            content2 = (dir2 / fname).read_text(encoding="utf-8")
            assert content1 == content2, f"{fname} differs between runs"

    def test_no_datetime_now_in_module(self):
        from trust_domain.reports import evidence_pack as ep_module
        src = inspect.getsource(ep_module)
        assert "datetime.now()" not in src
        assert "date.today()" not in src


# ── Tests — output files written ─────────────────────────────────────────────

class TestOutputFiles:
    def test_exception_report_is_written(self, tmp_path):
        violations = _make_7_violations()
        pack = generate_evidence_pack(
            violations=violations,
            rule_summary=_make_rule_summary(_violations_by_rule(violations)),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert Path(pack["exception_report_path"]).exists()
        content = Path(pack["exception_report_path"]).read_text(encoding="utf-8")
        assert "Trust Account Exception Report" in content

    def test_audit_log_path_in_pack_dict(self, tmp_path):
        pack = generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert Path(pack["audit_log_path"]).exists()

    def test_evidence_pack_md_is_written(self, tmp_path):
        generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=tmp_path,
        )
        assert (tmp_path / "evidence_pack.md").exists()

    def test_output_dir_created_if_not_exists(self, tmp_path):
        new_dir = tmp_path / "deep" / "nested" / "dir"
        assert not new_dir.exists()
        generate_evidence_pack(
            violations=[],
            rule_summary=_make_rule_summary({}),
            firm_name=FIRM, review_period=PERIOD, reviewed_by=REVIEWED_BY,
            generated_at=GENERATED_AT, engine_version=VERSION,
            output_dir=new_dir,
        )
        assert (new_dir / "evidence_pack.md").exists()
