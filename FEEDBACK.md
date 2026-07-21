# Feedback and Issue Reports

Use this file as a template when reporting a false positive, false negative,
or unexpected engine behaviour. Paste a completed copy into a GitHub issue
or email it to the maintainer.

**Repository:** https://github.com/[owner]/trust-account-integrity-engine
**Email:** [maintainer address]

---

## Report template

```
### Rule that fired (or failed to fire)
Rule ID:        e.g. R09_FEE_EXCEEDS_INVOICE
Rule label:     e.g. Fee exceeds invoice

### Type of report
[ ] False positive  — rule flagged a record that should be clean
[ ] False negative  — rule missed a breach I expected it to catch
[ ] Wrong evidence  — rule fired correctly but the evidence string is inaccurate
[ ] Other           — describe below

### Ledger record(s) involved
Record ID(s):   e.g. L040
Dataset:        e.g. client_ledger
Key field values (omit client names; use matter refs only):
  entry_date:     2026-06-01
  payment_nzd:    5000.00
  reference:      INV-00236
  matter_ref:     M018

### Supplementary record(s) involved (if any)
Dataset:        e.g. invoice_register
Record ID:      e.g. INV-00236
Key field values:
  amount_nzd:   3000.00
  matter_ref:   M018
  issue_date:   2026-05-20

### Expected behaviour
Describe what the rule should have done and why.

### Actual behaviour
Paste the evidence string from exception_report.json or funds_trail.json.

### Engine version / run_log excerpt
Paste the "engine_version" and "run_id" lines from run_log.json.

### Regulation reference (if known)
Cite the specific sub-clause you believe applies, e.g.:
  LCA (Trust Account) Regulations 2008, Reg 9(2)(b)
If unsure, leave blank — the maintainer will check against legislation.govt.nz.

### Additional context
Any other relevant details. Do NOT include real client names, bank account
numbers, or other personally identifiable information.
```

---

## Citation verification requests

Rules R08–R12 carry **PROVISIONAL** citation status (see README — Verification
Discipline). If you have verified a citation against legislation.govt.nz and
can provide the exact reprint date and sub-clause, please open an issue with:

- Rule ID
- Current citation string (from the rule file's `NZLS_REF` constant)
- Confirmed citation with sub-clause
- Legislation.govt.nz reprint date used

The maintainer will update the rule file's docstring and remove the
PROVISIONAL flag after independent review.

---

## Out of scope

- Feature requests for rules not in the NZ trust-account regulations
- Requests to add AI/LLM calls to the calculation path
- Support for non-NZ jurisdictions
