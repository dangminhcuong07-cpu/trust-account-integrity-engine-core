# trust_domain/rules — Rule Authoring Reference

Documentation only. Not imported by Python. Reference for developers adding or
reviewing trust-domain rules.

Everything below is derived from the seven existing rule files (r01–r07) and
their registry in `__init__.py`. Nothing is invented.

---

## 1. RULE FUNCTION SIGNATURE

There are two patterns. Choose based on whether the rule has a configurable
threshold.

### Pattern A — Direct function (no configurable threshold)

Used by: R01 (`overdrawn_ledger`), R03 (`recon_break`), R07 (`fee_without_invoice`)

```python
from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

def rule_name(record: Record) -> TrustRuleResult:
    ...
```

### Pattern B — Factory function (configurable threshold or reference date)

Used by: R02, R04, R05, R06

```python
from __future__ import annotations

import datetime
from integrity_engine.core.types import Record
from trust_domain.rules.types import TrustRuleResult

def make_x_rule(
    threshold_param: int = DEFAULT,
    reference_date: datetime.date | None = None,
) -> ...:   # returns a callable that satisfies RuleProtocol
    def _rule(record: Record) -> TrustRuleResult:
        ...
    return _rule
```

`reference_date` is always `None` in production (resolves to `date.today()` inside
`StalenessChecker`). Pass an explicit date only in tests for determinism.

### Every rule module also declares three module-level constants

```python
RULE_ID   = "R0N_RULE_NAME"           # matches the registry key exactly
NZLS_REF  = "LCA (Trust Account) ..."  # verbatim regulation citation
SEVERITY  = "CRITICAL"                 # or "HIGH"
```

These are referenced in `__init__.py` as `_rNN.NZLS_REF` and `_rNN.SEVERITY`.

### Module docstring structure (top of every rule file)

```python
"""
R0N_RULE_NAME

Brief plain-English description of what is flagged and under what conditions.
Threshold variables should be named here, not hardcoded.

Regulation: <verbatim NZLS_REF value>
Severity:   CRITICAL | HIGH
"""
```

---

## 2. RULERESULT REQUIRED FIELDS

`TrustRuleResult` extends `RuleResult` (defined in `trust_domain/rules/types.py`).
All six fields must be populated on every return, pass or fail.

| Field       | Type   | Example value                                            |
|-------------|--------|----------------------------------------------------------|
| `rule_id`   | `str`  | `"R01_OVERDRAWN_CLIENT_LEDGER"`                          |
| `passed`    | `bool` | `False`                                                  |
| `record_id` | `str`  | `record.record_id` (always use this — never hardcode)    |
| `evidence`  | `str`  | see Section 4                                            |
| `nzls_ref`  | `str`  | `NZLS_REF` module constant                               |
| `severity`  | `str`  | `SEVERITY` module constant                               |

`label` is a seventh field on `TrustRuleResult` but it defaults to `""` and is
populated by the report layer from `RULE_METADATA`, not by the rule itself.

Every branch — pass, fail, and skip (e.g. "not applicable") — must return a
fully-populated `TrustRuleResult`. Never return `None`.

---

## 3. REGISTRATION PATTERN

Three places in `trust_domain/rules/__init__.py` must be updated for every new rule.

### 3a. Import the module

```python
import trust_domain.rules.r0N_name as _r0N
```

Add this line with the other module imports at the top of `__init__.py`.

### 3b. Add an entry to `RULE_METADATA`

```python
"R0N_RULE_NAME": {
    "rule_id":  "R0N_RULE_NAME",
    "label":    "Human-readable single-line description",
    "nzls_ref": _r0N.NZLS_REF,
    "severity": _r0N.SEVERITY,
    "dataset":  "client_ledger",   # one of the four dataset names — see below
    "mode":     "evaluate_all",    # always "evaluate_all" in this domain
},
```

Valid `dataset` values (match the CSV names in `trust_domain/synthetic/sample/`):
- `"client_ledger"` — ledger entries (R01, R05, R07)
- `"matter_register"` — matter-level records (R02, R06)
- `"trust_bank_statement"` — bank statement lines (R04)
- `"reconciliation_summary"` — monthly reconciliation rows (R03)

