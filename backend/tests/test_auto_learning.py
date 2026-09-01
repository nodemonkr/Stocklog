import unittest

from app.auto_learning import (
    aggregate_learning_patterns,
    apply_learning_risk_adjustments,
    build_learning_memory,
    candidate_learning_risk,
    diagnostic_health,
    should_review_outcome,
)


class AutoLearningRulesTest(unittest.TestCase):
    def test_small_early_loss_is_not_failure(self):
        ready, reason = should_review_outcome(age_minutes=20, current_return_pct=-1.2, max_drawdown_pct=-1.5)
        self.assertFalse(ready)
        self.assertEqual(reason, "")

    def test_material_two_hour_loss_is_reviewed(self):
        ready, _ = should_review_outcome(age_minutes=130, current_return_pct=-3.2, max_drawdown_pct=-3.8)
        self.assertTrue(ready)

    def test_closed_loss_is_reviewed(self):
        ready, reason = should_review_outcome(age_minutes=15, current_return_pct=-0.7, max_drawdown_pct=-0.8,
                                              closed=True, realized_return_pct=-0.7)
        self.assertTrue(ready)
        self.assertIn("손실 청산", reason)

    def test_single_loss_does_not_become_recurring_pattern(self):
        rows = aggregate_learning_patterns([
            {"stock_name": "A", "failure_tags": ["weak_flow", "timing_error"]}
        ], min_repeat=2)
        self.assertEqual(rows, [])

    def test_repeated_pattern_is_aggregated(self):
        cases = [
            {"stock_name": "A", "failure_tags": ["weak_flow", "timing_error"]},
            {"stock_name": "B", "failure_tags": ["weak_flow"]},
        ]
        rows = aggregate_learning_patterns(cases, min_repeat=2)
        self.assertEqual(rows[0]["tag"], "weak_flow")
        self.assertEqual(rows[0]["count"], 2)

    def test_memory_keeps_recent_but_only_repeated_as_pattern(self):
        mem = build_learning_memory([
            {"stock_code": "000001", "stock_name": "A", "outcome_label": "loss", "current_return_pct": -4,
             "failure_tags": ["weak_flow"], "lessons": ["수급 약화 재확인"]},
            {"stock_code": "000002", "stock_name": "B", "outcome_label": "loss", "current_return_pct": -3,
             "failure_tags": ["weak_flow"], "lessons": []},
        ])
        self.assertEqual(mem["reviewed_loss_cases"], 2)
        self.assertEqual(mem["recurring_patterns"][0]["tag"], "weak_flow")
        self.assertEqual(len(mem["recent_adverse_cases"]), 2)

    def test_drawdown_is_memory_but_recovered_case_is_not(self):
        mem = build_learning_memory([
            {"stock_code": "A", "outcome_label": "drawdown", "current_return_pct": -4, "failure_tags": ["timing_error"]},
            {"stock_code": "B", "outcome_label": "recovered", "current_return_pct": 2, "failure_tags": ["timing_error"]},
        ])
        self.assertEqual(mem["reviewed_adverse_cases"], 1)
        self.assertEqual(mem["reviewed_loss_cases"], 0)
        self.assertEqual(len(mem["recent_adverse_cases"]), 1)

    def test_normal_variation_and_post_entry_event_are_not_reused(self):
        cases = [
            {
                "stock_code": "A", "outcome_label": "loss", "failure_tags": ["weak_flow"],
                "review": {"verdict": "normal_variation", "root_causes": [{"tag": "weak_flow", "severity": "high"}]},
            },
            {
                "stock_code": "B", "outcome_label": "loss", "failure_tags": ["post_entry_event"],
                "review": {"verdict": "mixed", "root_causes": [{"tag": "post_entry_event", "severity": "high"}]},
            },
        ]
        mem = build_learning_memory(cases)
        self.assertEqual(mem["actionable_cases"], 0)
        self.assertEqual(mem["recurring_patterns"], [])

    def test_same_stock_same_day_scale_ins_are_one_episode(self):
        cases = [
            {"stock_code": "A", "entry_at": "2026-08-01T09:10:00", "failure_tags": ["weak_flow"]},
            {"stock_code": "A", "entry_at": "2026-08-01T14:10:00", "failure_tags": ["weak_flow"]},
        ]
        self.assertEqual(aggregate_learning_patterns(cases, min_repeat=2), [])

    def test_two_repeats_warn_but_do_not_apply_deterministic_penalty(self):
        memory = build_learning_memory([
            {"stock_code": "A", "entry_at": "2026-08-01", "outcome_label": "loss", "failure_tags": ["weak_flow"]},
            {"stock_code": "B", "entry_at": "2026-08-02", "outcome_label": "loss", "failure_tags": ["weak_flow"]},
        ])
        risk = candidate_learning_risk({"foreign_net_5d": -10, "institution_net_5d": -20}, memory)
        self.assertEqual(risk["mode"], "warning")
        self.assertEqual(risk["confidence_penalty"], 0)

    def test_three_independent_cross_stock_repeats_adjust_buy_confidence(self):
        memory = build_learning_memory([
            {"stock_code": "A", "entry_at": "2026-08-01", "outcome_label": "loss", "current_return_pct": -3,
             "failure_tags": ["weak_flow"],
             "entry_candidate": {"foreign_net_5d": -5, "institution_net_5d": -8}},
            {"stock_code": "B", "entry_at": "2026-08-02", "outcome_label": "loss", "current_return_pct": -4,
             "failure_tags": ["weak_flow"],
             "entry_candidate": {"foreign_net_5d": -4, "institution_net_5d": -9}},
            {"stock_code": "A", "entry_at": "2026-08-03", "outcome_label": "loss", "current_return_pct": -2,
             "failure_tags": ["weak_flow"],
             "entry_candidate": {"foreign_net_5d": -6, "institution_net_5d": -7}},
        ])
        candidates = [{"code": "C", "foreign_net_5d": -10, "institution_net_5d": -20,
                       "flow_data_date": "2099-01-01"}]
        adjusted = apply_learning_risk_adjustments(
            [{"code": "C", "action": "buy", "confidence": 82}], candidates, memory,
        )
        self.assertEqual(adjusted[0]["_gbot_confidence"], 82)
        self.assertEqual(adjusted[0]["_learning_penalty"], 2)
        self.assertEqual(adjusted[0]["confidence"], 80)

    def test_non_matching_candidate_is_not_penalized(self):
        memory = build_learning_memory([
            {"stock_code": "A", "entry_at": "2026-08-01", "outcome_label": "loss", "failure_tags": ["weak_flow"]},
            {"stock_code": "B", "entry_at": "2026-08-02", "outcome_label": "loss", "failure_tags": ["weak_flow"]},
            {"stock_code": "C", "entry_at": "2026-08-03", "outcome_label": "loss", "failure_tags": ["weak_flow"]},
        ])
        risk = candidate_learning_risk({"foreign_net_5d": 10, "institution_net_5d": 20}, memory)
        self.assertEqual(risk["mode"], "none")
        self.assertEqual(risk["confidence_penalty"], 0)

    def test_matching_wins_can_disprove_a_failure_pattern(self):
        weak_flow = {"foreign_net_5d": -10, "institution_net_5d": -20, "flow_data_date": "2099-01-01"}
        memory = build_learning_memory([
            {"stock_code": "A", "entry_at": "2026-08-01", "outcome_label": "loss", "current_return_pct": -4,
             "failure_tags": ["weak_flow"], "entry_candidate": weak_flow},
            {"stock_code": "B", "entry_at": "2026-08-02", "outcome_label": "loss", "current_return_pct": -3,
             "failure_tags": ["weak_flow"], "entry_candidate": weak_flow},
            {"stock_code": "C", "entry_at": "2026-08-03", "outcome_label": "loss", "current_return_pct": -2,
             "failure_tags": ["weak_flow"], "entry_candidate": weak_flow},
            {"stock_code": "D", "entry_at": "2026-08-04", "outcome_label": "win", "current_return_pct": 8,
             "entry_candidate": weak_flow},
            {"stock_code": "E", "entry_at": "2026-08-05", "outcome_label": "win", "current_return_pct": 7,
             "entry_candidate": weak_flow},
        ])
        pattern = memory["recurring_patterns"][0]
        self.assertEqual(pattern["matched_adverse_rate_pct"], 60.0)
        self.assertEqual(pattern["validation"], "counterexamples_present")
        self.assertFalse(pattern["adjustment_ready"])
        self.assertEqual(candidate_learning_risk(weak_flow, memory)["confidence_penalty"], 0)

    def test_stale_current_data_never_receives_deterministic_penalty(self):
        entry = {"foreign_net_5d": -10, "institution_net_5d": -20}
        memory = build_learning_memory([
            {"stock_code": "A", "entry_at": "2026-08-01", "outcome_label": "loss", "current_return_pct": -3,
             "failure_tags": ["weak_flow"], "entry_candidate": entry},
            {"stock_code": "B", "entry_at": "2026-08-02", "outcome_label": "loss", "current_return_pct": -4,
             "failure_tags": ["weak_flow"], "entry_candidate": entry},
            {"stock_code": "C", "entry_at": "2026-08-03", "outcome_label": "loss", "current_return_pct": -5,
             "failure_tags": ["weak_flow"], "entry_candidate": entry},
        ])
        risk = candidate_learning_risk({**entry, "flow_data_date": "2020-01-01"}, memory)
        self.assertEqual(risk["mode"], "warning")
        self.assertFalse(risk["matched_patterns"][0]["data_fresh"])
        self.assertEqual(risk["confidence_penalty"], 0)

    def test_diagnostic_warns_when_enabled_but_no_cycles(self):
        health = diagnostic_health(watcher_running=True, heartbeat_age_seconds=10, enabled=True, market_open=True,
                                   today_cycles=0, error_cycles=0)
        self.assertEqual(health["level"], "warning")


if __name__ == "__main__":
    unittest.main()
