import json
import unittest

from backend.app.auto_trading_prompt import (
    build_auto_decision_batches,
    compact_auto_stock_context,
    compact_learning_memory,
    is_recoverable_gbot_completeness_error,
    is_recoverable_gbot_response_error,
)


class AutoTradingPromptTests(unittest.TestCase):
    def _stock(self, code: str) -> dict:
        return {
            "code": code,
            "name": "테스트종목",
            "price": 12345,
            "change_rate": 2.3,
            "smart_score": 81,
            "score_components": [{"name": "수급", "score": 82, "reason": "긴 설명" * 200}] * 12,
            "recent_news": [{"title": "뉴스 제목" * 80, "sentiment": "positive", "published_at": "2026-08-31"}] * 4,
            "broker_reports": [{"title": "리포트" * 80, "summary": "요약" * 200}] * 3,
            "recent_disclosures": [{"report_name": "공시" * 80, "receipt_date": "2026-08-31"}] * 3,
        }

    def test_stock_context_is_bounded_and_preserves_decision_facts(self):
        compact = compact_auto_stock_context(self._stock("005930"))
        self.assertEqual(compact["code"], "005930")
        self.assertEqual(compact["smart_score"], 81)
        self.assertLess(len(json.dumps(compact, ensure_ascii=False)), 2500)
        self.assertLessEqual(len(compact["news"]), 2)

    def test_holdings_and_candidates_are_split_into_separate_batches(self):
        owned = [self._stock(f"{index:06d}") for index in range(20)]
        candidates = [self._stock(f"1{index:05d}") for index in range(15)]
        batches = build_auto_decision_batches(owned, candidates, holding_review=False)
        self.assertEqual([row["kind"] for row in batches], ["owned", "owned", "candidates"])
        self.assertEqual([len(row["owned"]) for row in batches], [10, 10, 0])
        self.assertEqual(len(batches[-1]["candidates"]), 15)

    def test_holding_review_never_adds_candidate_batches(self):
        batches = build_auto_decision_batches([], [self._stock("005930")], holding_review=True)
        self.assertEqual(batches, [])

    def test_learning_memory_is_reduced_to_reusable_pattern_summary(self):
        memory = compact_learning_memory({
            "policy_version": 2,
            "policy": "긴 정책" * 1000,
            "recent_adverse_cases": [{"lessons": ["긴 학습" * 1000]}],
            "recurring_patterns": [{"tag": "weak_flow", "count": 3, "stock_count": 2, "adjustment_ready": True}],
        })
        self.assertNotIn("recent_adverse_cases", memory)
        self.assertTrue(memory["recurring_patterns"][0]["adjustment_ready"])

    def test_only_response_completeness_errors_are_recoverable(self):
        self.assertTrue(is_recoverable_gbot_completeness_error("AI 응답에서 유효한 JSON 객체를 찾지 못했습니다."))
        self.assertTrue(is_recoverable_gbot_completeness_error("Gbot이 보유종목 판단을 누락했습니다: 005930"))
        self.assertFalse(is_recoverable_gbot_completeness_error("Gemini API Key가 설정되지 않았습니다."))

    def test_contract_defects_are_safe_response_errors_not_connection_errors(self):
        self.assertTrue(is_recoverable_gbot_response_error("Gbot 응답 무결성 검사 실패: 001450 확신도 형식 오류"))
        self.assertTrue(is_recoverable_gbot_response_error("Gbot 응답의 decisions 형식이 배열이 아닙니다."))
        self.assertFalse(is_recoverable_gbot_response_error("Gemini API Key가 설정되지 않았습니다."))


if __name__ == "__main__":
    unittest.main()
