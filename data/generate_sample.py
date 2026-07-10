#!/usr/bin/env python3
"""
Synthetic trust ledger data generator - NZ residential property law firm.

Produces four CSV files modelling a small firm's trust account over the
period December 2024 – June 2026. Output is fully deterministic: the
same script always produces identical files.

Seeded errors (one per class of trust-account failure mode):
  ERR-1  Unreconciled ledger entry > 30 days old
           matter M008, entry L009, dated 2026-03-28 - reconciled=N,
           now 89 days old. Appears in bank statement but never formally
           matched; would be missed by a cursory end-of-month tick.

  ERR-2  Overdrawn (negative) client matter balance
           matter M016 (Fitzgerald). Deposit $95,000 received; settlement
           disbursement $97,500 paid - net balance -$2,500. Client funds
           were used to cover a shortfall that should have come from the
           firm's own account.

  ERR-3  Dormant matter with non-zero balance (no activity > 12 months)
           matter M017 (Rowe Estate). $8,500 received 2024-12-15; no
           further transactions. As at 2026-06-25 the balance is 557 days
           old with no activity. Funds should have been disbursed or
           transferred to the Public Trust.

  ERR-4  Monthly reconciliation discrepancy (ledger total ≠ bank balance)
           April 2026 reconciliation. Ledger total $798,500; bank balance
           $798,750 - difference $250.00. Cause: trust account interest
           credited by the bank on 2026-04-30 not allocated to any client
           matter and not posted to the ledger.

  ERR-5  Orphan bank entry - bank credit with no matching ledger entry
           trust_bank_statement.csv entry B038, 2026-05-22, $15,000 credit
           described as "Unidentified receipt - source unknown". No
           corresponding entry in client_ledger.csv. Cannot be traced to
           any client matter.

Output files:
  matter_register.csv       - client matter sub-accounts (20 rows)
  client_ledger.csv         - transaction entries per matter (~35 rows)
  trust_bank_statement.csv  - bank account transactions (~37 rows)
  reconciliation_summary.csv - monthly reconciliation snapshots (3 rows)

Usage:
  python data/generate_sample.py
  python data/generate_sample.py --output-dir data/sample
"""

import argparse
import csv
from pathlib import Path


# ── Matter register ───────────────────────────────────────────────────────────

MATTER_HEADERS = [
    "matter_ref", "client_name", "client_bank_account", "matter_type", "matter_description",
    "opened_date", "closed_date", "last_activity_date",
    "current_balance_nzd", "status",
]

