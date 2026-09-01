import unittest

from backend.app.kiwoom import KiwoomRestClient
from backend.app.live_trading_safety import (
    LIVE_ACTIVATION_TEXT,
    LIVE_AUTO_START_TEXT,
    LIVE_ORDER_TEXT,
    LiveTradingSafetyError,
    require_confirmation,
    validate_live_order_limits,
)
from backend.app.models import (
    KiwoomAccountSnapshot,
    KiwoomCredential,
    KiwoomLiveAccountSnapshot,
    KiwoomLiveCredential,
    LiveAutoTradingDecision,
    LiveAutoTradingSetting,
    LiveOrderAudit,
)


class LiveTradingSafetyTests(unittest.TestCase):
    def test_mock_and_live_clients_use_different_official_hosts(self):
        paper = KiwoomRestClient("paper", "secret", True)
        live = KiwoomRestClient("live", "secret", False)
        self.assertEqual(paper.base, "https://mockapi.kiwoom.com")
        self.assertEqual(live.base, "https://api.kiwoom.com")
        self.assertNotEqual(paper.base, live.base)

    def test_live_storage_is_not_shared_with_paper_storage(self):
        self.assertNotEqual(KiwoomCredential.__tablename__, KiwoomLiveCredential.__tablename__)
        self.assertNotEqual(KiwoomAccountSnapshot.__tablename__, KiwoomLiveAccountSnapshot.__tablename__)
        self.assertEqual(LiveOrderAudit.__tablename__, "live_order_audit")
        self.assertEqual(LiveAutoTradingSetting.__tablename__, "live_auto_trading_settings")
        self.assertEqual(LiveAutoTradingDecision.__tablename__, "live_auto_trading_decisions")

    def test_exact_live_confirmation_phrases_are_required(self):
        for phrase in (LIVE_ACTIVATION_TEXT, LIVE_ORDER_TEXT, LIVE_AUTO_START_TEXT):
            require_confirmation(phrase, phrase)
            with self.assertRaises(LiveTradingSafetyError):
                require_confirmation(phrase + "!", phrase)

    def test_buy_is_blocked_by_per_order_and_buying_power_limits(self):
        with self.assertRaisesRegex(LiveTradingSafetyError, "안전한도"):
            validate_live_order_limits(
                side="buy", quantity=60, reference_price=100_000,
                max_order_amount=5_000_000, buying_power=10_000_000,
            )
        with self.assertRaisesRegex(LiveTradingSafetyError, "주문가능금액"):
            validate_live_order_limits(
                side="buy", quantity=20, reference_price=100_000,
                max_order_amount=5_000_000, buying_power=1_000_000,
            )

    def test_sell_is_blocked_above_actual_holding(self):
        with self.assertRaisesRegex(LiveTradingSafetyError, "보유수량"):
            validate_live_order_limits(
                side="sell", quantity=11, reference_price=50_000,
                max_order_amount=5_000_000, held_quantity=10,
            )


if __name__ == "__main__":
    unittest.main()
