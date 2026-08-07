"""Run one SQL statement against the live database and print the rows.

The point of this file is that it contains no application logic. It opens the
connection named in `backend/.env` and prints exactly what the database
returns, so a number it prints can be compared against a number the dashboard
prints without either one having been through the agent code.

    cd backend
    ../.venv/Scripts/python.exe ../scripts/sql.py "SELECT 1"

Quote the statement. On PowerShell use single quotes inside, double outside.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    statement = " ".join(sys.argv[1:])
    try:
        with get_engine().connect() as connection:
            result = connection.execute(text(statement))
            columns = list(result.keys())
            rows = [tuple(r) for r in result]
    except SQLAlchemyError as error:
        # A mistyped column name is a normal part of exploring, not a crash.
        # Print what the database said and stop, so the shell stays readable.
        print(f"SQL error: {getattr(error, 'orig', error)}", file=sys.stderr)
        return 1

    widths = [
        max(
            len(str(columns[i])),
            max((len(f"{r[i]:,.2f}" if isinstance(r[i], float) else str(r[i]))
                 for r in rows), default=0),
        )
        for i in range(len(columns))
    ]

    print("  ".join(str(c).ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        cells = []
        for value, width in zip(row, widths):
            if isinstance(value, float):
                cells.append(f"{value:,.2f}".rjust(width))
            else:
                cells.append(str(value).ljust(width))
        print("  ".join(cells))
    print(f"\n({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
