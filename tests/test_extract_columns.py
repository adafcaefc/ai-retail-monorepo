from __future__ import annotations

import unittest

from src.llm.tools.monitoring_tools import extract_columns


class ExtractColumnsTest(unittest.TestCase):
    def test_ignores_sql_functions_and_filter(self) -> None:
        cols = extract_columns(
            "COUNT(*) FILTER (WHERE overdue_days > 60)"
        )
        self.assertEqual(cols, {"overdue_days"})
        self.assertNotIn("COUNT", {c.upper() for c in cols})
        self.assertNotIn("FILTER", {c.upper() for c in cols})

    def test_ignores_least_greatest(self) -> None:
        cols = extract_columns(
            "LEAST(balance, limit_amount) AS capped"
        )
        self.assertEqual(cols, {"balance", "limit_amount"})
        self.assertNotIn("LEAST", {c.upper() for c in cols})

    def test_keeps_real_columns_in_update(self) -> None:
        cols = extract_columns(
            "status = 'HELD', hold_reason = 'callback'"
        )
        self.assertEqual(cols, {"status", "hold_reason"})


if __name__ == "__main__":
    unittest.main()
