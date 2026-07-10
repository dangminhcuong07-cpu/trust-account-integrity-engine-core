# Trust Account Integrity Engine — Onboarding Guide

This document is for law firms and accounting practices receiving the engine.
Work through each section in order before running the engine against real client data.

---

## 1. Requirements

- **Python 3.11 or later** (check with `python --version`)
- **Windows, macOS, or Linux** — no other operating-system dependencies
- **Four CSV exports** from your trust accounting system, named exactly as follows:

  | File | Contents |
  |---|---|
  | `matter_register.csv` | One row per client matter: matter reference, client name, open/close dates, balance, last activity date, matter type |
  | `client_ledger.csv` | One row per ledger entry: entry ID, matter reference, date, receipt, payment, running balance, reconciliation status, invoice reference |
  | `trust_bank_statement.csv` | One row per bank statement line: statement ID, date, description, credit, debit, running balance, matched ledger entry ID |
  | `reconciliation_summary.csv` | One row per completed reconciliation period: period end date, ledger total, bank balance, stored difference |

  Column names must match the schema documented in `docs/DATA_HANDLING_BOUNDARY.md`.
  Export all four files in **UTF-8 CSV format** with headers on row 1.

- **Disk space:** approximately 50 MB per run for output files

---

## 2. Setup (3 steps)

**Step 1 — Copy the engine folder to your machine**

Copy the entire engine folder to a location you control.
No installation to system directories is required.

**Step 2 — Create your config file**

Copy `trust_domain/config/coastal_law.toml` and rename it to your firm name
(e.g. `clients/smith_law.toml`). Open it in a text editor and update:

```toml
[client]
firm_name   = "Smith Law Ltd"           # your firm name
reviewed_by = "A. Jones (TAS)"          # name of the Trust Account Supervisor
review_period = "May 2026"              # period being reviewed

[paths]
input_dir  = "../../data/smith_law"     # path to your four CSV files
output_dir = "../../output/smith_law"   # where reports will be written
```

Paths are relative to the config file's own location. Use `../../` to reach the
project root from inside a `clients/` folder, or use absolute paths if you prefer.

The `[thresholds]` and `[rules]` sections can be left at their defaults for the
first run. Defaults match current NZLS guidelines:

```toml
[thresholds]
dormancy_threshold_days = 365   # NZLS Guidelines s4.3
unreconciled_age_days   = 30    # LCA Reg 12(1)
unmatched_bank_days     = 5     # LCA Reg 11
fit_transfer_days       = 14    # NZLS PS-2 (eff. 1 Jan 2026)
```

**Step 3 — Run setup**

```
python setup.py --config clients/smith_law.toml
```

Setup will:
- Confirm Python 3.11+ is installed
- Install the `reportlab` dependency for PDF output
- Verify all four CSV input files are present
- Create the output directory

If any input files are missing, setup prints which ones are absent and exits.
Fix the missing files before proceeding.

---

## 3. Running the Engine

```
python run.py --config clients/smith_law.toml
```

The engine reads your four CSV files, runs all enabled rules, and writes
output to your `output_dir`. A summary is printed to the console:

```
Run complete - N violations found (C CRITICAL, H HIGH)
Output written to: /path/to/your/output_dir
Exception report: .../exception_report.pdf
Evidence pack:    .../evidence_pack.md
Run log:          .../run_log.json
```

---

## 4. Output Files

All files are written to your `output_dir`. Nothing is written anywhere else.

| File | Purpose |
|---|---|
| `exception_report.pdf` | Hand to the Trust Account Supervisor for review and sign-off. Lists every violation with the relevant regulation, the source record, and required action. |
| `exception_report.md` | Plain-text version of the same report. Suitable for pasting into correspondence or archiving as text. |
| `evidence_pack.md` | Attach to any Inspectorate correspondence as proof of a systematic, documented integrity review. Contains the full audit trail of every rule run. |
| `frontend_payload.json` | Machine-readable violation data for the web dashboard (if deployed). |
| `data.ts` | TypeScript data file for the web dashboard frontend. |
| `run_log.json` | Internal audit record: exactly which input files were read, which rules ran, how many violations were found, and whether output validation passed. |
| `audit.log` | Timestamped log of every rule run in execution order. Embedded in `evidence_pack.md`; also available as a standalone file. |

---

## 5. Data Privacy

- The engine **reads** your CSV files but **never modifies them**. Input files are
  opened once in read mode and closed after loading. Their contents are never copied
  to any output file beyond the narrow evidence strings required to identify each exception.

- All output goes **only** to your specified `output_dir`. No data is written
  outside that directory.

- **No data is sent to any external service.** The engine runs entirely on your
  machine with no network access.

- Evidence strings contain only the fields required to identify the specific
  exception (entry ID, balance, date). They do not contain client names, IRD numbers,
  bank account numbers, or other personal identifiers beyond the trust account record
  reference.

- Output files (`exception_report.pdf`, `evidence_pack.md`, `run_log.json`) should
  be treated as firm-confidential documents, consistent with your obligations under
  the **New Zealand Privacy Act 2020** and the
  **Lawyers and Conveyancers Act (Trust Account) Regulations 2008**.

- See `docs/DATA_HANDLING_BOUNDARY.md` for the full technical boundary statement,
  including how to verify the no-write guarantee by running the test suite.

---

## 6. Getting Help

- **`run_log.json` says `validation_passed: false`** — a validator caught an
  inconsistency between the source data and the produced report. Check the error
  message printed to the console. Re-run `setup.py` to verify your input files
  are complete and correctly formatted.

- **`setup.py` reports missing CSV files** — export the missing file from your
  trust accounting system and place it in your `input_dir`. Column names must
  match the schema in `docs/DATA_HANDLING_BOUNDARY.md` exactly.

- **A rule is producing unexpected results** — run the test suite against the
  synthetic demo data first to confirm the engine is working correctly:
  `python -m pytest tests/test_trust_rules.py -v`

- **Contact:** [your name / support email — fill in before sending to a real client]
