"""Where the Treasury forecast sits in time.

QC-035: not one of the twenty-two charts said what span it covered.

Each agent now derives its own period from its own `newdata` tables, next to
the query that produces the figures being labelled:

    Finance     `performance_data._period`   -- the reporting window
    Collection  `collection_data`            -- ageing snapshot + DSO basis
    Leakage     `leakage_data._period`       -- the months its cases fall in
    Treasury    here                         -- the forecast's own weeks

Treasury's stays here because `fact_cashflow_weekly` carries week labels and
no dates, so the span has to be read off the weeks themselves rather than
taken from a column.

This module used to hold a `finance_period`, `leakage_period` and
`collection_period` as well, each querying `financial_performance`,
`payment_leakage` and `collections` -- the pre-migration schemas. They had no
callers left after those three agents moved onto `newdata`, so they were dead
code pointed at stale tables.
"""

from __future__ import annotations

from src.llm.agents.common.tools.db import _rows


def treasury_period(connection, import_batch_id: int | None) -> str:
    """The span the cash forecast covers, read from its own week numbers."""
    rows = _rows(
        connection,
        """
        SELECT
            MIN(CAST(regexp_replace(week, '\\D', '', 'g') AS INT)) AS lo,
            MAX(CAST(regexp_replace(week, '\\D', '', 'g') AS INT)) AS hi,
            COUNT(*) AS weeks
        FROM newdata.fact_cashflow_weekly
        """,
        {},
    )
    row = rows[0] if rows else {}
    weeks = int(row.get("weeks") or 0)
    lo = row.get("lo")
    hi = row.get("hi")
    if lo is not None and hi is not None and weeks:
        return f"{weeks}-week forecast · W{lo}–W{hi}"
    return "rolling weekly forecast"


__all__ = ["treasury_period"]
