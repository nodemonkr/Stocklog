import unittest

from backend.app.analysis import enrich_financial_growth


class FinancialGrowthComparisonTests(unittest.TestCase):
    def test_filing_native_comparison_is_used_per_metric(self):
        rows = [{
            "period": "2026-2Q",
            "revenue": 120.0,
            "operating_profit": 24.0,
            "net_income": 18.0,
            "assets": 500.0,
            "liabilities": 200.0,
            "equity": 300.0,
            "comparison_revenue": 100.0,
            "comparison_operating_profit": 20.0,
            "comparison_net_income": 20.0,
            "comparison_assets": 480.0,
            "comparison_liabilities": 210.0,
            "comparison_equity": 270.0,
            "comparison_income_period": "2025-2Q 누적",
            "comparison_balance_period": "2025-FY",
            "income_basis": "누적",
        }]

        result = enrich_financial_growth(rows)[0]
        self.assertEqual(result["change"]["revenue"], 20.0)
        self.assertEqual(result["change"]["operating_profit"], 20.0)
        self.assertEqual(result["change"]["net_income"], -10.0)
        self.assertEqual(result["comparison_periods"]["revenue"], "2025-2Q 누적")
        self.assertEqual(result["comparison_periods"]["equity"], "2025-FY")

    def test_adjacent_quarters_are_not_compared(self):
        rows = [
            {"period": "2026-2Q", "revenue": 120.0, "operating_profit": 24.0, "net_income": 18.0, "assets": 500.0, "liabilities": 200.0, "equity": 300.0},
            {"period": "2026-1Q", "revenue": 55.0, "operating_profit": 11.0, "net_income": 9.0, "assets": 490.0, "liabilities": 205.0, "equity": 285.0},
        ]

        result = enrich_financial_growth(rows)[0]
        self.assertIsNone(result["change"]["revenue"])
        self.assertIsNone(result["change"]["operating_profit"])
        self.assertIsNone(result["change"]["net_income"])

    def test_profit_sign_changes_use_direction_symbols_not_misleading_percentages(self):
        rows = [{
            "period": "2026-2Q",
            "revenue": 120.0,
            "operating_profit": 15.0,
            "net_income": -5.0,
            "equity": 300.0,
            "comparison_revenue": 100.0,
            "comparison_operating_profit": -10.0,
            "comparison_net_income": 8.0,
            "comparison_equity": 270.0,
            "comparison_income_period": "2025-2Q 누적",
            "comparison_balance_period": "2025-FY",
        }]

        result = enrich_financial_growth(rows)[0]
        self.assertIsNone(result["change"]["operating_profit"])
        self.assertEqual(result["change_labels"]["operating_profit"], "+")
        self.assertEqual(result["change_directions"]["operating_profit"], "up")
        self.assertIsNone(result["change"]["net_income"])
        self.assertEqual(result["change_labels"]["net_income"], "-")
        self.assertEqual(result["change_directions"]["net_income"], "down")

    def test_negative_profit_to_less_negative_uses_positive_direction_symbol(self):
        rows = [{
            "period": "2026-1Q",
            "operating_profit": -4.0,
            "comparison_operating_profit": -10.0,
            "comparison_income_period": "2025-1Q 누적",
        }]
        result = enrich_financial_growth(rows)[0]
        self.assertIsNone(result["change"]["operating_profit"])
        self.assertEqual(result["change_labels"]["operating_profit"], "+")
        self.assertEqual(result["change_directions"]["operating_profit"], "up")


if __name__ == "__main__":
    unittest.main()
