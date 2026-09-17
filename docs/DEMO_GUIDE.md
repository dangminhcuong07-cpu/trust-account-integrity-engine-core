# Trust Account Integrity Engine — Demo Guide

This guide explains how to run and verify the demo against synthetic data.
Run it before using the engine on real client data.

---

## 1. Why the Demo Exists

The engine ships 13 rules in total (R01–R10, R12, R13, R14). The synthetic
NZ trust ledger data contains deliberately seeded errors covering 12 of them
(R01–R10, R12, R13), plus a clean complement for every rule so false
positives are caught. R14 (reconciliation timing) is not exercised by this
sample dataset — it requires a `reconciliation_date` column that the sample
`reconciliation_summary.csv` does not carry, so R14 is skipped (not run,
not a pass) when the demo pipeline runs against the sample data. Five of
the seeded scenarios are modelled on real, named NZLS Disciplinary Tribunal
decisions (Nguy; "Ms M"; Takena Stirling; Mehal Kejriwal; David Small) —
pattern only, with demo dollar figures, and each scenario's provenance is
recorded in the generator's comments.

This lets you verify the engine catches known breaches, and does not flag
clean records, before running it against real client data.

---

## 2. One dataset, one generator

There is a single canonical generator, `trust_domain/synthetic/generator.py`.
It writes the same six CSVs to two places:

| Directory | Who regenerates it | Purpose |
|---|---|---|
| `trust_domain/synthetic/sample/` | The test suite, automatically, on every run | Rule-testing fixture |
| `data/sample/` | You, manually (`python -m trust_domain.synthetic.generator --output-dir data/sample`) | Input for the CLI via `trust_domain/config/coastal_law.toml` |

The two directories are byte-identical when both are current. If they ever
differ, `data/sample/` is the stale one — regenerate it. (Earlier versions of
this guide described a schema difference between the two directories that
produced different violation counts; that split no longer exists.)

`data/generate_sample.py` is a vestigial Phase 1 script kept alive only by
its own isolated test. Do not use it for demos.

---

## 3. Running the Demo

**Option A — CLI, reproducible:**

```
python run.py --config trust_domain/config/coastal_law.toml --as-at 2026-06-25
```

Expected:

```
Run complete - 23 violations found (14 CRITICAL, 9 HIGH)
```

`--as-at` is the report date. The four ageing rules (R02, R04, R05, R06)
measure how old an item is *as at that date*. With `--as-at 2026-06-25` the
result is fully deterministic. Without it the engine uses today's date, so the
ageing findings grow as the calendar moves on — from 2026-06-29 the orphan
bulk credit B048 (dated 2026-06-24) also trips R04's 5-day threshold and the
count becomes 24. That is correct behaviour for a real monthly run (a report
dated today should age items to today); it is just not what you want for a
demo.

**Option B — Full pipeline via the test suite:**

```
python -m pytest tests/test_end_to_end.py -v
```

Runs `run_pipeline()` against `trust_domain/synthetic/sample/` with a fixed
`generated_at` of 2026-06-25, asserts exactly 23 violations, and asserts the
count does not change when the wall clock is faked to 2031.

**Option C — Rule-by-rule verification:**

```
python -m pytest tests/test_trust_rules.py tests/test_rules_r08_r12.py -v
```

Runs each rule individually against the synthetic data with a fixed reference
date and confirms the exact set of `(rule_id, record_id)` pairs — no more, no
fewer.

---

## 4. The Seeded Errors

All records below are present in the synthetic sample. The "Expected finding"
day-counts are as at the 2026-06-25 reference date.