# client_bank_account: client's nominated NZ bank account for remittance (XX-XXXX-XXXXXXX-XX).
# Uses a mix of ANZ (01/06), BNZ (02), Westpac (03), ASB (12), Kiwibank (38).
MATTER_ROWS = [
    # Clean matters
    ("M001", "Anderson, James & Susan",        "01-0100-0123456-00", "PROPERTY_PURCHASE", "Purchase of 15 Pohutukawa Drive, Takapuna",         "2026-03-01", "2026-04-15", "2026-04-15",    "0.00",      "CLOSED"),
    ("M002", "Patel, Raj & Anita",             "12-3142-0567890-00", "PROPERTY_PURCHASE", "Purchase of 7B Manukau Road, Epsom",                "2026-03-05", "2026-04-28", "2026-04-28",    "0.00",      "CLOSED"),
    ("M003", "Estate of R.J. Williams (dec.)", "01-0168-0891234-00", "ESTATE",            "Administration of estate - Williams",               "2026-02-14", "",           "2026-04-05",    "85000.00",  "ACTIVE"),
    ("M004", "Chen, Wei & Mei",                "38-9003-0456789-00", "PROPERTY_PURCHASE", "Purchase of 22 Rata Street, Mount Albert",          "2026-04-08", "",           "2026-04-08",    "30000.00",  "ACTIVE"),
    ("M005", "Tauranga Commercial Props Ltd",  "03-0743-0789012-00", "COMMERCIAL",        "Commercial lease deposit - Bay Plaza",              "2026-03-20", "",           "2026-05-02",    "5000.00",   "ACTIVE"),
    ("M006", "Ngata, Hemi & Aroha",            "01-0104-0348592-02", "PROPERTY_SALE",     "Sale of 8 Kauri Crescent, Henderson",               "2026-03-10", "2026-04-01", "2026-04-01",    "7500.00",   "CLOSED"),
    ("M007", "Okonkwo, Chidi",                 "06-0167-0901234-00", "PROPERTY_PURCHASE", "Purchase of 3A Lake Road, Takapuna",                "2026-04-15", "",           "2026-04-15",    "65000.00",  "ACTIVE"),
    ("M008", "Schmidt, Klaus & Ingrid",        "38-9011-0345678-00", "PROPERTY_PURCHASE", "Purchase of 45 Remuera Road, Remuera",              "2026-03-28", "",           "2026-03-28",    "120000.00", "ACTIVE"),
    ("M009", "Singh, Priya",                   "02-0128-0678901-00", "PROPERTY_SALE",     "Sale of 12 Totara Avenue, New Lynn",                "2026-04-02", "2026-05-12", "2026-05-12",    "5000.00",   "CLOSED"),
    ("M010", "Murphy Estate Trust",            "01-0748-0789012-00", "ESTATE",            "Estate distribution - Murphy",                      "2026-02-01", "2026-04-20", "2026-04-20",    "0.00",      "CLOSED"),
    ("M011", "Te Arawa Holdings Ltd",          "03-1550-0234567-00", "COMMERCIAL",        "Commercial settlement - Rotorua development",        "2026-05-01", "",           "2026-05-14",    "2000.00",   "ACTIVE"),
    ("M012", "Blackwood, Thomas J.",           "12-3052-0890123-00", "PROPERTY_PURCHASE", "Purchase of 6 Waimari Road, Westmere",              "2026-05-10", "",           "2026-05-10",    "55000.00",  "ACTIVE"),
    ("M013", "Liu, Jing & Yuan",               "02-0192-0456789-00", "PROPERTY_PURCHASE", "Purchase of 19 Prosford Street, Ponsonby",          "2026-05-15", "",           "2026-05-15",    "110000.00", "ACTIVE"),
    ("M014", "Robertson, Sarah M.",            "01-0104-0567890-00", "PROPERTY_SALE",     "Sale of 27 Dominion Road, Mt Eden",                 "2026-04-20", "2026-06-05", "2026-06-05",    "5000.00",   "CLOSED"),
    ("M015", "Garcia, Miguel A.",              "12-3164-0123456-00", "PROPERTY_PURCHASE", "Purchase of 4 The Strand, Parnell",                 "2026-05-20", "",           "2026-05-20",    "25000.00",  "ACTIVE"),
    # ERR-2: Overdrawn matter
    ("M016", "Fitzgerald, Declan & Erin",      "38-9008-0234567-00", "PROPERTY_PURCHASE", "Purchase of 11 Devonport Road, Devonport [ERR-2: OVERDRAWN]", "2026-03-15", "", "2026-04-28", "-2500.00",  "ACTIVE"),
    # ERR-3: Dormant matter
    ("M017", "Rowe, Margaret H. (Estate)",     "01-0748-0901234-00", "ESTATE",            "Administration of estate - Rowe [ERR-3: DORMANT - no activity since 2024-12-15]", "2024-11-01", "", "2024-12-15", "8500.00", "DORMANT"),
    # Clean matters continued
    ("M018", "Kowalski, Adam & Ewa",           "02-0158-0678901-00", "PROPERTY_PURCHASE", "Purchase of 33 Sandringham Road, Sandringham",      "2026-05-28", "",           "2026-05-28",    "40000.00",  "ACTIVE"),
    ("M019", "Nkosi, Thabo & Nomsa",           "03-0742-0345678-00", "PROPERTY_SALE",     "Sale of 9 Harbour View Road, Northcote",            "2026-04-25", "2026-06-10", "2026-06-10",    "0.00",      "CLOSED"),
    ("M020", "Yamamoto, Kenji",                "38-9015-0789012-00", "PROPERTY_PURCHASE", "Purchase of 17 Gladstone Road, Parnell",            "2026-06-01", "",           "2026-06-01",    "70000.00",  "ACTIVE"),
]


# ── Client ledger ─────────────────────────────────────────────────────────────
# Running balance column is per-matter, not aggregate.

LEDGER_HEADERS = [
    "entry_id", "matter_ref", "entry_date", "description",
    "receipt_nzd", "payment_nzd", "balance_after_nzd",
    "reconciled", "reconciled_date", "notes",
]

