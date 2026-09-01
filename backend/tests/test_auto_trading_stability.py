from datetime import datetime, timedelta
import unittest

from backend.app.auto_trading_stability import (
    monitor_health_payload,
    protective_exit_assessment,
    recent_trade_guard_message,
    stable_entry_guard_message,
)


class AutoTradingStabilityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 1, 13, 0, 0)

    def test_repeat_partial_sell_is_cooled_down_but_risk_exit_bypasses(self):
        recent = self.now - timedelta(minutes=7)
        self.assertIn("연속 부분매도", recent_trade_guard_message(
            action="sell", now=self.now, recent_same_action_at=recent,
        ))
        self.assertEqual("", recent_trade_guard_message(
            action="sell", now=self.now, recent_same_action_at=recent, risk_guard=True,
        ))

    def test_same_day_reentry_is_blocked(self):
        message = recent_trade_guard_message(
            action="buy", now=self.now,
            recent_opposite_action_at=self.now - timedelta(hours=2),
        )
        self.assertIn("다음 거래일", message)

    def test_unstable_entries_and_averaging_down_are_blocked(self):
        self.assertIn("추격매수", stable_entry_guard_message(
            change_rate=6.2, current_return_pct=None, is_new_position=True,
        ))
        self.assertIn("하락 안정", stable_entry_guard_message(
            change_rate=-4.5, current_return_pct=None, is_new_position=True,
        ))
        self.assertIn("물타기", stable_entry_guard_message(
            change_rate=0.2, current_return_pct=-2.1, is_new_position=False,
        ))

    def test_monitor_requires_recent_success_to_claim_verified(self):
        common = dict(
            enabled=True, market_open=True, interval_seconds=60,
            position_count=3, last_started_at=self.now, last_failure_at=None,
            last_error="", checked_positions=3, check_count=4, now=self.now,
        )
        waiting = monitor_health_payload(last_success_at=None, **common)
        self.assertEqual(waiting["status"], "waiting")
        verified = monitor_health_payload(last_success_at=self.now - timedelta(seconds=50), **common)
        self.assertEqual(verified["status"], "verified")
        delayed = monitor_health_payload(last_success_at=self.now - timedelta(minutes=4), **common)
        self.assertEqual(delayed["status"], "delayed")

    def test_failure_after_last_success_is_visible(self):
        result = monitor_health_payload(
            enabled=True, market_open=True, interval_seconds=60, position_count=2,
            last_started_at=self.now - timedelta(seconds=20),
            last_success_at=self.now - timedelta(minutes=2),
            last_failure_at=self.now - timedelta(seconds=20), last_error="timeout",
            checked_positions=2, check_count=7, now=self.now,
        )
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["verified"])

    def test_stop_warning_is_not_the_execution_threshold(self):
        warning = protective_exit_assessment(
            current_price=95, average_price=100, stop_loss_pct=6, take_profit_pct=12,
        )
        self.assertEqual(warning["status"], "stop_approaching")
        self.assertAlmostEqual(warning["stop_warning_return"], -4.8)
        self.assertAlmostEqual(warning["stop_trigger_return"], -6.0)
        self.assertEqual(warning["trigger"], "")

    def test_stop_trigger_uses_supplied_broker_price(self):
        triggered = protective_exit_assessment(
            current_price=93, average_price=100, stop_loss_pct=6, take_profit_pct=12,
        )
        self.assertEqual(triggered["status"], "stop_triggered")
        self.assertIn("-6% 도달", triggered["trigger"])
        self.assertEqual(triggered["price_source"], "키움 계좌 현재가")


if __name__ == "__main__":
    unittest.main()
