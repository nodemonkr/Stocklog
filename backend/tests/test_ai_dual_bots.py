import asyncio

import pytest

from backend.app.ai_analyst import HybridAnalyst, DualAnalysisUnavailable, build_dual_bot_views


def _context():
    return {
        "company":{"name":"테스트","code":"000001"},
        "metrics":{"revenue_growth_pct":10.0,"operating_margin_pct":8.0,"roe_pct":12.0,"per":9.0,"pbr":0.9},
        "peer":{"median":{"per":13.0,"pbr":1.2,"roe":9.0}},
        "financials":[{"period":"2026-2Q","revenue":100000000000,"operating_profit":8000000000,"net_income":6000000000,"equity":50000000000,"revenue_change_pct":10.0,"operating_profit_change_pct":12.0,"net_income_change_pct":8.0,"debt_ratio_pct":70.0}],
        "momentum":{"return_20d_pct":4.0,"return_60d_pct":6.0,"price_vs_ma20":"above","price_vs_ma60":"above"},
        "supply_demand":{"latest_period":{"days":5,"foreign_institution_net":100000,"foreign_net":60000,"institution_net":40000}},
        "news":{"count":4,"sentiment_counts":{"positive":2,"neutral":1,"negative":1}},
        "reports":{"items":[{"sentiment":"positive"}]},
        "disclosures":{"items":[{"name":"분기보고서"}]},
    }


def _opinion(verdict, confidence, prefix):
    return {
        "verdict":verdict,
        "confidence":confidence,
        "headline":f"{prefix} 독립 판단",
        "executive_summary":f"{prefix}이 실제 데이터를 기준으로 독립 분석했습니다.",
        "positive_factors":[f"{prefix} 긍정 근거 {i}" for i in range(1,7)],
        "risk_factors":[f"{prefix} 주의 근거 {i}" for i in range(1,7)],
        "watch_conditions":[f"{prefix} 조건 {i}" for i in range(1,6)],
    }


class FakeGbot:
    model="g-internal"

    async def analyze(self, context):
        return _opinion("buy_bias",78,"Gbot"), {"provider":"internal-g","model":self.model,"fallback":False}

    async def finalize_from_obot(self, context, o):
        assert o["headline"].startswith("Obot")
        result=_opinion("buy_bias",79,"Gbot")
        result["model_consensus"]={"status":"mixed","summary":"Obot 의견과 정량 데이터를 비교했습니다."}
        return result, {"provider":"internal-g-final","model":self.model,"fallback":False}


class FakeObot:
    model="o-internal"

    async def analyze(self, context):
        return _opinion("wait",69,"Obot"), {"provider":"internal-o","model":self.model,"fallback":False}

    async def analyze_fast_risk(self, context, *, progress_callback=None):
        if progress_callback:
            progress_callback("obot_running", {"phase":"generating","received_chars":120,"message":"테스트 Obot 생성 중"})
        return _opinion("wait",69,"Obot"), {"provider":"internal-o","model":self.model,"fallback":False,"fast_risk_pass":True}


class BrokenObot(FakeObot):
    async def analyze_fast_risk(self, context, *, progress_callback=None):
        raise RuntimeError("offline")


def test_bot_views_use_stocklog_branding_only():
    views=build_dual_bot_views(_opinion("buy_bias",80,"A"),_opinion("wait",70,"B"))
    assert views["gbot"]["label"] == "StockLog Gbot"
    assert views["obot"]["label"] == "StockLog Obot"
    assert views["agreement"]["status"] == "mixed"


def test_premium_dual_analysis_requires_and_preserves_both_opinions():
    analyst=HybridAnalyst("dummy")
    analyst.gemini=FakeGbot()
    analyst.ollama=FakeObot()
    analyst.gemini_stage_timeout=2
    analyst.ollama_stage_timeout=2
    analyst.synthesis_timeout=2
    result,meta=asyncio.run(analyst.analyze(_context(),require_dual=True))
    assert result["dual_analysis"] is True
    assert result["bot_views"]["gbot"]["verdict"] == "buy_bias"
    assert result["bot_views"]["obot"]["verdict"] == "wait"
    assert result["analysis_pipeline"] == "obot_then_gbot"
    assert result["model_consensus"]["gbot_verdict"] == "buy_bias"
    assert result["model_consensus"]["obot_verdict"] == "wait"
    assert meta["dual_complete"] is True


def test_premium_dual_analysis_never_silently_falls_back_to_one_bot():
    analyst=HybridAnalyst("dummy")
    analyst.gemini=FakeGbot()
    analyst.ollama=BrokenObot()
    analyst.gemini_stage_timeout=2
    analyst.ollama_stage_timeout=2
    with pytest.raises(DualAnalysisUnavailable):
        asyncio.run(analyst.analyze(_context(),require_dual=True))



def test_premium_pipeline_reports_obot_then_gbot_then_verifying():
    analyst=HybridAnalyst("dummy")
    analyst.gemini=FakeGbot()
    analyst.ollama=FakeObot()
    analyst.gemini_stage_timeout=2
    analyst.ollama_stage_timeout=2
    stages=[]
    def capture(stage, detail=None):
        stages.append(stage)
    asyncio.run(analyst.analyze(_context(),require_dual=True,progress_callback=capture))
    assert stages[0] == "obot_running"
    assert "obot_completed" in stages
    assert "gbot_running" in stages
    assert "gbot_completed" in stages
    assert stages[-1] == "verifying"
