# Trust Account Integrity Engine — Quick Start

Get from clone to a full compliance run in under five minutes.

---

## 1. Prerequisites

- Python 3.11+
- pip

No database, no external services, no API keys.

---

## 2. Install

```bash
python -m venv venv
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

---

## 3. Generate the synthetic demo dataset

```bash
python trust_domain/synthetic/generator.py
```

Writes six CSVs to `trust_domain/synthetic/sample/`:
`matter_register`, `client_ledger`, `trust_bank_statement`,
`reconciliation_summary`, `invoice_register`, `allocations`.

The dataset contains **thirteen seeded breaches** (one per rule variant)
and clean complements for every rule.

---

## 4. Run the engine

```bash
python run.py --config trust_domain/config/coastal_law.toml
```

All outputs land in `output/coastal_law/`:

| File | Contents |
|------|----------|
| `exception_report.pdf` | Printable violation report |
| `exception_report.md` | Same report, Markdown |
| `exception_report.json` | Machine-readable violations |
| `evidence_pack.md` | Per-rule record counts and pass/fail |
| `funds_trail.md` | Per-matter receipt and fee-payment chain |
| `funds_trail.json` | Same trail, JSON |
| `frontend_payload.json` | Data bundle for the React frontend |
| `run_log.json` | Reproducibility log |

---

## 5. Expected result

```
Run complete - 15 violations found (2 CRITICAL, 13 HIGH)
Output written to: output/coastal_law
Exception report: output/coastal_law/exception_report.pdf
Evidence pack:    output/coastal_law/evidence_pack.md
Run log:          output/coastal_law/run_log.json
```

The 15 violations are deterministic — same ledger always produces the same report.

---

## 6. Run the test suite

```bash
pytest
```

Expected: **444 passed, 0 skipped**.

---

## 7. Use your own data

1. Export your practice-management system to the six CSV schemas (see `data/sample/` for column headers).
2. Copy `trust_domain/config/coastal_law.toml` and edit `firm_name`, `input_dir`, `output_dir`.
3. Run `python run.py --config your_config.toml`.

See `docs/DATA_HANDLING_BOUNDARY.md` for the data-handling and confidentiality boundary before loading real client data.

---

## 8. View in the browser (optional)

```bash
cd trust-account-integrity-engine
npm install
npm run dev
```

Open http://localhost:5173. The frontend reads `frontend_payload.json` from the engine output.