LEDGER_ROWS = [
    # ERR-3: Rowe Estate - dormant since this entry (Dec 2024)
    ("L001", "M017", "2024-12-15", "Receipt - Estate funds deposited (Rowe estate)",
     "8500.00",   "0.00",     "8500.00",    "Y", "2025-01-10", "ERR-3: no further activity; funds not disbursed"),
    # Murphy Estate (clean)
    ("L002", "M010", "2026-02-01", "Receipt - Estate funds received from Public Trust",
     "340000.00", "0.00",     "340000.00",  "Y", "2026-03-05", ""),
    # Williams Estate (clean)
    ("L003", "M003", "2026-02-14", "Receipt - Estate funds received - Williams estate",
     "125000.00", "0.00",     "125000.00",  "Y", "2026-03-05", ""),
    # Anderson purchase deposit
    ("L004", "M001", "2026-03-01", "Receipt - Purchase deposit (10%)",
     "80000.00",  "0.00",     "80000.00",   "Y", "2026-03-05", ""),
    # Patel purchase deposit
    ("L005", "M002", "2026-03-05", "Receipt - Purchase deposit (10%)",
     "50000.00",  "0.00",     "50000.00",   "Y", "2026-03-10", ""),
    # Ngata sale - sale proceeds from purchaser's solicitor
    ("L006", "M006", "2026-03-10", "Receipt - Sale proceeds received from purchaser's solicitors",
     "490000.00", "0.00",     "490000.00",  "Y", "2026-03-15", ""),
    # ERR-2: Fitzgerald purchase deposit (first entry, seems clean)
    ("L007", "M016", "2026-03-15", "Receipt - Purchase deposit (10%)",
     "95000.00",  "0.00",     "95000.00",   "Y", "2026-03-20", ""),
    # Tauranga Commercial deposit
    ("L008", "M005", "2026-03-20", "Receipt - Commercial lease deposit received",
     "200000.00", "0.00",     "200000.00",  "Y", "2026-03-25", ""),
    # ERR-1: Schmidt deposit - unreconciled, >30 days old
    ("L009", "M008", "2026-03-28", "Receipt - Purchase deposit received",
     "120000.00", "0.00",     "120000.00",  "N", "",           "ERR-1: unreconciled entry 89 days old as at 2026-06-25"),
    # Ngata - vendor payment
    ("L010", "M006", "2026-04-01", "Payment - Net sale proceeds to vendor (after retained costs)",
     "0.00",      "482500.00","7500.00",    "Y", "2026-04-05", ""),
    # Williams Estate - partial disbursement
    ("L011", "M003", "2026-04-05", "Payment - Disbursement to beneficiary J. Williams",
     "0.00",      "40000.00", "85000.00",   "Y", "2026-04-10", ""),
    # Chen deposit
    ("L012", "M004", "2026-04-08", "Receipt - Purchase deposit received",
     "30000.00",  "0.00",     "30000.00",   "Y", "2026-04-10", ""),
    # Anderson - settlement funds received
    ("L013", "M001", "2026-04-12", "Receipt - Settlement funds received from purchaser's mortgagee",
     "645000.00", "0.00",     "725000.00",  "Y", "2026-04-15", ""),
    # Anderson - settlement payment to vendor
    ("L014", "M001", "2026-04-15", "Payment - Settlement funds paid to vendor's solicitors",
     "0.00",      "725000.00","0.00",       "Y", "2026-04-15", ""),
    # Okonkwo deposit
    ("L015", "M007", "2026-04-15", "Receipt - Purchase deposit received",
     "65000.00",  "0.00",     "65000.00",   "Y", "2026-04-20", ""),
    # Murphy Estate - beneficiary payments
    ("L016", "M010", "2026-04-18", "Payment - Distribution to beneficiary P. Murphy",
     "0.00",      "200000.00","140000.00",  "Y", "2026-04-20", ""),
    ("L017", "M010", "2026-04-20", "Payment - Final distribution to beneficiary T. Murphy",
     "0.00",      "140000.00","0.00",       "Y", "2026-04-20", ""),
    # Patel - settlement
    ("L018", "M002", "2026-04-21", "Receipt - Settlement funds received",
     "405000.00", "0.00",     "455000.00",  "Y", "2026-04-25", ""),
    # Nkosi - sale proceeds received
    ("L019", "M019", "2026-04-25", "Receipt - Sale proceeds received from purchaser's solicitors",
     "285000.00", "0.00",     "285000.00",  "Y", "2026-04-30", ""),
    # Patel - settlement payment
    ("L020", "M002", "2026-04-28", "Payment - Settlement funds paid to vendor's solicitors",
     "0.00",      "455000.00","0.00",       "Y", "2026-04-28", ""),
    # ERR-2: Fitzgerald - settlement disbursement EXCEEDS deposit by $2,500
    ("L021", "M016", "2026-04-28", "Payment - Settlement disbursement to vendor's solicitors",
     "0.00",      "97500.00", "-2500.00",   "Y", "2026-04-30", "ERR-2: payment exceeds receipts; matter overdrawn by $2,500"),
    # Te Arawa commercial settlement
    ("L022", "M011", "2026-05-01", "Receipt - Commercial settlement funds received",
     "450000.00", "0.00",     "450000.00",  "Y", "2026-05-05", ""),
    # Tauranga Commercial - deposit refund after settled
    ("L023", "M005", "2026-05-02", "Payment - Lease deposit refunded to tenant (net of costs)",
     "0.00",      "195000.00","5000.00",    "Y", "2026-05-05", ""),
    # Singh - sale proceeds
    ("L024", "M009", "2026-05-10", "Receipt - Sale proceeds received from purchaser's solicitors",
     "380000.00", "0.00",     "380000.00",  "Y", "2026-05-12", ""),
    # Blackwood deposit
    ("L025", "M012", "2026-05-10", "Receipt - Purchase deposit received",
     "55000.00",  "0.00",     "55000.00",   "Y", "2026-05-12", ""),
    # Singh - vendor payment
    ("L026", "M009", "2026-05-12", "Payment - Net proceeds paid to vendor Singh",
     "0.00",      "375000.00","5000.00",    "Y", "2026-05-15", ""),
    # Te Arawa - vendor payment
    ("L027", "M011", "2026-05-14", "Payment - Settlement payment to vendor",
     "0.00",      "448000.00","2000.00",    "Y", "2026-05-15", ""),
    # Liu deposit
    ("L028", "M013", "2026-05-15", "Receipt - Purchase deposit received",
     "110000.00", "0.00",     "110000.00",  "Y", "2026-05-20", ""),
    # Garcia deposit
    ("L029", "M015", "2026-05-20", "Receipt - Purchase deposit received",
     "25000.00",  "0.00",     "25000.00",   "Y", "2026-05-22", ""),
    # Kowalski deposit
    ("L030", "M018", "2026-05-28", "Receipt - Purchase deposit received",
     "40000.00",  "0.00",     "40000.00",   "Y", "2026-05-30", ""),
    # Yamamoto deposit
    ("L031", "M020", "2026-06-01", "Receipt - Purchase deposit received",
     "70000.00",  "0.00",     "70000.00",   "Y", "2026-06-05", ""),
    # Robertson - sale proceeds received
    ("L032", "M014", "2026-06-02", "Receipt - Sale proceeds received from purchaser's solicitors",
     "620000.00", "0.00",     "620000.00",  "Y", "2026-06-05", ""),
    # Nkosi - vendor payment
    ("L033", "M019", "2026-06-02", "Payment - Net proceeds paid to vendor Nkosi",
     "0.00",      "280000.00","5000.00",    "Y", "2026-06-05", ""),
    # Robertson - vendor payment
    ("L034", "M014", "2026-06-05", "Payment - Settlement payment to vendor Robertson",
     "0.00",      "615000.00","5000.00",    "Y", "2026-06-05", ""),
    # Nkosi - final disbursement
    ("L035", "M019", "2026-06-10", "Payment - Final disbursement of retained costs to vendor",
     "0.00",      "5000.00",  "0.00",       "Y", "2026-06-10", ""),
]


