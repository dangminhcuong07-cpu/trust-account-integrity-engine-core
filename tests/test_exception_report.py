"""
Tests for trust_domain.reports.exception_report (Step 2.3).

Reference date throughout: 2026-06-25.
9 seeded violations (R01-R07 scope; R01 now catches 3: L021, L053, L061 -
see ERR-14a and ERR-15 in trust_domain/synthetic/generator.py) are exercised
via the trust_domain synthetic data.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from trust_domain.reports.exception_report import (
    build_markdown,
    build_report_dict,
    write_report,
)
from trust_domain.rules.types import TrustRuleResult

REF_DATE  = datetime.date(2026, 6, 25)
FIRM      = "Coastal Law Ltd"
PERIOD    = "May 2026"
SAMPLE_DIR = Path("trust_domain/synthetic/sample")


# ── Generate synthetic data once per session ──────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def trust_sample_data():
    from trust_domain.synthetic.generator import generate
    generate(SAMPLE_DIR)


# ── Collect all 9 violations from synthetic data ──────────────────────────────

def _all_violations() -> list[TrustRuleResult]:
    from data.load_sample import load_file
    import trust_domain.rules.r01_overdrawn_ledger as r01
    import trust_domain.rules.r02_dormant_balance as r02
    import trust_domain.rules.r03_reconciliation as r03
    import trust_domain.rules.r04_unmatched_bank_line as r04
    import trust_domain.rules.r05_unreconciled_ageing as r05
    import trust_domain.rules.r06_fit_overheld as r06
    import trust_domain.rules.r07_fee_without_invoice as r07

    ledger  = load_file("client_ledger",         SAMPLE_DIR)
    matters = load_file("matter_register",        SAMPLE_DIR)
    bank    = load_file("trust_bank_statement",   SAMPLE_DIR)
    recon   = load_file("reconciliation_summary", SAMPLE_DIR)

    _r02 = r02.make_dormant_rule(reference_date=REF_DATE)
    _r04 = r04.make_unmatched_rule(max_age_days=5, reference_date=REF_DATE)
    _r05 = r05.make_ageing_rule(max_days=30, reference_date=REF_DATE)
    _r06 = r06.make_fit_rule(max_days=14, reference_date=REF_DATE)

    results: list[TrustRuleResult] = []
    for rec in ledger:
        results.extend([r01.overdrawn_ledger(rec), _r05(rec), r07.fee_without_invoice(rec)])
    for rec in matters:
        results.extend([_r02(rec), _r06(rec)])
    for rec in bank:
        results.append(_r04(rec))
    for rec in recon:
        results.append(r03.recon_break(rec))

    return [r for r in results if not r.passed]


# ── Helper to build a minimal synthetic TrustRuleResult ──────────────────────

def _viol(rule_id: str, record_id: str, severity: str,
          nzls_ref: str = "Reg X", evidence: str = "test evidence") -> TrustRuleResult:
    return TrustRuleResult(
        rule_id=rule_id, passed=False, record_id=record_id,
        evidence=evidence, nzls_ref=nzls_ref, severity=severity,
    )


# ── build_report_dict ─────────────────────────────────────────────────────────

class TestBuildReportDict:

    def test_total_violations_9(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        assert d["total_violations"] == 9

    def test_critical_count_is_4(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        assert d["critical_count"] == 4   # R01 x3 (L021, L053, L061) + R03

    def test_high_count_is_5(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        assert d["high_count"] == 5       # R02, R04, R05, R06, R07

    def test_critical_violations_appear_before_high(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        severities = [v["severity"] for v in d["violations"]]
        critical_idx = [i for i, s in enumerate(severities) if s == "CRITICAL"]
        high_idx     = [i for i, s in enumerate(severities) if s == "HIGH"]
        assert all(c < h for c in critical_idx for h in high_idx)

    def test_within_severity_ordered_alphabetically_by_rule_id(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        critical_ids = [v["rule_id"] for v in d["violations"] if v["severity"] == "CRITICAL"]
        high_ids     = [v["rule_id"] for v in d["violations"] if v["severity"] == "HIGH"]
        assert critical_ids == sorted(critical_ids)
        assert high_ids     == sorted(high_ids)

    def test_rank_is_1_based_sequential(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        ranks = [v["rank"] for v in d["violations"]]
        assert ranks == list(range(1, 10))

    def test_all_violation_fields_populated(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        for v in d["violations"]:
            assert v["rule_id"]   != "", f"rule_id empty for rank {v['rank']}"
            assert v["severity"]  != "", f"severity empty for rank {v['rank']}"
            assert v["nzls_ref"]  != "", f"nzls_ref empty for rank {v['rank']}"
            assert v["label"]     != "", f"label empty for rank {v['rank']}"
            assert v["record_id"] != "", f"record_id empty for rank {v['rank']}"
            assert v["evidence"]  != "", f"evidence empty for rank {v['rank']}"
            assert v["recommended_action"] in ("ESCALATE", "REVIEW")

    def test_critical_recommended_action_is_escalate(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        for v in d["violations"]:
            if v["severity"] == "CRITICAL":
                assert v["recommended_action"] == "ESCALATE", v["rule_id"]
            elif v["severity"] == "HIGH":
                assert v["recommended_action"] == "REVIEW", v["rule_id"]

    def test_generated_at_is_iso_date_string(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        assert d["generated_at"] == "2026-06-25"

    def test_firm_name_and_period_in_dict(self):
        d = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        assert d["firm_name"]     == FIRM
        assert d["report_period"] == PERIOD

    def test_zero_violations_dict(self):
        d = build_report_dict([], PERIOD, FIRM, REF_DATE)
        assert d["total_violations"] == 0
        assert d["critical_count"]   == 0
        assert d["high_count"]       == 0
        assert d["violations"]       == []

    def test_ordering_stable_with_synthetic_violations(self):
        """Same violations sorted twice produce the same order."""
        v = _all_violations()
        d1 = build_report_dict(v, PERIOD, FIRM, REF_DATE)
        d2 = build_report_dict(v, PERIOD, FIRM, REF_DATE)
        assert [(x["rule_id"], x["record_id"]) for x in d1["violations"]] == \
               [(x["rule_id"], x["record_id"]) for x in d2["violations"]]

    def test_minimal_synthetic_violations(self):
        """Ordering with two hand-crafted violations."""
        vs = [
            _viol("R05_UNRECONCILED_AGEING", "L009", "HIGH"),
            _viol("R01_OVERDRAWN_CLIENT_LEDGER", "L021", "CRITICAL"),
        ]
        d = build_report_dict(vs, PERIOD, FIRM, REF_DATE)
        assert d["violations"][0]["severity"] == "CRITICAL"
        assert d["violations"][1]["severity"] == "HIGH"


# ── build_markdown ────────────────────────────────────────────────────────────

class TestBuildMarkdown:

    def test_contains_firm_name(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert FIRM in md

    def test_contains_period(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert PERIOD in md

    def test_contains_generated_date(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "2026-06-25" in md

    def test_critical_section_before_high_section(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert md.index("## CRITICAL") < md.index("## HIGH")

    def test_action_text_exact_language(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "Investigate and resolve immediately." in md
        assert "within 2 business days" in md

    def test_r01_evidence_in_report(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "-$2,500.00" in md   # overdrawn balance

    def test_r03_evidence_in_report(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "bank exceeds ledger" in md

    def test_record_ids_present(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        for expected_id in ("L021", "R002", "M017", "B031", "L009", "M021", "L037"):
            assert expected_id in md, f"{expected_id} missing from markdown"

    def test_summary_table_present(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "## Summary" in md
        assert "| CRITICAL |" in md
        assert "| HIGH |" in md

    def test_zero_violations_clean_section(self):
        d  = build_report_dict([], PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "## No exceptions found" in md
        assert PERIOD in md
        assert "## CRITICAL" not in md
        assert "## HIGH" not in md

    def test_determinism_identical_bytes(self):
        violations = _all_violations()
        d1 = build_report_dict(violations, PERIOD, FIRM, REF_DATE)
        d2 = build_report_dict(violations, PERIOD, FIRM, REF_DATE)
        assert build_markdown(d1) == build_markdown(d2)

    def test_no_datetime_now_in_output(self):
        """Confirm generated_at is the injected date, not today."""
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "2026-06-25" in md

    def test_nzls_refs_in_markdown(self):
        d  = build_report_dict(_all_violations(), PERIOD, FIRM, REF_DATE)
        md = build_markdown(d)
        assert "LCA (Trust Account) Regulations 2008" in md
        assert "LTAG June 2024" in md


# ── write_report ──────────────────────────────────────────────────────────────

class TestWriteReport:

    def test_writes_file_to_disk(self, tmp_path):
        out = tmp_path / "report.md"
        write_report(_all_violations(), PERIOD, FIRM, REF_DATE, out)
        assert out.exists()

    def test_written_content_matches_build_markdown(self, tmp_path):
        violations = _all_violations()
        out = tmp_path / "report.md"
        d   = write_report(violations, PERIOD, FIRM, REF_DATE, out)
        assert out.read_text(encoding="utf-8") == build_markdown(d)

    def test_returns_dict_with_correct_total(self, tmp_path):
        out = tmp_path / "report.md"
        d   = write_report(_all_violations(), PERIOD, FIRM, REF_DATE, out)
        assert d["total_violations"] == 9

    def test_creates_nested_parent_directories(self, tmp_path):
        out = tmp_path / "trust" / "reports" / "2026" / "may.md"
        write_report(_all_violations(), PERIOD, FIRM, REF_DATE, out)
        assert out.exists()

    def test_zero_violations_writes_clean_report(self, tmp_path):
        out = tmp_path / "clean.md"
        d   = write_report([], PERIOD, FIRM, REF_DATE, out)
        assert "No exceptions found" in out.read_text(encoding="utf-8")
        assert d["total_violations"] == 0

    def test_file_encoding_is_utf8(self, tmp_path):
        out = tmp_path / "report.md"
        write_report(_all_violations(), PERIOD, FIRM, REF_DATE, out)
        content = out.read_bytes()
        content.decode("utf-8")   # must not raise
