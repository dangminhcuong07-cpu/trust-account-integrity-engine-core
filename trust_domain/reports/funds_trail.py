"""
Funds-trail report for NZ trust account integrity audits.

Per matter, the report covers two legs:

  1. RECEIPTS — bank statement credit lines traced to each matter via
     allocations.csv or matched_ledger_entry → client_ledger.matter_ref.
     Status: PROVEN | UNTRACED | UNDER_ALLOCATED | OVER_ALLOCATED |
             INVALID_LEDGER_REF.

  2. FEE/DISBURSEMENT PAYMENTS — client_ledger entries where
     description contains "fee" or "disbursement" and payment_nzd > 0,
     with invoice-matching status derived from invoice_register.
     Status: PROVEN | EXCEPTION (rule_id=R08/R09/R10) |
             NO_INVOICE_REF | UNCHECKED.

Credits where no matter can be determined go to unattributed_receipts.
Debit bank-statement lines are excluded from the receipt leg.

Citation status: PROVISIONAL - pending verification against legislation.govt.nz
by the maintainer.

Usage:
    from trust_domain.reports.funds_trail import write_funds_trail

    trail = write_funds_trail(
        bank_statement=bank_records,
        allocations=alloc_records,
        client_ledger=ledger_records,
        invoice_register=invoice_records,
        firm_name="Coastal Law Ltd",
        report_period="May 2026",
        generated_at=datetime.date(2026, 6, 25),
        output_path=Path("reports/funds_trail.md"),
    )
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from integrity_engine.core.types import Record

_FEE_TERMS = ("fee", "disbursement")
_INV_RE = re.compile(r"^INV-\d{5}$")


# ── private helpers ───────────────────────────────────────────────────────────

def _bank_line_status(
    credit: float,
    matched_entry: str,
    alloc_records: list[Record],
    ledger_ids: set[str] | None,
) -> tuple[str, float | None, str]:
    """Return (status, alloc_sum_or_None, notes) for a credit bank line."""
    if not alloc_records:
        if matched_entry:
            return "PROVEN", None, f"1:1 matched to ledger entry {matched_entry!r}"
        return "UNTRACED", None, "No allocation rows and no matched ledger entry"

    alloc_sum = round(
        sum(float(r.data.get("amount_nzd", 0.0) or 0.0) for r in alloc_records),
        2,
    )
    credit_r = round(credit, 2)

    invalid: list[str] = []
    if ledger_ids is not None:
        invalid = [
            r.data.get("ledger_entry_id", "?")
            for r in alloc_records
            if r.data.get("ledger_entry_id", "?") not in ledger_ids
        ]

    if invalid:
        return (
            "INVALID_LEDGER_REF",
            alloc_sum,
            f"Allocation ledger_entry_id(s) not in client ledger: {invalid}",
        )
    if alloc_sum == credit_r:
        n = len(alloc_records)
        return (
            "PROVEN",
            alloc_sum,
            f"Fully allocated across {n} ledger entr{'y' if n == 1 else 'ies'}",
        )
    if alloc_sum < credit_r:
        gap = credit_r - alloc_sum
        return (
            "UNDER_ALLOCATED",
            alloc_sum,
            f"Allocations sum ${alloc_sum:,.2f} < credit ${credit_r:,.2f} "
            f"(gap ${gap:,.2f})",
        )
    excess = alloc_sum - credit_r
    return (
        "OVER_ALLOCATED",
        alloc_sum,
        f"Allocations sum ${alloc_sum:,.2f} > credit ${credit_r:,.2f} "
        f"(excess ${excess:,.2f})",
    )


def _payment_fields(
    rec: Record,
    inv_by_id: dict[str, Record],
    invoice_register_provided: bool,
) -> dict:
    """
    Classify one fee/disbursement ledger entry against invoice_register.

    Returns a partial payment_row dict covering the invoice-side fields:
    reference, invoice_id, invoice_amount_nzd, invoice_issue_date,
    status, rule_id, notes.
    """
    reference = (rec.data.get("reference") or "").strip()
    payment = float(rec.data.get("payment_nzd", 0.0) or 0.0)
    matter = rec.data.get("matter_ref", "?")
    entry_date = rec.data.get("entry_date", "")

    base: dict = {
        "reference": reference,
        "invoice_id": None,
        "invoice_amount_nzd": None,
        "invoice_issue_date": None,
        "status": None,
        "rule_id": None,
        "notes": None,
    }

    if not _INV_RE.match(reference):
        return {
            **base,
            "status": "NO_INVOICE_REF",
            "notes": (
                f"No INV-NNNNN reference "
                f"(reference={reference!r} — R07 domain)"
            ),
        }

    if not invoice_register_provided:
        return {
            **base,
            "invoice_id": reference,
            "status": "UNCHECKED",
            "notes": "Invoice register not provided",
        }

    inv = inv_by_id.get(reference)
    if inv is None:
        return {
            **base,
            "invoice_id": reference,
            "status": "EXCEPTION",
            "rule_id": "R08_FEE_INVOICE_MISSING",
            "notes": f"Invoice {reference} not found in invoice register",
        }

    inv_matter = inv.data.get("matter_ref", "?")
    inv_amount = float(inv.data.get("amount_nzd", 0.0) or 0.0)
    inv_date = str(inv.data.get("issue_date", "") or "")

    if inv_matter != matter:
        return {
            **base,
            "invoice_id": reference,
            "invoice_amount_nzd": inv_amount,
            "invoice_issue_date": inv_date,
            "status": "EXCEPTION",
            "rule_id": "R08_FEE_INVOICE_MISSING",
            "notes": (
                f"Invoice {reference} matter {inv_matter!r} "
                f"!= ledger matter {matter!r}"
            ),
        }

    if payment > inv_amount:
        return {
            **base,
            "invoice_id": reference,
            "invoice_amount_nzd": inv_amount,
            "invoice_issue_date": inv_date,
            "status": "EXCEPTION",
            "rule_id": "R09_FEE_EXCEEDS_INVOICE",
            "notes": (
                f"Payment ${payment:,.2f} NZD exceeds "
                f"invoice {reference} amount ${inv_amount:,.2f} NZD"
            ),
        }

    if inv_date and entry_date and inv_date > entry_date:
        return {
            **base,
            "invoice_id": reference,
            "invoice_amount_nzd": inv_amount,
            "invoice_issue_date": inv_date,
            "status": "EXCEPTION",
            "rule_id": "R10_INVOICE_POSTDATES_PAYMENT",
            "notes": (
                f"Invoice {reference} issued {inv_date} "
                f"after payment date {entry_date}"
            ),
        }

    return {
        **base,
        "invoice_id": reference,
        "invoice_amount_nzd": inv_amount,
        "invoice_issue_date": inv_date,
        "status": "PROVEN",
        "notes": (
            f"Invoice {reference}: amount ${inv_amount:,.2f} NZD, "
            f"issued {inv_date} — verified"
        ),
    }


# ── public API ────────────────────────────────────────────────────────────────

def build_funds_trail(
    bank_statement: list[Record],
    allocations: list[Record],
    client_ledger: list[Record] | None = None,
    invoice_register: list[Record] | None = None,
    firm_name: str = "",
    report_period: str = "",
    generated_at: datetime.date | None = None,
) -> dict:
    """
    Build the per-matter funds-trail dict.

    Returns a dict with keys:
        firm_name, report_period, generated_at,
        receipt_summary, payment_summary,
        matters, unattributed_receipts

    receipt_summary: {total, proven, untraced, mismatch}
    payment_summary: {total, proven, exception}

    matters[matter_ref]:
        receipts: list of receipt row dicts
        payments: list of payment row dicts

    Each receipt row:
        bank_line_id, ledger_entry_id, transaction_date,
        amount_nzd, bank_line_credit_nzd, bank_line_status, notes

    Each payment row:
        entry_id, entry_date, description, payment_nzd,
        reference, invoice_id, invoice_amount_nzd, invoice_issue_date,
        status, rule_id, notes
    """
    # ── lookups ───────────────────────────────────────────────────────────────
    _ledger_by_id: dict[str, Record] = {
        r.record_id: r for r in (client_ledger or [])
    }
    _inv_by_id: dict[str, Record] = {
        r.record_id: r for r in (invoice_register or [])
    }
    _alloc_by_line: dict[str, list[Record]] = {}
    for rec in allocations:
        bid = rec.data.get("bank_line_id", rec.record_id)
        _alloc_by_line.setdefault(bid, []).append(rec)

    _ledger_ids: set[str] | None = (
        {r.record_id for r in client_ledger} if client_ledger is not None else None
    )
    _inv_provided = invoice_register is not None

    matters: dict[str, dict] = {}
    unattributed: list[dict] = []

    def _matter(ref: str) -> dict:
        if ref not in matters:
            matters[ref] = {"receipts": [], "payments": []}
        return matters[ref]

    # ── receipt leg (bank statement credit lines) ─────────────────────────────
    rcpt_proven = rcpt_untraced = rcpt_mismatch = 0

    for rec in bank_statement:
        credit = float(rec.data.get("credit_nzd", 0.0) or 0.0)
        if credit == 0.0:
            continue

        bid = rec.record_id
        transaction_date = rec.data.get("transaction_date", "")
        matched_entry = rec.data.get("matched_ledger_entry", "")
        alloc_records = _alloc_by_line.get(bid, [])

        status, _, notes = _bank_line_status(
            credit, matched_entry, alloc_records, _ledger_ids
        )
        if status == "PROVEN":
            rcpt_proven += 1
        elif status == "UNTRACED":
            rcpt_untraced += 1
        else:
            rcpt_mismatch += 1

        if alloc_records:
            # Attribute each portion to its own matter
            for alloc in alloc_records:
                led_id = alloc.data.get("ledger_entry_id", "")
                portion = float(alloc.data.get("amount_nzd", 0.0) or 0.0)
                ledger_rec = _ledger_by_id.get(led_id)
                matter_ref = (
                    ledger_rec.data.get("matter_ref", "") if ledger_rec else ""
                )
                alloc_count = len(alloc_records)
                row_notes = (
                    notes
                    if alloc_count == 1
                    else f"Portion of {bid} (${credit:,.2f}): {notes}"
                )
                receipt_row = {
                    "bank_line_id": bid,
                    "ledger_entry_id": led_id,
                    "transaction_date": transaction_date,
                    "amount_nzd": portion,
                    "bank_line_credit_nzd": credit,
                    "bank_line_status": status,
                    "notes": row_notes,
                }
                if matter_ref:
                    _matter(matter_ref)["receipts"].append(receipt_row)
                else:
                    unattributed.append(receipt_row)
        else:
            # 1:1 or untraced: resolve matter via ledger lookup
            ledger_rec = _ledger_by_id.get(matched_entry) if matched_entry else None
            matter_ref = (
                ledger_rec.data.get("matter_ref", "") if ledger_rec else ""
            )
            receipt_row = {
                "bank_line_id": bid,
                "ledger_entry_id": matched_entry,
                "transaction_date": transaction_date,
                "amount_nzd": credit,
                "bank_line_credit_nzd": credit,
                "bank_line_status": status,
                "notes": notes,
            }
            if matter_ref:
                _matter(matter_ref)["receipts"].append(receipt_row)
            else:
                unattributed.append(receipt_row)

    # ── payment leg (client_ledger fee/disbursement entries) ──────────────────
    pay_total = pay_proven = pay_exception = 0

    for rec in (client_ledger or []):
        payment = float(rec.data.get("payment_nzd", 0.0) or 0.0)
        if payment <= 0:
            continue
        description = rec.data.get("description", "")
        if not any(t in description.lower() for t in _FEE_TERMS):
            continue

        pay_total += 1
        matter_ref = rec.data.get("matter_ref", "")
        inv_fields = _payment_fields(rec, _inv_by_id, _inv_provided)
        pay_status = inv_fields["status"]

        if pay_status == "PROVEN":
            pay_proven += 1
        elif pay_status == "EXCEPTION":
            pay_exception += 1

        payment_row = {
            "entry_id":           rec.record_id,
            "entry_date":         rec.data.get("entry_date", ""),
            "description":        description,
            "payment_nzd":        payment,
            **inv_fields,
        }
        _matter(matter_ref)["payments"].append(payment_row)

    return {
        "firm_name":     firm_name,
        "report_period": report_period,
        "generated_at":  generated_at.isoformat() if generated_at else "",
        "receipt_summary": {
            "total":   rcpt_proven + rcpt_untraced + rcpt_mismatch,
            "proven":  rcpt_proven,
            "untraced": rcpt_untraced,
            "mismatch": rcpt_mismatch,
        },
        "payment_summary": {
            "total":     pay_total,
            "proven":    pay_proven,
            "exception": pay_exception,
        },
        "matters":              dict(sorted(matters.items())),
        "unattributed_receipts": unattributed,
    }


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _build_markdown(trail: dict) -> str:
    lines: list[str] = []

    rs = trail["receipt_summary"]
    ps = trail["payment_summary"]

    lines.append("# Funds Trail Report")
    lines.append(f"**Firm:** {trail['firm_name']}")
    lines.append(f"**Period:** {trail['report_period']}")
    lines.append(f"**Generated:** {trail['generated_at']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("**Receipts**")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    for s in ("proven", "untraced", "mismatch"):
        lines.append(f"| {s.upper()} | {rs[s]} |")
    lines.append(f"| **Total credit lines** | **{rs['total']}** |")
    lines.append("")
    lines.append("**Fee / Disbursement Payments**")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| PROVEN | {ps['proven']} |")
    lines.append(f"| EXCEPTION | {ps['exception']} |")
    lines.append(f"| **Total payment entries** | **{ps['total']}** |")

    # ── per-matter sections ───────────────────────────────────────────────────
    for matter_ref, sections in trail["matters"].items():
        receipts = sections["receipts"]
        payments = sections["payments"]

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"## Matter {matter_ref}")

        # receipts table
        lines.append("")
        lines.append("### Receipts")
        lines.append("")
        if receipts:
            lines.append(
                "| Bank Line | Ledger Entry | Date | Amount (NZD) "
                "| Bank Line Status | Notes |"
            )
            lines.append(
                "|-----------|-------------|------|-------------|"
                "-----------------|-------|"
            )
            for r in receipts:
                lines.append(
                    f"| {r['bank_line_id']} "
                    f"| {r['ledger_entry_id'] or '—'} "
                    f"| {r['transaction_date']} "
                    f"| ${r['amount_nzd']:,.2f} "
                    f"| {r['bank_line_status']} "
                    f"| {r['notes']} |"
                )
        else:
            lines.append("_No receipts in this period._")

        # payments table (only shown if there are fee/disbursement entries)
        if payments:
            lines.append("")
            lines.append("### Fee / Disbursement Payments")
            lines.append("")
            lines.append(
                "| Entry | Date | Amount (NZD) | Reference "
                "| Invoice ID | Invoice Amount | Invoice Date "
                "| Status | Rule |"
            )
            lines.append(
                "|-------|------|-------------|-----------|"
                "-----------|---------------|-------------|"
                "--------|------|"
            )
            for p in payments:
                inv_amt = (
                    f"${p['invoice_amount_nzd']:,.2f}"
                    if p["invoice_amount_nzd"] is not None
                    else "—"
                )
                lines.append(
                    f"| {p['entry_id']} "
                    f"| {p['entry_date']} "
                    f"| ${p['payment_nzd']:,.2f} "
                    f"| {p['reference'] or '—'} "
                    f"| {p['invoice_id'] or '—'} "
                    f"| {inv_amt} "
                    f"| {p['invoice_issue_date'] or '—'} "
                    f"| {p['status']} "
                    f"| {p['rule_id'] or '—'} |"
                )

    # ── unattributed credits ──────────────────────────────────────────────────
    if trail["unattributed_receipts"]:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Unattributed Credits")
        lines.append(
            "_Credits not linked to any client matter "
            "(no ledger mapping available)._"
        )
        lines.append("")
        lines.append(
            "| Bank Line | Ledger Entry | Date | Amount (NZD) "
            "| Status | Notes |"
        )
        lines.append(
            "|-----------|-------------|------|-------------|"
            "--------|-------|"
        )
        for r in trail["unattributed_receipts"]:
            lines.append(
                f"| {r['bank_line_id']} "
                f"| {r['ledger_entry_id'] or '—'} "
                f"| {r['transaction_date']} "
                f"| ${r['amount_nzd']:,.2f} "
                f"| {r['bank_line_status']} "
                f"| {r['notes']} |"
            )

    return "\n".join(lines)


def write_funds_trail(
    bank_statement: list[Record],
    allocations: list[Record],
    client_ledger: list[Record] | None = None,
    invoice_register: list[Record] | None = None,
    firm_name: str = "",
    report_period: str = "",
    generated_at: datetime.date | None = None,
    output_path: Path = Path("funds_trail.md"),
) -> dict:
    """
    Build the funds-trail dict, render markdown, write .md and .json.

    The .json file is written alongside the .md (same stem, .json suffix).
    Parent directories are created automatically. Returns the trail dict.
    """
    trail = build_funds_trail(
        bank_statement=bank_statement,
        allocations=allocations,
        client_ledger=client_ledger,
        invoice_register=invoice_register,
        firm_name=firm_name,
        report_period=report_period,
        generated_at=generated_at,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_build_markdown(trail), encoding="utf-8")
    output_path.with_suffix(".json").write_text(
        json.dumps(trail, indent=2), encoding="utf-8"
    )
    return trail
