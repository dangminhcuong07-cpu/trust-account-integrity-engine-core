"""
ClientConfig — per-client configuration schema for the integrity engine.

All configurable fields live here. The engine itself is constant; clients
differ only through their config file. Path fields are stored as posix strings
(forward slashes) after loading, regardless of the host OS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_ALL_RULE_IDS: list[str] = [
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
]


@dataclass
class ClientConfig:
    # Identity
    firm_name: str
    reviewed_by: str
    engine_version: str

    # Data paths — stored as posix strings (forward slashes) after loading
    input_dir: str
    output_dir: str

    # Rule thresholds — defaults match NZ trust-accounting practice
    dormancy_threshold_days: int = 365
    unreconciled_age_days: int = 30
    unmatched_bank_days: int = 5
    fit_transfer_days: int = 14
    bulk_min_nzd: float = 0.0

    # Rules to run — default: all seven
    enabled_rules: list = field(default_factory=lambda: list(_ALL_RULE_IDS))

    # Report identity
    review_period: str = ""

    # Column name mapping: {dataset_name: {internal_field_name: client_column_name}}
    # Empty dict (default) = no renaming; engine uses its own internal field names.
    column_map: dict = field(default_factory=dict)
