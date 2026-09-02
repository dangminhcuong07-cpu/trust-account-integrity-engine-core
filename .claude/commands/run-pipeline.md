# /project:run-pipeline

Run the Trust Account Integrity Engine pipeline on a set of client data files.

## What to do

Ask the user for:
1. The path to their client config `.toml` file (or offer to create one from scratch if they don't have one).
2. An optional `--as-at` date (YYYY-MM-DD). If not provided, use today's date.

If no config file exists yet, gather these details from the user and create one:
- Firm name
- Review period (e.g. "May 2026")
- Reviewed by (name/initials)
- Input directory (where their CSVs are)
- Output directory (where to write reports)
- Any column-map overrides

Then run:

```bash
python run.py --config <config_path> [--as-at YYYY-MM-DD]
```

After the run, report:
- Total violations found
- Count by severity (CRITICAL / WARNING)
- Location of key output files: `exception_report.pdf`, `evidence_pack.md`, `run_log.json`
- Any WARNING: lines printed during the run (config validation issues)

If the run fails, read the traceback, diagnose the cause (missing column, wrong file format, unparseable date, etc.), and suggest a fix before retrying.

## Sample data test run

To verify the engine is working, run against the included synthetic sample:

```bash
python run.py --config trust_domain/config/coastal_law.toml --as-at 2026-06-25
```

Expected: 23 violations (14 CRITICAL, 9 WARNING). Output goes to `output/coastal_law/`.
