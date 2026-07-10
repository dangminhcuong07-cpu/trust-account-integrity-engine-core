# Data Handling Boundary — Trust Account Integrity Engine

**Version:** 1.0.0
**Applies to:** `integrity_engine/` and `trust_domain/` packages
**Intended audience:** Trust Account Supervisors (TAS), law firm IT administrators,
and anyone evaluating this engine before installation on a system that holds
real client trust-account data.

---

## 1. What the Engine Reads

The engine reads **four CSV files** from a caller-specified source directory.
In a production deployment these files are exports from the firm's trust
accounting software. In testing and demonstration runs they are the synthetic
dataset in `trust_domain/synthetic/sample/`.

| File | Contents |
|---|---|
| `matter_register.csv` | One row per client matter: matter reference, client name, open date, balance, last activity date, matter type |
| `client_ledger.csv` | One row per ledger entry: entry ID, matter reference, date, receipt, payment, running balance, reconciliation status, reference |
| `trust_bank_statement.csv` | One row per bank statement line: statement ID, date, description, credit, debit, running balance, matched ledger entry |
| `reconciliation_summary.csv` | One row per completed reconciliation period: period end date, ledger total, bank balance, stored difference |

**Format:** UTF-8 CSV only. No database connections, no live API calls, no
spreadsheet files, no binary formats.

**How they are read:** `data/load_sample.py` opens each file once with
`csv.DictReader` in read mode (`"r"`). Numeric fields are cast to `float`.
No other transformation is applied. The file is closed after reading.

---

## 2. What the Engine Writes

The engine writes **only** to a caller-specified `output_dir`. Nothing is ever
written outside that directory. The caller controls the path — the engine never
chooses or hard-codes an output location.

All output is generated afresh on each run. The only in-place deletion is
`audit.log` at the start of each `generate_evidence_pack()` call, which clears
the previous run's log before appending the current run's entries (idempotency).
That file is inside `output_dir`.

| Output file | Produced by | Purpose |
|---|---|---|
| `exception_report.md` | `write_report()` | Human-readable list of rule violations |
| `exception_report.json` | `write_report()` | Machine-readable structured report |
| `audit.log` | `AuditWriter.append_to_log()` | Append-only record of each rule run with wall-clock timestamps |
| `evidence_pack.md` | `generate_evidence_pack()` | Proof-of-diligence document for the NZLS Inspectorate |
| `run_log.json` | `write_run_log()` | Complete record of inputs, rules applied, outputs, and validation result |

**What is never written:**
- The source CSV files (they are never opened for writing)
- Any database
- Any file in the trading system or any other system
- Any file outside `output_dir`

---

## 3. The No-Write Guarantee

> **The engine never modifies, deletes, overwrites, or renames any input file.**
> All output goes to a single caller-specified `output_dir`.
> The source data is read once, processed entirely in memory, and released.

This guarantee is enforced by construction:

**1. All write paths are injected by the caller.**
Every module that writes to disk receives its target path as a parameter
(`output_dir: Path`, `output_path: Path`, or `self._output_dir` injected at
construction). No module hard-codes a path that could resolve to a source file.

**2. The rule layer contains zero write operations.**
The seven rule modules in `trust_domain/rules/` (`r01_overdrawn_ledger.py`
through `r07_fee_without_invoice.py`) contain no file-write calls. They receive
`Record` objects, apply logic, and return `TrustRuleResult` objects. They touch
no filesystem state.

**3. The engine core contains zero write operations.**
The modules in `integrity_engine/rules/`, `integrity_engine/consistency/`,
`integrity_engine/flagging/`, `integrity_engine/stats/`, and
`integrity_engine/core/` contain no file-write calls.

**4. The data generators are not pipeline components.**
`data/generate_sample.py` and `trust_domain/synthetic/generator.py` write CSV
files but they are setup tools, not part of the integrity pipeline. They are
called only once (by a developer or test fixture) to create test data. They
are never called during a client data review run.

**5. Output validation runs before any file is returned.**
`validate_violations()`, `validate_report()`, and `validate_evidence_pack()` are
called on the critical path. A report that does not match its source violations
raises `ValidationError` before the caller can act on it.

---

## 4. How to Verify the Guarantee

The test suite includes `tests/test_data_boundary.py` which enforces the
no-write guarantee automatically on every test run.

**`test_engine_does_not_modify_input_files`**
Records the SHA-256 hash of each source CSV before running the full pipeline.
Runs the pipeline. Asserts that every hash is identical after the run, and that
no new file appeared in either source data directory. If any source file was
modified or any unexpected file was created, the test fails with the filename.

**`test_output_goes_to_output_dir_only`**
Runs the full pipeline into a known `output_dir`. Reads `run_log.json` and
asserts that every file listed in `output_files` exists inside `output_dir`.
Asserts that `data/sample/` contains exactly the same files before and after
the run.

To run the boundary tests:

```
python -m pytest tests/test_data_boundary.py -v
```

To run the full suite (213 tests as of Phase 3 completion):

```
python -m pytest -q
```

---

## 5. NZ Privacy Act 2020 Relevance

Client trust-account data is **processed in memory only**. The engine reads
source CSV records into Python `Record` objects (a `record_id` string and a
`data` dict), evaluates rules against them, and discards the in-memory
representation when the pipeline function returns. No copy of the source records
is retained in any output file beyond what appears in evidence strings.

Evidence strings are deliberately narrow: they contain only the fields required
to identify the specific exception (e.g. a ledger entry ID, a balance figure,
a date). They do not reproduce the full source row, and they do not contain
client names, IRD numbers, bank account numbers, or other personal identifiers
beyond those required to identify the trust account record in question.

Output files (`exception_report.md`, `evidence_pack.md`, `run_log.json`) should
be treated as firm-confidential documents and stored or transmitted with the
same controls applied to the source trust-account records, consistent with the
firm's obligations under the **New Zealand Privacy Act 2020** and the
**Lawyers and Conveyancers Act (Trust Account) Regulations 2008**.

The engine does not transmit data to any external service, does not log to any
remote system, and does not retain any copy of input data after the pipeline
function returns.