# ── Trust bank statement ──────────────────────────────────────────────────────
# running_balance_nzd reflects the actual bank account balance after each entry.
# matched_ledger_entry is empty for unmatched items (ERR-1, ERR-4 interest, ERR-5).

BANK_HEADERS = [
    "statement_id", "trust_account_number", "transaction_date", "description",
    "credit_nzd", "debit_nzd", "running_balance_nzd",
    "matched_ledger_entry", "notes",
]

# trust_account_number: the firm's ANZ trust account (01 = ANZ, branch 0748 = Shortland St Auckland).
# All 37 rows carry the same value — this is how real bank CSV exports repeat the account number.
_TA = "01-0748-0234567-00"

BANK_ROWS = [
    ("B001", _TA, "2024-12-15", "Credit - Rowe Estate (Dec 2024)",               "8500.00",   "0.00",      "8500.00",    "L001", ""),
    ("B002", _TA, "2026-02-01", "Credit - Murphy Estate funds",                   "340000.00", "0.00",      "348500.00",  "L002", ""),
    ("B003", _TA, "2026-02-14", "Credit - Williams Estate funds",                 "125000.00", "0.00",      "473500.00",  "L003", ""),
    ("B004", _TA, "2026-03-01", "Credit - Anderson purchase deposit",             "80000.00",  "0.00",      "553500.00",  "L004", ""),
    ("B005", _TA, "2026-03-05", "Credit - Patel purchase deposit",                "50000.00",  "0.00",      "603500.00",  "L005", ""),
    ("B006", _TA, "2026-03-10", "Credit - Ngata sale proceeds",                   "490000.00", "0.00",      "1093500.00", "L006", ""),
    ("B007", _TA, "2026-03-15", "Credit - Fitzgerald purchase deposit",           "95000.00",  "0.00",      "1188500.00", "L007", ""),
    ("B008", _TA, "2026-03-20", "Credit - Tauranga Commercial deposit",           "200000.00", "0.00",      "1388500.00", "L008", ""),
    # ERR-1: Schmidt deposit is in the bank but ledger entry L009 is unreconciled (no matched_ledger_entry)
    ("B009", _TA, "2026-03-28", "Credit - Schmidt purchase deposit",              "120000.00", "0.00",      "1508500.00", "",     "ERR-1: corresponds to ledger L009 but never formally reconciled"),
    ("B010", _TA, "2026-04-01", "Debit - Ngata vendor payment",                   "0.00",      "482500.00", "1026000.00", "L010", ""),
    ("B011", _TA, "2026-04-05", "Debit - Williams Estate beneficiary payment",     "0.00",      "40000.00",  "986000.00",  "L011", ""),
    ("B012", _TA, "2026-04-08", "Credit - Chen purchase deposit",                 "30000.00",  "0.00",      "1016000.00", "L012", ""),
    ("B013", _TA, "2026-04-12", "Credit - Anderson settlement funds",             "645000.00", "0.00",      "1661000.00", "L013", ""),
    ("B014", _TA, "2026-04-15", "Debit - Anderson settlement to vendor",          "0.00",      "725000.00", "936000.00",  "L014", ""),
    ("B015", _TA, "2026-04-15", "Credit - Okonkwo purchase deposit",              "65000.00",  "0.00",      "1001000.00", "L015", ""),
    ("B016", _TA, "2026-04-18", "Debit - Murphy Estate beneficiary P. Murphy",    "0.00",      "200000.00", "801000.00",  "L016", ""),
    ("B017", _TA, "2026-04-20", "Debit - Murphy Estate final distribution",       "0.00",      "140000.00", "661000.00",  "L017", ""),
    ("B018", _TA, "2026-04-21", "Credit - Patel settlement funds",                "405000.00", "0.00",      "1066000.00", "L018", ""),
    ("B019", _TA, "2026-04-25", "Credit - Nkosi sale proceeds",                   "285000.00", "0.00",      "1351000.00", "L019", ""),
    ("B020", _TA, "2026-04-28", "Debit - Patel settlement to vendor",             "0.00",      "455000.00", "896000.00",  "L020", ""),
    ("B021", _TA, "2026-04-28", "Debit - Fitzgerald settlement to vendor",        "0.00",      "97500.00",  "798500.00",  "L021", ""),
    # ERR-4: bank interest credited April 30 - no ledger entry; causes reconciliation discrepancy
    ("B022", _TA, "2026-04-30", "Credit - Trust account interest (Apr 2026)",     "250.00",    "0.00",      "798750.00",  "",     "ERR-4: interest not allocated to any client matter; causes April recon discrepancy of $250"),
    ("B023", _TA, "2026-05-01", "Credit - Te Arawa commercial settlement",        "450000.00", "0.00",      "1248750.00", "L022", ""),
    ("B024", _TA, "2026-05-02", "Debit - Tauranga lease deposit refund",          "0.00",      "195000.00", "1053750.00", "L023", ""),
    ("B025", _TA, "2026-05-10", "Credit - Singh sale proceeds",                   "380000.00", "0.00",      "1433750.00", "L024", ""),
    ("B026", _TA, "2026-05-10", "Credit - Blackwood purchase deposit",            "55000.00",  "0.00",      "1488750.00", "L025", ""),
    ("B027", _TA, "2026-05-12", "Debit - Singh vendor payment",                   "0.00",      "375000.00", "1113750.00", "L026", ""),
    ("B028", _TA, "2026-05-14", "Debit - Te Arawa vendor payment",                "0.00",      "448000.00", "665750.00",  "L027", ""),
    ("B029", _TA, "2026-05-15", "Credit - Liu purchase deposit",                  "110000.00", "0.00",      "775750.00",  "L028", ""),
    ("B030", _TA, "2026-05-20", "Credit - Garcia purchase deposit",               "25000.00",  "0.00",      "800750.00",  "L029", ""),
    # ERR-5: orphan bank credit - no ledger entry, source unknown
    ("B031", _TA, "2026-05-22", "Credit - Unidentified receipt (source unknown)", "15000.00",  "0.00",      "815750.00",  "",     "ERR-5: no matching ledger entry; cannot be traced to any client matter"),
    ("B032", _TA, "2026-05-28", "Credit - Kowalski purchase deposit",             "40000.00",  "0.00",      "855750.00",  "L030", ""),
    ("B033", _TA, "2026-06-01", "Credit - Yamamoto purchase deposit",             "70000.00",  "0.00",      "925750.00",  "L031", ""),
    ("B034", _TA, "2026-06-02", "Credit - Robertson sale proceeds",               "620000.00", "0.00",      "1545750.00", "L032", ""),
    ("B035", _TA, "2026-06-02", "Debit - Nkosi vendor payment",                   "0.00",      "280000.00", "1265750.00", "L033", ""),
    ("B036", _TA, "2026-06-05", "Debit - Robertson settlement to vendor",         "0.00",      "615000.00", "650750.00",  "L034", ""),
    ("B037", _TA, "2026-06-10", "Debit - Nkosi final disbursement",               "0.00",      "5000.00",   "645750.00",  "L035", ""),
]


