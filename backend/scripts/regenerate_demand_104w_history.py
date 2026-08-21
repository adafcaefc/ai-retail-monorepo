"""Diversify only the historical side of synthetic.demand_store_sku_104w.

The script is intentionally independent of the Demand Forecasting runtime.
It reads the complete 104W table, writes a reversible full-row CSV snapshot,
generates deterministic SKU x Store histories, validates every hard gate in
memory, and only then (with ``--apply``) updates the 52 ``actual_*`` columns in
one transaction.  Forecasts, identifiers, categories, the 32W table, and all
retail tables are outside the write statement.

Examples::

    # Dry-run, including the backup and all in-memory validation gates.
    .venv/bin/python backend/scripts/regenerate_demand_104w_history.py \
        --dry-run \
        --backup artifacts/demand_store_sku_104w_history_backup_20260821.csv

    # Re-check the same live fingerprint, then update only actual_w52..actual_w1.
    .venv/bin/python backend/scripts/regenerate_demand_104w_history.py \
        --apply \
        --backup artifacts/demand_store_sku_104w_history_backup_20260821.csv

Rollback is provided by ``rollback_demand_104w_history.py``.  It defaults to a
dry-run and requires ``--apply`` before issuing its own actual-only UPDATE.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.retail_data_bootstrap.database import open_connection


TABLE_SCHEMA = "synthetic"
TABLE_NAME = "demand_store_sku_104w"
FULL_TABLE_NAME = f"{TABLE_SCHEMA}.{TABLE_NAME}"
OLD_TABLE_NAME = "demand_store_sku_32w"
OLD_FULL_TABLE_NAME = f"{TABLE_SCHEMA}.{OLD_TABLE_NAME}"
REPORT_PATH = REPO_ROOT / "plans" / "demand-104w-history-diversification-report.md"
UPDATE_BATCH_SIZE = 500
QUANTITY_QUANTUM = Decimal("0.000001")
DECIMAL_TOLERANCE = Decimal("0.000001")
W1_MIN_RATIO = Decimal("0.98")
W1_MAX_RATIO = Decimal("1.02")
SEED_VERSION = "demand-104w-history-diversification-v1"
GENERATOR_VERSION = "demand-104w-history-diversification-v1.0.0"

ACTUAL_COLUMNS = tuple(f"actual_w{week}" for week in range(52, 0, -1))
FORECAST_COLUMNS = tuple(f"forecast_w{week}" for week in range(1, 53))
IDENTIFIER_COLUMNS = ("sku_id", "store_id", "cat")
ALL_COLUMNS = (*IDENTIFIER_COLUMNS, *ACTUAL_COLUMNS, *FORECAST_COLUMNS)

EXPECTED_ROW_COUNT = 16_000
EXPECTED_SKU_COUNT = 800
EXPECTED_STORE_COUNT = 160
EXPECTED_ROWS_PER_STORE = 100

SHAPE_NAMES = (
    "strong upward trend",
    "strong downward trend",
    "U-shaped recovery",
    "inverted-U peak",
    "strong seasonal oscillation",
    "double peak",
    "early spike then decline",
    "late acceleration",
    "mostly flat with periodic peaks",
    "cyclical rise/fall",
)


class HistoryGenerationError(RuntimeError):
    """Raised when a backup, generation, or validation gate fails."""


@dataclass(frozen=True)
class DemandRow:
    """One complete SQL row, with actuals oldest-to-newest in ``actuals``."""

    sku_id: str
    store_id: str
    cat: str
    actuals: tuple[Decimal, ...]
    forecasts: tuple[Decimal, ...]

    @property
    def key(self) -> tuple[str, str]:
        return self.sku_id, self.store_id

    def actual(self, week: int) -> Decimal:
        if not 1 <= week <= 52:
            raise ValueError(f"actual week must be 1..52, got {week}")
        return self.actuals[52 - week]

    def forecast(self, week: int) -> Decimal:
        if not 1 <= week <= 52:
            raise ValueError(f"forecast week must be 1..52, got {week}")
        return self.forecasts[week - 1]

    def with_actuals(self, actuals: Sequence[Decimal]) -> "DemandRow":
        return DemandRow(
            sku_id=self.sku_id,
            store_id=self.store_id,
            cat=self.cat,
            actuals=tuple(actuals),
            forecasts=self.forecasts,
        )


@dataclass(frozen=True)
class StoreProfile:
    store_id: str
    shape: str
    slope: float
    amplitude: float
    phase13: float
    phase26: float
    phase52: float
    center1: float
    center2: float
    width1: float
    width2: float

    def signal(self, week: int) -> float:
        """Return a smooth log-scale Store curve signal for a historical week."""

        t = 52 - week  # W-52 = 0, W-1 = 51; chronological direction.
        x = t / 51.0
        boundary_x = 48.0 / 51.0  # W-4 is the fixed boundary.
        two_pi = 2.0 * math.pi

        if self.shape == "strong upward trend":
            return self.slope * (x - boundary_x)
        if self.shape == "strong downward trend":
            return -self.slope * (x - boundary_x)
        if self.shape == "U-shaped recovery":
            center = 0.48
            return self.slope * ((x - center) ** 2 - (boundary_x - center) ** 2)
        if self.shape == "inverted-U peak":
            center = 0.52
            return -self.slope * (
                (x - center) ** 2 - (boundary_x - center) ** 2
            )
        if self.shape == "strong seasonal oscillation":
            seasonal_amplitude = 0.38 * self.amplitude
            return (
                seasonal_amplitude * math.sin(two_pi * t / 13.0 + self.phase13)
                + 0.58 * seasonal_amplitude * math.sin(two_pi * t / 26.0 + self.phase26)
                + 0.30 * seasonal_amplitude * math.sin(two_pi * t / 52.0 + self.phase52)
                + 0.16 * self.slope * (x - boundary_x)
            )
        if self.shape == "double peak":
            first = math.exp(-0.5 * ((x - self.center1) / self.width1) ** 2)
            second = math.exp(-0.5 * ((x - self.center2) / self.width2) ** 2)
            return (
                self.amplitude * first
                + 0.76 * self.amplitude * second
                + 0.18 * self.slope * (x - boundary_x)
            )
        if self.shape == "early spike then decline":
            spike = math.exp(-0.5 * ((x - self.center1) / self.width1) ** 2)
            return self.amplitude * spike - self.slope * x
        if self.shape == "late acceleration":
            return self.slope * (x * x - boundary_x * boundary_x) + 0.12 * (
                x - boundary_x
            )
        if self.shape == "mostly flat with periodic peaks":
            return (
                0.34 * self.amplitude * math.sin(two_pi * t / 13.0 + self.phase13)
                + 0.18 * self.amplitude * math.sin(two_pi * t / 26.0 + self.phase26)
                + 0.12 * self.slope * (x - boundary_x)
            )
        if self.shape == "cyclical rise/fall":
            cycle_amplitude = 0.70 * self.amplitude
            return (
                cycle_amplitude * math.sin(two_pi * t / 26.0 + self.phase26)
                + 0.55 * cycle_amplitude * math.sin(two_pi * t / 52.0 + self.phase52)
                + 0.12 * self.slope * (x - boundary_x)
            )
        raise HistoryGenerationError(f"Unknown Store shape: {self.shape}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HistoryGenerationError(message)


def quantity(value: Any) -> Decimal:
    try:
        result = Decimal(str(value)).quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise HistoryGenerationError(f"Invalid numeric quantity: {value!r}") from exc
    _require(result.is_finite() and result >= 0, f"Invalid quantity: {value!r}")
    return result


def quantity_text(value: Any) -> str:
    return format(quantity(value), "f")


def _stable_uint(*parts: object) -> int:
    payload = "|".join((SEED_VERSION, *(str(part) for part in parts))).encode(
        "utf-8"
    )
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _stable_unit(*parts: object) -> float:
    return _stable_uint(*parts) / float((1 << 64) - 1)


def _stable_signed(*parts: object) -> float:
    return 2.0 * _stable_unit(*parts) - 1.0


def _stable_phase(*parts: object) -> float:
    return 2.0 * math.pi * _stable_unit(*parts)


def profile_for_store(store_id: str) -> StoreProfile:
    shape = SHAPE_NAMES[_stable_uint(store_id, "shape") % len(SHAPE_NAMES)]
    slope = 1.05 + 0.55 * _stable_unit(store_id, "slope")
    amplitude = 0.38 + 0.18 * _stable_unit(store_id, "amplitude")
    return StoreProfile(
        store_id=store_id,
        shape=shape,
        slope=slope,
        amplitude=amplitude,
        phase13=_stable_phase(store_id, "phase", 13),
        phase26=_stable_phase(store_id, "phase", 26),
        phase52=_stable_phase(store_id, "phase", 52),
        center1=0.16 + 0.08 * _stable_unit(store_id, "center1"),
        center2=0.65 + 0.14 * _stable_unit(store_id, "center2"),
        width1=0.105 + 0.035 * _stable_unit(store_id, "width1"),
        width2=0.12 + 0.045 * _stable_unit(store_id, "width2"),
    )


def _sku_signal(sku_id: str, week: int) -> float:
    """Small stable SKU variation; Store signal amplitudes remain dominant."""

    t = 52 - week
    x = t / 51.0
    boundary_x = 48.0 / 51.0
    amplitude = 0.035 + 0.055 * _stable_unit(sku_id, "sku-amplitude")
    phase26 = _stable_phase(sku_id, "sku-phase", 26)
    phase13 = _stable_phase(sku_id, "sku-phase", 13)
    drift = 0.025 * _stable_signed(sku_id, "sku-drift")
    return (
        amplitude * math.sin(2.0 * math.pi * t / 26.0 + phase26)
        + 0.45 * amplitude * math.sin(2.0 * math.pi * t / 13.0 + phase13)
        + drift * (x - boundary_x)
    )


def _history_multiplier(
    profile: StoreProfile,
    sku_id: str,
    week: int,
    boundary_week: int = 4,
) -> float:
    log_multiplier = (
        profile.signal(week)
        + _sku_signal(sku_id, week)
        - profile.signal(boundary_week)
        - _sku_signal(sku_id, boundary_week)
    )
    multiplier = math.exp(log_multiplier)
    _require(math.isfinite(multiplier) and multiplier > 0, "Non-finite history multiplier")
    return multiplier


def _four_week_values(row: DemandRow) -> dict[int, Decimal]:
    """Choose W-1 near Forecast W+1, then close the old four-week total."""

    old_total = sum((row.actual(week) for week in (4, 3, 2, 1)), Decimal("0"))
    new_w1 = quantity(row.forecast(1))
    remaining = old_total - new_w1
    _require(
        remaining >= 0,
        f"{row.key}: old 4W total cannot support forecast_w1={new_w1}",
    )

    # Three nearby shares of the residual keep W-4..W-2 smooth while retaining
    # deterministic SKU x Store micro-variation.  W-4 is the exact residual
    # after quantization, so the original four-week total reconciles exactly.
    w4_share = 0.3333333333333333 + 0.005 * _stable_signed(
        row.sku_id, row.store_id, "w4-share"
    )
    w3_share = 0.3333333333333333 + 0.005 * _stable_signed(
        row.sku_id, row.store_id, "w3-share"
    )
    w2_share = 1.0 - w4_share - w3_share
    _require(0.28 <= w2_share <= 0.40, "Four-week share escaped safety bounds")
    w4 = quantity(remaining * Decimal(str(w4_share)))
    w3 = quantity(remaining * Decimal(str(w3_share)))
    w2 = quantity(remaining - w4 - w3)
    _require(w2 >= 0 and w3 >= 0 and w4 >= 0, f"{row.key}: negative recent history")
    _require(
        w4 + w3 + w2 + new_w1 == old_total,
        f"{row.key}: four-week sum did not reconcile after quantization",
    )
    return {1: new_w1, 2: w2, 3: w3, 4: w4}


def generate_candidate(
    rows: Sequence[DemandRow],
) -> tuple[list[DemandRow], dict[str, StoreProfile]]:
    """Generate W-52..W-5 from each row's newly generated W-4 boundary."""

    profiles = {store_id: profile_for_store(store_id) for store_id in {row.store_id for row in rows}}
    candidate: list[DemandRow] = []
    for row in rows:
        recent = _four_week_values(row)
        by_week = dict(recent)
        profile = profiles[row.store_id]
        boundary = recent[4]
        # Walk backward from W-4.  The multiplier is anchored at exactly 1.0
        # for W-4, so W-5 joins the newly generated recent block smoothly.
        for week in range(5, 53):
            by_week[week] = quantity(
                boundary
                * Decimal(str(_history_multiplier(profile, row.sku_id, week)))
            )
        actuals = tuple(by_week[week] for week in range(52, 0, -1))
        candidate.append(row.with_actuals(actuals))
    return candidate, profiles


