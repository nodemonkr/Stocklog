from backend.app.ai_analyst import finalize_deep_result


def _context():
    return {
        "company":{"name":"테스트","code":"000001"},
        "metrics":{"revenue_growth_pct":12.0,"operating_margin_pct":8.0,"roe_pct":11.0,"per":9.0,"pbr":0.8,"dividend_yield_pct":2.0,"market_cap_억원":5000},
        "peer":{"median":{"per":14.0,"pbr":1.2,"roe":8.0}},
        "financials":[{"period":"2026-2Q","revenue":100000000000,"operating_profit":8000000000,"net_income":6000000000,"equity":50000000000,"revenue_change_pct":10.0,"operating_profit_change_pct":15.0,"net_income_change_pct":12.0,"debt_ratio_pct":80.0,"equity_change_pct":5.0}],
        "momentum":{"return_20d_pct":4.0,"return_60d_pct":8.0,"price_vs_ma20":"above","price_vs_ma60":"above"},
        "supply_demand":{"latest_period":{"days":5,"foreign_institution_net":120000,"foreign_net":80000,"institution_net":40000}},
        "news":{"count":5,"sentiment_counts":{"positive":3,"neutral":1,"negative":1}},
        "reports":{"items":[{"sentiment":"positive"},{"sentiment":"neutral"}]},
        "disclosures":{"items":[{"name":"분기보고서"}]},
    }


def test_premium_analysis_has_detailed_both_sides_and_watch_conditions():
    result=finalize_deep_result({"verdict":"wait","positive_factors":[],"risk_factors":[],"watch_conditions":[]},_context())
    assert len(result["positive_factors"]) >= 5
    assert len(result["risk_factors"]) >= 5
    assert len(result["watch_conditions"]) >= 5
    assert "관망" in result["verdict_reason"]
    assert "위험 근거가 충분하지" not in " ".join(result["risk_factors"])


def test_quantitative_breakdown_and_reason_are_concrete():
    result=finalize_deep_result({"verdict":"wait","positive_factors":[],"risk_factors":[],"watch_conditions":[]},_context())
    rows=result.get("quantitative_breakdown") or []
    labels={x.get("label") for x in rows}
    assert {"기업 실적","가격 수준","수급","최근 추세","뉴스·리포트·공시"}.issubset(labels)
    reason=result.get("verdict_reason") or ""
    assert "관망" in reason
    assert "PER" in reason
    assert "외국인" in reason or "기관" in reason
    assert "20일" in reason
    assert len(result.get("positive_factors") or []) >= 5
    assert len(result.get("risk_factors") or []) >= 5


def test_final_verdict_rewrites_stale_llm_copy_and_exposes_balance():
    result=finalize_deep_result({
        "verdict":"wait",
        "headline":"테스트: 관망 의견입니다.",
        "executive_summary":"현재 판단은 관망입니다.",
        "positive_factors":[],"risk_factors":[],"watch_conditions":[]
    },_context())
    # This fixture has positive performance, valuation, flow, trend and public-info dimensions,
    # so the deterministic consistency layer upgrades wait -> buy_bias.
    assert result["verdict"] == "buy_bias"
    assert "매수 추천" in result["headline"]
    assert "관망" not in result["headline"]
    assert "매수 추천" in result["executive_summary"]
    assert "현재 판단은 관망" not in result["executive_summary"]
    assert result["decision_balance"]["positive"] >= 4
    assert result["decision_consistency"] == "aligned"
