# /project:run-web

Start the Trust Account Integrity Engine web UI.

## What to do

Run the Flask web app so the user can upload CSVs and see violations in their browser without using the CLI.

```bash
python app.py
```

Tell the user:
- The app is running at **http://127.0.0.1:5000/**
- They can open that URL in their browser
- To stop the server, press Ctrl+C in the terminal

## What the web UI does

1. **Upload form** — user fills in firm details and uploads up to 6 CSV/XLSX files (4 required, 2 optional)
2. **Pipeline runs automatically** — no CLI needed
3. **Results dashboard** — shows violation cards grouped by severity, rule compliance table, and download links for PDF, evidence pack, funds trail

## Test run

To verify the web UI works, use the sample data in `data/sample/` with these form values:

| Field | Value |
|---|---|
| Firm name | Coastal Law Ltd |
| Review period | May 2026 |
| Reviewed by | J. Smith (TAS) |
| Report date | 2026-06-25 |

Upload all 6 files from `data/sample/`. Expected result: 23 violations.

## Troubleshooting

- **"No module named flask"** — run `pip install flask` first
- **Port already in use** — run `python app.py --port 8080` to use a different port
- **Pipeline error shown on page** — check that the uploaded files have the expected columns (see CLAUDE.md for the full column list)