# ── Reconciliation summary ────────────────────────────────────────────────────
# ledger_total_nzd = sum of all client matter balances at period end.
# bank_balance_nzd = trust bank statement closing balance at period end.
# March: clean. April: ERR-4 ($250 discrepancy). May: in progress.

RECON_HEADERS = [
    "recon_id", "period_end_date",
    "ledger_total_nzd", "bank_balance_nzd", "difference_nzd",
    "prepared_by", "approved_by", "status", "notes",
]

RECON_ROWS = [
    # March 2026: AGREED - all balances reconcile
    ("R001", "2026-03-31", "1508500.00", "1508500.00", "0.00",
     "J. Anderson", "S. Mitchell", "AGREED", ""),
    # April 2026: ERR-4 - $250 discrepancy (trust interest not allocated)
    ("R002", "2026-04-30", "798500.00",  "798750.00",  "-250.00",
     "J. Anderson", "S. Mitchell", "DISCREPANCY",
     "ERR-4: $250 difference - trust account interest (B022) not allocated to any client matter ledger"),
    # May 2026: not yet completed (in progress)
    ("R003", "2026-05-31", "",           "",           "",
     "J. Anderson", "",            "IN PROGRESS",
     "ERR-5 (B031 $15,000 orphan credit) and ERR-1 (L009 unreconciled 65+ days) both present in this period"),
]


