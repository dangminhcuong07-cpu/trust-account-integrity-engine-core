# /project:run-tests

Run the Trust Account Integrity Engine test suite.

## What to do

```bash
# Full suite (fast — ~1.5 seconds, 545 tests)
python -m pytest tests/ -q

# With details on any failures
python -m pytest tests/ -v --tb=short

# A specific test file
python -m pytest tests/test_r03_source_verification.py -v

# A specific rule's tests
python -m pytest tests/ -k "r01" -v
```

Report:
- Total tests run
- Pass/fail count
- Any failures with their error messages and the file/line where they occurred

If any tests fail, diagnose the root cause and suggest a fix. Common causes:
- A rule implementation change that broke existing test expectations
- A date-sensitive test (check if it uses `datetime.date.today()` rather than a fixed reference date)
- A missing dependency (`pip install -r requirements.txt`)

## Test structure

| File | Covers |
|------|--------|
| `test_trust_rules.py` | All 12 rules — core pass/fail behaviour |
| `test_r03_source_verification.py` | R03 secondary bank-balance fabrication check |
| `test_ingestion.py` | CSV/XLSX loader, column mapping |
| `test_hostile_ingestion.py` | Mixed date formats, blank rows, CRLF, extra columns |
| `test_pipeline.py` | Full end-to-end pipeline run (23 violations, fixed date) |
| `test_config.py` | Config loading and validation |
| `test_reports.py` | Report generation (MD, PDF, evidence pack, funds trail) |
