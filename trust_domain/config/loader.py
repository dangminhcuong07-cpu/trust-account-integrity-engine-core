"""
Config loader for the integrity engine.

Reads a TOML client config file, validates all fields, resolves paths relative
to the config file's own directory (making configs portable), and returns a
ClientConfig instance with posix-normalised path strings.

Usage:
    from trust_domain.config import load_config, validate_config, ConfigError
    config = load_config(Path("clients/coastal_law.toml"))
    warnings = validate_config(config)
"""

from __future__ import annotations

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-reuse-without-import]

from pathlib import Path

from trust_domain.config.schema import ClientConfig, _ALL_RULE_IDS

_KNOWN_RULE_IDS: frozenset[str] = frozenset(_ALL_RULE_IDS)

_REQUIRED_FIELDS = {
    "client": ["firm_name", "reviewed_by", "engine_version", "review_period"],
    "paths":  ["input_dir", "output_dir"],
}

_THRESHOLD_FIELDS = [
    "dormancy_threshold_days",
    "unreconciled_age_days",
    "unmatched_bank_days",
    "fit_transfer_days",
]


class ConfigError(Exception):
    """Raised when a client config file is missing or has invalid fields."""


def load_config(path: Path) -> ClientConfig:
    """
    Read and validate a TOML client config file.

    Paths are resolved relative to the config file's directory so configs are
    portable across machines. All path strings are normalised to posix format
    (forward slashes) regardless of host OS.

    Raises ConfigError with the name of the offending field on any validation
    failure.
    """
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}")
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}")

    # --- Required fields ---
    for section, fields in _REQUIRED_FIELDS.items():
        if section not in raw:
            raise ConfigError(f"Missing section [{section}] in {path}")
        for field in fields:
            if field not in raw[section]:
                raise ConfigError(
                    f"Missing required field '{field}' in [{section}] section"
                )

    client = raw["client"]
    paths  = raw["paths"]
    thresholds = raw.get("thresholds", {})
    rules_section = raw.get("rules", {})
    column_map_raw = raw.get("column_map", {})

    # --- Thresholds: must be positive integers ---
    threshold_values: dict[str, int] = {}
    defaults = {
        "dormancy_threshold_days": 365,
        "unreconciled_age_days":   30,
        "unmatched_bank_days":     5,
        "fit_transfer_days":       14,
    }
    for key in _THRESHOLD_FIELDS:
        value = thresholds.get(key, defaults[key])
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(
                f"Threshold '{key}' must be a positive integer, got: {value!r}"
            )
        threshold_values[key] = value

    # --- enabled_rules: must all be known ---
    enabled_rules: list[str] = rules_section.get("enabled", list(_ALL_RULE_IDS))
    for rule_id in enabled_rules:
        if rule_id not in _KNOWN_RULE_IDS:
            raise ConfigError(
                f"Unknown rule ID '{rule_id}' in [rules] enabled list. "
                f"Known IDs: {sorted(_KNOWN_RULE_IDS)}"
            )

    # --- Resolve and normalise paths ---
    config_dir = path.parent.resolve()

    def _resolve(rel: str) -> str:
        return (config_dir / rel).resolve().as_posix()

    return ClientConfig(
        firm_name=client["firm_name"],
        reviewed_by=client["reviewed_by"],
        engine_version=client["engine_version"],
        review_period=client["review_period"],
        input_dir=_resolve(paths["input_dir"]),
        output_dir=_resolve(paths["output_dir"]),
        dormancy_threshold_days=threshold_values["dormancy_threshold_days"],
        unreconciled_age_days=threshold_values["unreconciled_age_days"],
        unmatched_bank_days=threshold_values["unmatched_bank_days"],
        fit_transfer_days=threshold_values["fit_transfer_days"],
        enabled_rules=enabled_rules,
        column_map=column_map_raw,
    )


def validate_config(config: ClientConfig) -> list[str]:
    """
    Return a list of non-fatal warning strings for the given config.

    Returns an empty list if the config has no warnings. Does not raise.
    """
    warnings: list[str] = []

    if config.dormancy_threshold_days < 180:
        warnings.append(
            f"dormancy_threshold_days={config.dormancy_threshold_days} is unusually "
            f"short - verify this is intentional (NZLS guideline default is 365 days)"
        )

    if config.unreconciled_age_days < 7:
        warnings.append(
            f"unreconciled_age_days={config.unreconciled_age_days} is unusually "
            f"short - verify this is intentional"
        )

    if config.fit_transfer_days < 5:
        warnings.append(
            f"fit_transfer_days={config.fit_transfer_days} is unusually "
            f"short - verify this is intentional"
        )

    return warnings
