# /project:new-client

Scaffold a new client configuration for the Trust Account Integrity Engine.

## What to do

Ask the user for the following, then create a config file and test that it loads:

1. **Firm name** (e.g. "Smith & Partners Ltd")
2. **Review period** (e.g. "June 2026")
3. **Reviewed by** (e.g. "A. Jones (TAS)")
4. **Input directory** — where their CSV/XLSX exports are stored
5. **Output directory** — where to write the reports (create if it doesn't exist)
6. **Column mappings** (optional) — ask "Do any of your CSV columns have different names to the standard ones?" and show them the standard names from CLAUDE.md. Gather any overrides.
7. **Custom thresholds** (optional) — ask if they want to change dormancy_threshold_days (default 365), fit_transfer_days (default 14), unreconciled_age_days (default 30), unmatched_bank_days (default 5).

## Create the config file

Save to `trust_domain/config/<slug>.toml` where `<slug>` is the firm name lowercased with spaces replaced by underscores (e.g. `smith_partners_ltd.toml`).

Template:

```toml
[client]
firm_name = "<firm_name>"
reviewed_by = "<reviewed_by>"
engine_version = "1.0.0"
review_period = "<review_period>"

[paths]
input_dir = "<input_dir>"
output_dir = "<output_dir>"

[thresholds]
dormancy_threshold_days = 365
unreconciled_age_days   = 30
unmatched_bank_days     = 5
fit_transfer_days       = 14
bulk_min_nzd            = 0.0

[rules]
enabled = [
  "R01_OVERDRAWN_CLIENT_LEDGER",
  "R02_DORMANT_BALANCE",
  "R03_RECON_BREAK",
  "R04_UNMATCHED_BANK_LINE",
  "R05_UNRECONCILED_AGEING",
  "R06_FIT_OVERHELD",
  "R07_FEE_WITHOUT_INVOICE",
  "R08_FEE_INVOICE_MISSING",
  "R09_FEE_EXCEEDS_INVOICE",
  "R10_INVOICE_POSTDATES_PAYMENT",
  "R12_BULK_DEPOSIT_UNALLOCATED",
  "R13_BANK_BALANCE_OVERDRAWN",
]
```

Add a `[column_map.<dataset>]` section for each dataset that has non-standard column names.

## Verify it loads

Run:

```bash
python -c "from trust_domain.config import load_config, validate_config; c = load_config('trust_domain/config/<slug>.toml'); print('OK:', c.firm_name)"
```

If it fails, diagnose and fix the issue before telling the user it's ready.

## Tell the user

- Path to the new config file
- Command to run their first integrity check: `python run.py --config trust_domain/config/<slug>.toml`
- Or: open the web UI (`python app.py`) and use the upload form instead — no config file needed for the web UI