| Error | Rule ID | What it tests | Record | Expected finding |
|---|---|---|---|---|
| ERR-1 | R05_UNRECONCILED_AGEING | Ledger entry unreconciled beyond threshold | L009 (M008) | Dated 2026-03-28; open 89 days (threshold 30) |
| ERR-2 | R01_OVERDRAWN_CLIENT_LEDGER | Client matter balance goes negative | L021 (M016) | Balance −$2,500.00 after payment on 2026-04-28 |
| ERR-3 | R02_DORMANT_BALANCE | Funds held with no activity beyond threshold | M017 | $8,500.00; last activity 2024-12-15; 557 days (threshold 365) |
| ERR-4 | R03_RECON_BREAK | Ledger total ≠ bank balance in a completed reconciliation | R002 (Apr 2026) | Bank exceeds ledger by $250.00 |
| ERR-5 | R04_UNMATCHED_BANK_LINE | Bank line with no matching ledger entry beyond posting window | B031 (2026-05-22) | $15,000 unidentified credit; open 34 days (threshold 5) |
| ERR-6 | R06_FIT_OVERHELD | Interest-bearing-deposit balance held past transfer deadline | M021 | $125.00 credited 2026-06-01; 24 days (threshold 14) |
| ERR-7 | R07_FEE_WITHOUT_INVOICE | Fee/disbursement with no INV-NNNNN reference | L037 (M012) | $200.00; reference blank |
| ERR-8 | R08_FEE_INVOICE_MISSING | Fee references an invoice not in the register | L039 (M004) | INV-99999 absent from invoice_register |
| ERR-9 | R09_FEE_EXCEEDS_INVOICE | Payment exceeds the invoice amount | L040 (M018) | $5,000 > INV-00236 $3,000 |
| ERR-10 | R10_INVOICE_POSTDATES_PAYMENT | Invoice issued after the payment | L041 (M015) | INV-00237 issued 2026-06-15 > payment 2026-06-01 |
| ERR-12a | R12_BULK_DEPOSIT_UNALLOCATED | Bulk deposit under-allocated | B046 | Allocations $7,500 < credit $9,000 |
| ERR-12b | R12_BULK_DEPOSIT_UNALLOCATED | Bulk deposit over-allocated | B047 | Allocations $5,500 > credit $5,000 |
| ERR-12c | R12_BULK_DEPOSIT_UNALLOCATED | Bulk deposit with no allocations and no match | B048 | $15,000, zero allocation rows (R04 also fires once ≥5 days old) |
| ERR-13 | R13_BANK_BALANCE_OVERDRAWN | Trust bank running balance goes negative | B050 | Running balance −$14,175.00 |
| ERR-14a | R01_OVERDRAWN_CLIENT_LEDGER | Cross-matter correlation (Nguy pattern) | L053 (M022) | −$1,800.00; offset by unexplained credit L055/M023 (ERR-14b, not itself a rule hit) |
| ERR-15 | R01_OVERDRAWN_CLIENT_LEDGER | Gradual deficit via four small transfers (Ms M pattern) | L061 (M025) | −$400.00 after the 4th transfer |
| ERR-16 | R13_BANK_BALANCE_OVERDRAWN | Gradual deficit, bank side (Ms M pattern) | B055 | Running balance −$575.00 after four debits |
| ERR-17 | R03_RECON_BREAK | Period falsely certified AGREED with difference stated as $0.00 (Stirling pattern) | R004 (Jun 2026) | Recomputed difference $400.00 — R03 ignores the stored status |
| ERR-18 | R08_FEE_INVOICE_MISSING | Disbursement authorised by a phantom invoice reference (Kejriwal pattern) | L068 (M027) | INV-88801 absent from invoice_register |
| ERR-19 | R01_OVERDRAWN_CLIENT_LEDGER | Persistent, worsening overdraw across successive entries (David Small pattern) | L071, L072, L073 (M028) | −$3,000 → −$4,000 → −$4,500; every row flagged while overdrawn |

R12 also flags B031 (no allocation, no match), so the per-rule totals are:
R01 6, R02 1, R03 2, R04 1, R05 1, R06 1, R07 1, R08 2, R09 1, R10 1, R12 4,
R13 2 = **23**.

---

## 5. Verifying Precision and Recall

```
python -m pytest tests/test_trust_rules.py -v -k "Integration"
```

- `test_exactly_13_violations_total` — the R01–R07 subset finds exactly 13
  violations at the fixed reference date
- `test_violation_record_ids_match_expected_errors` — the exact
  `(rule_id, record_id)` pairs match

For the R08–R13 rules, `tests/test_rules_r08_r12.py` and
`tests/test_trust_rules.py::TestR13BankBalanceOverdrawn` carry the equivalent
exact-set assertions.

To run the full suite:

```
python -m pytest -q
```

Expected: **531 passed, 0 failed, 0 skipped.** The suite regenerates
`trust_domain/synthetic/sample/` on every run; with the generator's LF line
endings and the repository's `.gitattributes`, a test run leaves
`git status` clean.
