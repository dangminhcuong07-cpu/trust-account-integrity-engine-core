"""
integrity_engine — domain-agnostic data-integrity checking framework.

Submodules
----------
core          Shared base types (Record, RuleResult, Flag, AuditEntry).
rules         Rule-evaluation loop and gate-enforcer pattern.
audit_trail   DB-to-file audit trail writer (create vs sync semantics).
consistency   Cross-path consistency checker.
flagging      Staleness and invalidity flagging.
stats         Exception-rate statistics and bin analysis.
"""

__version__ = "0.1.0"