# ── Writer ────────────────────────────────────────────────────────────────────

def _write_csv(path: Path, headers: list, rows: list) -> int:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return len(rows)


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    counts = {
        "matter_register":      _write_csv(output_dir / "matter_register.csv",      MATTER_HEADERS, MATTER_ROWS),
        "client_ledger":        _write_csv(output_dir / "client_ledger.csv",         LEDGER_HEADERS, LEDGER_ROWS),
        "trust_bank_statement": _write_csv(output_dir / "trust_bank_statement.csv",  BANK_HEADERS,   BANK_ROWS),
        "reconciliation_summary": _write_csv(output_dir / "reconciliation_summary.csv", RECON_HEADERS, RECON_ROWS),
    }

    print(f"\nSynthetic trust ledger written to: {output_dir.resolve()}\n")
    for name, n in counts.items():
        print(f"  {name}.csv  -  {n} rows")

    print("""
Seeded errors summary:
  ERR-1  Unreconciled entry > 30 days   matter M008 / ledger L009 / bank B009
  ERR-2  Overdrawn matter               matter M016 / balance -$2,500
  ERR-3  Dormant matter with balance    matter M017 / balance $8,500 / last activity 2024-12-15
  ERR-4  Reconciliation discrepancy     April 2026 recon (R002) / difference -$250 / bank B022
  ERR-5  Orphan bank entry              bank B031 / $15,000 / 2026-05-22
""")


def main() -> int:
    p = argparse.ArgumentParser(description="Generate synthetic NZ trust ledger sample data")
    p.add_argument("--output-dir", default="data/sample",
                   help="Directory to write CSV files into (default: data/sample)")
    args = p.parse_args()
    generate(Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
