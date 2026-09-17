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
from trust_domain.rules import SENSITIVITY_MODES

app = Flask(__name__)
app.jinja_env.globals["demo_mode"] = lambda: os.environ.get("TRUSTSENTRY_DEMO") == "true"
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
        "R14_RECONCILIATION_TIMING",
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
<title>TrustSentry</title>
<style>
:root{
  --bg:#F8F9FB;--card:#FFFFFF;--navy:#1E2A3B;--border:#E5E7EB;
  --primary:#1A56DB;--primary-h:#1543AD;
  --danger:#DC2626;--warn:#D97706;--ok:#059669;
  --text:#111827;--muted:#6B7280;
  --radius:8px;--shadow:0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.04);
  --ease-out:cubic-bezier(.23,1,.32,1);
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:15px/1.6 var(--font);padding:32px 16px}
.brand{display:flex;flex-direction:column;align-items:center;gap:6px;margin-bottom:28px;text-align:center}
.brand-mark{display:flex;align-items:center;gap:10px;color:var(--navy)}
.brand-mark svg{color:var(--primary)}
.brand-mark span{font-size:1.4rem;font-weight:700;letter-spacing:-.01em}
.tagline{color:var(--muted);font-size:.92rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;
      box-shadow:var(--shadow);padding:32px;max-width:760px;margin:0 auto}
h2{font-size:.95rem;font-weight:700;margin-bottom:16px;padding-bottom:8px;
   border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;
   text-transform:uppercase;letter-spacing:.03em;color:var(--navy)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px 24px}
label{display:block;font-size:.875rem;font-weight:600;margin-bottom:6px;color:var(--text)}
.req::after{content:" *";color:var(--danger)}
.field-wrap{position:relative}
.field-wrap svg.field-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);
  color:var(--muted);pointer-events:none}
input[type=text],input[type=date],input[type=number]{
  width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:8px;
  font:inherit;background:#fff;transition:border-color 160ms var(--ease-out),box-shadow 160ms var(--ease-out)}
input[type=date]{padding-left:34px}
input:focus-visible{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(26,86,219,.15)}
.section{margin-bottom:28px}
.hint{font-size:.78rem;color:var(--muted);margin-top:4px}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:.68rem;font-weight:700;
       background:#E0E7FF;color:#3730A3;margin-left:2px;vertical-align:middle;text-transform:none;
       letter-spacing:normal}
