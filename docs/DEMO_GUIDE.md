# Trust Account Integrity Engine — Demo Guide

This guide explains how to run and verify the demo against synthetic data.
Run it before using the engine on real client data.

---

## 1. Why the Demo Exists

The engine ships with synthetic NZ trust ledger data containing 7 deliberately
seeded errors — one per rule class. This lets you verify the engine catches known
breaches before running it against real client data.

The synthetic dataset (`trust_domain/synthetic/sample/`) was built to match the
structure of a real NZ law firm trust account, with realistic matter references,
ledger entries, bank statement lines, and reconciliation records. The 7 seeded
errors cover every violation category the engine detects.

---

## 2. Running the Demo

**Option A — Full pipeline run (produces all output files):**

The test suite uses the synthetic sample data and asserts all 7 violations are found:

```
python -m pytest tests/test_end_to_end.py -v
```

This runs the full pipeline (`run.py`) against `trust_domain/synthetic/sample/`
and verifies all expected output files are produced.

**Option B — Rule-by-rule verification:**

```
python -m pytest tests/test_trust_rules.py -v
```

This runs each rule individually against the synthetic data and confirms:
- exactly 7 violations are detected (one per seeded error)
- no false positives on clean records

**Note on `python run.py --config trust_domain/config/coastal_law.toml`:**

Running the CLI directly against `coastal_law.toml` produces results from
`data/sample/` — see Section 4 for why this shows 10 violations rather than 7.

---

## 3. The 7 Seeded Errors

All 7 errors are present in `trust_domain/synthetic/sample/`. Each is caught by
exactly one rule, and no clean record triggers a false positive.

| Error | Rule ID | What it tests | Record | Expected finding |
|---|---|---|---|---|
| ERR-1 | R05_UNRECONCILED_AGEING | Ledger entry unreconciled for more than 30 days | L009 (matter M008) | Entry dated 2026-03-28 unreconciled; open 89 days (threshold 30) |
| ERR-2 | R01_OVERDRAWN_CLIENT_LEDGER | Client matter running balance goes negative | L021 (matter M016) | Balance -$2,500.00 NZD after payment on 2026-04-28 — client funds in deficit |
| ERR-3 | R02_DORMANT_BALANCE | Matter holds funds with no activity beyond threshold | M017 (Rowe Estate) | Balance $8,500.00 NZD; last activity 2024-12-15; dormant 557 days (threshold 365) |
| ERR-4 | R03_RECON_BREAK | Completed monthly reconciliation where ledger total does not equal bank balance | R002 (April 2026) | Bank exceeds ledger by $250.00 NZD — trust interest not posted to any client matter |
| ERR-5 | R04_UNMATCHED_BANK_LINE | Bank statement line with no matching ledger entry beyond posting window | B031 (2026-05-22) | $15,000 unidentified credit; no matched ledger entry; open 34 days (threshold 5) |
| ERR-6 | R06_FIT_OVERHELD | Firm Interest in Trust balance held beyond transfer deadline | M021 (FIT account) | $125.00 FIT balance credited 2026-06-01; held 24 days (threshold 14) — transfer overdue |
| ERR-7 | R07_FEE_WITHOUT_INVOICE | Fee or disbursement entry lacks a valid INV-XXXXX invoice reference | L037 (matter M012) | LINZ title search fee $200.00; reference="" — no INV-XXXXX reference found |

---

## 4. Note on Violation Counts

Running `python run.py --config trust_domain/config/coastal_law.toml` uses
`data/sample/` as its input directory. That dataset uses a simpler schema
(no `reference` column in `client_ledger.csv`) and has different values for some
`matched_ledger_entry` fields. As a result:

- **R04** additionally flags B009 and B022 as spuriously unmatched (in
  `trust_domain/synthetic/sample/` these are correctly matched to L009 and BANK-INTEREST)
- **R07** additionally flags L011, L021, and L035 because their descriptions contain
  "disbursement" but there is no `reference` field to check (in
  `trust_domain/synthetic/sample/` these descriptions were changed to remove the
  keyword, and a `reference` column was added)

This produces **10 violations** from `data/sample/` versus **7** from
`trust_domain/synthetic/sample/`. This difference is expected and does not indicate
an engine error. The `data/sample/` dataset is a Phase 1 scaffold; the
`trust_domain/synthetic/sample/` dataset is the definitive rule-testing fixture.

To demo the engine to a prospective client, use the test suite (Option B above),
which always runs against `trust_domain/synthetic/sample/` and produces the
deterministic 7-violation result.

---

## 5. Verifying Precision and Recall

The integration test confirms no false positives and no missed detections:

```
python -m pytest tests/test_trust_rules.py -v -k "integration"
```

Specifically:
- `test_exactly_7_violations_total` — asserts the engine finds exactly 7 violations, no more
- `test_violation_record_ids_match_expected_errors` — asserts the exact
  `(rule_id, record_id)` pairs match the 7 seeded errors in the table above

To run the full test suite and confirm no regressions:

```
python -m pytest -q
```

Expected result: **300 passed, 0 skipped, 0 failed** (as of Phase 4 completion).
