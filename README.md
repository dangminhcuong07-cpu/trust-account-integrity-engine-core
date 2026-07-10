# Trust Account Integrity Engine

A Python rules engine that checks NZ law firm trust account ledgers against the *Lawyers and Conveyancers Act (Trust Account) Regulations 2008*. It ingests CSV exports, evaluates seven deterministic compliance rules, and produces a dated exception report with source evidence.

**Live demo →** https://trust-account-integrity-engine.vercel.app/

---

## The Problem

NZ law firms hold client money in trust accounts that are legally separate from office funds. The Trust Account Supervisor must certify monthly under Regulation 17 that all client ledgers reconcile against the bank statement and no client account is overdrawn — breaches carry personal professional consequences under the Lawyers and Conveyancers Act 2006. Manual checking of ledger exports across dozens of matters is slow and error-prone: a single transposed figure or missed unreconciled entry can go undetected until a formal review.

---

## Why Deterministic, Not AI

LLMs are unreliable at multi-step arithmetic over large tables and produce non-deterministic output across runs. A compliance check must be reproducible — the same ledger must always produce the same report so a Trust Account Supervisor can stand behind it. Pasting privileged client financial data into an external AI tool also risks breaching lawyer confidentiality obligations under the Lawyers and Conveyancers Act 2006. There is no AI anywhere in the calculation path: every flag is the result of deterministic arithmetic and exact string matching against the ledger rows.

---

## Verification Discipline

Every rule's regulation citation was verified against legislation.govt.nz (reprint as at 1 Jul 2022), with the verification date recorded in each rule file's docstring. R02 and R06 were additionally verified against the NZLS Lawyers Trust Accounting Guidelines, June 2024.

Citation strings used verbatim throughout the codebase:

| ID  | Citation |
|-----|----------|
| R01 | `LCA (Trust Account) Regulations 2008, Reg 6 and Reg 12(6)(a)` |
| R02 | `LCA (Trust Account) Regulations 2008, Reg 12(7); LTAG June 2024 (guidance)` |
| R03 | `LCA (Trust Account) Regulations 2008, Reg 17 (with Reg 11)` |
| R04 | `LCA (Trust Account) Regulations 2008, Reg 11` |
| R05 | `LCA (Trust Account) Regulations 2008, Reg 11 / Reg 17` |
| R06 | `LCA 2006, s110; LCA (Trust Account) Regulations 2008, Reg 8/Reg 9` |
| R07 | `LCA (Trust Account) Regulations 2008, Reg 9` |

Correct firing is proved by a seeded-breach synthetic corpus: each rule's synthetic dataset contains at least one deliberately seeded violation and a clean complement. 333 tests, 0 skipped.

---

## Rules Checked

Each rule maps to a numbered regulation or identified guidance. Where the regulations prescribe no interval, thresholds are configurable and documented as firm-policy defaults (see Limitations).

| ID  | Rule                    | Severity |
|-----|-------------------------|----------|
| R01 | Overdrawn client ledger | CRITICAL |
| R02 | Dormant balance         | HIGH     |
| R03 | Reconciliation break    | CRITICAL |
| R04 | Unmatched bank line     | HIGH     |
| R05 | Unreconciled ageing     | HIGH     |
| R06 | FIT overheld            | HIGH     |
| R07 | Fee without invoice     | HIGH     |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (frontend only)

### Install

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
python run.py trust_domain/config/coastal_law.toml
```

Outputs land in `output/<firm-slug>/`:

- `exception_report.md` — human-readable exception report
- `exception_report.json` — machine-readable version for downstream tooling
- `exception_report.pdf` — printable report
- `evidence/` — per-rule evidence CSVs
- `frontend_payload.json` — data bundle for the React frontend

---

## Tests

```bash
pytest
```

333 tests, 0 skipped. Coverage spans every rule, the ingestion layer, the report writer, the run-log layer, and the evidence pack.

---

## Limitations

- Synthetic data only — not yet run against a real firm's production ledger.
- Seven rules cover a significant subset of the Regulations, not every obligation.
- Thresholds for R02 (dormancy) and R06 (FIT transfer deadline) are configurable firm-policy defaults, not statutory periods; the Regulations do not prescribe these exact intervals.
- This tool supports but never replaces the Trust Account Supervisor. The TAS remains solely responsible for the Reg 17 certification.

---

## Roadmap

- Regulation traceability matrix linking every rule to the specific sub-clause it implements
- Hash-chained run log for tamper-evident evidence preservation
- Practice-management-system export adapters (LEAP, Actionstep)
- Reg 17 monthly certification support report
- Additional rules: client statement intervals, FIT ledger overdraw, unclaimed money escalation

---

## Project Layout

```
trust_domain/
  rules/          # Seven compliance rule modules (r01–r07)
  config/         # Firm TOML configuration + schema
  ingestion/      # CSV loader and column-map normaliser
  reports/        # Markdown / PDF / evidence-pack writers
  synthetic/      # Synthetic ledger data generator
integrity_engine/ # Rule-runner, run log, flagging, stats
data/sample/      # Synthetic demo ledger (CSV)
tests/            # 333 pytest tests
docs/             # Data-handling boundary, onboarding, demo guide
```

---

## DISCLAIMER

**Demonstration release — provided as-is, without warranty.** It is not legal advice. It does not replace the obligations of a Trust Account Supervisor under Regulation 16 and 17 of the *Lawyers and Conveyancers Act (Trust Account) Regulations 2008*. The New Zealand Law Society does not endorse this software. All data used in demonstrations and examples is **synthetic** — no real client data has been used or included in this repository.

---

## License

MIT — see [LICENSE](LICENSE).