### 3c. Add to `_TRUST_RULE_REGISTRY` and `load_trust_rules_from_config`

For a **direct function** rule:

```python
# In _TRUST_RULE_REGISTRY:
"R0N_RULE_NAME": _r0N.rule_function,

# In load_trust_rules_from_config:
# No extra branch needed — falls through to:
#   rules.append(_TRUST_RULE_REGISTRY[rid])
```

For a **factory function** rule with a configurable threshold (e.g. `my_days`):

```python
# In _TRUST_RULE_REGISTRY (use default args — this is the production default):
"R0N_RULE_NAME": _r0N.make_x_rule(),

# In load_trust_rules_from_config, add an elif before the else branch:
elif rid == "R0N_RULE_NAME":
    rules.append(_r0N.make_x_rule(
        my_days=spec.get("my_days", DEFAULT_VALUE)
    ))
```

---

## 4. EVIDENCE STRING CONVENTION

The evidence string must be readable by a non-technical trust account supervisor.
It answers: which record, what values triggered the flag, and what is wrong.

**Template (R07 — the clearest existing example):**

```python
evidence=(
    f"entry {record.record_id} (matter {matter}): "
    f"description={description!r}, payment=${float(payment):,.2f}, "
    f"reference={reference!r} - no INV-XXXXX invoice reference found (Reg 9 breach)"
)
```

**Rules derived from the existing seven:**

1. Open with the record ID and its parent identifier:
   `"entry {record_id} (matter {matter_ref})"` or `"bank line {record_id}"`

2. Include the date when the record is time-sensitive:
   `"dated {entry_date}"` or `"({transaction_date})"`

3. List the specific field values that caused the failure:
   - Currency: `${value:,.2f} NZD` (always two decimal places, always comma-thousands)
   - Strings: `{value!r}` (preserves quotes, makes empty string visible as `''`)
   - Day counts: `"open N days (threshold M)"` — both actual and threshold

4. End with a plain-English diagnosis, separated by ` - ` (space-hyphen-space):
   `"- client funds in deficit"` or `"- no INV-XXXXX invoice reference found (Reg 9 breach)"`

5. Never use em dashes (`—`). Use ` - ` (space-hyphen-space). PowerShell encoding
   on Windows corrupts em dashes to `â€"`.

**Pass evidence** is shorter but must still be non-empty:
```python
evidence=f"balance ${balance:,.2f} NZD"          # R01 pass
evidence="not a FIT matter - rule not applicable" # R06 skip
evidence=f"unreconciled but within {max_days}-day limit"  # R05 grace-period pass
```

---

## 5. TEST STRUCTURE

Every rule must have at minimum two tests in `tests/test_trust_rules.py`.
Both live inside a class named `TestR0NRuleName`.

### Mandatory test 1 — "catches seeded error"

Loads the full synthetic dataset and asserts the expected record ID appears in
the failure list.

```python
def test_catches_err2_from_synthetic_data(self):
    records = _load("client_ledger")
    results = [_r01.overdrawn_ledger(r) for r in records]
    failures = [res for res in results if not res.passed]
    assert any(res.record_id == "L021" for res in failures), \
        "ERR-2 (L021) not caught by R01_OVERDRAWN_CLIENT_LEDGER"
```

### Mandatory test 2 — "clean data passes without flagging"

Asserts the full synthetic dataset produces exactly one violation (the seeded
error), proving the rule does not false-positive on clean records.

```python
def test_only_one_violation_in_synthetic_data(self):
    records = _load("client_ledger")
    failures = [res for res in [_r01.overdrawn_ledger(r) for r in records]
                if not res.passed]
    assert len(failures) == 1, \
        f"Expected 1 violation, got: {[f.record_id for f in failures]}"
```

### Loading synthetic data in tests

```python
SAMPLE_DIR = Path("trust_domain/synthetic/sample")

@pytest.fixture(scope="session", autouse=True)
def trust_sample_data():
    from trust_domain.synthetic.generator import generate
    generate(SAMPLE_DIR)

def _load(name: str) -> list[Record]:
    from data.load_sample import load_file
    return load_file(name, SAMPLE_DIR)
```

