import unittest

from backend.app.auto_trading_safety import GbotDecisionContractError, validate_gbot_decisions


def _decision(code="005930", action="buy", confidence=82):
    return {
        "code": code,
        "action": action,
        "confidence": confidence,
        "reason": "가격과 수급, 실적 데이터를 함께 확인한 결과 현재 조건에서 유효한 판단입니다.",
        "evidence": ["재무·밸류 근거 확인", "가격 모멘텀 확인", "수급·뉴스 근거 확인"],
        "risks": ["시장 변동성"],
        "exit_plan": "투자 논리 훼손 또는 위험 신호 발생 시 재평가합니다.",
    }


class AutoTradingSafetyTests(unittest.TestCase):
    def test_candidate_buy_is_accepted(self):
        result = validate_gbot_decisions([_decision()], candidate_codes={"005930"}, owned_codes=set())
        self.assertEqual(result.decisions[0]["code"], "005930")
        self.assertTrue(result.coverage["whitelist_enforced"])

    def test_outside_candidate_buy_fails_closed(self):
        with self.assertRaisesRegex(GbotDecisionContractError, "후보/보유 목록 밖"):
            validate_gbot_decisions([_decision(code="000660")], candidate_codes={"005930"}, owned_codes=set())

    def test_malformed_actionable_decision_fails_closed(self):
        row = _decision()
        row["evidence"] = []
        with self.assertRaisesRegex(GbotDecisionContractError, "근거"):
            validate_gbot_decisions([row], candidate_codes={"005930"}, owned_codes=set())

    def test_empty_response_with_inputs_is_not_healthy(self):
        with self.assertRaisesRegex(GbotDecisionContractError, "판단이 0건"):
            validate_gbot_decisions([], candidate_codes={"005930"}, owned_codes=set())

    def test_missing_owned_position_fails_closed(self):
        with self.assertRaisesRegex(GbotDecisionContractError, "보유종목 판단을 누락"):
            validate_gbot_decisions([_decision(code="005930")], candidate_codes={"005930"}, owned_codes={"000660"})

    def test_holding_review_accepts_reduce_for_owned_stock(self):
        row = _decision(code="000660", action="reduce")
        row["reduce_pct"] = 50
        result = validate_gbot_decisions([row], candidate_codes=set(), owned_codes={"000660"}, holding_review=True)
        self.assertEqual(result.decisions[0]["action"], "reduce")

    def test_non_actionable_holding_without_confidence_is_safely_normalized(self):
        row = _decision(code="000660", action="hold")
        row.pop("confidence")
        row["evidence"] = []
        row["risks"] = []
        row["exit_plan"] = ""
        result = validate_gbot_decisions([row], candidate_codes=set(), owned_codes={"000660"})
        self.assertEqual(result.decisions[0]["confidence"], 0)

    def test_actionable_confidence_percent_string_is_normalized(self):
        row = _decision(confidence="82%")
        row["allocation_pct"] = "25%"
        result = validate_gbot_decisions([row], candidate_codes={"005930"}, owned_codes=set())
        self.assertEqual(result.decisions[0]["confidence"], 82)
        self.assertEqual(result.decisions[0]["allocation_pct"], 25)

    def test_actionable_confidence_fraction_is_normalized(self):
        result = validate_gbot_decisions([_decision(confidence=0.82)], candidate_codes={"005930"}, owned_codes=set())
        self.assertAlmostEqual(result.decisions[0]["confidence"], 82)

    def test_actionable_missing_confidence_still_fails_closed(self):
        row = _decision()
        row.pop("confidence")
        with self.assertRaisesRegex(GbotDecisionContractError, "확신도 형식 오류"):
            validate_gbot_decisions([row], candidate_codes={"005930"}, owned_codes=set())

    def test_numeric_stock_code_restores_leading_zero_only_inside_whitelist(self):
        row = _decision(code=1450, action="hold")
        row["evidence"] = []
        row["risks"] = []
        row["exit_plan"] = ""
        result = validate_gbot_decisions([row], candidate_codes=set(), owned_codes={"001450"})
        self.assertEqual(result.decisions[0]["code"], "001450")

    def test_reduce_percentage_string_is_normalized(self):
        row = _decision(code="000660", action="reduce")
        row["reduce_pct"] = "50%"
        result = validate_gbot_decisions([row], candidate_codes=set(), owned_codes={"000660"}, holding_review=True)
        self.assertEqual(result.decisions[0]["reduce_pct"], 50)


if __name__ == "__main__":
    unittest.main()
