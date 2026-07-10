"""
setup.py -- one-command setup for the Trust Account Integrity Engine.

Usage: python setup.py --config trust_domain/config/coastal_law.toml
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set up the Trust Account Integrity Engine for a client."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to a .toml client config file.",
    )
    args = parser.parse_args()

    # 1. Check Python version
    if sys.version_info < (3, 11):
        print(
            f"ERROR: Python 3.11 or later is required. "
            f"You have {sys.version_info.major}.{sys.version_info.minor}."
        )
        sys.exit(1)

    print(f"Python {sys.version_info.major}.{sys.version_info.minor} -- OK")

    # 2. Install dependencies
    packages = ["reportlab", "openpyxl"]
    if sys.version_info < (3, 11):
        packages.append("tomli")

    print(f"Installing: {', '.join(packages)} ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + packages,
    )
    if result.returncode != 0:
        print("ERROR: Dependency installation failed (see pip output above).")
        sys.exit(1)

    # 3. Load config and verify input files
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-reuse-without-import]
        except ImportError:
            print(
                "ERROR: tomllib not available and tomli is not installed. "
                "Run: pip install tomli"
            )
            sys.exit(1)

    config_path = Path(args.config)
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    except tomllib.TOMLDecodeError as exc:
        print(f"ERROR: Invalid TOML in {config_path}: {exc}")
        sys.exit(1)

    config_dir = config_path.parent.resolve()

    try:
        input_rel = raw["paths"]["input_dir"]
        output_rel = raw["paths"]["output_dir"]
    except KeyError as exc:
        print(f"ERROR: Missing field in config [paths]: {exc}")
        sys.exit(1)

    input_dir = (config_dir / input_rel).resolve()
    output_dir = (config_dir / output_rel).resolve()

    dataset_names = [
        "matter_register",
        "client_ledger",
        "trust_bank_statement",
        "reconciliation_summary",
    ]
    missing = []
    for name in dataset_names:
        csv_p  = input_dir / f"{name}.csv"
        xlsx_p = input_dir / f"{name}.xlsx"
        if not csv_p.exists() and not xlsx_p.exists():
            missing.append(name)

    if missing:
        print(f"ERROR: The following input datasets are missing from {input_dir}:")
        for name in missing:
            print(f"  {name}.csv  OR  {name}.xlsx  (neither found)")
        sys.exit(1)

    found = len(dataset_names) - len(missing)
    print(f"Input files verified ({found} datasets found in {input_dir})")

    # 4. Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory ready: {output_dir}")

    # 5. Summary
    print(f"\nSetup complete. Run: python run.py --config {args.config}")


if __name__ == "__main__":
    main()