def _value_for_column(row: DemandRow, column: str) -> str:
    if column in IDENTIFIER_COLUMNS:
        return {"sku_id": row.sku_id, "store_id": row.store_id, "cat": row.cat}[column]
    if column.startswith("actual_w"):
        return quantity_text(row.actual(int(column.removeprefix("actual_w"))))
    if column.startswith("forecast_w"):
        return quantity_text(row.forecast(int(column.removeprefix("forecast_w"))))
    raise HistoryGenerationError(f"Unknown table column: {column}")


def fingerprint(rows: Sequence[DemandRow], columns: Sequence[str] = ALL_COLUMNS) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item.key):
        digest.update(",".join(_value_for_column(row, column) for column in columns).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _backup_manifest_path(path: Path) -> Path:
    return path.with_suffix(".manifest.json")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(f"{path}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _write_backup(rows: Sequence[DemandRow], path: Path) -> dict[str, Any]:
    manifest_path = _backup_manifest_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(f"{path}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(ALL_COLUMNS)
        for row in sorted(rows, key=lambda item: item.key):
            writer.writerow([_value_for_column(row, column) for column in ALL_COLUMNS])
    os.replace(temporary, path)
    metadata: dict[str, Any] = {
        "table": FULL_TABLE_NAME,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "seed_version": SEED_VERSION,
        "row_count": len(rows),
        "columns": list(ALL_COLUMNS),
        "update_columns": list(ACTUAL_COLUMNS),
        "source_full_fingerprint": fingerprint(rows),
        "source_history_fingerprint": fingerprint(
            rows, (*IDENTIFIER_COLUMNS, *ACTUAL_COLUMNS)
        ),
        "source_forecast_fingerprint": fingerprint(
            rows, (*IDENTIFIER_COLUMNS, *FORECAST_COLUMNS)
        ),
        "backup_csv": str(path),
        "backup_csv_sha256": _file_sha256(path),
    }
    _atomic_write(manifest_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return metadata


def _read_backup_manifest(path: Path) -> dict[str, Any]:
    manifest_path = _backup_manifest_path(path)
    _require(path.is_file(), f"Backup CSV does not exist: {path}")
    _require(manifest_path.is_file(), f"Backup manifest does not exist: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryGenerationError(f"Invalid backup manifest: {manifest_path}") from exc
    _require(manifest.get("table") == FULL_TABLE_NAME, "Backup belongs to another table")
    _require(manifest.get("columns") == list(ALL_COLUMNS), "Backup columns differ")
    _require(manifest.get("update_columns") == list(ACTUAL_COLUMNS), "Backup update scope differs")
    _require(
        manifest.get("backup_csv_sha256") == _file_sha256(path),
        "Backup CSV checksum differs from its manifest",
    )
    return manifest


def _load_csv_rows(path: Path) -> list[DemandRow]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            _require(tuple(reader.fieldnames or ()) == ALL_COLUMNS, "Backup CSV header differs")
            rows: list[DemandRow] = []
            for raw in reader:
                rows.append(
                    DemandRow(
                        sku_id=str(raw["sku_id"]),
                        store_id=str(raw["store_id"]),
                        cat=str(raw["cat"]),
                        actuals=tuple(quantity(raw[column]) for column in ACTUAL_COLUMNS),
                        forecasts=tuple(quantity(raw[column]) for column in FORECAST_COLUMNS),
                    )
                )
    except OSError as exc:
        raise HistoryGenerationError(f"Unable to read backup CSV: {path}") from exc
    rows.sort(key=lambda row: row.key)
    return rows


def prepare_backup(rows: Sequence[DemandRow], path: Path) -> dict[str, Any]:
    """Create a backup or safely reuse one matching the current fingerprint."""

    manifest_path = _backup_manifest_path(path)
    if path.exists() or manifest_path.exists():
        manifest = _read_backup_manifest(path)
        backup_rows = _load_csv_rows(path)
        _require(
            len(backup_rows) == len(rows)
            and fingerprint(backup_rows) == fingerprint(rows),
            "Existing backup does not exactly match the current live table",
        )
        return manifest
    return _write_backup(rows, path)


def update_backup_manifest(path: Path, updates: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _read_backup_manifest(path)
    manifest.update(updates)
    _atomic_write(
        _backup_manifest_path(path), json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _read_table_rows(cursor: Any) -> list[DemandRow]:
    selected = ", ".join(f"[{column}]" for column in ALL_COLUMNS)
    cursor.execute(
        f"SELECT {selected} FROM [{TABLE_SCHEMA}].[{TABLE_NAME}] "
        "ORDER BY [sku_id], [store_id];"
    )
    descriptions = tuple(description[0] for description in cursor.description)
    _require(descriptions == ALL_COLUMNS, "Live table column order differs from contract")
    rows: list[DemandRow] = []
    for raw in cursor.fetchall():
        rows.append(
            DemandRow(
                sku_id=str(raw[0]),
                store_id=str(raw[1]),
                cat=str(raw[2]),
                actuals=tuple(quantity(value) for value in raw[3:55]),
                forecasts=tuple(quantity(value) for value in raw[55:107]),
            )
        )
    return rows


def _read_store_verticals(cursor: Any) -> dict[str, str]:
    cursor.execute(
        "SELECT [store_id], [vertical_id] FROM [retail].[dim_store] "
        "ORDER BY [store_id];"
    )
    return {str(store_id): str(vertical_id) for store_id, vertical_id in cursor.fetchall()}


def validate_schema(cursor: Any) -> None:
    cursor.execute(
        """
        SELECT c.name, ty.name AS type_name, c.max_length, c.precision,
               c.scale, c.is_nullable, c.column_id
        FROM sys.columns AS c
        JOIN sys.tables AS t ON t.object_id = c.object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
        WHERE s.name = ? AND t.name = ?
        ORDER BY c.column_id;
        """,
        (TABLE_SCHEMA, TABLE_NAME),
    )
    definitions = cursor.fetchall()
    _require(
        tuple(row[0] for row in definitions) == ALL_COLUMNS,
        "104W table columns differ from the expected 107-column contract",
    )
    for index, row in enumerate(definitions):
        name, type_name, max_length, precision, scale, nullable, _column_id = row
        if index == 0:
            expected_type, expected_length = "nvarchar", 60
        elif index == 1:
            expected_type, expected_length = "nvarchar", 40
        elif index == 2:
            expected_type, expected_length = "nvarchar", 60
        else:
            expected_type, expected_length = "decimal", None
        _require(str(type_name).lower() == expected_type, f"Type drift for {name}")
        if expected_length is not None:
            _require(int(max_length or 0) == expected_length, f"Length drift for {name}")
        else:
            _require(
                int(precision or 0) == 20 and int(scale or 0) == 6,
                f"Precision drift for {name}",
            )
        _require(not bool(nullable), f"Nullable drift for {name}")
    cursor.execute(
        """
        SELECT c.name
        FROM sys.indexes AS i
        JOIN sys.index_columns AS ic
          ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns AS c
          ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.object_id = OBJECT_ID(?) AND i.is_primary_key = 1
        ORDER BY ic.key_ordinal;
        """,
        (FULL_TABLE_NAME,),
    )
    _require(
        tuple(row[0] for row in cursor.fetchall()) == ("sku_id", "store_id"),
        "104W primary key differs from (sku_id, store_id)",
    )


def validate_population(rows: Sequence[DemandRow]) -> dict[str, Any]:
    stores = Counter(row.store_id for row in rows)
    _require(len(rows) == EXPECTED_ROW_COUNT, f"Expected {EXPECTED_ROW_COUNT} rows")
    _require(len({row.sku_id for row in rows}) == EXPECTED_SKU_COUNT, "SKU count drift")
    _require(len(stores) == EXPECTED_STORE_COUNT, "Store count drift")
    _require(len({row.key for row in rows}) == EXPECTED_ROW_COUNT, "Duplicate SKU x Store key")
    _require(set(stores.values()) == {EXPECTED_ROWS_PER_STORE}, "Rows per Store drift")
    _require(all(row.cat.strip() for row in rows), "Blank category found")
    return {
        "rows": len(rows),
        "skus": len({row.sku_id for row in rows}),
        "stores": len(stores),
        "unique_keys": len({row.key for row in rows}),
        "rows_per_store": EXPECTED_ROWS_PER_STORE,
    }


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _ratio_change(previous: Decimal, current: Decimal) -> float:
    if previous == 0:
        return 0.0 if current == 0 else math.inf
    return abs(float(current / previous - Decimal("1")))


def adjacent_change_stats(rows: Sequence[DemandRow]) -> dict[str, Any]:
    changes: list[float] = []
    for row in rows:
        for older_week, newer_week in zip(range(52, 1, -1), range(51, 0, -1)):
            changes.append(_ratio_change(row.actual(older_week), row.actual(newer_week)))
    return {
        "count": len(changes),
        "max": max(changes),
        "p99": _percentile(changes, 0.99),
        "p95": _percentile(changes, 0.95),
        "median": _percentile(changes, 0.50),
        "over_20_pct": sum(change > 0.20 for change in changes),
        "over_20_pct_allowed": 0,
    }


def _pearson(first: Sequence[float], second: Sequence[float]) -> float:
    first_mean = statistics.fmean(first)
    second_mean = statistics.fmean(second)
    first_delta = [value - first_mean for value in first]
    second_delta = [value - second_mean for value in second]
    denominator = math.sqrt(
        sum(value * value for value in first_delta)
        * sum(value * value for value in second_delta)
    )
    if denominator == 0:
        return 1.0 if first == second else 0.0
    return sum(a * b for a, b in zip(first_delta, second_delta)) / denominator


def _store_curves(rows: Sequence[DemandRow]) -> dict[str, list[float]]:
    totals: dict[str, dict[int, Decimal]] = defaultdict(
        lambda: {week: Decimal("0") for week in range(52, 0, -1)}
    )
    for row in rows:
        for week in range(52, 0, -1):
            totals[row.store_id][week] += row.actual(week)
    return {
        store_id: [float(totals[store_id][week]) for week in range(52, 0, -1)]
        for store_id in sorted(totals)
    }


def _normalised_curve(values: Sequence[float]) -> list[float]:
    mean = statistics.fmean(values)
    return [value / mean if mean else 0.0 for value in values]


def diversity_stats(
    old_rows: Sequence[DemandRow],
    new_rows: Sequence[DemandRow],
    profiles: Mapping[str, StoreProfile],
) -> dict[str, Any]:
    old_curves = _store_curves(old_rows)
    new_curves = _store_curves(new_rows)
    store_ids = sorted(new_curves)
    old_pairwise: list[float] = []
    new_pairwise: list[float] = []
    for index, first_store in enumerate(store_ids):
        for second_store in store_ids[index + 1 :]:
            old_pairwise.append(_pearson(old_curves[first_store], old_curves[second_store]))
            new_pairwise.append(_pearson(new_curves[first_store], new_curves[second_store]))
    shape_counts = Counter(profiles[store_id].shape for store_id in store_ids)
    rounded_curve_keys = {
        tuple(round(value, 6) for value in new_curves[store_id]) for store_id in store_ids
    }
    result = {
        "store_count": len(store_ids),
        "shape_counts": dict(sorted(shape_counts.items())),
        "shape_count": len(shape_counts),
        "unique_curve_count_6dp": len(rounded_curve_keys),
        "pair_count": len(new_pairwise),
        "old_pairwise_correlation": {
            "min": min(old_pairwise),
            "median": _percentile(old_pairwise, 0.50),
            "p95": _percentile(old_pairwise, 0.95),
            "max": max(old_pairwise),
        },
        "new_pairwise_correlation": {
            "min": min(new_pairwise),
            "median": _percentile(new_pairwise, 0.50),
            "p05": _percentile(new_pairwise, 0.05),
            "p95": _percentile(new_pairwise, 0.95),
            "max": max(new_pairwise),
            "below_0_95": sum(value < 0.95 for value in new_pairwise),
            "below_0_95_pct": 100.0 * sum(value < 0.95 for value in new_pairwise) / len(new_pairwise),
        },
        "curves": new_curves,
    }
    result["passed"] = bool(
        len(store_ids) == EXPECTED_STORE_COUNT
        and len(shape_counts) >= 8
        and len(rounded_curve_keys) == EXPECTED_STORE_COUNT
        and result["new_pairwise_correlation"]["median"] < 0.95
    )
    _require(result["passed"], "Store aggregate curves are not materially diverse")
    return result


def store_curve_examples(
    diversity: Mapping[str, Any],
    profiles: Mapping[str, StoreProfile],
) -> list[dict[str, Any]]:
    requested = ["S001", "S009", "S010", "S020", "S040", "S060", "S080", "S100", "S107", "S120"]
    available = set(diversity["curves"])
    selected = [store_id for store_id in requested if store_id in available]
    selected.extend(store_id for store_id in sorted(available) if store_id not in selected)
    selected = selected[:10]
    examples: list[dict[str, Any]] = []
    sample_weeks = (52, 48, 44, 40, 36, 32, 28, 24, 20, 16, 12, 8, 4, 1)
    for store_id in selected:
        curve = diversity["curves"][store_id]
        max_index = max(range(len(curve)), key=curve.__getitem__)
        min_index = min(range(len(curve)), key=curve.__getitem__)
        first = curve[0]
        last = curve[-1]
        examples.append(
            {
                "store_id": store_id,
                "shape": profiles[store_id].shape,
                "growth_w52_to_w1_pct": (last / first - 1.0) * 100.0 if first else math.inf,
                "peak": f"W-{52 - max_index}",
                "trough": f"W-{52 - min_index}",
                "range_pct": (max(curve) / min(curve) - 1.0) * 100.0 if min(curve) else math.inf,
                "sample_weeks": list(sample_weeks),
                "normalised_curve": [
                    value / statistics.fmean(curve) for value in [
                        curve[52 - week] for week in sample_weeks
                    ]
                ],
            }
        )
    return examples


def _filter_rows(
    rows: Sequence[DemandRow],
    *,
    vertical: str | None = None,
    store_id: str | None = None,
    cat: str | None = None,
    sku_id: str | None = None,
    store_verticals: Mapping[str, str],
) -> list[DemandRow]:
    return [
        row
        for row in rows
        if (vertical is None or store_verticals.get(row.store_id) == vertical)
        and (store_id is None or row.store_id == store_id)
        and (cat is None or row.cat == cat)
        and (sku_id is None or row.sku_id == sku_id)
    ]


def _trend_values(rows: Sequence[DemandRow]) -> dict[str, Any]:
    actual = sum(
        (row.actual(week) for row in rows for week in (4, 3, 2, 1)), Decimal("0")
    )
    forecast = sum(
        (row.forecast(week) for row in rows for week in (1, 2, 3, 4)), Decimal("0")
    )
    trend = None if actual <= 0 else (forecast / actual - Decimal("1")) * Decimal("100")
    return {"rows": len(rows), "actual_4w": actual, "forecast_4w": forecast, "trend_pct": trend}


def trend_regression(
    old_rows: Sequence[DemandRow],
    new_rows: Sequence[DemandRow],
    store_verticals: Mapping[str, str],
) -> dict[str, Any]:
    categories = sorted({row.cat for row in old_rows})
    category = "GRC-C01" if "GRC-C01" in categories else categories[0]
    skus = sorted({row.sku_id for row in old_rows})
    sku = "GRC-001" if "GRC-001" in skus else skus[0]
    scopes = [
        ("ALL", {}),
        ("GRC", {"vertical": "GRC"}),
        ("S001", {"store_id": "S001"}),
        ("S009", {"store_id": "S009"}),
        ("S107", {"store_id": "S107"}),
        (f"Category {category}", {"cat": category}),
        (f"SKU {sku}", {"sku_id": sku}),
        (f"S001 + {category}", {"store_id": "S001", "cat": category}),
        (f"S001 + {sku}", {"store_id": "S001", "sku_id": sku}),
    ]
    results: list[dict[str, Any]] = []
    for label, filters in scopes:
        before = _trend_values(_filter_rows(old_rows, store_verticals=store_verticals, **filters))
        after = _trend_values(_filter_rows(new_rows, store_verticals=store_verticals, **filters))
        actual_difference = after["actual_4w"] - before["actual_4w"]
        forecast_difference = after["forecast_4w"] - before["forecast_4w"]
        trend_difference = (
            None
            if before["trend_pct"] is None or after["trend_pct"] is None
            else after["trend_pct"] - before["trend_pct"]
        )
        _require(
            abs(actual_difference) <= DECIMAL_TOLERANCE
            and abs(forecast_difference) <= DECIMAL_TOLERANCE
            and (trend_difference is None or abs(trend_difference) <= Decimal("0.0000001")),
            f"Demand Trend changed for {label}",
        )
        results.append(
            {
                "scope": label,
                "before": before,
                "after": after,
                "actual_4w_difference": actual_difference,
                "forecast_4w_difference": forecast_difference,
                "trend_difference_pp": trend_difference,
                "passed": True,
            }
        )
    return {"passed": True, "scopes": results}


def row_level_validation(
    old_rows: Sequence[DemandRow],
    new_rows: Sequence[DemandRow],
) -> dict[str, Any]:
    old_by_key = {row.key: row for row in old_rows}
    new_by_key = {row.key: row for row in new_rows}
    _require(set(old_by_key) == set(new_by_key), "SKU x Store keys changed")
    forecast_changed = 0
    identity_changed = 0
    four_week_differences: list[Decimal] = []
    w1_gaps: list[float] = []
    changed_rows = 0
    changed_values = 0
    for key in sorted(old_by_key):
        old = old_by_key[key]
        new = new_by_key[key]
        if old.cat != new.cat:
            identity_changed += 1
        if old.forecasts != new.forecasts:
            forecast_changed += sum(a != b for a, b in zip(old.forecasts, new.forecasts))
        _require(old.cat == new.cat, f"Category changed for {key}")
        _require(old.forecasts == new.forecasts, f"Forecast changed for {key}")
        old_total = sum((old.actual(week) for week in (4, 3, 2, 1)), Decimal("0"))
        new_total = sum((new.actual(week) for week in (4, 3, 2, 1)), Decimal("0"))
        difference = new_total - old_total
        four_week_differences.append(difference)
        _require(abs(difference) <= DECIMAL_TOLERANCE, f"4W total changed for {key}")
        _require(
            all(value.is_finite() and value >= 0 for value in new.actuals),
            f"Invalid generated actual for {key}",
        )
        forecast_w1 = new.forecast(1)
        _require(forecast_w1 > 0, f"Non-positive forecast_w1 for {key}")
        ratio = new.actual(1) / forecast_w1
        gap = abs(float(ratio - Decimal("1")))
        w1_gaps.append(gap)
        _require(
            W1_MIN_RATIO <= ratio <= W1_MAX_RATIO,
            f"W-1 continuity failed for {key}: ratio={ratio}",
        )
        if old.actuals != new.actuals:
            changed_rows += 1
        changed_values += sum(a != b for a, b in zip(old.actuals, new.actuals))
    return {
        "forecast_values_changed": forecast_changed,
        "identity_values_changed": identity_changed,
        "four_week_max_abs_difference": max(abs(value) for value in four_week_differences),
        "four_week_nonzero_differences": sum(value != 0 for value in four_week_differences),
        "w1_gap": {
            "max": max(w1_gaps),
            "median": _percentile(w1_gaps, 0.50),
            "p95": _percentile(w1_gaps, 0.95),
            "outside_plus_minus_2_pct": sum(gap > 0.02 for gap in w1_gaps),
        },
        "changed_rows": changed_rows,
        "changed_values": changed_values,
    }


def aggregated_store_w1_validation(
    rows: Sequence[DemandRow],
) -> dict[str, Any]:
    actuals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    forecasts: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        actuals[row.store_id] += row.actual(1)
        forecasts[row.store_id] += row.forecast(1)
    gaps = [abs(float(actuals[store] / forecasts[store] - Decimal("1"))) for store in actuals]
    return {
        "stores": len(gaps),
        "max": max(gaps),
        "median": _percentile(gaps, 0.50),
        "p95": _percentile(gaps, 0.95),
        "outside_plus_minus_2_pct": sum(gap > 0.02 for gap in gaps),
    }


def validate_candidate(
    old_rows: Sequence[DemandRow],
    new_rows: Sequence[DemandRow],
    profiles: Mapping[str, StoreProfile],
    store_verticals: Mapping[str, str],
) -> dict[str, Any]:
    old_population = validate_population(old_rows)
    new_population = validate_population(new_rows)
    _require(old_population == new_population, "Population changed during generation")
    rows_by_old_key = {row.key: row for row in old_rows}
    rows_by_new_key = {row.key: row for row in new_rows}
    _require(set(rows_by_old_key) == set(rows_by_new_key), "Key population changed")
    row_checks = row_level_validation(old_rows, new_rows)
    store_w1 = aggregated_store_w1_validation(new_rows)
    _require(store_w1["outside_plus_minus_2_pct"] == 0, "Store aggregate W-1 continuity failed")
    smoothness = adjacent_change_stats(new_rows)
    _require(smoothness["over_20_pct"] == 0, "Adjacent history movement exceeded 20%")
    diversity = diversity_stats(old_rows, new_rows, profiles)
    examples = store_curve_examples(diversity, profiles)
    trends = trend_regression(old_rows, new_rows, store_verticals)
    return {
        "population": new_population,
        "rows": row_checks,
        "store_w1": store_w1,
        "smoothness": smoothness,
        "diversity": diversity,
        "store_examples": examples,
        "trend_regression": trends,
        "forecast_fingerprint_before": fingerprint(old_rows, (*IDENTIFIER_COLUMNS, *FORECAST_COLUMNS)),
        "forecast_fingerprint_after": fingerprint(new_rows, (*IDENTIFIER_COLUMNS, *FORECAST_COLUMNS)),
        "full_fingerprint_before": fingerprint(old_rows),
        "full_fingerprint_candidate": fingerprint(new_rows),
    }


def _compare_committed_rows(
    expected_old: Sequence[DemandRow],
    expected_new: Sequence[DemandRow],
    committed: Sequence[DemandRow],
) -> dict[str, Any]:
    _require(fingerprint(committed) == fingerprint(expected_new), "Committed values differ from candidate")
    checks = row_level_validation(expected_old, committed)
    _require(checks["forecast_values_changed"] == 0, "Committed forecast values changed")
    return {
        "passed": True,
        "full_fingerprint": fingerprint(committed),
        "forecast_fingerprint": fingerprint(committed, (*IDENTIFIER_COLUMNS, *FORECAST_COLUMNS)),
        "row_checks": checks,
    }


def _update_statement() -> str:
    assignments = ", ".join(f"[{column}] = ?" for column in ACTUAL_COLUMNS)
    return (
        f"UPDATE [{TABLE_SCHEMA}].[{TABLE_NAME}] SET {assignments} "
        "WHERE [sku_id] = ? AND [store_id] = ? AND [cat] = ?;"
    )


def _update_batches(cursor: Any, rows: Sequence[DemandRow]) -> int:
    statement = _update_statement()
    values = [
        tuple(quantity_text(value) for value in row.actuals)
        + (row.sku_id, row.store_id, row.cat)
        for row in sorted(rows, key=lambda item: item.key)
    ]
    updated = 0
    for start in range(0, len(values), UPDATE_BATCH_SIZE):
        batch = values[start : start + UPDATE_BATCH_SIZE]
        if hasattr(cursor, "fast_executemany"):
            cursor.fast_executemany = True
        cursor.executemany(statement, batch)
        updated += len(batch)
    return updated


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return f"{value:.{digits}f}"
    return str(value)


def _report_table_rows(trend_result: Mapping[str, Any]) -> list[str]:
    lines = [
        "| Scope | Rows | Trend before | Trend after | Difference (pp) | Result |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for item in trend_result["scopes"]:
        before = item["before"]["trend_pct"]
        after = item["after"]["trend_pct"]
        difference = item["trend_difference_pp"]
        lines.append(
            f"| {item['scope']} | {item['before']['rows']} | {_fmt(before, 8)}% "
            f"| {_fmt(after, 8)}% | {_fmt(difference, 10)} | PASS |"
        )
    return lines


def render_report(result: Mapping[str, Any]) -> str:
    validation = result["validation"]
    rows_check = validation["rows"]
    diversity = validation["diversity"]
    correlation = diversity["new_pairwise_correlation"]
    smoothness = validation["smoothness"]
    w1 = rows_check["w1_gap"]
    backup = result["backup"]
    verdict = result["verdict"]
    lines = [
        "# Demand 104W History Diversification Report",
        "",
        f"- **Verdict:** `{verdict}`",
        f"- **Rows updated:** `{result['rows_updated']}`" + (" (dry-run would update 16,000)" if result["mode"] == "dry-run" else ""),
        f"- **Columns updated:** `{', '.join(ACTUAL_COLUMNS)}`",
        f"- **Forecast values changed:** `{rows_check['forecast_values_changed']}`",
        f"- **4W totals preserved:** `PASS` (max absolute difference `{_fmt(rows_check['four_week_max_abs_difference'])}`; non-zero rows `{rows_check['four_week_nonzero_differences']}`)",
        f"- **Demand Trend regression:** `PASS` for `{len(validation['trend_regression']['scopes'])}` required scopes",
        f"- **Maximum W-1/W+1 row gap:** `{w1['max'] * 100:.8f}%` (median `{w1['median'] * 100:.8f}%`; P95 `{w1['p95'] * 100:.8f}%`)",
        f"- **Store diversity result:** `PASS` ({diversity['shape_count']} deterministic Store shapes; median pairwise correlation `{correlation['median']:.6f}`; `{correlation['below_0_95_pct']:.2f}%` of pairs below 0.95)",
        f"- **SQL validation result:** `{result['sql_validation']}`",
        f"- **Rollback artifact/path:** `{backup['csv']}`; manifest `{backup['manifest']}`",
        "",
        "## Scope and write contract",
        "",
        f"Only `{FULL_TABLE_NAME}` was eligible for a write. The SQL statement updates the 52 columns "
        "`actual_w52` through `actual_w1`, keyed by `(sku_id, store_id, cat)`. No forecast column, "
        f"identifier, category, `{OLD_FULL_TABLE_NAME}`, retail source table, frontend/backend logic, "
        "Formula Manager, or KPI formula was changed.",
        "",
        "## Backup and fingerprints",
        "",
        f"The pre-update table was exported before any UPDATE. The backup contains all 107 table columns "
        f"so rollback can restore historical values while verifying forecast and identity preservation.",
        "",
        "| Fingerprint | Value |",
        "|---|---|",
        f"| Pre-update full table | `{result['before_full_fingerprint']}` |",
        f"| Candidate full table | `{validation['full_fingerprint_candidate']}` |",
        f"| Post-commit full table | `{result.get('after_full_fingerprint', 'not committed in this run')}` |",
        f"| Pre-update forecast/identity | `{validation['forecast_fingerprint_before']}` |",
        f"| Backup CSV SHA-256 | `{backup['sha256']}` |",
        "",
        "## Generation and validation gates",
        "",
        f"Fixed seed/version: `{SEED_VERSION}` / `{GENERATOR_VERSION}`. Store profiles are assigned from a "
        "stable SHA-256 hash of `store_id`; SKU-specific smooth perturbations use `sku_id`. W-1 is set "
        "to the row's existing `forecast_w1`, W-2..W-4 close the original row-level 4-week total exactly, "
        "and W-5..W-52 are generated backward from W-4 using smooth log-scale curves.",
        "",
        "| Gate | Result |",
        "|---|---|",
        f"| Population | PASS (`{validation['population']['rows']}` rows, `{validation['population']['skus']}` SKUs, `{validation['population']['stores']}` Stores, `{validation['population']['unique_keys']}` unique keys) |",
        f"| Forecast preservation | PASS (`{rows_check['forecast_values_changed']}` changed forecast values) |",
        f"| Identity/category preservation | PASS (`{rows_check['identity_values_changed']}` changed categories) |",
        f"| Row-level 4W preservation | PASS (max `{_fmt(rows_check['four_week_max_abs_difference'])}`) |",
        f"| Row-level W-1 continuity | PASS (`{w1['outside_plus_minus_2_pct']}` rows outside ±2%) |",
        f"| Store aggregate W-1 continuity | PASS (max `{validation['store_w1']['max'] * 100:.8f}%`; `{validation['store_w1']['outside_plus_minus_2_pct']}` outside ±2%) |",
        f"| Non-negative/finite histories | PASS |",
        f"| Smoothness | PASS (max `{smoothness['max'] * 100:.4f}%`; P95 `{smoothness['p95'] * 100:.4f}%`; over 20% `{smoothness['over_20_pct']}`) |",
        f"| Store diversity | PASS |",
        "",
        "## Demand Trend regression",
        "",
        "Trend is reported as `(aggregate forecast W+1..W+4 / aggregate actual W-4..W-1 - 1) × 100`. "
        "The actual denominator is preserved at row grain, so all filtered aggregates reconcile without "
        "tuning to workbook constants.",
        "",
        *_report_table_rows(validation["trend_regression"]),
        "",
        "## Store diversity",
        "",
        f"The 160 Store aggregate curves have `{diversity['unique_curve_count_6dp']}` unique six-decimal "
        f"trajectories across `{diversity['pair_count']}` Store pairs. Before regeneration, the median "
        f"pairwise correlation was `{diversity['old_pairwise_correlation']['median']:.6f}`; after, it is "
        f"`{correlation['median']:.6f}` (range `{correlation['min']:.6f}` to `{correlation['max']:.6f}`). "
        f"The stable Store shape counts are: `{json.dumps(diversity['shape_counts'], sort_keys=True)}`.",
        "",
        "| Store | Deterministic shape | W-52→W-1 growth | Peak | Trough | Range | Normalised sample curve (W-52 … W-1) |",
        "|---|---|---:|---|---|---:|---|",
    ]
    for example in validation["store_examples"]:
        curve = ", ".join(f"{value:.2f}" for value in example["normalised_curve"])
        lines.append(
            f"| {example['store_id']} | {example['shape']} | {example['growth_w52_to_w1_pct']:.1f}% "
            f"| {example['peak']} | {example['trough']} | {example['range_pct']:.1f}% | `{curve}` |"
        )
    lines.extend(
        [
            "",
            "## Smoothness statistics",
            "",
            f"Adjacent historical movement was measured across `{smoothness['count']}` row/week transitions "
            f"using `abs(current / previous - 1)`. Median: `{smoothness['median'] * 100:.4f}%`; "
            f"P95: `{smoothness['p95'] * 100:.4f}%`; P99: `{smoothness['p99'] * 100:.4f}%`; "
            f"maximum: `{smoothness['max'] * 100:.4f}%`. No transition exceeded 20%.",
            "",
            "## Read-back and rollback",
            "",
            f"Mode: `{result['mode']}`. SQL update batches: `{result['update_batches']}`; rows submitted: `{result['rows_submitted']}`.",
            f"Read-back: `{result['sql_validation']}`. Committed full fingerprint: `{result.get('after_full_fingerprint', 'not committed')}`.",
            "",
            "Rollback requires the original backup and is guarded by the committed candidate fingerprint:",
            "",
            "```bash",
            f".venv/bin/python backend/scripts/rollback_demand_104w_history.py --backup {backup['csv']}",
            f".venv/bin/python backend/scripts/rollback_demand_104w_history.py --apply --backup {backup['csv']}",
            "```",
            "",
            "The rollback process also updates only `actual_w52`…`actual_w1`; it never writes forecasts, "
            "identifiers, categories, the 32W table, or retail source tables.",
            "",
        ]
    )
    return "\n".join(lines)


def _default_backup_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "artifacts" / f"demand_store_sku_104w_history_backup_{stamp}.csv"


def run(mode: str, backup_path: Path, report_path: Path) -> dict[str, Any]:
    _require(mode in {"dry-run", "apply"}, f"Unknown mode: {mode}")
    connection = open_connection()
    try:
        cursor = connection.cursor()
        validate_schema(cursor)
        old_rows = _read_table_rows(cursor)
        store_verticals = _read_store_verticals(cursor)
    finally:
        connection.close()
    validate_population(old_rows)
    _require(
        set(store_verticals) >= {row.store_id for row in old_rows},
        "A live store-to-vertical mapping is missing",
    )
    before_full_fingerprint = fingerprint(old_rows)
    backup_manifest = prepare_backup(old_rows, backup_path)
    candidate_rows, profiles = generate_candidate(old_rows)
    validation = validate_candidate(old_rows, candidate_rows, profiles, store_verticals)
    _require(
        backup_manifest["source_full_fingerprint"] == before_full_fingerprint,
        "Backup fingerprint does not match current table",
    )
    update_backup_manifest(
        backup_path,
        {
            "candidate_full_fingerprint": validation["full_fingerprint_candidate"],
            "candidate_forecast_fingerprint": validation["forecast_fingerprint_after"],
            "candidate_generator_version": GENERATOR_VERSION,
        },
    )

    print("SAMPLE STORE AGGREGATE CURVES BEFORE WRITE (normalised; chronological W-52 ... W-1)")
    for example in validation["store_examples"]:
        curve = ", ".join(f"{value:.2f}" for value in example["normalised_curve"])
        print(
            f"{example['store_id']} | {example['shape']} | "
            f"growth={example['growth_w52_to_w1_pct']:.1f}% | curve={curve}"
        )
    validation_summary = dict(validation)
    validation_summary["diversity"] = {
        key: value
        for key, value in validation["diversity"].items()
        if key != "curves"
    }
    print(json.dumps({"validation": validation_summary}, indent=2, default=_json_default))

    result: dict[str, Any] = {
        "mode": mode,
        "verdict": "COMPLETE WITH CAVEATS" if mode == "dry-run" else "COMPLETE",
        "rows_updated": 0 if mode == "dry-run" else EXPECTED_ROW_COUNT,
        "rows_submitted": 0,
        "update_batches": 0,
        "sql_validation": "NOT RUN (dry-run)",
        "before_full_fingerprint": before_full_fingerprint,
        "validation": validation,
        "backup": {
            "csv": str(backup_path),
            "manifest": str(_backup_manifest_path(backup_path)),
            "sha256": _file_sha256(backup_path),
        },
    }
    if mode == "apply":
        # Optimistic concurrency guard: the backup/dry-run fingerprint must
        # still be the live table immediately before entering the write txn.
        connection = open_connection()
        try:
            cursor = connection.cursor()
            validate_schema(cursor)
            current_rows = _read_table_rows(cursor)
            _require(
                fingerprint(current_rows) == before_full_fingerprint,
                "Live table changed after dry-run/backup; aborting without UPDATE",
            )
            _require(
                fingerprint(current_rows) == backup_manifest["source_full_fingerprint"],
                "Live table no longer matches backup; aborting without UPDATE",
            )
            rows_submitted = _update_batches(cursor, candidate_rows)
            in_transaction = _read_table_rows(cursor)
            _compare_committed_rows(current_rows, candidate_rows, in_transaction)
            connection.commit()
            result["rows_submitted"] = rows_submitted
            result["update_batches"] = math.ceil(rows_submitted / UPDATE_BATCH_SIZE)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        readback_connection = open_connection()
        try:
            readback_cursor = readback_connection.cursor()
            validate_schema(readback_cursor)
            committed_rows = _read_table_rows(readback_cursor)
            committed_check = _compare_committed_rows(
                old_rows, candidate_rows, committed_rows
            )
        finally:
            readback_connection.close()
        result["sql_validation"] = "PASS"
        result["after_full_fingerprint"] = committed_check["full_fingerprint"]
        update_backup_manifest(
            backup_path,
            {
                "committed_at_utc": datetime.now(timezone.utc).isoformat(),
                "committed_full_fingerprint": committed_check["full_fingerprint"],
                "committed_forecast_fingerprint": committed_check["forecast_fingerprint"],
                "committed_rows": result["rows_submitted"],
                "committed_update_batches": result["update_batches"],
            },
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "validation"}, indent=2, default=_json_default))
    print(f"Report: {report_path}")
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    backup = args.backup or _default_backup_path()
    mode = "apply" if args.apply else "dry-run"
    try:
        run(mode, backup, args.report)
    except Exception as exc:
        print(f"HISTORY DIVERSIFICATION FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
