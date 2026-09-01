import unittest

from backend.app.sync_policy import (
    classify_sync_result,
    classify_flow_error,
    is_quota_like_error,
    normalize_run_times,
    provider_circuit_should_open,
    retry_delay_seconds,
    select_due_run_slot,
)


class SyncPolicyTests(unittest.TestCase):
    def test_schedule_is_sorted_and_deduplicated(self):
        self.assertEqual(normalize_run_times(["22:00", "09:30", "22:00"]), ["09:30", "22:00"])

    def test_schedule_rejects_invalid_or_empty_values(self):
        with self.assertRaises(ValueError):
            normalize_run_times([])
        with self.assertRaises(ValueError):
            normalize_run_times(["25:00"])


    def test_schedule_due_slot_survives_exact_minute(self):
        self.assertEqual(
            select_due_run_slot(["09:00", "15:00"], date_iso="2026-08-25", current_hhmm="09:07"),
            "2026-08-25@09:00",
        )

    def test_schedule_due_slot_uses_latest_when_multiple_were_missed(self):
        self.assertEqual(
            select_due_run_slot(["09:00", "15:00", "22:00"], date_iso="2026-08-25", current_hhmm="16:30", last_auto_slot="2026-08-24@22:00"),
            "2026-08-25@15:00",
        )

    def test_schedule_due_slot_does_not_duplicate_started_slot(self):
        self.assertIsNone(
            select_due_run_slot(["09:00", "15:00"], date_iso="2026-08-25", current_hhmm="15:40", last_auto_slot="2026-08-25@15:00")
        )

    def test_schedule_due_slot_waits_for_future_time(self):
        self.assertIsNone(
            select_due_run_slot(["22:00"], date_iso="2026-08-25", current_hhmm="21:59", last_auto_slot="2026-08-24@22:00")
        )

    def test_flow_expected_absence_is_not_failure(self):
        self.assertEqual(classify_flow_error("조회 데이터가 없습니다"), "no_data")

    def test_flow_transient_errors_are_retryable(self):
        self.assertEqual(classify_flow_error("429 Too Many Requests"), "transient")
        self.assertEqual(classify_flow_error("connection timed out"), "transient")
        self.assertEqual(classify_flow_error("사용한도를 초과하였습니다"), "transient")

    def test_flow_unknown_error_is_hard(self):
        self.assertEqual(classify_flow_error("invalid payload format"), "hard")

    def test_retry_delay_is_bounded(self):
        self.assertEqual(retry_delay_seconds(1), 0.7)
        self.assertEqual(retry_delay_seconds(2), 1.4)
        self.assertEqual(retry_delay_seconds(10), 3.0)

    def test_quota_like_error_detects_dart_and_http_rate_limits(self):
        self.assertTrue(is_quota_like_error("status=020 사용한도를 초과하였습니다"))
        self.assertTrue(is_quota_like_error("429 Too Many Requests"))
        self.assertFalse(is_quota_like_error("invalid payload format"))

    def test_provider_circuit_opens_only_at_threshold(self):
        self.assertFalse(provider_circuit_should_open(5, threshold=6))
        self.assertTrue(provider_circuit_should_open(6, threshold=6))
        self.assertTrue(provider_circuit_should_open(20, threshold=6))

    def test_sync_result_keeps_expected_absence_informational(self):
        self.assertEqual(classify_sync_result(missing_data=8), "info")
        self.assertEqual(classify_sync_result(deferred=3), "retry")
        self.assertEqual(classify_sync_result(hard_failures=1, deferred=3), "error")
        self.assertEqual(classify_sync_result(), "success")


if __name__ == "__main__":
    unittest.main()