This fixture is already defined at the top of `test_trust_rules.py`. Do not
add a second one.

### For factory-based rules, pass `reference_date=REF_DATE` in tests

```python
REF_DATE = datetime.date(2026, 6, 25)

rule = _r02.make_dormant_rule(reference_date=REF_DATE)
```

Never call a factory rule without `reference_date` in tests — the result would
depend on the wall clock and become non-deterministic.

---

## 6. SEVERITY LEVELS AND THEIR MEANING

### CRITICAL

Assign when the rule catches a condition that is an immediate regulatory breach
with no grace period and no operational workaround. The report layer maps
CRITICAL → "ESCALATE" and places these violations in the first section of the
exception report.

**Existing CRITICAL rules:**
- R01 — overdrawn client ledger (LCA Reg 12(6)(a)): a negative running balance
  means client funds are in deficit right now. There is no threshold or grace period.
- R03 — reconciliation break (LCA Reg 12(1)): a completed monthly reconciliation
  where ledger ≠ bank balance. Once the period is closed, the discrepancy is fact.

### HIGH

Assign when the rule catches a condition that requires investigation but has a
configurable grace period or threshold before it becomes a formal breach. The
report layer maps HIGH → "REVIEW".

**Existing HIGH rules:**
- R02 — dormant balance: only stale after `max_inactive_days` (default 365)
- R04 — unmatched bank line: only stale after `max_age_days` (default 5)
- R05 — unreconciled ageing: only stale after `max_days` (default 30)
- R06 — FIT overheld: only a breach after `max_days` transfer deadline (default 14)
- R07 — fee without invoice: any disbursement payment without an `INV-XXXXX`
  reference. No grace period, but domain severity is HIGH not CRITICAL because
  it may indicate a process gap rather than an immediate client-funds risk.

---

## 7. ADDING A NEW RULE — CHECKLIST

Follow this order exactly. Do not skip steps.

1. **Create `trust_domain/rules/rNN_name.py`**
   - Write the module docstring (rule ID, description, regulation, severity)
   - Declare `RULE_ID`, `NZLS_REF`, `SEVERITY` constants
   - Implement the rule function (Pattern A or B from Section 1)
   - Every return path must produce a fully-populated `TrustRuleResult`
   - Use ` - ` not `—` in evidence strings

2. **Implement the rule function following the signature in Section 1**
   - If thresholds are configurable, use a factory function
   - Always include `reference_date: datetime.date | None = None` in factories
   - Guard against missing fields with `.get("field", default)` — never assume keys exist

3. **Register in `trust_domain/rules/__init__.py` with full metadata**
   - Add `import trust_domain.rules.rNN_name as _rNN`
   - Add entry to `RULE_METADATA` (rule_id, label, nzls_ref, severity, dataset, mode)
   - Add entry to `_TRUST_RULE_REGISTRY`
   - For factory rules: add `elif` branch in `load_trust_rules_from_config`

4. **Seed the error in `trust_domain/synthetic/generator.py`**
   - Add a row that the new rule should catch (ERR-N)
   - Add a corresponding clean row that the new rule should pass (to make the
     "only one violation" test meaningful)
   - Update the integration test's `expected` set in `TestIntegration`

5. **Write two tests in `tests/test_trust_rules.py`**
   - Add a new `TestR0NRuleName` class
   - Mandatory test 1: `test_catches_errN_from_synthetic_data`
   - Mandatory test 2: `test_only_one_violation_in_synthetic_data`
   - For factory rules, always pass `reference_date=REF_DATE`
   - Update `_collect_all_violations()` to include the new rule
   - Update `test_exactly_7_violations_total` → change the expected count from N to N+1, and add the new `(rule_id, record_id)` tuple to the `expected` set in `test_violation_record_ids_match_expected_errors`

6. **Run `pytest tests/test_trust_rules.py -q` and confirm both new tests pass**

7. **Run full suite `pytest -q` and confirm no regressions**
   - Expected baseline before this step: 185 passed, 1 skipped
   - After adding a rule with 2+ tests: count should increase by at least 2
