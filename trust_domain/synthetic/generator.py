#!/usr/bin/env python3
"""
Enhanced trust ledger data generator for the trust_domain rule suite.

Produces four CSV files identical in structure to data/sample/ but with
targeted changes required to exercise all seven trust-domain rules:

  ERR-1  R05_UNRECONCILED_AGEING  — L009, reconciled=N, 89 days old
  ERR-2  R01_OVERDRAWN_CLIENT_LEDGER — L021, balance_after=-2500.00
  ERR-3  R02_DORMANT_BALANCE      — M017, last_activity=2024-12-15 (557 days)
  ERR-4  R03_RECON_BREAK          — R002, ledger=798500 vs bank=798750
  ERR-5  R04_UNMATCHED_BANK_LINE  — B031, matched_ledger_entry="" (34 days old)
  ERR-6  R06_FIT_OVERHELD         — M021, FIT balance 24 days old (> 14 threshold)
  ERR-7  R07_FEE_WITHOUT_INVOICE  — L037, disbursement without INV-XXXXX reference

Key differences from data/generate_sample.py (DO NOT MODIFY THAT FILE):
  - LEDGER_HEADERS gains a "reference" column (all existing rows get "")
  - B009 gets matched_ledger_entry="L009"   (was "" — prevents spurious R04 flag)
  - B022 gets matched_ledger_entry="BANK-INTEREST" (was "" — prevents spurious R04 flag)
  - Descriptions for L011, L021, L035 no longer contain "disbursement"
    (prevents spurious R07 flags on legitimate vendor payments)
  - M012 current_balance_nzd updated to 54800.00 (reflects L037 -200)
  - M013 current_balance_nzd updated to 109500.00 (reflects L038 -500)
  - M021 added (FIT matter, balance=125.00, last_activity=2026-06-01)
  - L036 added (FIT credit — ERR-6 seed)
  - L037 added (disbursement without invoice — ERR-7 seed)
  - L038 added (fee WITH invoice — clean counterpart to L037)
  - B038-B040 added (bank counterparts to L036-L038)
  - Output directory: trust_domain/synthetic/sample/

Usage:
  python trust_domain/synthetic/generator.py
  python trust_domain/synthetic/generator.py --output-dir trust_domain/synthetic/sample
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

MATTER_ROWS = [
    # Clean matters
    ("M001", "Anderson, James & Susan",        "01-0100-0123456-00", "PROPERTY_PURCHASE", "Purchase of 15 Pohutukawa Drive, Takapuna",         "2026-03-01", "2026-04-15", "2026-04-15",    "0.00",       "CLOSED"),
    ("M002", "Patel, Raj & Anita",             "12-3142-0567890-00", "PROPERTY_PURCHASE", "Purchase of 7B Manukau Road, Epsom",                "2026-03-05", "2026-04-28", "2026-04-28",    "0.00",       "CLOSED"),
    ("M003", "Estate of R.J. Williams (dec.)", "01-0168-0891234-00", "ESTATE",            "Administration of estate - Williams",               "2026-02-14", "",           "2026-04-05",    "85000.00",   "ACTIVE"),
    ("M004", "Chen, Wei & Mei",                "38-9003-0456789-00", "PROPERTY_PURCHASE", "Purchase of 22 Rata Street, Mount Albert",          "2026-04-08", "",           "2026-04-08",    "30000.00",   "ACTIVE"),
    ("M005", "Tauranga Commercial Props Ltd",  "03-0743-0789012-00", "COMMERCIAL",        "Commercial lease deposit - Bay Plaza",              "2026-03-20", "",           "2026-05-02",    "5000.00",    "ACTIVE"),
    ("M006", "Ngata, Hemi & Aroha",            "01-0104-0348592-02", "PROPERTY_SALE",     "Sale of 8 Kauri Crescent, Henderson",               "2026-03-10", "2026-04-01", "2026-04-01",    "7500.00",    "CLOSED"),
    ("M007", "Okonkwo, Chidi",                 "06-0167-0901234-00", "PROPERTY_PURCHASE", "Purchase of 3A Lake Road, Takapuna",                "2026-04-15", "",           "2026-04-15",    "65000.00",   "ACTIVE"),
    ("M008", "Schmidt, Klaus & Ingrid",        "38-9011-0345678-00", "PROPERTY_PURCHASE", "Purchase of 45 Remuera Road, Remuera",              "2026-03-28", "",           "2026-03-28",    "120000.00",  "ACTIVE"),
    ("M009", "Singh, Priya",                   "02-0128-0678901-00", "PROPERTY_SALE",     "Sale of 12 Totara Avenue, New Lynn",                "2026-04-02", "2026-05-12", "2026-05-12",    "5000.00",    "CLOSED"),
    ("M010", "Murphy Estate Trust",            "01-0748-0789012-00", "ESTATE",            "Estate distribution - Murphy",                      "2026-02-01", "2026-04-20", "2026-04-20",    "0.00",       "CLOSED"),
    ("M011", "Te Arawa Holdings Ltd",          "03-1550-0234567-00", "COMMERCIAL",        "Commercial settlement - Rotorua development",        "2026-05-01", "",           "2026-05-14",    "2000.00",    "ACTIVE"),
    # M012 balance updated: 55000 - 200 (L037 disbursement) = 54800
    ("M012", "Blackwood, Thomas J.",           "12-3052-0890123-00", "PROPERTY_PURCHASE", "Purchase of 6 Waimari Road, Westmere",              "2026-05-10", "",           "2026-05-28",    "54800.00",   "ACTIVE"),
    # M013 balance updated: 110000 - 500 (L038 fee) = 109500
    ("M013", "Liu, Jing & Yuan",               "02-0192-0456789-00", "PROPERTY_PURCHASE", "Purchase of 19 Prosford Street, Ponsonby",          "2026-05-15", "",           "2026-05-28",    "109500.00",  "ACTIVE"),
    ("M014", "Robertson, Sarah M.",            "01-0104-0567890-00", "PROPERTY_SALE",     "Sale of 27 Dominion Road, Mt Eden",                 "2026-04-20", "2026-06-05", "2026-06-05",    "5000.00",    "CLOSED"),
    ("M015", "Garcia, Miguel A.",              "12-3164-0123456-00", "PROPERTY_PURCHASE", "Purchase of 4 The Strand, Parnell",                 "2026-05-20", "",           "2026-05-20",    "25000.00",   "ACTIVE"),
    # ERR-2: Overdrawn matter
    ("M016", "Fitzgerald, Declan & Erin",      "38-9008-0234567-00", "PROPERTY_PURCHASE", "Purchase of 11 Devonport Road, Devonport [ERR-2: OVERDRAWN]", "2026-03-15", "", "2026-04-28", "-2500.00",   "ACTIVE"),
    # ERR-3: Dormant matter (557 days as at 2026-06-25)
    ("M017", "Rowe, Margaret H. (Estate)",     "01-0748-0901234-00", "ESTATE",            "Administration of estate - Rowe [ERR-3: DORMANT - no activity since 2024-12-15]", "2024-11-01", "", "2024-12-15", "8500.00", "DORMANT"),
    ("M018", "Kowalski, Adam & Ewa",           "02-0158-0678901-00", "PROPERTY_PURCHASE", "Purchase of 33 Sandringham Road, Sandringham",      "2026-05-28", "",           "2026-05-28",    "40000.00",   "ACTIVE"),
    ("M019", "Nkosi, Thabo & Nomsa",           "03-0742-0345678-00", "PROPERTY_SALE",     "Sale of 9 Harbour View Road, Northcote",            "2026-04-25", "2026-06-10", "2026-06-10",    "0.00",       "CLOSED"),
    ("M020", "Yamamoto, Kenji",                "38-9015-0789012-00", "PROPERTY_PURCHASE", "Purchase of 17 Gladstone Road, Parnell",            "2026-06-01", "",           "2026-06-01",    "70000.00",   "ACTIVE"),
    # ERR-6: FIT matter — balance held 24 days (2026-06-01 to 2026-06-25) > 14-day deadline
    ("M021", "Firm Interest in Trust (FIT account)", "01-0748-0234567-00", "FIT",         "FIT pooled trust interest account [ERR-6: OVERHELD - 24 days, deadline 14]", "2026-06-01", "", "2026-06-01", "125.00",  "ACTIVE"),
]


# ── Client ledger ─────────────────────────────────────────────────────────────
# "reference" field added: invoice number for fee/disbursement entries.
# Format: INV-DDDDD. Empty for all non-fee entries and for ERR-7.

LEDGER_HEADERS = [
    "entry_id", "matter_ref", "entry_date", "description",
    "receipt_nzd", "payment_nzd", "balance_after_nzd",
    "reconciled", "reconciled_date", "notes", "reference",
]

LEDGER_ROWS = [
    # ERR-3: Rowe Estate - dormant since this entry (Dec 2024)
    ("L001", "M017", "2024-12-15", "Receipt - Estate funds deposited (Rowe estate)",
     "8500.00",   "0.00",      "8500.00",    "Y", "2025-01-10", "ERR-3: no further activity; funds not disbursed", ""),
    # Murphy Estate (clean)
    ("L002", "M010", "2026-02-01", "Receipt - Estate funds received from Public Trust",
     "340000.00", "0.00",      "340000.00",  "Y", "2026-03-05", "", ""),
    # Williams Estate (clean)
    ("L003", "M003", "2026-02-14", "Receipt - Estate funds received - Williams estate",
     "125000.00", "0.00",      "125000.00",  "Y", "2026-03-05", "", ""),
    # Anderson purchase deposit
    ("L004", "M001", "2026-03-01", "Receipt - Purchase deposit (10%)",
     "80000.00",  "0.00",      "80000.00",   "Y", "2026-03-05", "", ""),
    # Patel purchase deposit
    ("L005", "M002", "2026-03-05", "Receipt - Purchase deposit (10%)",
     "50000.00",  "0.00",      "50000.00",   "Y", "2026-03-10", "", ""),
    # Ngata sale - sale proceeds from purchaser's solicitor
    ("L006", "M006", "2026-03-10", "Receipt - Sale proceeds received from purchaser's solicitors",
     "490000.00", "0.00",      "490000.00",  "Y", "2026-03-15", "", ""),
    # ERR-2: Fitzgerald purchase deposit (first entry, seems clean)
    ("L007", "M016", "2026-03-15", "Receipt - Purchase deposit (10%)",
     "95000.00",  "0.00",      "95000.00",   "Y", "2026-03-20", "", ""),
    # Tauranga Commercial deposit
    ("L008", "M005", "2026-03-20", "Receipt - Commercial lease deposit received",
     "200000.00", "0.00",      "200000.00",  "Y", "2026-03-25", "", ""),
    # ERR-1: Schmidt deposit - unreconciled, >30 days old (89 days as at 2026-06-25)
    ("L009", "M008", "2026-03-28", "Receipt - Purchase deposit received",
     "120000.00", "0.00",      "120000.00",  "N", "",           "ERR-1: unreconciled entry 89 days old as at 2026-06-25", ""),
    # Ngata - vendor payment (description changed: no "disbursement")
    ("L010", "M006", "2026-04-01", "Payment - Net sale proceeds to vendor (after retained costs)",
     "0.00",      "482500.00", "7500.00",    "Y", "2026-04-05", "", ""),
    # Williams Estate - partial beneficiary payment (was "Disbursement to beneficiary" - changed to avoid R07)
    ("L011", "M003", "2026-04-05", "Payment - Beneficiary payment J. Williams",
     "0.00",      "40000.00",  "85000.00",   "Y", "2026-04-10", "", ""),
    # Chen deposit
    ("L012", "M004", "2026-04-08", "Receipt - Purchase deposit received",
     "30000.00",  "0.00",      "30000.00",   "Y", "2026-04-10", "", ""),
    # Anderson - settlement funds received
    ("L013", "M001", "2026-04-12", "Receipt - Settlement funds received from purchaser's mortgagee",
     "645000.00", "0.00",      "725000.00",  "Y", "2026-04-15", "", ""),
    # Anderson - settlement payment to vendor
    ("L014", "M001", "2026-04-15", "Payment - Settlement funds paid to vendor's solicitors",
     "0.00",      "725000.00", "0.00",       "Y", "2026-04-15", "", ""),
    # Okonkwo deposit
    ("L015", "M007", "2026-04-15", "Receipt - Purchase deposit received",
     "65000.00",  "0.00",      "65000.00",   "Y", "2026-04-20", "", ""),
    # Murphy Estate - beneficiary payments
    ("L016", "M010", "2026-04-18", "Payment - Distribution to beneficiary P. Murphy",
     "0.00",      "200000.00", "140000.00",  "Y", "2026-04-20", "", ""),
    ("L017", "M010", "2026-04-20", "Payment - Final distribution to beneficiary T. Murphy",
     "0.00",      "140000.00", "0.00",       "Y", "2026-04-20", "", ""),
    # Patel - settlement
    ("L018", "M002", "2026-04-21", "Receipt - Settlement funds received",
     "405000.00", "0.00",      "455000.00",  "Y", "2026-04-25", "", ""),
    # Nkosi - sale proceeds received
    ("L019", "M019", "2026-04-25", "Receipt - Sale proceeds received from purchaser's solicitors",
     "285000.00", "0.00",      "285000.00",  "Y", "2026-04-30", "", ""),
    # Patel - settlement payment
    ("L020", "M002", "2026-04-28", "Payment - Settlement funds paid to vendor's solicitors",
     "0.00",      "455000.00", "0.00",       "Y", "2026-04-28", "", ""),
    # ERR-2: Fitzgerald - settlement payment EXCEEDS deposit by $2,500 (description changed: no "disbursement")
    ("L021", "M016", "2026-04-28", "Payment - Settlement payment to vendor's solicitors",
     "0.00",      "97500.00",  "-2500.00",   "Y", "2026-04-30", "ERR-2: payment exceeds receipts; matter overdrawn by $2,500", ""),
    # Te Arawa commercial settlement
    ("L022", "M011", "2026-05-01", "Receipt - Commercial settlement funds received",
     "450000.00", "0.00",      "450000.00",  "Y", "2026-05-05", "", ""),
    # Tauranga Commercial - deposit refund after settled
    ("L023", "M005", "2026-05-02", "Payment - Lease deposit refunded to tenant (net of costs)",
     "0.00",      "195000.00", "5000.00",    "Y", "2026-05-05", "", ""),
    # Singh - sale proceeds
    ("L024", "M009", "2026-05-10", "Receipt - Sale proceeds received from purchaser's solicitors",
     "380000.00", "0.00",      "380000.00",  "Y", "2026-05-12", "", ""),
    # Blackwood deposit
    ("L025", "M012", "2026-05-10", "Receipt - Purchase deposit received",
     "55000.00",  "0.00",      "55000.00",   "Y", "2026-05-12", "", ""),
    # Singh - vendor payment
    ("L026", "M009", "2026-05-12", "Payment - Net proceeds paid to vendor Singh",
     "0.00",      "375000.00", "5000.00",    "Y", "2026-05-15", "", ""),
    # Te Arawa - vendor payment
    ("L027", "M011", "2026-05-14", "Payment - Settlement payment to vendor",
     "0.00",      "448000.00", "2000.00",    "Y", "2026-05-15", "", ""),
    # Liu deposit
    ("L028", "M013", "2026-05-15", "Receipt - Purchase deposit received",
     "110000.00", "0.00",      "110000.00",  "Y", "2026-05-20", "", ""),
    # Garcia deposit
    ("L029", "M015", "2026-05-20", "Receipt - Purchase deposit received",
     "25000.00",  "0.00",      "25000.00",   "Y", "2026-05-22", "", ""),
    # Kowalski deposit
    ("L030", "M018", "2026-05-28", "Receipt - Purchase deposit received",
     "40000.00",  "0.00",      "40000.00",   "Y", "2026-05-30", "", ""),
    # Yamamoto deposit
    ("L031", "M020", "2026-06-01", "Receipt - Purchase deposit received",
     "70000.00",  "0.00",      "70000.00",   "Y", "2026-06-05", "", ""),
    # Robertson - sale proceeds received
    ("L032", "M014", "2026-06-02", "Receipt - Sale proceeds received from purchaser's solicitors",
     "620000.00", "0.00",      "620000.00",  "Y", "2026-06-05", "", ""),
    # Nkosi - vendor payment
    ("L033", "M019", "2026-06-02", "Payment - Net proceeds paid to vendor Nkosi",
     "0.00",      "280000.00", "5000.00",    "Y", "2026-06-05", "", ""),
    # Robertson - vendor payment
    ("L034", "M014", "2026-06-05", "Payment - Settlement payment to vendor Robertson",
     "0.00",      "615000.00", "5000.00",    "Y", "2026-06-05", "", ""),
    # Nkosi - final payment (description changed: no "disbursement")
    ("L035", "M019", "2026-06-10", "Payment - Final retained costs payment to vendor",
     "0.00",      "5000.00",   "0.00",       "Y", "2026-06-10", "", ""),
    # ERR-6: FIT credit - triggers R06_FIT_OVERHELD (24 days old > 14-day threshold)
    ("L036", "M021", "2026-06-01", "FIT credit - Interest on pooled trust funds (May 2026)",
     "125.00",    "0.00",      "125.00",     "Y", "2026-06-02", "ERR-6: FIT balance not transferred within 14 days", ""),
    # ERR-7: Disbursement without valid invoice reference — triggers R07_FEE_WITHOUT_INVOICE
    ("L037", "M012", "2026-05-28", "Disbursement - LINZ title search fee",
     "0.00",      "200.00",    "54800.00",   "Y", "2026-05-29", "ERR-7: no INV-XXXXX reference for fee entry", ""),
    # Clean: fee WITH valid invoice reference — should NOT be flagged
    ("L038", "M013", "2026-05-28", "Fee - professional conveyancing services",
     "0.00",      "500.00",    "109500.00",  "Y", "2026-05-29", "", "INV-00234"),
]


# ── Trust bank statement ──────────────────────────────────────────────────────

BANK_HEADERS = [
    "statement_id", "trust_account_number", "transaction_date", "description",
    "credit_nzd", "debit_nzd", "running_balance_nzd",
    "matched_ledger_entry", "notes",
]

_TA = "01-0748-0234567-00"

BANK_ROWS = [
    ("B001", _TA, "2024-12-15", "Credit - Rowe Estate (Dec 2024)",               "8500.00",   "0.00",      "8500.00",    "L001",          ""),
    ("B002", _TA, "2026-02-01", "Credit - Murphy Estate funds",                   "340000.00", "0.00",      "348500.00",  "L002",          ""),
    ("B003", _TA, "2026-02-14", "Credit - Williams Estate funds",                 "125000.00", "0.00",      "473500.00",  "L003",          ""),
    ("B004", _TA, "2026-03-01", "Credit - Anderson purchase deposit",             "80000.00",  "0.00",      "553500.00",  "L004",          ""),
    ("B005", _TA, "2026-03-05", "Credit - Patel purchase deposit",                "50000.00",  "0.00",      "603500.00",  "L005",          ""),
    ("B006", _TA, "2026-03-10", "Credit - Ngata sale proceeds",                   "490000.00", "0.00",      "1093500.00", "L006",          ""),
    ("B007", _TA, "2026-03-15", "Credit - Fitzgerald purchase deposit",           "95000.00",  "0.00",      "1188500.00", "L007",          ""),
    ("B008", _TA, "2026-03-20", "Credit - Tauranga Commercial deposit",           "200000.00", "0.00",      "1388500.00", "L008",          ""),
    # B009 matched_ledger_entry set to "L009" (changed from "" in original) to avoid spurious R04 flag
    ("B009", _TA, "2026-03-28", "Credit - Schmidt purchase deposit",              "120000.00", "0.00",      "1508500.00", "L009",          "ERR-1: corresponds to ledger L009 which is unreconciled (reconciled=N in ledger)"),
    ("B010", _TA, "2026-04-01", "Debit - Ngata vendor payment",                   "0.00",      "482500.00", "1026000.00", "L010",          ""),
    ("B011", _TA, "2026-04-05", "Debit - Williams Estate beneficiary payment",     "0.00",      "40000.00",  "986000.00",  "L011",          ""),
    ("B012", _TA, "2026-04-08", "Credit - Chen purchase deposit",                 "30000.00",  "0.00",      "1016000.00", "L012",          ""),
    ("B013", _TA, "2026-04-12", "Credit - Anderson settlement funds",             "645000.00", "0.00",      "1661000.00", "L013",          ""),
    ("B014", _TA, "2026-04-15", "Debit - Anderson settlement to vendor",          "0.00",      "725000.00", "936000.00",  "L014",          ""),
    ("B015", _TA, "2026-04-15", "Credit - Okonkwo purchase deposit",              "65000.00",  "0.00",      "1001000.00", "L015",          ""),
    ("B016", _TA, "2026-04-18", "Debit - Murphy Estate beneficiary P. Murphy",    "0.00",      "200000.00", "801000.00",  "L016",          ""),
    ("B017", _TA, "2026-04-20", "Debit - Murphy Estate final distribution",       "0.00",      "140000.00", "661000.00",  "L017",          ""),
    ("B018", _TA, "2026-04-21", "Credit - Patel settlement funds",                "405000.00", "0.00",      "1066000.00", "L018",          ""),
    ("B019", _TA, "2026-04-25", "Credit - Nkosi sale proceeds",                   "285000.00", "0.00",      "1351000.00", "L019",          ""),
    ("B020", _TA, "2026-04-28", "Debit - Patel settlement to vendor",             "0.00",      "455000.00", "896000.00",  "L020",          ""),
    ("B021", _TA, "2026-04-28", "Debit - Fitzgerald settlement to vendor",        "0.00",      "97500.00",  "798500.00",  "L021",          ""),
    # B022 matched_ledger_entry set to "BANK-INTEREST" (changed from "" in original) to avoid spurious R04 flag
    # The April reconciliation break (ERR-4) is still caught by R03 via RECON_ROWS (R002 difference=-250)
    ("B022", _TA, "2026-04-30", "Credit - Trust account interest (Apr 2026)",     "250.00",    "0.00",      "798750.00",  "BANK-INTEREST", "ERR-4: interest not allocated to any client matter; causes April recon discrepancy of $250"),
    ("B023", _TA, "2026-05-01", "Credit - Te Arawa commercial settlement",        "450000.00", "0.00",      "1248750.00", "L022",          ""),
    ("B024", _TA, "2026-05-02", "Debit - Tauranga lease deposit refund",          "0.00",      "195000.00", "1053750.00", "L023",          ""),
    ("B025", _TA, "2026-05-10", "Credit - Singh sale proceeds",                   "380000.00", "0.00",      "1433750.00", "L024",          ""),
    ("B026", _TA, "2026-05-10", "Credit - Blackwood purchase deposit",            "55000.00",  "0.00",      "1488750.00", "L025",          ""),
    ("B027", _TA, "2026-05-12", "Debit - Singh vendor payment",                   "0.00",      "375000.00", "1113750.00", "L026",          ""),
    ("B028", _TA, "2026-05-14", "Debit - Te Arawa vendor payment",                "0.00",      "448000.00", "665750.00",  "L027",          ""),
    ("B029", _TA, "2026-05-15", "Credit - Liu purchase deposit",                  "110000.00", "0.00",      "775750.00",  "L028",          ""),
    ("B030", _TA, "2026-05-20", "Credit - Garcia purchase deposit",               "25000.00",  "0.00",      "800750.00",  "L029",          ""),
    # ERR-5: orphan bank credit - matched_ledger_entry="" (B031, 34 days old as at 2026-06-25 > 5-day threshold)
    ("B031", _TA, "2026-05-22", "Credit - Unidentified receipt (source unknown)", "15000.00",  "0.00",      "815750.00",  "",              "ERR-5: no matching ledger entry; cannot be traced to any client matter"),
    ("B032", _TA, "2026-05-28", "Credit - Kowalski purchase deposit",             "40000.00",  "0.00",      "855750.00",  "L030",          ""),
    ("B033", _TA, "2026-06-01", "Credit - Yamamoto purchase deposit",             "70000.00",  "0.00",      "925750.00",  "L031",          ""),
    ("B034", _TA, "2026-06-02", "Credit - Robertson sale proceeds",               "620000.00", "0.00",      "1545750.00", "L032",          ""),
    ("B035", _TA, "2026-06-02", "Debit - Nkosi vendor payment",                   "0.00",      "280000.00", "1265750.00", "L033",          ""),
    ("B036", _TA, "2026-06-05", "Debit - Robertson settlement to vendor",         "0.00",      "615000.00", "650750.00",  "L034",          ""),
    ("B037", _TA, "2026-06-10", "Debit - Nkosi final payment",                    "0.00",      "5000.00",   "645750.00",  "L035",          ""),
    # Bank entries for new ledger rows L036-L038
    # B038: FIT interest credit (L036) — running 645750 + 125 = 645875
    ("B038", _TA, "2026-06-01", "Credit - Trust account interest (Jun 2026 FIT)", "125.00",    "0.00",      "645875.00",  "L036",          ""),
    # B039: Blackwood LINZ fee payment (L037) — running 645875 - 200 = 645675
    ("B039", _TA, "2026-05-28", "Debit - LINZ title search fee (Blackwood)",      "0.00",      "200.00",    "645675.00",  "L037",          ""),
    # B040: Liu conveyancing fee (L038) — running 645675 - 500 = 645175
    ("B040", _TA, "2026-05-28", "Debit - Conveyancing fee (Liu)",                 "0.00",      "500.00",    "645175.00",  "L038",          ""),
]


# ── Reconciliation summary ────────────────────────────────────────────────────

RECON_HEADERS = [
    "recon_id", "period_end_date",
    "ledger_total_nzd", "bank_balance_nzd", "difference_nzd",
    "prepared_by", "approved_by", "status", "notes",
]

RECON_ROWS = [
    # March 2026: AGREED
    ("R001", "2026-03-31", "1508500.00", "1508500.00", "0.00",
     "J. Anderson", "S. Mitchell", "AGREED", ""),
    # April 2026: ERR-4 - $250 discrepancy (trust interest B022 not allocated to any client matter ledger)
    ("R002", "2026-04-30", "798500.00",  "798750.00",  "-250.00",
     "J. Anderson", "S. Mitchell", "DISCREPANCY",
     "ERR-4: $250 difference - trust account interest (B022) not allocated to any client matter ledger"),
    # May 2026: not yet completed
    ("R003", "2026-05-31", "",           "",           "",
     "J. Anderson", "",            "IN PROGRESS",
     "ERR-5 (B031 $15,000 orphan credit) and ERR-1 (L009 unreconciled) both present in this period"),
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
        "matter_register":        _write_csv(output_dir / "matter_register.csv",       MATTER_HEADERS, MATTER_ROWS),
        "client_ledger":          _write_csv(output_dir / "client_ledger.csv",          LEDGER_HEADERS, LEDGER_ROWS),
        "trust_bank_statement":   _write_csv(output_dir / "trust_bank_statement.csv",   BANK_HEADERS,   BANK_ROWS),
        "reconciliation_summary": _write_csv(output_dir / "reconciliation_summary.csv", RECON_HEADERS,  RECON_ROWS),
    }

    print(f"\nTrust-domain synthetic data written to: {output_dir.resolve()}\n")
    for name, n in counts.items():
        print(f"  {name}.csv  -  {n} rows")

    print("""
Seeded errors (7 total):
  ERR-1  Unreconciled entry > 30 days    ledger L009 / matter M008 / 89 days old
  ERR-2  Overdrawn client matter         ledger L021 / matter M016 / balance -$2,500
  ERR-3  Dormant matter with balance     matter M017 / balance $8,500 / last activity 2024-12-15
  ERR-4  Reconciliation discrepancy      recon R002 / April 2026 / difference -$250
  ERR-5  Orphan bank entry               bank B031 / $15,000 / 2026-05-22 / 34 days old
  ERR-6  FIT balance overheld            matter M021 / $125.00 / 24 days old (deadline 14)
  ERR-7  Fee without invoice reference   ledger L037 / M012 / $200 / reference=""
""")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Generate enhanced synthetic NZ trust ledger data for trust_domain rules"
    )
    p.add_argument(
        "--output-dir",
        default="trust_domain/synthetic/sample",
        help="Directory to write CSV files into (default: trust_domain/synthetic/sample)",
    )
    args = p.parse_args()
    generate(Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
