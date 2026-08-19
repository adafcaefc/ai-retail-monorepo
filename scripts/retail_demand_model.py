"""The demand model both retail fixture builders write into their payloads.

Two boards read the same workbook and both have to answer "how much sells
tomorrow": Demand Forecasting draws it as a curve, Inventory Risk burns it
against stock. Keeping the seven day-of-week factors and the seasonal
decomposition here means the two fixtures cannot be regenerated out of step
with each other -- which is exactly what happened when Inventory Risk had no
shape at all and burned a flat ADS instead.

The browser-side counterpart is `frontend/src/agents/retail/common/demandModel.js`,
which evaluates what this module ships.
"""

from __future__ import annotations

from typing import Any

# The seven factors and the twelve month labels come from the backend, which
# holds the canonical copy (`warehouse.DOW_PROFILE`). `scripts/` already puts
# `backend/` on sys.path to reach the formula catalogue, so importing costs
# nothing and removes the last place these numbers could drift.
from src.formulas.expression import evaluate, parse  # noqa: E402
from src.llm.agents.retail.common.warehouse import (  # noqa: E402
    DOW_PROFILE,
    MONTH_LABELS,
    formulas,
)

# z for a two-sided 90% prediction interval.
#
# This is what puts a number on the A1 spec's "band ±12%". Forecast error grows
# with the square root of the horizon (variance accumulates linearly under a
# random walk), so the band at horizon h is
#
#     yhat +/- z * (1 - accuracy/100) * sqrt(h)
#
# At h = 1 with the workbook's 92.4% accuracy that is 1.645 * 0.076 = 12.5%,
# which is where the spec's flat ±12% comes from. Stating it this way makes the
# band widen with horizon, as a prediction interval must.
INTERVAL_Z = 1.645

def seasonal_indices(
    series: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Twelve classical seasonal indices per vertical, from monthly GMV.

    Textbook decomposition: each calendar month's average divided by the
    series average. The workbook's series repeats one year twice, so the two
    observations per month are the same number -- which makes the average
    exact rather than noisy, and means no de-trending step is needed. There is
    no trend to remove.

    The per-month ratio itself is `fc01-seasonal-index`
    (`resources/custom_formulas.json`), evaluated here rather than retyped, so
    a fixture built offline from this script and a live board's
    `warehouse.seasonal_indices()` cannot drift onto two different rules.

    This function's job is the part `fc01` cannot do alone: multi-year
    averaging. `fc01` takes one month's GMV and the series mean as plain
    numbers; folding several years of the same calendar month into one
    observation happens here, before the formula ever runs.

    These are NOT the `Seasonality idx` KPI. That column is typed into the A1
    sheet and does not agree with this calculation (Grocery: 114 typed against
    108.3 derived). Both are kept, and the payload labels which is which.
    """
    months: dict[str, list[str]] = {}
    values: dict[str, dict[str, float]] = {}

    for row in series:
        vertical = row["vertical_id"]
        values.setdefault(vertical, {})[row["month"]] = row["gmv"]
        order = months.setdefault(vertical, [])
        if row["month"] not in order:
            order.append(row["month"])

    node = parse(formulas(("fc01-seasonal-index",))["fc01-seasonal-index"])

    indices: dict[str, list[float]] = {}
    for vertical, order in months.items():
        observations = [values[vertical][month] for month in order]
        if len(observations) % 12:
            raise SystemExit(
                f"FAIL  {vertical} has {len(observations)} months, not a whole"
                " number of years"
            )
        mean = sum(observations) / len(observations)
        years = len(observations) // 12
        indices[vertical] = [
            evaluate(
                node,
                {
                    "month_gmv": sum(
                        observations[month + 12 * year] for year in range(years)
                    )
                    / years,
                    "series_mean": mean,
                },
            )
            / 100
            for month in range(12)
        ]

    return indices


def check_profile(dow_sum: float) -> None:
    """Insist the seven factors still add up to the workbook's own week.

    `DOW_PROFILE` is a modelled allocation, but the total it allocates is
    measured: `Constants` B7, the same 7.45 f08 multiplies ADS by. If the two
    ever drift, a daily view stops rolling up to the weekly figure the workbook
    publishes and both boards start quietly disagreeing with the sheet. Cheaper
    to fail the build.
    """
    total = sum(DOW_PROFILE)
    if abs(total - dow_sum) > 1e-9:
        raise SystemExit(
            f"FAIL  DOW_PROFILE sums to {total}, not the workbook's {dow_sum}"
        )


def seasonality_payload(
    time_series: list[dict[str, Any]],
    month_index: int,
) -> dict[str, Any]:
    """The seasonality block, identical in shape for every board that ships it.

    Percentage points rather than ratios, because that is how the workbook's
    own `Seasonality idx` column reads and a reader comparing the two should
    not have to rescale one of them in their head.
    """
    indices = seasonal_indices(time_series)
    return {
        "month_labels": list(MONTH_LABELS),
        "current_month_index": month_index,
        "by_legal_entity": {
            vertical_id: [round(value * 100, 4) for value in indices[vertical_id]]
            for vertical_id in indices
        },
    }