.badge.opt{background:#F3F4F6;color:var(--muted)}

/* Drop zones */
.dropzone{position:relative;border:1.5px dashed var(--border);border-radius:10px;
  padding:18px 12px;text-align:center;background:#FAFBFC;cursor:pointer;
  transition:border-color 200ms var(--ease-out),background 200ms var(--ease-out)}
.dropzone:hover{border-color:#C7D2E0}
@media (hover:hover) and (pointer:fine){.dropzone:hover{background:#F5F7FA}}
.dropzone.dragover{border-color:var(--primary);background:#EFF4FE}
.dropzone.has-file{border-style:solid;border-color:var(--primary);background:#F5F8FF}
.dropzone-input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.dropzone-input:focus-visible ~ .dropzone-content{outline:2px solid var(--primary);outline-offset:2px;border-radius:8px}
.dropzone-content svg{color:var(--muted);margin-bottom:6px}
.dropzone.has-file .dropzone-content svg{color:var(--primary)}
.dz-label{font-size:.875rem;font-weight:600;margin-bottom:2px;color:var(--text)}
.dz-hint{font-size:.76rem;color:var(--muted)}
.dz-filename{font-size:.76rem;color:var(--primary);font-weight:600;margin-top:4px;min-height:1.1em;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

button[type=submit]{
  margin-top:8px;width:100%;padding:13px;background:var(--primary);color:#fff;
  border:none;border-radius:8px;font:700 .95rem/1 var(--font);letter-spacing:.01em;
  cursor:pointer;transition:background 160ms var(--ease-out),transform 120ms var(--ease-out);
  display:flex;align-items:center;justify-content:center;gap:8px}
button[type=submit]:hover{background:var(--primary-h)}
button[type=submit]:active{transform:scale(.98)}
button[type=submit]:disabled{opacity:.75;cursor:default;transform:none}
button[type=submit]:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.error-box{background:#FEF2F2;border:1px solid #FCA5A5;border-radius:var(--radius);
           padding:12px 16px;color:var(--danger);margin-bottom:20px;font-size:.9rem;
           display:flex;align-items:flex-start;gap:8px}
.error-box svg{flex-shrink:0;margin-top:2px}
.adv-toggle{cursor:pointer;color:var(--primary);font-size:.85rem;user-select:none;
  display:inline-flex;align-items:center;gap:6px;font-weight:600;background:none;border:none;
  font-family:inherit;padding:4px 0}
.adv-toggle:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
#adv-section{display:none}
footer{text-align:center;color:var(--muted);font-size:.8rem;margin-top:28px}
@media (prefers-reduced-motion:reduce){*{transition-duration:.001ms!important}}
@media print{.dropzone,button[type=submit]{display:none}}
</style>
</head>
<body>
{% if demo_mode() %}
<div style="background:#D97706;color:#fff;padding:10px 16px;text-align:center;font-weight:600;position:sticky;top:0;z-index:999">
  DEMO MODE — Synthetic data only. Do not upload real client data to this instance.
</div>
{% endif %}
<div class="brand">
  <div class="brand-mark">
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 2.5l7.5 3v6c0 5-3.2 8.7-7.5 10-4.3-1.3-7.5-5-7.5-10v-6l7.5-3z"/>
      <path d="M8.7 12.2l2.3 2.3 4.3-4.6"/>
    </svg>
    <span>TrustSentry</span>
  </div>
  <p class="tagline">Trust account compliance, verified.</p>
</div>

<div class="card">
  {% if error %}
  <div class="error-box" role="alert">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 3l10 18H2L12 3z"/><path d="M12 10v4M12 17h.01"/>
    </svg>
    <span>{{ error }}</span>
  </div>
  {% endif %}

  <form method="POST" action="/run" enctype="multipart/form-data"
        onsubmit="var b=document.getElementById('submitBtn');b.disabled=true;b.setAttribute('aria-busy','true');b.textContent='Running check…';">

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
          <div class="field-wrap">
            <svg class="field-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>
            </svg>
            <input type="date" id="as_at" name="as_at" value="{{ as_at or '' }}">
          </div>
          <span class="hint">Leave blank to use today's date.</span>
        </div>
      </div>
    </div>

    <div class="section">
      <h2>Required datasets <span class="badge">CSV or XLSX</span></h2>
      <div class="grid">
        {% for fid, flabel in [('matter_register','Matter register'),('client_ledger','Client ledger'),('trust_bank_statement','Trust bank statement'),('reconciliation_summary','Reconciliation summary')] %}
        <div>
          <label class="req" for="{{ fid }}">{{ flabel }}</label>
          <div class="dropzone" data-zone>
            <input type="file" id="{{ fid }}" name="{{ fid }}" accept=".csv,.xlsx" required class="dropzone-input">
            <div class="dropzone-content">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 15V4M12 4l-3.5 3.5M12 4l3.5 3.5"/><path d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3"/>
              </svg>
              <div class="dz-label">Drag and drop or click to browse</div>
              <div class="dz-hint">.csv or .xlsx</div>
              <div class="dz-filename"></div>
            </div>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>

    <div class="section">
      <h2>Optional datasets <span class="badge opt">OPT</span></h2>
      <div class="grid">
        <div>
          <label for="invoice_register">Invoice register</label>
          <div class="dropzone" data-zone>
            <input type="file" id="invoice_register" name="invoice_register" accept=".csv,.xlsx" class="dropzone-input">
            <div class="dropzone-content">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 15V4M12 4l-3.5 3.5M12 4l3.5 3.5"/><path d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3"/>
              </svg>
              <div class="dz-label">Drag and drop or click to browse</div>
              <div class="dz-hint">.csv or .xlsx</div>
              <div class="dz-filename"></div>
            </div>
          </div>
          <span class="hint">Required for R08/R09/R10 fee-invoice checks.</span>
        </div>
        <div>
          <label for="allocations">Allocations</label>
          <div class="dropzone" data-zone>
            <input type="file" id="allocations" name="allocations" accept=".csv,.xlsx" class="dropzone-input">
            <div class="dropzone-content">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 15V4M12 4l-3.5 3.5M12 4l3.5 3.5"/><path d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3"/>
              </svg>
              <div class="dz-label">Drag and drop or click to browse</div>
              <div class="dz-hint">.csv or .xlsx</div>
              <div class="dz-filename"></div>
            </div>
          </div>
          <span class="hint">Required for R12 bulk-deposit check.</span>
        </div>
      </div>
    </div>

    <div class="section">
      <button type="button" class="adv-toggle" aria-expanded="false" aria-controls="adv-section"
        onclick="var s=document.getElementById('adv-section');var open=s.style.display==='block';s.style.display=open?'none':'block';this.setAttribute('aria-expanded',String(!open));">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="3"/>
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>
        </svg>
        Advanced thresholds
      </button>
      <div id="adv-section" style="margin-top:14px">
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

    <div class="section">
      <label for="sensitivity">Detection sensitivity</label>
      <select id="sensitivity" name="sensitivity">
        <option value="broad" {% if sensitivity == 'broad' %}selected{% endif %}>Broad — cast a wide net</option>
        <option value="standard" {% if sensitivity != 'broad' and sensitivity != 'precise' %}selected{% endif %}>Standard — default thresholds</option>
        <option value="precise" {% if sensitivity == 'precise' %}selected{% endif %}>Precise — high-confidence only</option>
      </select>
      <span class="hint">Controls what gets surfaced, not which checks run — all 13 rules always run.</span>
    </div>

    <button type="submit" id="submitBtn">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 2.5l7.5 3v6c0 5-3.2 8.7-7.5 10-4.3-1.3-7.5-5-7.5-10v-6l7.5-3z"/>
        <path d="M8.7 12.2l2.3 2.3 4.3-4.6"/>
      </svg>
      Run Compliance Check
    </button>
  </form>
</div>
<footer>Runs locally — your data never leaves this machine</footer>

<script>
document.querySelectorAll('[data-zone]').forEach(function(zone){
  var input = zone.querySelector('.dropzone-input');
  var filenameEl = zone.querySelector('.dz-filename');
  function showFile(){
    if(input.files && input.files.length){
      filenameEl.textContent = input.files[0].name;
      zone.classList.add('has-file');
    } else {
      filenameEl.textContent = '';
      zone.classList.remove('has-file');
    }
  }
  input.addEventListener('change', showFile);
  ['dragenter','dragover'].forEach(function(evt){
    zone.addEventListener(evt, function(e){ e.preventDefault(); zone.classList.add('dragover'); });
  });
  ['dragleave','drop'].forEach(function(evt){
    zone.addEventListener(evt, function(e){ e.preventDefault(); zone.classList.remove('dragover'); });
  });
  zone.addEventListener('drop', function(e){
    if(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length){
      input.files = e.dataTransfer.files;
      showFile();
    }
  });
});
</script>
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
<title>Results — {{ summary.firmName }} — TrustSentry</title>
<style>
:root{
  --bg:#F8F9FB;--card:#FFFFFF;--navy:#1E2A3B;--border:#E5E7EB;
  --primary:#1A56DB;--primary-h:#1543AD;
  --crit:#DC2626;--crit-bg:#FEF2F2;--crit-border:#FECACA;
  --high:#D97706;--high-badge:#B45309;--high-bg:#FFFBEB;--high-border:#FDE68A;
  --pass:#059669;--pass-bg:#ECFDF5;--pass-border:#A7F3D0;
  --text:#111827;--muted:#6B7280;--radius:10px;--shadow:0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.04);
  --ease-out:cubic-bezier(.23,1,.32,1);
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:15px/1.6 var(--font)}

/* Top nav */
.topnav{background:var(--navy);color:#fff;padding:14px 28px;display:flex;
        align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.topnav-brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:1.05rem}
.topnav-brand svg{color:#7DA6FF}
.new-check-btn{background:var(--primary);color:#fff;padding:8px 16px;border-radius:7px;
        text-decoration:none;font-size:.85rem;font-weight:700;white-space:nowrap;
        display:inline-flex;align-items:center;gap:6px;
        transition:background 160ms var(--ease-out),transform 120ms var(--ease-out)}
.new-check-btn:hover{background:var(--primary-h)}
.new-check-btn:active{transform:scale(.97)}
.new-check-btn:focus-visible{outline:2px solid #fff;outline-offset:2px}

.page-body{padding:24px 16px 40px}
.page-meta{max-width:1000px;margin:0 auto 20px}
.page-meta h1{font-size:1.35rem;font-weight:700}
.page-meta .period{color:var(--muted);font-size:.9rem}

/* Summary cards */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;
       max-width:1000px;margin:0 auto 24px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
           box-shadow:var(--shadow);padding:18px 20px;position:relative;overflow:hidden}
.stat-card::before{content:"";position:absolute;top:0;left:0;right:0;height:4px}
.stat-card.crit::before{background:var(--crit)}
.stat-card.high::before{background:var(--high)}
.stat-card.pass::before{background:var(--pass)}
.stat-card.neutral::before{background:var(--primary)}
.stat-card .val{font-size:2rem;font-weight:700;line-height:1}
.stat-card .lbl{font-size:.8rem;color:var(--muted);margin-top:6px;font-weight:600;
                text-transform:uppercase;letter-spacing:.03em}
.stat-card.crit .val{color:var(--crit)}
.stat-card.high .val{color:var(--high)}
.stat-card.pass .val{color:var(--pass)}
.stat-card.neutral .val{color:var(--navy)}

/* Section wrapper */
.section{max-width:1000px;margin:0 auto 20px;background:var(--card);
         border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);
         overflow:hidden}
.section.accent-crit{border-left:4px solid var(--crit)}
.section.accent-high{border-left:4px solid var(--high)}
.section-head{padding:16px 20px;border-bottom:1px solid var(--border);
              display:flex;align-items:center;gap:10px}
.section-head svg{flex-shrink:0}
.section-head.accent-crit-icon svg{color:var(--crit)}
.section-head.accent-high-icon svg{color:var(--high)}
.section-head h2{font-size:1rem;font-weight:700}
.count-badge{padding:2px 9px;border-radius:10px;font-size:.75rem;font-weight:700}
.badge-crit{background:var(--crit-bg);color:var(--crit);border:1px solid var(--crit-border)}
.badge-high{background:var(--high-bg);color:var(--high);border:1px solid var(--high-border)}
.badge-pass{background:var(--pass-bg);color:var(--pass);border:1px solid var(--pass-border)}

/* Violation task cards */
.violation{padding:16px 20px;border-bottom:1px solid var(--border)}
.violation:last-child{border-bottom:none}
.v-head{display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap}
.v-id{font-size:.78rem;color:var(--muted);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
      background:#F3F4F6;padding:1px 6px;border-radius:4px}
.v-type{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;font-weight:600}
.v-rule{font-weight:700;font-size:.92rem;flex:1;min-width:180px}
.sev-pill{padding:2px 9px;border-radius:10px;font-size:.72rem;font-weight:700;color:#fff}
.sev-CRITICAL{background:var(--crit)}
.sev-HIGH{background:var(--high-badge)}
.v-evidence{font-size:.87rem;color:#374151;background:#F9FAFB;border-radius:6px;
            padding:10px 12px;margin-top:6px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
            white-space:pre-wrap;word-break:break-word}
.v-ref{font-size:.75rem;color:var(--muted);margin-top:6px}

/* Compliance table */
table{width:100%;border-collapse:collapse}
th{padding:10px 20px;text-align:left;font-size:.78rem;font-weight:700;color:var(--muted);
   border-bottom:1px solid var(--border);background:#F9FAFB;text-transform:uppercase;letter-spacing:.03em}
td{padding:12px 20px;font-size:.87rem;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:none}
.status-pass{color:var(--pass);font-weight:700;display:inline-flex;align-items:center;gap:5px}
.status-fail{color:var(--crit);font-weight:700;display:inline-flex;align-items:center;gap:5px}
.status-na{color:var(--muted);font-weight:700;display:inline-flex;align-items:center;gap:5px}

/* Downloads */
.dl-area{padding:18px 20px;display:flex;flex-direction:column;gap:14px}
.dl-primary{background:var(--primary);color:#fff;padding:12px 20px;border-radius:8px;
        text-decoration:none;font-size:.92rem;font-weight:700;display:inline-flex;
        align-items:center;gap:8px;align-self:flex-start;
        transition:background 160ms var(--ease-out),transform 120ms var(--ease-out)}
.dl-primary:hover{background:var(--primary-h)}
.dl-primary:active{transform:scale(.98)}
.dl-primary:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.dl-secondary{display:flex;gap:10px;flex-wrap:wrap}
.dl-btn{padding:7px 14px;background:#F3F4F6;border:1px solid var(--border);border-radius:6px;
        text-decoration:none;color:var(--text);font-size:.82rem;white-space:nowrap;
        display:inline-flex;align-items:center;gap:6px;
        transition:background 160ms var(--ease-out)}
.dl-btn:hover{background:#E5E7EB}
.dl-btn:focus-visible{outline:2px solid var(--primary);outline-offset:2px}

/* Empty state */
.empty-state{text-align:center;padding:48px 24px}
.empty-state svg{color:var(--pass);margin-bottom:12px}
.empty-state h2{font-size:1.1rem;font-weight:700;color:var(--pass);border:none;padding:0;margin-bottom:6px}
.empty-state p{color:var(--muted);font-size:.9rem}

footer{text-align:center;color:var(--muted);font-size:.8rem;margin-top:16px;padding-bottom:24px}
@media (prefers-reduced-motion:reduce){*{transition-duration:.001ms!important}}
@media print{.topnav,.new-check-btn,.dl-area{display:none}}
</style>
</head>
<body>
{% if demo_mode() %}
<div style="background:#D97706;color:#fff;padding:10px 16px;text-align:center;font-weight:600;position:sticky;top:0;z-index:999">
  DEMO MODE — Synthetic data only. Do not upload real client data to this instance.
</div>
{% endif %}

<nav class="topnav">
  <div class="topnav-brand">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 2.5l7.5 3v6c0 5-3.2 8.7-7.5 10-4.3-1.3-7.5-5-7.5-10v-6l7.5-3z"/>
      <path d="M8.7 12.2l2.3 2.3 4.3-4.6"/>
    </svg>
    TrustSentry
  </div>
  <a href="/" class="new-check-btn">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 5v14M5 12h14"/>
    </svg>
    New Check
  </a>
</nav>

<div class="page-body">
<div class="page-meta">
  <h1>{{ summary.firmName }}</h1>
  <span class="period">Period: {{ summary.period }} &nbsp;·&nbsp; Generated: {{ summary.generatedAt }} &nbsp;·&nbsp; Sensitivity: {{ (summary.sensitivity or 'standard')|capitalize }}</span>
</div>

<!-- Summary cards -->
<div class="cards">
  <div class="stat-card {% if summary.totalViolations > 0 %}crit{% else %}pass{% endif %}">
    <div class="val">{{ summary.totalViolations }}</div>
    <div class="lbl">Total Violations</div>
  </div>
  <div class="stat-card crit">
    <div class="val">{{ summary.criticalCount }}</div>
    <div class="lbl">Critical</div>
  </div>
  <div class="stat-card high">
    <div class="val">{{ summary.highCount }}</div>
    <div class="lbl">High</div>
  </div>
  <div class="stat-card {% if rules_passed == rules_total %}pass{% else %}neutral{% endif %}">
    <div class="val">{{ rules_passed }}/{{ rules_total }}</div>
    <div class="lbl">Rules Checked</div>
  </div>
</div>

<!-- Downloads -->
<div class="section">
  <div class="section-head"><h2>Download reports</h2></div>
  <div class="dl-area">
    <a class="dl-primary" href="/download/{{ run_id }}/exception_report.pdf">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 3v12M12 15l-4-4M12 15l4-4"/><path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/>
      </svg>
      Download PDF Report
    </a>
    <div class="dl-secondary">
      <a class="dl-btn" href="/download/{{ run_id }}/evidence_pack.md">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h9l3 3v13a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z"/><path d="M14 2v4h4M9 11h6M9 15h6"/></svg>
        Evidence pack
      </a>
      <a class="dl-btn" href="/download/{{ run_id }}/funds_trail.md">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5c0-1 1-1.5 2.5-1.5s2.5.7 2.5 1.7c0 2.3-5 1.3-5 3.6 0 1 1 1.7 2.5 1.7s2.5-.5 2.5-1.5"/></svg>
        Funds trail
      </a>
      <a class="dl-btn" href="/download/{{ run_id }}/exception_report.json">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3c-1.5 0-2 .8-2 2v3c0 1-.5 2-2 2 1.5 0 2 1 2 2v3c0 1.2.5 2 2 2"/><path d="M16 3c1.5 0 2 .8 2 2v3c0 1 .5 2 2 2-1.5 0-2 1-2 2v3c0 1.2-.5 2-2 2"/></svg>
        Exception report (JSON)
      </a>
      <a class="dl-btn" href="/download/{{ run_id }}/run_log.json">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h9l3 3v13a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z"/><path d="M14 2v4h4M9 11h6M9 15h6M9 7h3"/></svg>
        Run log
      </a>
    </div>
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
        <td class="{% if chk.status == 'passed' %}status-pass{% elif chk.status == 'not_evaluated' %}status-na{% else %}status-fail{% endif %}">
          {% if chk.status == 'passed' %}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5 5.5-6"/></svg> PASS
          {% elif chk.status == 'not_evaluated' %}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M5 19L19 5"/></svg> N/A
          {% else %}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/></svg> {{ chk.resultCount }} violation{{ 's' if chk.resultCount != 1 }}
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<!-- Violations list -->
{% if violations %}
{% for sev_label, sev_key, badge_class, accent in [('CRITICAL violations', 'CRITICAL', 'badge-crit', 'crit'), ('HIGH violations', 'WARNING', 'badge-high', 'high')] %}
{% set sev_violations = violations | selectattr('severity', 'equalto', sev_key) | list %}
{% if sev_violations %}
<div class="section accent-{{ accent }}">
  <div class="section-head accent-{{ accent }}-icon">
    {% if accent == 'crit' %}
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l10 18H2L12 3z"/><path d="M12 10v4M12 17h.01"/></svg>
    {% else %}
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>
    {% endif %}
    <h2>{{ sev_label }}</h2>
    <span class="count-badge {{ badge_class }}">{{ sev_violations | length }}</span>
  </div>
  {% for v in sev_violations %}
  <div class="violation">
    <div class="v-head">
      <span class="v-id">{{ v.sourceRecordId }}</span>
      <span class="v-type">{{ v.sourceRecordType.replace('_',' ')|title }}</span>
      <span class="v-rule">{{ v.ruleName }}</span>
      {% set display_sev = 'HIGH' if v.severity == 'WARNING' else v.severity %}
      <span class="sev-pill sev-{{ display_sev }}">{{ display_sev }}</span>
    </div>
    <div class="v-evidence">{{ v.evidence }}</div>
    <div class="v-ref">{{ v.nzLawSocietyRule }}</div>
  </div>
  {% endfor %}
</div>
{% endif %}
{% endfor %}
{% else %}
<div class="section empty-state">
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5 5.5-6"/></svg>
  <h2>No violations found</h2>
  <p>All {{ rules_total }} rules passed for the review period.</p>
</div>
{% endif %}
</div>

<footer>TrustSentry — NZ Law Society compliance</footer>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(INDEX_HTML, error=None, firm_name="", review_period="",
                                  reviewed_by="", as_at="", sensitivity="standard")


@app.route("/run", methods=["POST"])
def run():
    """Accept uploads, build a temp config, execute the pipeline, redirect to results."""
    # ── 1. Validate required form fields ──
    firm_name     = request.form.get("firm_name", "").strip()
    review_period = request.form.get("review_period", "").strip()
    reviewed_by   = request.form.get("reviewed_by", "Trust Accounting Review").strip()
    as_at_raw     = request.form.get("as_at", "").strip()
    sensitivity   = request.form.get("sensitivity", "standard").strip()
    if sensitivity not in SENSITIVITY_MODES:
        sensitivity = "standard"

    if not firm_name or not review_period:
        return render_template_string(INDEX_HTML, error="Firm name and review period are required.",
                                      firm_name=firm_name, review_period=review_period,
                                      reviewed_by=reviewed_by, as_at=as_at_raw, sensitivity=sensitivity)

    # ── 2. Validate required file uploads ──
    required = ["matter_register", "client_ledger", "trust_bank_statement", "reconciliation_summary"]
    for name in required:
        f = request.files.get(name)
        if not f or not f.filename:
            return render_template_string(INDEX_HTML,
                                          error=f"Missing required file: {name.replace('_', ' ')}.",
                                          firm_name=firm_name, review_period=review_period,
                                          reviewed_by=reviewed_by, as_at=as_at_raw, sensitivity=sensitivity)

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
                                          reviewed_by=reviewed_by, as_at=as_at_raw, sensitivity=sensitivity)

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
                                          reviewed_by=reviewed_by, as_at=as_at_raw, sensitivity=sensitivity)
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
            demo_watermark=os.environ.get("TRUSTSENTRY_DEMO") == "true",
            sensitivity=sensitivity,
        )
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        return render_template_string(INDEX_HTML,
                                      error=f"Pipeline error: {exc}",
                                      firm_name=firm_name, review_period=review_period,
                                      reviewed_by=reviewed_by, as_at=as_at_raw, sensitivity=sensitivity)

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
