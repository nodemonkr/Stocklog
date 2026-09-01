from datetime import datetime
import unittest

from backend.app.auto_trading_metrics import auto_position_return_rates, krx_market_phase


class AutoTradingMetricsTests(unittest.TestCase):
    def test_krx_market_phase_distinguishes_preopen_open_and_closed(self):
        self.assertEqual(krx_market_phase(datetime(2026, 8, 31, 8, 59)), "preopen")
        self.assertEqual(krx_market_phase(datetime(2026, 8, 31, 9, 0)), "open")
        self.assertEqual(krx_market_phase(datetime(2026, 8, 31, 15, 30)), "closed")
        self.assertEqual(krx_market_phase(datetime(2026, 8, 30, 11, 0)), "closed")

    def test_preopen_daily_return_is_zero_but_cumulative_return_is_preserved(self):
        result = auto_position_return_rates(
            current_price=110,
            average_price=100,
            portfolio_day_return_rate=3.5,
            market_change_rate=3.5,
            market_phase="preopen",
        )
        self.assertAlmostEqual(result["return_rate"], 10.0)
        self.assertEqual(result["day_return_rate"], 0.0)

    def test_open_and_closed_daily_return_use_the_latest_market_value(self):
        open_result = auto_position_return_rates(
            current_price=95,
            average_price=100,
            portfolio_day_return_rate=-2.25,
            market_phase="open",
        )
        closed_result = auto_position_return_rates(
            current_price=108,
            average_price=100,
            portfolio_day_return_rate=0,
            market_change_rate=1.75,
            market_phase="closed",
        )
        self.assertEqual(open_result["day_return_rate"], -2.25)
        self.assertAlmostEqual(closed_result["return_rate"], 8.0)
        self.assertEqual(closed_result["day_return_rate"], 1.75)

    def test_same_day_purchase_does_not_inherit_pre_purchase_market_move(self):
        result = auto_position_return_rates(
            current_price=100,
            average_price=100,
            portfolio_day_return_rate=0,
            market_change_rate=4.2,
            day_profit_basis="today_acquired_kiwoom_net",
            market_phase="open",
        )
        self.assertEqual(result["day_return_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
