"""Safely restore actual_w52..actual_w1 from a diversification backup."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.retail_data_bootstrap.database import open_connection

from regenerate_demand_104w_history import (
    ACTUAL_COLUMNS,
    FULL_TABLE_NAME,
    _backup_manifest_path,
    _compare_committed_rows,
    _load_csv_rows,
    _read_backup_manifest,
    _read_table_rows,
    _update_batches,
    fingerprint,
    validate_population,
    validate_schema,
)


class RollbackError(RuntimeError):
    """Raised when the rollback guard cannot prove the target is safe."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RollbackError(message)


def rollback(backup_path: Path, apply: bool) -> dict[str, Any]:
    manifest = _read_backup_manifest(backup_path)
    backup_rows = _load_csv_rows(backup_path)
    validate_population(backup_rows)
    source_fingerprint = manifest["source_full_fingerprint"]
    committed_fingerprint = manifest.get("committed_full_fingerprint")
    _require(
        fingerprint(backup_rows) == source_fingerprint,
        "Backup rows do not match their recorded source fingerprint",
    )
    _require(
        committed_fingerprint,
        "Backup manifest has no committed candidate fingerprint; refusing rollback",
    )

    connection = open_connection()
    try:
        cursor = connection.cursor()
        validate_schema(cursor)
        current_rows = _read_table_rows(cursor)
        current_fingerprint = fingerprint(current_rows)
        _require(
            current_fingerprint == committed_fingerprint,
            "Live table is not the committed diversification candidate; refusing rollback",
        )
        _require(
            fingerprint(current_rows, (*["sku_id", "store_id", "cat"], *[f"forecast_w{week}" for week in range(1, 53)]))
            == fingerprint(backup_rows, (*["sku_id", "store_id", "cat"], *[f"forecast_w{week}" for week in range(1, 53)])),
            "Forecast or identity values drifted; refusing rollback",
        )
        if not apply:
            return {
                "mode": "dry-run",
                "table": FULL_TABLE_NAME,
                "rows_to_restore": len(backup_rows),
                "columns": list(ACTUAL_COLUMNS),
                "current_fingerprint": current_fingerprint,
                "source_fingerprint": source_fingerprint,
                "manifest": str(_backup_manifest_path(backup_path)),
            }
        rows_submitted = _update_batches(cursor, backup_rows)
        in_transaction = _read_table_rows(cursor)
        _require(
            fingerprint(in_transaction) == source_fingerprint,
            "Rollback values did not match backup inside transaction",
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    readback_connection = open_connection()
    try:
        readback_cursor = readback_connection.cursor()
        validate_schema(readback_cursor)
        readback_rows = _read_table_rows(readback_cursor)
        _require(
            fingerprint(readback_rows) == source_fingerprint,
            "Rollback read-back fingerprint differs from backup",
        )
    finally:
        readback_connection.close()
    return {
        "mode": "apply",
        "table": FULL_TABLE_NAME,
        "rows_restored": rows_submitted,
        "columns": list(ACTUAL_COLUMNS),
        "restored_fingerprint": source_fingerprint,
        "manifest": str(_backup_manifest_path(backup_path)),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = rollback(args.backup, args.apply)
    except Exception as exc:
        print(f"ROLLBACK FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
