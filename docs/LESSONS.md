# Lessons (read before changing anything they cover)

One line per lesson: **what happened → the rule → where it's enforced.** Add a line when a session hits a mistake the next one could repeat. Keep `.claude/CLAUDE.md` short and point here.

## Facts that drift
- **Rule count and severities drifted across docs** (7, 11, 12, 13 and 14 "rules"; CLAUDE.md had five wrong severities and seeded wrong outreach copy) → `RULE_METADATA` is the only source of truth; never type a rule count or severity from memory → `tests/test_docs_match_code.py` checks README and CLAUDE.md tables.
- **Exact test counts went stale in 6 places** (333, 468, 531, 545, 553, 609) → docs say "600+" or "run pytest"; never write an exact count → review in PRs.
- **There is no R11.** The 13 rules are R01–R10, R12–R14. R09 is an internal control with no direct statutory basis, so say "12 regulatory checks + 1 internal control", never "13 obligations".

## Web app and deployment
- **In-process `_RUNS` with `--workers 2` lost about 1 in 5 results pages** ("Run not found") → the web app must run as **one worker**, using threads for concurrency → `tests/test_deploy_config.py`.
- **Going to 1 worker without `--threads` made one run block every request** (regression from the fix above) → keep `--threads 4` in both render.yaml and the Dockerfile → `test_deploy_config.py`.
- **Shell-form `CMD` made `/bin/sh` PID 1**, so `docker stop` / Ctrl+C waited 10s then killed gunicorn → exec-form CMD with `exec gunicorn` → `test_deploy_config.py`.
- **`COPY . .` would have baked `legal/`, `.env` and outreach docs into the image** → `.dockerignore` must mirror the private entries in `.gitignore`; build from a clean clone → `test_deploy_config.py`.
- **Docker Hub rate-limits (429) cloud sessions, and pip can't reach PyPI inside a build there** → verify the Dockerfile on a real machine; a cloud session can only replay its steps in the base image.

## Claims the product makes
- **The hosted demo said "your data never leaves this machine"**, "all 13 rules always run" (R14 can be skipped), and "NZ Law Society compliance" (implies endorsement) → demo-mode footer, accurate hint, "not affiliated with or endorsed by the NZLS" → `tests/test_webapp_claims.py`.
- **A skipped rule must never read as PASS.** R14 is skipped when the input has no `reconciliation_date`; PR #8 shows it as N/A on the web results page. **OPEN:** `run.py` still records `result="PASS"`, so the evidence pack, audit log, CLEAR conclusion and PDF still say PASS, and the results page says "All 13 rules passed" and shows a red "12/13" badge on a clean run → fix: a first-class "NOT EVALUATED" result handled by every writer (changes report format: needs a decision).
- **Every number on a page or in outreach must trace to the code or a cited source.** Outreach drafts invented "audit data", called it "the same check an NZLS auditor would run", and promised an R14 finding the sample can't show.

## Engine and reports
- **The evidence pack didn't record sensitivity or thresholds**, so a "precise" PASS looked like a standard one → `generate_evidence_pack(sensitivity, thresholds)` and a "Detection Settings" section → `tests/test_evidence_pack.py`.
- **…and its rewrite of `exception_report.md` still dropped sensitivity** (the first fix was incomplete; found in the post-merge review) → pass `sensitivity` to every writer → `test_exception_report_md_carries_the_run_sensitivity`.
- **Python `round()` rounds halves to even** (182.5→182, 13.5→14) → thresholds use `int(x + 0.5)` → `tests/test_sensitivity.py::TestHalfUpRounding`.
- **The README's run command failed** (`--config` is required) → copy commands from a real terminal run; the expected output is "23 violations (14 CRITICAL, 9 HIGH)".

## Replay gate (Dream-RSI)
- **The gate scored "did the rule fire this month?"**, so over-flagging inside an expected month scored 1.0 → `expected_records` per snapshot plus a record-level score → `tests/test_replay_monotonicity.py` and the mutation test in `tests/test_replay_engine.py`.
- **Ratios hide a single extra record once the corpus grows** (20/21 = 0.952 ≥ 0.95) → the gate also requires `record_mismatches == []`.
- **A new snapshot needs `expected_records` covering exactly its `expected_breaches`**; `null` means none → `LedgerSnapshot.__post_init__` raises otherwise.
- **Before any change: record a baseline** (pytest count, `run.py` violations, replay scores, output fingerprints with timestamps stripped), **write the prediction**, then replay and diff. Two predictions were wrong in the demo work; a written prediction is what exposed them.

## Process
- **Merge order matters across repos**: engine changes first, then regenerate the frontend's `data.ts` and PDF from the merged engine.
- **The repo is public.** Outreach, strategy and legal documents live in `outreach/`, `docs/strategy/` and `legal/` (all git-ignored). Never `git add .` from a working folder with untracked business documents.
- **Windows (PowerShell 5):** quote paths with spaces; use `Get-Content -Encoding UTF8` (otherwise "—" shows as "â€”"); Docker Desktop needs WSL 2 and virtualisation enabled.
- **Cloud sessions can't merge to master** (the permission system blocks it): Claude prepares the PRs and checks CI, and the owner merges.

## Known small debts
- `tests/test_r14_not_evaluated_badge.py`, `test_webapp_sensitivity.py` and `test_webapp_claims.py` each copy the same `client` fixture; move it to `tests/conftest.py`. The R14 badge tests also write into the real `output/coastal_law`; they should use `tmp_path`.
- `run.py` builds the five-threshold dict twice (for `apply_sensitivity` and for the evidence pack); build it once.
- `tests/test_hostile_ingestion.py:74` puts `@staticmethod` above `@pytest.fixture` (pytest warns).
