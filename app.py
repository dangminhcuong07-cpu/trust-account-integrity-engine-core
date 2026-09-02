"""
app.py — Trust Account Integrity Engine Web UI

Usage:
    python app.py                    # starts on http://localhost:5000
    python app.py --port 8080

A browser-based front end for the pipeline.  The user uploads up to 6 CSVs
(4 required, 2 optional), fills in a few config fields, and the results page
shows violations, rule compliance, and provides report download links.

No external CDN dependencies — runs fully offline.
"""
from __future__ import annotations

import datetime
import os
import shutil
import tempfile
import textwrap
import tomllib
from pathlib import Path

from flask import Flask, request, render_template_string, send_file, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename

from run import run_pipeline

app = Flask(__name__)
app.secret_key = os.urandom(24)  # session for storing run results path

# Per-session output lives in a temp dir.
# We keep a dict: run_id -> output_dir (in-process; restarts clear history — acceptable for local tool).
_RUNS: dict[str, Path] = {}

# ──────────────────────────────────────────────────────────────────────────────
# Helper: build a config TOML from web form inputs + temp dirs
# ──────────────────────────────────────────────────────────────────────────────

def _build_toml(
    firm_name: str,
    review_period: str,
    reviewed_by: str,
    input_dir: str,
    output_dir: str,
    dormancy_days: int = 365,
    unreconciled_days: int = 30,
    unmatched_days: int = 5,
    fit_days: int = 14,
    bulk_min_nzd: float = 0.0,
) -> str:
    rules = [
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
    enabled_str = "\n  ".join(f'"{r}",' for r in rules)
    return textwrap.dedent(f"""\
        [client]
        firm_name = {firm_name!r}
        reviewed_by = {reviewed_by!r}
        engine_version = "1.0.0"
        review_period = {review_period!r}

        [paths]
        input_dir = {input_dir!r}
        output_dir = {output_dir!r}

        [thresholds]
        dormancy_threshold_days = {dormancy_days}
        unreconciled_age_days = {unreconciled_days}
        unmatched_bank_days = {unmatched_days}
        fit_transfer_days = {fit_days}
        bulk_min_nzd = {bulk_min_nzd}

        [rules]
        enabled = [
          {enabled_str}
        ]
    """)


# ──────────────────────────────────────────────────────────────────────────────
# Index page — upload form
# ──────────────────────────────────────────────────────────────────────────────

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trust Account Integrity Engine</title>
<style>
:root{
  --bg:#f5f6fa;--card:#fff;--border:#d1d5db;--primary:#1d4ed8;--primary-h:#1e40af;
  --danger:#dc2626;--warn:#d97706;--ok:#16a34a;--text:#111827;--muted:#6b7280;
  --radius:8px;--shadow:0 1px 4px rgba(0,0,0,.1);
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:15px/1.6 system-ui,sans-serif;padding:24px}
h1{font-size:1.5rem;font-weight:700;margin-bottom:4px}
.subtitle{color:var(--muted);margin-bottom:28px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
      box-shadow:var(--shadow);padding:24px;max-width:760px;margin:0 auto}
h2{font-size:1rem;font-weight:600;margin-bottom:16px;padding-bottom:8px;
   border-bottom:1px solid var(--border)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 24px}
label{display:block;font-size:.875rem;font-weight:500;margin-bottom:4px}
.req::after{content:" *";color:var(--danger)}
input[type=text],input[type=date],input[type=number],select{
  width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font:inherit}
input[type=file]{width:100%;padding:6px 0;font:inherit;cursor:pointer}
.file-wrap{border:1.5px dashed var(--border);border-radius:6px;padding:10px 12px;background:#fafafa}
.file-wrap.optional{border-style:dashed;opacity:.85}
.section{margin-bottom:24px}
.hint{font-size:.78rem;color:var(--muted);margin-top:2px}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:.72rem;font-weight:600;
       background:#e0e7ff;color:#3730a3;margin-left:6px;vertical-align:middle}
.badge.opt{background:#f3f4f6;color:var(--muted)}
button[type=submit]{
  margin-top:12px;width:100%;padding:12px;background:var(--primary);color:#fff;
  border:none;border-radius:var(--radius);font:600 1rem/1 system-ui,sans-serif;
  cursor:pointer;transition:background .15s}
button[type=submit]:hover{background:var(--primary-h)}
.error-box{background:#fef2f2;border:1px solid #fca5a5;border-radius:var(--radius);
           padding:12px 16px;color:var(--danger);margin-bottom:16px;font-size:.9rem}
.adv-toggle{cursor:pointer;color:var(--primary);font-size:.85rem;user-select:none}
#adv-section{display:none}
footer{text-align:center;color:var(--muted);font-size:.8rem;margin-top:32px}
</style>
</head>
<body>
<div class="card">
  <h1>Trust Account Integrity Engine</h1>
  <p class="subtitle">Upload your practice-management exports to check compliance with NZ Law Society trust accounting regulations.</p>

  {% if error %}
  <div class="error-box">{{ error }}</div>
  {% endif %}

  <form method="POST" action="/run" enctype="multipart/form-data">

    <div class="section">
      <h2>Firm details</h2>
      <div class="grid">
        <div>
          <label class="req" for="firm_name">Firm name</label>
          <input type="text" id="firm_name" name="firm_name" required
                 placeholder="e.g. Coastal Law Ltd" value="{{ firm_name or '' }}">
        </div>
        <div>
          <label class="req" for="review_period">Review period</label>
          <input type="text" id="review_period" name="review_period" required
                 placeholder="e.g. May 2026" value="{{ review_period or '' }}">
        </div>
        <div>
          <label for="reviewed_by">Reviewed by</label>
          <input type="text" id="reviewed_by" name="reviewed_by"
                 placeholder="e.g. J. Smith (TAS)" value="{{ reviewed_by or '' }}">
        </div>
        <div>
          <label for="as_at">Report date (as-at)</label>
          <input type="date" id="as_at" name="as_at" value="{{ as_at or '' }}">
          <span class="hint">Leave blank to use today's date.</span>
        </div>
      </div>
    </div>

    <div class="section">
      <h2>Required datasets <span class="badge">CSV or XLSX</span></h2>
      <div class="grid">
        <div>
          <label class="req" for="matter_register">Matter register</label>
          <div class="file-wrap">
            <input type="file" id="matter_register" name="matter_register"
                   accept=".csv,.xlsx" required>
          </div>
        </div>
        <div>
          <label class="req" for="client_ledger">Client ledger</label>
          <div class="file-wrap">
            <input type="file" id="client_ledger" name="client_ledger"
                   accept=".csv,.xlsx" required>
          </div>
        </div>
        <div>
          <label class="req" for="trust_bank_statement">Trust bank statement</label>
          <div class="file-wrap">
            <input type="file" id="trust_bank_statement" name="trust_bank_statement"
                   accept=".csv,.xlsx" required>
          </div>
        </div>
        <div>
          <label class="req" for="reconciliation_summary">Reconciliation summary</label>
          <div class="file-wrap">
            <input type="file" id="reconciliation_summary" name="reconciliation_summary"
                   accept=".csv,.xlsx" required>
          </div>
        </div>
      </div>
    </div>

    <div class="section">
      <h2>Optional datasets <span class="badge opt">OPT</span></h2>
      <div class="grid">
        <div>
          <label for="invoice_register">Invoice register</label>
          <div class="file-wrap optional">
            <input type="file" id="invoice_register" name="invoice_register"
                   accept=".csv,.xlsx">
          </div>
          <span class="hint">Required for R08/R09/R10 fee-invoice checks.</span>
        </div>
        <div>
          <label for="allocations">Allocations</label>
          <div class="file-wrap optional">
            <input type="file" id="allocations" name="allocations"
                   accept=".csv,.xlsx">
          </div>
          <span class="hint">Required for R12 bulk-deposit check.</span>
        </div>
      </div>
    </div>

    <div class="section">
      <p class="adv-toggle" onclick="document.getElementById('adv-section').style.display=document.getElementById('adv-section').style.display==='none'?'block':'none'">
        ⚙ Advanced thresholds (click to expand)
      </p>
      <div id="adv-section" style="margin-top:12px">
        <div class="grid">
          <div>
            <label for="dormancy_days">Dormancy threshold (days)</label>
            <input type="number" id="dormancy_days" name="dormancy_days" value="365" min="1">
          </div>
          <div>
            <label for="fit_days">FIT transfer deadline (days)</label>
            <input type="number" id="fit_days" name="fit_days" value="14" min="1">
          </div>
          <div>
            <label for="unreconciled_days">Unreconciled ageing (days)</label>
            <input type="number" id="unreconciled_days" name="unreconciled_days" value="30" min="1">
          </div>
          <div>
            <label for="unmatched_days">Unmatched bank line (days)</label>
            <input type="number" id="unmatched_days" name="unmatched_days" value="5" min="1">
          </div>
        </div>
      </div>
    </div>

    <button type="submit">▶ Run integrity check</button>
  </form>
</div>
<footer>Trust Account Integrity Engine — NZ Law Society compliance</footer>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Results page template
# ──────────────────────────────────────────────────────────────────────────────

RESULTS_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Results — {{ summary.firmName }} — Trust Integrity</title>
<style>
:root{
  --bg:#f5f6fa;--card:#fff;--border:#d1d5db;--primary:#1d4ed8;--primary-h:#1e40af;
  --crit:#dc2626;--crit-bg:#fef2f2;--crit-border:#fca5a5;
  --high:#d97706;--high-bg:#fffbeb;--high-border:#fcd34d;
  --pass:#16a34a;--pass-bg:#f0fdf4;--pass-border:#86efac;
  --text:#111827;--muted:#6b7280;--radius:8px;--shadow:0 1px 4px rgba(0,0,0,.1);
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:15px/1.6 system-ui,sans-serif;padding:24px}
.page-header{max-width:960px;margin:0 auto 20px;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
.page-header h1{font-size:1.4rem;font-weight:700}
.page-header .period{color:var(--muted);font-size:.95rem}
.back-btn{margin-left:auto;padding:6px 14px;background:var(--primary);color:#fff;
          border:none;border-radius:6px;font:inherit;cursor:pointer;text-decoration:none;
          font-size:.85rem;white-space:nowrap}
.back-btn:hover{background:var(--primary-h)}

/* Summary cards */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;
       max-width:960px;margin:0 auto 24px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
           box-shadow:var(--shadow);padding:16px 20px;text-align:center}
.stat-card .val{font-size:2rem;font-weight:700;line-height:1}
.stat-card .lbl{font-size:.8rem;color:var(--muted);margin-top:4px}
.stat-card.crit .val{color:var(--crit)}
.stat-card.high .val{color:var(--high)}
.stat-card.pass .val{color:var(--pass)}

/* Section wrapper */
.section{max-width:960px;margin:0 auto 24px;background:var(--card);
         border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow)}
.section-head{padding:14px 20px;border-bottom:1px solid var(--border);
              display:flex;align-items:center;gap:10px}
.section-head h2{font-size:1rem;font-weight:600}
.count-badge{padding:2px 9px;border-radius:10px;font-size:.75rem;font-weight:700}
.badge-crit{background:var(--crit-bg);color:var(--crit);border:1px solid var(--crit-border)}
.badge-high{background:var(--high-bg);color:var(--high);border:1px solid var(--high-border)}
.badge-pass{background:var(--pass-bg);color:var(--pass);border:1px solid var(--pass-border)}

/* Violations */
.violation{padding:14px 20px;border-bottom:1px solid var(--border)}
.violation:last-child{border-bottom:none}
.v-head{display:flex;align-items:baseline;gap:10px;margin-bottom:4px;flex-wrap:wrap}
.v-id{font-size:.78rem;color:var(--muted);font-family:monospace}
.v-rule{font-weight:600;font-size:.9rem}
.sev-pill{padding:1px 8px;border-radius:10px;font-size:.72rem;font-weight:700}
.sev-CRITICAL{background:var(--crit-bg);color:var(--crit)}
.sev-HIGH{background:var(--high-bg);color:var(--high)}
.v-evidence{font-size:.87rem;color:#374151;background:#f9fafb;border-radius:4px;
            padding:8px 10px;margin-top:6px;font-family:monospace;white-space:pre-wrap;word-break:break-all}
.v-ref{font-size:.75rem;color:var(--muted);margin-top:4px}

/* Compliance table */
table{width:100%;border-collapse:collapse}
th{padding:10px 16px;text-align:left;font-size:.8rem;font-weight:600;color:var(--muted);
   border-bottom:1px solid var(--border);background:#f9fafb}
td{padding:10px 16px;font-size:.87rem;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:none}
.status-pass{color:var(--pass);font-weight:600}
.status-fail{color:var(--crit);font-weight:600}

/* Downloads */
.dl-grid{display:flex;gap:10px;flex-wrap:wrap;padding:16px 20px}
.dl-btn{padding:8px 16px;background:#f3f4f6;border:1px solid var(--border);border-radius:6px;
        text-decoration:none;color:var(--text);font-size:.875rem;white-space:nowrap}
.dl-btn:hover{background:#e5e7eb}
.dl-btn .icon{margin-right:4px}

footer{text-align:center;color:var(--muted);font-size:.8rem;margin-top:32px}
</style>
</head>
<body>

<div class="page-header">
  <h1>{{ summary.firmName }}</h1>
  <span class="period">Period: {{ summary.period }} &nbsp;·&nbsp; Generated: {{ summary.generatedAt }}</span>
  <a href="/" class="back-btn">← New check</a>
</div>

<!-- Summary cards -->
<div class="cards">
  <div class="stat-card {% if summary.totalViolations > 0 %}crit{% else %}pass{% endif %}">
    <div class="val">{{ summary.totalViolations }}</div>
    <div class="lbl">Total violations</div>
  </div>
  <div class="stat-card crit">
    <div class="val">{{ summary.criticalCount }}</div>
    <div class="lbl">CRITICAL</div>
  </div>
  <div class="stat-card high">
    <div class="val">{{ summary.highCount }}</div>
    <div class="lbl">HIGH / WARNING</div>
  </div>
  <div class="stat-card {% if rules_passed == rules_total %}pass{% else %}crit{% endif %}">
    <div class="val">{{ rules_passed }}/{{ rules_total }}</div>
    <div class="lbl">Rules passed</div>
  </div>
</div>

<!-- Downloads -->
<div class="section">
  <div class="section-head"><h2>📥 Download reports</h2></div>
  <div class="dl-grid">
    <a class="dl-btn" href="/download/{{ run_id }}/exception_report.pdf"><span class="icon">📄</span>Exception report (PDF)</a>
    <a class="dl-btn" href="/download/{{ run_id }}/evidence_pack.md"><span class="icon">📋</span>Evidence pack (MD)</a>
    <a class="dl-btn" href="/download/{{ run_id }}/funds_trail.md"><span class="icon">💰</span>Funds trail (MD)</a>
    <a class="dl-btn" href="/download/{{ run_id }}/exception_report.json"><span class="icon">{ }</span>Exception report (JSON)</a>
    <a class="dl-btn" href="/download/{{ run_id }}/run_log.json"><span class="icon">📝</span>Run log (JSON)</a>
  </div>
</div>

<!-- Rule compliance table -->
<div class="section">
  <div class="section-head">
    <h2>Rule compliance summary</h2>
    <span class="count-badge {% if rules_passed == rules_total %}badge-pass{% else %}badge-crit{% endif %}">
      {{ rules_passed }}/{{ rules_total }} passed
    </span>
  </div>
  <table>
    <thead>
      <tr>
        <th>Rule</th>
        <th>Regulation</th>
        <th>Records checked</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {% for chk in compliance_checks %}
      <tr>
        <td>{{ chk.id }}<br><small style="color:var(--muted)">{{ chk.name }}</small></td>
        <td style="font-size:.78rem;color:var(--muted)">{{ chk.nzlsReference }}</td>
        <td style="text-align:center">—</td>
        <td class="{% if chk.status == 'passed' %}status-pass{% else %}status-fail{% endif %}">
          {% if chk.status == 'passed' %}✓ PASS{% else %}✗ {{ chk.resultCount }} violation{{ 's' if chk.resultCount != 1 }}{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<!-- Violations list -->
{% if violations %}
{% for sev_label, sev_key, badge_class in [('CRITICAL violations', 'CRITICAL', 'badge-crit'), ('HIGH / WARNING violations', 'WARNING', 'badge-high')] %}
{% set sev_violations = violations | selectattr('severity', 'equalto', sev_key) | list %}
{% if sev_violations %}
<div class="section">
  <div class="section-head">
    <h2>{{ sev_label }}</h2>
    <span class="count-badge {{ badge_class }}">{{ sev_violations | length }}</span>
  </div>
  {% for v in sev_violations %}
  <div class="violation">
    <div class="v-head">
      <span class="v-id">{{ v.sourceRecordId }}</span>
      <span class="v-rule">{{ v.ruleName }}</span>
      <span class="sev-pill sev-{{ v.severity }}">{{ v.severity }}</span>
    </div>
    <div class="v-evidence">{{ v.evidence }}</div>
    <div class="v-ref">{{ v.nzLawSocietyRule }}</div>
  </div>
  {% endfor %}
</div>
{% endif %}
{% endfor %}
{% else %}
<div class="section">
  <div class="section-head"><h2 style="color:var(--pass)">✓ No violations found</h2></div>
  <div style="padding:16px 20px;color:var(--muted)">All rules passed for the review period.</div>
</div>
{% endif %}

<footer>Trust Account Integrity Engine — NZ Law Society compliance</footer>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(INDEX_HTML, error=None, firm_name="", review_period="", reviewed_by="", as_at="")


@app.route("/run", methods=["POST"])
def run():
    """Accept uploads, build a temp config, execute the pipeline, redirect to results."""
    # ── 1. Validate required form fields ──
    firm_name     = request.form.get("firm_name", "").strip()
    review_period = request.form.get("review_period", "").strip()
    reviewed_by   = request.form.get("reviewed_by", "Trust Accounting Review").strip()
    as_at_raw     = request.form.get("as_at", "").strip()

    if not firm_name or not review_period:
        return render_template_string(INDEX_HTML, error="Firm name and review period are required.",
                                      firm_name=firm_name, review_period=review_period,
                                      reviewed_by=reviewed_by, as_at=as_at_raw)

    # ── 2. Validate required file uploads ──
    required = ["matter_register", "client_ledger", "trust_bank_statement", "reconciliation_summary"]
    for name in required:
        f = request.files.get(name)
        if not f or not f.filename:
            return render_template_string(INDEX_HTML,
                                          error=f"Missing required file: {name.replace('_', ' ')}.",
                                          firm_name=firm_name, review_period=review_period,
                                          reviewed_by=reviewed_by, as_at=as_at_raw)

    # ── 3. Parse as-at date ──
    generated_at: datetime.datetime | None = None
    if as_at_raw:
        try:
            as_at_date = datetime.date.fromisoformat(as_at_raw)
            generated_at = datetime.datetime.combine(as_at_date, datetime.time(0, 0, 0))
        except ValueError:
            return render_template_string(INDEX_HTML,
                                          error=f"Report date must be YYYY-MM-DD, got {as_at_raw!r}.",
                                          firm_name=firm_name, review_period=review_period,
                                          reviewed_by=reviewed_by, as_at=as_at_raw)

    # ── 4. Create temp workspace ──
    work_dir = Path(tempfile.mkdtemp(prefix="taie_run_"))
    input_dir  = work_dir / "input"
    output_dir = work_dir / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    # ── 5. Save uploaded files ──
    all_datasets = required + ["invoice_register", "allocations"]
    for name in all_datasets:
        f = request.files.get(name)
        if not f or not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in (".csv", ".xlsx"):
            return render_template_string(INDEX_HTML,
                                          error=f"{name}: only .csv and .xlsx files are accepted.",
                                          firm_name=firm_name, review_period=review_period,
                                          reviewed_by=reviewed_by, as_at=as_at_raw)
        dest = input_dir / f"{name}{ext}"
        f.save(dest)

    # ── 6. Build config TOML ──
    def _int(field: str, default: int) -> int:
        try:
            return int(request.form.get(field, default))
        except (ValueError, TypeError):
            return default

    config_toml = _build_toml(
        firm_name=firm_name,
        review_period=review_period,
        reviewed_by=reviewed_by,
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        dormancy_days=_int("dormancy_days", 365),
        unreconciled_days=_int("unreconciled_days", 30),
        unmatched_days=_int("unmatched_days", 5),
        fit_days=_int("fit_days", 14),
    )
    config_path = work_dir / "config.toml"
    config_path.write_text(config_toml, encoding="utf-8")

    # ── 7. Run the pipeline ──
    try:
        run_pipeline(
            config_path=config_path,
            output_dir=output_dir,
            input_dir=input_dir,
            generated_at=generated_at,
        )
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        return render_template_string(INDEX_HTML,
                                      error=f"Pipeline error: {exc}",
                                      firm_name=firm_name, review_period=review_period,
                                      reviewed_by=reviewed_by, as_at=as_at_raw)

    # ── 8. Store run for download ──
    import uuid
    run_id = uuid.uuid4().hex
    _RUNS[run_id] = output_dir

    # ── 9. Read frontend_payload.json and redirect to results ──
    return redirect(url_for("results", run_id=run_id))


@app.route("/results/<run_id>")
def results(run_id: str):
    out_dir = _RUNS.get(run_id)
    if not out_dir:
        return "Run not found (server may have restarted). <a href='/'>Start a new check.</a>", 404

    import json
    payload_path = out_dir / "frontend_payload.json"
    if not payload_path.exists():
        return "Results payload missing. <a href='/'>Start a new check.</a>", 500

    with open(payload_path, encoding="utf-8") as f:
        payload = json.load(f)

    violations      = payload.get("violations", [])
    compliance      = payload.get("complianceChecks", [])
    summary         = payload.get("summary", {})
    rules_passed    = sum(1 for c in compliance if c.get("status") == "passed")
    rules_total     = len(compliance)

    return render_template_string(
        RESULTS_HTML,
        run_id=run_id,
        summary=summary,
        violations=violations,
        compliance_checks=compliance,
        rules_passed=rules_passed,
        rules_total=rules_total,
    )


@app.route("/download/<run_id>/<filename>")
def download(run_id: str, filename: str):
    """Stream a report file for download."""
    out_dir = _RUNS.get(run_id)
    if not out_dir:
        return "Run not found.", 404
    # Sanitise filename — only allow known output files
    allowed = {
        "exception_report.pdf", "exception_report.md", "exception_report.json",
        "evidence_pack.md", "funds_trail.md", "funds_trail.json",
        "frontend_payload.json", "run_log.json",
    }
    if filename not in allowed:
        return "File not available.", 403
    file_path = out_dir / filename
    if not file_path.exists():
        return "File not generated for this run.", 404
    return send_file(file_path, as_attachment=True, download_name=filename)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trust Account Integrity Engine Web UI")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address (127.0.0.1 for local-only, 0.0.0.0 for network)")
    args = parser.parse_args()
    print(f"\nTrust Account Integrity Engine — Web UI")
    print(f"Open in your browser: http://{args.host}:{args.port}/\n")
    app.run(host=args.host, port=args.port, debug=False)
