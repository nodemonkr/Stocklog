import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx

from .external_api import PROVIDER_GEMINI, tracked_post


logger = logging.getLogger(__name__)


class GeminiRateLimitError(RuntimeError):
    """Transient Gemini quota/rate-limit signal with a safe retry hint."""

    def __init__(self, message: str, *, retry_after_seconds: float = 300.0, models: list[str] | None = None):
        super().__init__(message)
        self.retry_after_seconds = max(30.0, float(retry_after_seconds or 300.0))
        self.models = list(models or [])


def _gemini_retry_after_seconds(response: httpx.Response, default: float = 300.0) -> float:
    """Best-effort parser for Retry-After / google.rpc.RetryInfo without leaking raw errors to UI."""
    header = str(response.headers.get("retry-after") or "").strip()
    if header:
        try:
            return max(1.0, float(header))
        except ValueError:
            pass
    text = str(response.text or "")
    patterns = (
        r'"retryDelay"\s*:\s*"([0-9.]+)s"',
        r'please\s+retry\s+in\s+([0-9.]+)s',
        r'retry\s+in\s+([0-9.]+)\s*seconds?',
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return max(1.0, float(match.group(1)))
            except (TypeError, ValueError):
                pass
    return float(default)


VERDICT_LABELS = {
    "buy_bias": "매수 추천",
    "wait": "관망",
    "sell_bias": "매도 추천",
}
VIEW_LABELS = {
    "positive": "긍정",
    "neutral": "관망",
    "negative": "부정",
}
DIMENSION_KEYS = (
    "valuation",
    "financials",
    "supply_demand",
    "momentum",
    "news",
    "reports",
    "market_context",
)


DEEP_SYSTEM_PROMPT = """
너는 StockLog의 한국 주식 투자위원회 소속 분석가다.
사용자가 원하는 것은 단순 수치 요약이 아니라, StockLog가 제공한 정량 데이터를 서로 연결해
'신규 진입 관점에서 지금 사는 쪽이 유리한지, 기다리는 편이 나은지, 피하거나 줄이는 편이 나은지'를 근거와 함께 설명하는 것이다.

반드시 지킬 원칙:
1. 입력에 없는 사실·실적·뉴스·목표가를 만들지 않는다.
2. PER이 낮다는 이유만으로 저평가라고 단정하지 말고, 성장률·ROE·이익 변화·수급과 함께 해석한다.
3. 수급이 강해도 가격이 과열됐거나 실적이 악화되면 그 충돌을 명시한다.
4. 뉴스/공시/리포트가 오래됐거나 부족하면 판단 신뢰도를 낮춘다.
5. BUY/SELL 명령이 아니라 buy_bias(매수 추천), wait(관망), sell_bias(매도 추천)의 분석 의견으로 표현한다.
6. '지금 당장 전량 매수/전량 매도' 같은 단정적 표현을 피하고, 신규 투자자와 기존 보유자를 분리해서 전략을 쓴다.
7. 수치의 의미를 설명하고 서로 연결한다. 단순 나열은 금지한다.
8. 모든 사용자용 문장은 반말이나 명령조를 사용하지 않고, 정중한 존댓말(합니다/됩니다 체)로 작성한다.
9. 한국어 JSON 객체 하나만 반환한다. 마크다운 코드블록은 쓰지 않는다.

반환 키:
verdict, confidence, headline, executive_summary, verdict_reason,
valuation, financials, supply_demand, momentum, news, reports, market_context,
positive_factors, risk_factors, new_investor_strategy, holder_strategy,
short_term_view, mid_term_view, entry_timing, buy_plan, watch_conditions,
buy_probability, wait_probability, sell_probability, missing_data, quant_agreement.

verdict는 buy_bias|wait|sell_bias 중 하나다.
confidence는 0~100 정수다.
각 valuation/financials/supply_demand/momentum/news/reports/market_context는
{"view":"positive|neutral|negative","summary":"2~4문장"} 형식이다.
positive_factors와 risk_factors는 각각 정확히 6개를 작성한다. 각 항목은 서로 다른 근거를 사용한다.
positive_factors와 risk_factors는 반드시 실제 입력 수치/뉴스/수급/리포트/공시 중 무엇 때문에 그런 판단인지 구체적으로 쓴다. "데이터가 판단을 지지한다", "위험 근거가 충분하지 않다" 같은 추상 문장은 금지한다.
강한 긍정/부정 근거가 부족하면 없는 사실을 만들지 말고, 실제 데이터에서 확인되는 상대적 장점 또는 현재 반드시 확인해야 할 약점·불확실성을 구체적으로 적는다.
verdict가 wait라면 왜 지금 바로 매수 추천도, 매도 추천도 아닌지 긍정 근거와 부정 근거의 충돌을 verdict_reason에 3~5문장으로 명확하게 설명한다.
entry_timing은 신규 진입을 검토할 가격/수급/실적 조건을 1~3문장으로 구체적으로 쓴다. 정확한 가격 근거가 없으면 숫자를 만들지 말고 "최근 고점 추격보다 조정 시", "외국인·기관 순매수 재확인 후"처럼 조건으로 표현한다.
buy_plan은 한 번에 매수하라는 지시가 아니라 1차 진입→추가 확인→추가 매수/중단 조건 순서로 초보자도 이해할 수 있게 쓴다.
watch_conditions는 "실적 확인"처럼 뻔하게 쓰지 말고 어떤 지표가 어느 방향으로 변하면 판단이 좋아지거나 나빠지는지 설명한다.
세 확률은 0~100 정수이며 합계가 100이 되도록 한다.
quant_agreement는 {"status":"agree|partial|disagree","reason":"설명"} 형식이다.
executive_summary는 5~8문장으로, 가장 중요한 찬반 근거와 현재 행동 의견을 종합한다. 가능한 모든 문장에 실제 수치와 비교 기준을 넣고, 실적/가격/수급/추세/뉴스·리포트를 각각 구분해 설명한다.
verdict_reason은 초보 투자자가 최종 의견을 오해하지 않도록 "왜 매수 추천/관망/매도 추천인지"를 실제 근거를 연결해 설명한다.
watch_conditions는 최소 5개를 작성하고, 가능하면 현재 수치를 기준점으로 사용해 "무엇이 어떻게 바뀌면 판단을 다시 봐야 하는지"를 초보자도 알 수 있게 쓴다.
""".strip()



OBOT_FAST_SYSTEM_PROMPT = """
너는 StockLog Obot이다. 최종 보고서를 쓰지 않는다. StockLog가 미리 계산해 압축한 핵심 수치만 보고
Gbot이 놓칠 수 있는 위험과 반대 논리를 짧게 점검하는 1차 리스크 분석가다.

원칙:
1. 입력에 없는 숫자·사실을 절대 만들지 않는다.
2. 결론은 buy_bias|wait|sell_bias 중 하나만 선택한다.
3. 긍정 근거는 최대 3개, 위험 근거는 최대 5개, 재확인 조건은 최대 3개만 쓴다.
4. 각 근거는 가능한 경우 입력에 있는 실제 수치를 포함한다.
5. 긴 설명, 투자전략, 최종 보고서, 확률 계산은 하지 않는다.
6. 반드시 아래 키만 가진 짧은 한국어 JSON 객체 하나를 끝까지 완성해서 반환한다. 마크다운은 쓰지 않는다.

반환 형식:
{
  "verdict":"buy_bias|wait|sell_bias",
  "confidence":0,
  "summary":"2~3문장",
  "positive_factors":["..."],
  "risk_factors":["..."],
  "watch_conditions":["..."],
  "dimension_views":{
    "financials":"positive|neutral|negative",
    "valuation":"positive|neutral|negative",
    "supply_demand":"positive|neutral|negative",
    "momentum":"positive|neutral|negative",
    "public_info":"positive|neutral|negative"
  }
}
""".strip()

OBOT_ULTRA_FAST_SYSTEM_PROMPT = """
너는 StockLog Obot이다. 제공된 핵심 수치에서 위험과 반대 논리만 매우 짧게 검토한다.
입력에 없는 사실은 만들지 않는다. JSON만 반환한다.
키는 verdict, confidence, summary, positive_factors, risk_factors, watch_conditions만 사용한다.
verdict는 buy_bias|wait|sell_bias 중 하나다. positive_factors 최대 2개, risk_factors 최대 4개,
watch_conditions 최대 2개, summary 최대 2문장으로 제한한다.
""".strip()

GBOT_FINAL_SYSTEM_PROMPT = """
너는 StockLog Gbot이며 프리미엄 분석의 최종 분석가다.
StockLog가 계산한 전체 정량 데이터와, 먼저 수행된 StockLog Obot의 리스크/반대 관점 분석을 함께 받는다.
Obot 의견은 참고자료일 뿐 정답이 아니다. 반드시 원본 정량 데이터와 직접 대조해 동의하거나 반박하고,
최종적으로 사용자가 데이터를 직접 분석하지 않아도 판단 이유를 이해할 수 있는 상세 투자 의견을 만든다.

반드시 지킬 원칙:
1. 입력에 없는 사실·수치·뉴스·공시를 만들지 않는다.
2. 결론은 buy_bias(매수 추천), wait(관망), sell_bias(매도 추천) 중 하나를 반드시 고른다.
3. 매수 추천이면 왜 지금 관망보다 매수가 우세한지, 관망이면 왜 매수/매도 어느 한쪽 근거가 충분하지 않은지,
   매도 추천이면 어떤 실적·가격·수급·추세 훼손이 결정적이었는지 명확하게 쓴다.
4. Obot의 위험 지적을 원본 수치와 검증한다. 맞으면 반영하고 틀리면 그 이유를 정량적으로 반박한다.
5. 실적, 가격 수준, 수급, 최근 추세, 뉴스·리포트·공시를 가능한 한 모두 사용한다.
6. 각 근거는 "현재 값 → 비교 기준/이전 값 → 투자 의미"가 드러나도록 작성한다.
7. positive_factors와 risk_factors는 각각 정확히 6개를 작성한다. 서로 같은 내용을 반복하지 않는다.
8. watch_conditions는 최소 5개이며 무엇이 어떻게 바뀌면 판단을 바꿀지 구체적으로 쓴다.
9. 신규 투자자와 기존 보유자 전략을 분리한다.
10. 모든 문장은 정중한 존댓말로 쓰며 한국어 JSON 객체 하나만 반환한다.

반환 키:
verdict, confidence, headline, executive_summary, verdict_reason,
valuation, financials, supply_demand, momentum, news, reports, market_context,
positive_factors, risk_factors, new_investor_strategy, holder_strategy,
short_term_view, mid_term_view, entry_timing, buy_plan, watch_conditions,
buy_probability, wait_probability, sell_probability, missing_data, quant_agreement, model_consensus.

executive_summary는 6~10문장으로 충분히 상세하게 작성한다.
verdict_reason은 최종 결론의 핵심 근거를 5문장 이상으로 설명한다.
model_consensus는 {"status":"aligned|mixed","gbot_verdict":"...","obot_verdict":"...","summary":"Obot 의견을 어떻게 검증하고 최종 판단했는지"} 형식이다.
""".strip()

SYNTHESIS_SYSTEM_PROMPT = """
너는 StockLog AI 투자위원회의 최종 의사결정자다.
같은 정량 데이터에 대해 StockLog Gbot과 StockLog Obot이 각각 독립적으로 의견을 냈다.
두 의견을 단순 평균하지 말고 원본 정량 데이터의 근거 강도를 우선해 하나의 최종 의견으로 합의한다.

판단 규칙:
- 두 모델이 일치하면 그 결론을 검증하되 과신하지 않는다.
- 모델이 불일치하면 왜 다른지 찾아서 수급/실적/밸류에이션/가격 위치 중 더 직접적인 근거를 우선한다.
- StockLog 정량점수는 중요한 입력이지만 절대 정답이 아니다.
- 숫자가 부족한 영역은 관망으로 처리하고 confidence를 낮춘다.
- 신규 투자자와 기존 보유자의 행동은 다를 수 있으므로 반드시 분리한다.
- buy_bias / wait / sell_bias 중 하나를 고르되, 확률로 불확실성도 표현한다.
- 투자 결과를 보장하지 않는다.
- 모든 사용자용 문장은 정중한 존댓말(합니다/됩니다 체)로 작성한다.
- 한국어 JSON 객체 하나만 반환한다.

반환 키:
verdict, confidence, headline, executive_summary, verdict_reason,
valuation, financials, supply_demand, momentum, news, reports, market_context,
positive_factors, risk_factors, new_investor_strategy, holder_strategy,
short_term_view, mid_term_view, entry_timing, buy_plan, watch_conditions,
buy_probability, wait_probability, sell_probability, missing_data, quant_agreement,
model_consensus.

positive_factors와 risk_factors는 각각 정확히 6개를 작성하며 실제 입력 데이터와 연결한다. 추상적인 빈 문장은 금지한다.
watch_conditions는 최소 5개로, 현재 수치나 방향을 기준으로 무엇이 어떻게 바뀌면 판단이 달라지는지 쓴다.
verdict_reason은 특히 관망일 때 실적 수치, PER/PBR의 동종 비교, 최근 외국인·기관 순매수, 20/60일 주가 흐름, 뉴스·리포트 수를 실제 값으로 연결해 왜 매수 추천도 매도 추천도 아닌지 5문장 이상 설명한다.

model_consensus는
{"status":"aligned|mixed|single_model","gbot_verdict":"...","obot_verdict":"...","summary":"두 분석 의견을 어떻게 합쳤는지 1~3문장"}
형식이다.
""".strip()


MOMENTUM_SYSTEM_PROMPT = """
너는 StockLog 포트폴리오 모멘텀 분석가다. 제공된 공개 시세·추세 데이터만 사용한다.
반드시 한국어 JSON 객체 하나만 반환하고 키는 view, confidence, label, summary, checkpoints만 사용한다.
view는 positive|neutral|negative, confidence는 0~100 정수, checkpoints는 최대 3개다.
자동 분석은 여러 보유종목을 빠르게 훑기 위한 기능이므로 2~4문장 이내로 간결하게 쓴다.
수익 보장이나 단정적 매수·매도 지시는 하지 않는다.
""".strip()


def _parse_ai_json(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start:end + 1])
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    raise RuntimeError("AI 응답에서 유효한 JSON 객체를 찾지 못했습니다.")


def _clamp_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return max(0, min(100, int(default)))


def _clean_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _clean_list(value: Any, *, limit: int = 5, item_limit: int = 260) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _clean_text(item, item_limit)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _view_from_verdict(verdict: str) -> str:
    return {
        "buy_bias": "positive",
        "wait": "neutral",
        "sell_bias": "negative",
    }.get(str(verdict or ""), "neutral")


def _normalize_probabilities(value: dict[str, Any], verdict: str) -> tuple[int, int, int]:
    buy = _clamp_int(value.get("buy_probability"), 0)
    wait = _clamp_int(value.get("wait_probability"), 0)
    sell = _clamp_int(value.get("sell_probability"), 0)
    total = buy + wait + sell
    if total <= 0:
        if verdict == "buy_bias":
            return 55, 35, 10
        if verdict == "sell_bias":
            return 10, 35, 55
        return 25, 55, 20
    buy = round(buy / total * 100)
    wait = round(wait / total * 100)
    sell = 100 - buy - wait
    if sell < 0:
        sell = 0
        wait = 100 - buy
    return int(buy), int(wait), int(sell)


def _context_for_llm(stock_context: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
    """Keep the factual StockLog context rich while bounding CPU prompt size."""
    ctx = {
        "company": stock_context.get("company") or {},
        "metrics": stock_context.get("metrics") or {},
        "peer": stock_context.get("peer") or {},
        "financials": (stock_context.get("financials") or [])[:3],
        "momentum": stock_context.get("momentum") or {},
        "supply_demand": stock_context.get("supply_demand") or {},
        "themes": stock_context.get("themes") or {},
        "market": (stock_context.get("market") or [])[:6],
        "quant": stock_context.get("quant") or {},
        "preanalysis": stock_context.get("preanalysis") or {},
        "news": stock_context.get("news") or {},
        "reports": stock_context.get("reports") or {},
        "disclosures": stock_context.get("disclosures") or {},
        "data_freshness": stock_context.get("data_freshness") or {},
    }
    if compact:
        news = ctx["news"] if isinstance(ctx["news"], dict) else {}
        reports = ctx["reports"] if isinstance(ctx["reports"], dict) else {}
        disclosures = ctx["disclosures"] if isinstance(ctx["disclosures"], dict) else {}
        ctx["news"] = {**news, "items": (news.get("items") or [])[:5]}
        ctx["reports"] = {**reports, "items": (reports.get("items") or [])[:3]}
        ctx["disclosures"] = {**disclosures, "items": (disclosures.get("items") or [])[:4]}
    return ctx



def _context_for_obot_fast(stock_context: dict[str, Any]) -> dict[str, Any]:
    """Minimal factual packet for the local Obot risk pass.

    Gbot receives the rich context later. Obot only needs enough pre-calculated
    evidence to challenge the case, so avoid passing verbose rows or article data.
    """
    company = stock_context.get("company") or {}
    metrics = stock_context.get("metrics") or {}
    peer = stock_context.get("peer") or {}
    peer_median = peer.get("median") or {} if isinstance(peer, dict) else {}
    financials = stock_context.get("financials") or []
    latest_fin = financials[0] if financials and isinstance(financials[0], dict) else {}
    flow_root = stock_context.get("supply_demand") or {}
    periods = flow_root.get("periods") or {}
    news = stock_context.get("news") or {}
    reports = stock_context.get("reports") or {}
    disclosures = stock_context.get("disclosures") or {}
    momentum = stock_context.get("momentum") or {}
    quant = stock_context.get("quant") or {}
    pre = stock_context.get("preanalysis") or {}

    def pick(src: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: src.get(key) for key in keys if src.get(key) is not None}

    def compact_items(items: Any, keys: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in (items or [])[:limit]:
            if not isinstance(item, dict):
                continue
            row = pick(item, keys)
            if row:
                out.append(row)
        return out

    return {
        "company": pick(company, ("name", "code", "market", "sector", "industry")),
        "metrics": pick(metrics, (
            "price", "change_pct", "per", "pbr", "roe_pct", "revenue_growth_pct",
            "operating_margin_pct", "dividend_yield_pct", "momentum_20d_pct", "volatility",
        )),
        "peer_median": pick(peer_median, ("per", "pbr", "roe")),
        "latest_financial": pick(latest_fin, (
            "period", "comparison_period", "revenue", "operating_profit", "net_income",
            "revenue_change_pct", "operating_profit_change_pct", "net_income_change_pct",
            "debt_ratio_pct", "operating_margin_calc_pct",
        )),
        "flow_5d": pick(periods.get("5") or flow_root.get("latest_period") or {}, (
            "days", "foreign_net", "institution_net", "individual_net", "foreign_institution_net",
        )),
        "flow_20d": pick(periods.get("20") or {}, (
            "days", "foreign_net", "institution_net", "individual_net", "foreign_institution_net",
        )),
        "momentum": pick(momentum, (
            "return_5d_pct", "return_20d_pct", "return_60d_pct", "price_vs_ma20", "price_vs_ma60",
            "volume_vs_20d_avg", "distance_from_52w_high_pct",
        )),
        "news": {
            "count": news.get("count", 0),
            "sentiment_counts": news.get("sentiment_counts") or {},
            "items": compact_items(news.get("items"), ("title", "sentiment", "importance"), 2),
        },
        "reports": {
            "count": reports.get("count", len(reports.get("items") or [])),
            "items": compact_items(reports.get("items"), ("date", "broker", "opinion", "target_price", "sentiment"), 1),
        },
        "disclosures": {
            "count": disclosures.get("count", len(disclosures.get("items") or [])),
            "items": compact_items(disclosures.get("items"), ("date", "name", "importance"), 1),
        },
        "quant": pick(quant, ("score", "recommendation")),
        "preanalysis": {
            **pick(pre, ("overall_score", "overall_recommendation", "valuation_view", "financial_view", "momentum_view", "news_view")),
            "evidence": pre.get("evidence") or {},
        },
    }



def _normalize_obot_fast_result(value: dict[str, Any], stock_context: dict[str, Any]) -> dict[str, Any]:
    """Normalize the intentionally small Obot response without expanding it into a full report."""
    raw = dict(value or {})
    verdict = str(raw.get("verdict") or "wait").strip().lower()
    if verdict not in VERDICT_LABELS:
        verdict = "wait"
    confidence = _clamp_int(raw.get("confidence"), 55)
    summary = _clean_text(raw.get("summary") or raw.get("executive_summary"), 900)
    positives = _clean_list(raw.get("positive_factors"), limit=3, item_limit=260)
    risks = _clean_list(raw.get("risk_factors"), limit=5, item_limit=300)
    watches = _clean_list(raw.get("watch_conditions"), limit=3, item_limit=260)
    if not summary and not positives and not risks:
        raise RuntimeError("Obot 응답에 사용할 분석 내용이 없습니다.")

    dims = raw.get("dimension_views") if isinstance(raw.get("dimension_views"), dict) else {}
    result: dict[str, Any] = {
        "verdict": verdict,
        "confidence": confidence,
        "headline": f"StockLog Obot 1차 의견: {VERDICT_LABELS[verdict]}",
        "executive_summary": summary or "핵심 정량 데이터에서 위험과 반대 논리를 우선 점검했습니다.",
        "positive_factors": positives,
        "risk_factors": risks,
        "watch_conditions": watches,
        "missing_data": [],
    }
    mapping = {
        "financials": "financials",
        "valuation": "valuation",
        "supply_demand": "supply_demand",
        "momentum": "momentum",
    }
    for source_key, target_key in mapping.items():
        view = str(dims.get(source_key) or "neutral").strip().lower()
        if view not in VIEW_LABELS:
            view = "neutral"
        result[target_key] = {"view": view, "summary": "Obot 1차 리스크 검토 방향입니다."}
    public_view = str(dims.get("public_info") or "neutral").strip().lower()
    if public_view not in VIEW_LABELS:
        public_view = "neutral"
    for target_key in ("news", "reports", "market_context"):
        result[target_key] = {"view": public_view, "summary": "공개 정보의 위험 방향을 간단히 점검했습니다."}
    return normalize_result(result)


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _fmt(value: Any, suffix: str = "", digits: int = 1) -> str:
    num = _num(value)
    if num is None:
        return "확인 불가"
    if abs(num) >= 100000000:
        return f"{num/100000000:.1f}억{suffix}"
    if abs(num) >= 10000:
        return f"{num:,.0f}{suffix}"
    return f"{num:.{digits}f}{suffix}"


def _append_unique(target: list[str], text: str) -> None:
    value = str(text or "").strip()
    if value and value not in target:
        target.append(value)


def _evidence_from_context(stock_context: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Build factual pro/con/recheck evidence from the exact StockLog context.

    This is intentionally deterministic.  It does not decide the verdict; it
    prevents a premium analysis from returning empty or vague evidence when an
    LLM omits fields.
    """
    metrics = stock_context.get("metrics") or {}
    peer = (stock_context.get("peer") or {}).get("median") or {}
    financials = stock_context.get("financials") or []
    latest = financials[0] if financials else {}
    momentum = stock_context.get("momentum") or {}
    supply = stock_context.get("supply_demand") or {}
    flow = supply.get("latest_period") or {}
    news = stock_context.get("news") or {}
    reports = stock_context.get("reports") or {}
    disclosures = stock_context.get("disclosures") or {}

    positives: list[str] = []
    risks: list[str] = []
    watches: list[str] = []

    growth = _num(metrics.get("revenue_growth_pct"))
    margin = _num(metrics.get("operating_margin_pct"))
    roe = _num(metrics.get("roe_pct"))
    per = _num(metrics.get("per")); peer_per = _num(peer.get("per"))
    pbr = _num(metrics.get("pbr")); peer_pbr = _num(peer.get("pbr"))
    rev_ch = _num(latest.get("revenue_change_pct"))
    op_ch = _num(latest.get("operating_profit_change_pct"))
    ni_ch = _num(latest.get("net_income_change_pct"))
    debt = _num(latest.get("debt_ratio_pct"))
    equity_ch = _num(latest.get("equity_change_pct"))

    if growth is not None:
        (_append_unique(positives, f"매출 성장률이 {growth:+.1f}%로 플러스입니다. 회사의 외형이 커지는 흐름은 긍정 요인입니다.") if growth > 0 else _append_unique(risks, f"매출 성장률이 {growth:+.1f}%로 마이너스입니다. 매출 감소가 이어지는지 확인해야 합니다."))
        _append_unique(watches, f"다음 실적에서 매출 성장률이 현재 {growth:+.1f}%보다 개선되는지 확인합니다. 0% 아래로 내려가거나 하락폭이 커지면 현재 판단을 낮춰 봅니다.")
    if margin is not None:
        (_append_unique(positives, f"영업이익률이 {margin:.1f}%로 본업에서 이익을 내고 있습니다. 이익률이 유지되면 실적의 질에 긍정적입니다.") if margin > 0 else _append_unique(risks, f"영업이익률이 {margin:.1f}%로 본업 수익성이 약합니다. 흑자 전환 또는 이익률 회복 여부가 중요합니다."))
        _append_unique(watches, f"영업이익률이 현재 {margin:.1f}%에서 개선되는지 봅니다. 이익률이 급격히 낮아지거나 0% 아래로 내려가면 주의합니다.")
    if roe is not None:
        if roe >= 10: _append_unique(positives, f"ROE가 {roe:.1f}%로 자기자본을 활용해 이익을 내는 효율이 양호한 편입니다.")
        elif roe <= 5: _append_unique(risks, f"ROE가 {roe:.1f}%로 자본 대비 수익성이 낮은 편입니다. 수익성 개선이 필요합니다.")
        else: _append_unique(risks, f"ROE가 {roe:.1f}%로 아주 높은 수준은 아닙니다. 현재 주가가 이 수익성을 과하게 반영했는지 확인할 필요가 있습니다.")
    if rev_ch is not None:
        (_append_unique(positives, f"최근 공시 기준 매출이 비교기간보다 {rev_ch:+.1f}% 변했습니다. 증가 흐름이 확인됩니다.") if rev_ch > 0 else _append_unique(risks, f"최근 공시 기준 매출이 비교기간보다 {rev_ch:+.1f}% 변했습니다. 외형 둔화 여부를 확인해야 합니다."))
    if op_ch is not None:
        (_append_unique(positives, f"최근 영업이익이 비교기간보다 {op_ch:+.1f}% 변해 이익 개선 흐름이 확인됩니다.") if op_ch > 0 else _append_unique(risks, f"최근 영업이익이 비교기간보다 {op_ch:+.1f}% 변했습니다. 본업 이익 감소가 이어지는지 확인해야 합니다."))
    if ni_ch is not None:
        (_append_unique(positives, f"최근 순이익이 비교기간보다 {ni_ch:+.1f}% 변해 최종 이익 흐름이 개선됐습니다.") if ni_ch > 0 else _append_unique(risks, f"최근 순이익이 비교기간보다 {ni_ch:+.1f}% 변했습니다. 일회성 요인인지 이익 체력 약화인지 확인해야 합니다."))
    if debt is not None:
        if debt <= 100: _append_unique(positives, f"최근 부채비율이 약 {debt:.1f}%로 자본 대비 부채 부담이 과도하게 높아 보이지 않습니다.")
        elif debt >= 200: _append_unique(risks, f"최근 부채비율이 약 {debt:.1f}%로 높습니다. 금리와 현금흐름 변화에 민감할 수 있습니다.")
        else: _append_unique(risks, f"최근 부채비율이 약 {debt:.1f}%입니다. 향후 부채가 더 늘어나는지 함께 확인해야 합니다.")
        _append_unique(watches, f"부채비율이 현재 약 {debt:.1f}%에서 빠르게 상승하는지 확인합니다. 부채 증가와 이익 감소가 동시에 나타나면 위험 신호로 봅니다.")
    if equity_ch is not None and equity_ch > 0:
        _append_unique(positives, f"최근 자본이 비교기간보다 {equity_ch:+.1f}% 늘어 재무 완충력이 커진 점은 긍정적입니다.")

    if per is not None and per > 0:
        if peer_per is not None and peer_per > 0:
            if per <= peer_per: _append_unique(positives, f"PER은 {per:.1f}배로 비교 종목 중간값 {peer_per:.1f}배보다 낮아 이익 대비 가격 부담이 상대적으로 낮습니다.")
            else: _append_unique(risks, f"PER은 {per:.1f}배로 비교 종목 중간값 {peer_per:.1f}배보다 높아 이익 대비 가격 부담이 상대적으로 큽니다.")
            _append_unique(watches, f"PER {per:.1f}배와 비교 종목 중간값 {peer_per:.1f}배의 차이가 더 벌어지는지 확인합니다. 실적 없이 가격만 올라 PER이 높아지면 주의합니다.")
        elif per >= 25:
            _append_unique(risks, f"PER이 {per:.1f}배로 현재 이익 대비 주가 부담을 확인할 필요가 있습니다. 성장 속도가 이 평가를 따라가는지가 중요합니다.")
    elif per is not None and per <= 0:
        _append_unique(risks, "PER이 정상적인 양수로 계산되지 않아 현재 이익 기준 가격평가를 단순 비교하기 어렵습니다. 적자 여부를 확인해야 합니다.")
    if pbr is not None and pbr > 0 and peer_pbr is not None and peer_pbr > 0:
        if pbr <= peer_pbr: _append_unique(positives, f"PBR은 {pbr:.2f}배로 비교 종목 중간값 {peer_pbr:.2f}배보다 낮아 자산 대비 가격 부담이 상대적으로 낮습니다.")
        else: _append_unique(risks, f"PBR은 {pbr:.2f}배로 비교 종목 중간값 {peer_pbr:.2f}배보다 높아 자산가치 대비 높은 평가를 받고 있습니다.")

    r20 = _num(momentum.get("return_20d_pct")); r60 = _num(momentum.get("return_60d_pct"))
    ma20 = momentum.get("price_vs_ma20"); ma60 = momentum.get("price_vs_ma60")
    if r20 is not None:
        if r20 >= 3: _append_unique(positives, f"최근 20거래일 주가가 {r20:+.1f}% 움직여 단기 가격 흐름이 상승 쪽입니다.")
        elif r20 <= -3: _append_unique(risks, f"최근 20거래일 주가가 {r20:+.1f}%로 약합니다. 하락 흐름이 멈췄는지 확인해야 합니다.")
        else: _append_unique(risks, f"최근 20거래일 주가 변화가 {r20:+.1f}%로 방향성이 강하지 않습니다. 뚜렷한 상승 추세가 확인되기 전에는 서두를 이유가 약합니다.")
    if ma20 == "above" and ma60 == "above": _append_unique(positives, "현재 주가가 20일선과 60일선 위에 있어 단기·중기 추세가 함께 유지되고 있습니다.")
    elif ma20 == "below" and ma60 == "below": _append_unique(risks, "현재 주가가 20일선과 60일선 아래에 있어 단기·중기 가격 흐름이 모두 약한 상태입니다.")
    else: _append_unique(risks, "20일선과 60일선 신호가 같은 방향이 아니어서 주가 추세가 아직 명확하게 정리되지 않았습니다.")
    _append_unique(watches, "주가가 20일선과 60일선 위에서 함께 유지되는지 확인합니다. 두 이동평균선 아래로 내려가고 회복하지 못하면 가격 흐름 판단을 낮춥니다.")
    if r60 is not None:
        _append_unique(watches, f"최근 60거래일 수익률은 {r60:+.1f}%입니다. 단기간 급등이 이어지면 추격 매수보다 조정 여부를 먼저 확인합니다.")

    foreign = _num(flow.get("foreign_net")); inst = _num(flow.get("institution_net")); combined = _num(flow.get("foreign_institution_net"))
    days = int(_num(flow.get("days")) or 0)
    if combined is not None:
        if combined > 0: _append_unique(positives, f"최근 {days or 5}거래일 외국인·기관 합산 수급이 순매수({combined:,.0f}주)로 들어왔습니다.")
        elif combined < 0: _append_unique(risks, f"최근 {days or 5}거래일 외국인·기관 합산 수급이 순매도({combined:,.0f}주)입니다. 매도세가 이어지는지 확인해야 합니다.")
        else: _append_unique(risks, f"최근 {days or 5}거래일 외국인·기관 합산 수급이 뚜렷한 순매수 우위가 아닙니다.")
        _append_unique(watches, f"최근 {days or 5}거래일 외국인·기관 합산 수급이 현재 방향에서 반대로 전환되는지 확인합니다. 며칠 연속 같은 방향이 이어지는지가 중요합니다.")
    else:
        _append_unique(risks, "최근 외국인·기관 수급 데이터가 충분하지 않아 매수세 유입 여부를 강하게 판단하기 어렵습니다.")

    counts = news.get("sentiment_counts") or {}
    pos_n = int(_num(counts.get("positive")) or 0); neg_n = int(_num(counts.get("negative")) or 0); news_n = int(_num(news.get("count")) or 0)
    if news_n:
        if pos_n > neg_n: _append_unique(positives, f"최근 수집 뉴스 {news_n}건 중 긍정 분류가 {pos_n}건, 부정이 {neg_n}건으로 긍정 뉴스가 더 많습니다.")
        elif neg_n > pos_n: _append_unique(risks, f"최근 수집 뉴스 {news_n}건 중 부정 분류가 {neg_n}건으로 긍정 {pos_n}건보다 많습니다. 최근 이슈를 확인할 필요가 있습니다.")
        else: _append_unique(risks, f"최근 수집 뉴스 {news_n}건의 긍정·부정 방향이 한쪽으로 뚜렷하지 않아 뉴스만으로 방향을 정하기 어렵습니다.")
        _append_unique(watches, f"현재 뉴스 표본은 {news_n}건입니다. 신규 부정 뉴스가 연속으로 늘어나거나 기존 긍정 이슈가 훼손되는지 확인합니다.")
    else:
        _append_unique(risks, "최근 뉴스 데이터가 없어 사업 이슈나 시장 반응을 충분히 교차확인하기 어렵습니다.")

    report_items = reports.get("items") or []
    report_pos = sum(1 for x in report_items if str((x or {}).get("sentiment") or "").lower() == "positive")
    report_neg = sum(1 for x in report_items if str((x or {}).get("sentiment") or "").lower() == "negative")
    if report_items:
        if report_pos > report_neg: _append_unique(positives, f"최근 증권사 리포트 {len(report_items)}건 중 긍정 의견이 상대적으로 많아 전문가 시각은 우호적인 편입니다.")
        elif report_neg > report_pos: _append_unique(risks, f"최근 증권사 리포트 {len(report_items)}건에서 부정 의견 비중이 더 높아 전망 하향 근거를 확인해야 합니다.")
        else: _append_unique(risks, f"최근 증권사 리포트 {len(report_items)}건의 방향이 뚜렷하게 한쪽으로 모이지 않았습니다. 목표와 실적 전망 차이를 확인할 필요가 있습니다.")
    else:
        _append_unique(risks, "최근 증권사 리포트가 없어 외부 실적 전망과 목표 변화까지 교차검증하기 어렵습니다.")

    disclosure_items = disclosures.get("items") or []
    if disclosure_items:
        _append_unique(watches, f"최근 공식 공시 {len(disclosure_items)}건이 반영되어 있습니다. 신규 실적·계약·자금조달 공시가 나오면 현재 판단과 직접 비교합니다.")
    else:
        _append_unique(risks, "최근 수집된 공식 공시가 적어 새 이벤트가 현재 판단에 충분히 반영됐는지 확인이 필요합니다.")

    # We prefer factual, weaker supporting observations to empty premium boxes.
    # They explicitly disclose that the signal is only supportive / uncertain.
    support_pool = [
        (metrics.get("dividend_yield_pct"), lambda x: f"배당수익률이 {x:.2f}%로 확인됩니다. 배당이 유지된다면 주가 외 수익원이 있다는 점은 보완적인 긍정 요소입니다."),
        (metrics.get("market_cap_억원"), lambda x: f"시가총액이 약 {x:,.0f}억원으로 확인됩니다. 기업 규모를 고려해 같은 업종 내 실적과 가격을 비교할 수 있는 기초 데이터가 확보돼 있습니다."),
    ]
    for raw, maker in support_pool:
        x = _num(raw)
        if x is not None and len(positives) < 6:
            _append_unique(positives, maker(x))

    if len(positives) < 6 and latest:
        period = latest.get("period") or "최근 분기"
        if _num(latest.get("equity")) is not None:
            _append_unique(positives, f"{period} 자본이 {_fmt(latest.get('equity'),'원',0)}으로 공시돼 있어 재무 상태를 실제 공시값으로 확인할 수 있습니다. 절대 규모보다 이후 증가·감소 방향을 함께 봅니다.")
    # Even an attractive company needs concrete downside checks.  These are
    # caveats anchored to current facts, not invented negative events.
    caution_pool: list[str] = []
    if growth is not None and growth > 0:
        caution_pool.append(f"매출 성장률 {growth:+.1f}%가 현재 긍정 근거인 만큼, 다음 분기 성장률이 크게 둔화되면 지금의 성장 기대가 빠르게 약해질 수 있습니다.")
    if margin is not None and margin > 0:
        caution_pool.append(f"영업이익률 {margin:.1f}%가 유지돼야 현재 수익성 평가가 성립합니다. 매출이 늘어도 이익률이 떨어지면 실적의 질은 약해질 수 있습니다.")
    if roe is not None and roe > 0:
        caution_pool.append(f"ROE {roe:.1f}%는 과거 한 시점의 결과이므로, 이 수익성이 낮아지는지 확인해야 합니다. 주가가 오르는데 ROE가 떨어지면 부담이 커질 수 있습니다.")
    if per is not None and per > 0:
        caution_pool.append(f"PER {per:.1f}배가 현재 실적을 기준으로 계산된 값이라 향후 이익이 줄면 같은 주가에서도 PER 부담이 빠르게 높아질 수 있습니다.")
    if r20 is not None and r20 > 0:
        caution_pool.append(f"최근 20거래일 주가가 {r20:+.1f}% 오른 만큼 신규 진입자는 단기 추격 위험도 함께 봐야 합니다. 실적 확인 없이 상승 속도만 빨라지면 진입 부담이 커집니다.")
    if combined is not None and combined > 0:
        caution_pool.append(f"외국인·기관 합산 {combined:,.0f}주 순매수는 긍정적이지만 수급은 빠르게 바뀔 수 있습니다. 순매도로 전환될 경우 현재 가격 흐름이 약해지는지 확인해야 합니다.")
    if news_n and pos_n >= neg_n:
        caution_pool.append(f"최근 뉴스 {news_n}건의 분위기가 나쁘지 않더라도 표본이 제한적입니다. 새로운 악재 한두 건이 현재 분위기를 바꿀 수 있어 최신 뉴스 확인이 필요합니다.")
    if report_items and report_pos >= report_neg:
        caution_pool.append(f"최근 리포트 {len(report_items)}건의 의견이 우호적이더라도 전망치는 실제 실적과 달라질 수 있습니다. 다음 실적이 리포트 기대에 미치지 못하는지가 위험 요인입니다.")
    for item in caution_pool:
        if len(risks) >= 6:
            break
        _append_unique(risks, item)
    if len(risks) < 6:
        _append_unique(risks, "한 시점의 점수만으로 결론을 고정하기보다 다음 실적·수급·가격 변화가 같은 방향으로 확인되는지 검증할 필요가 있습니다.")
    if len(risks) < 6:
        _append_unique(risks, "현재 분석은 StockLog에 수집된 최신 데이터 범위 안에서 이뤄집니다. 아직 반영되지 않은 신규 공시나 장중 이벤트가 있는지 최종 확인이 필요합니다.")

    # Concrete default re-check triggers. Keep at least five if data allows.
    defaults = [
        "외국인과 기관이 동시에 순매도로 돌아서고 그 흐름이 여러 거래일 이어지면 수급 판단을 낮춥니다.",
        "최근 고점 이후 주가가 20일선과 60일선을 모두 이탈하고 회복하지 못하면 가격 흐름을 다시 봅니다.",
        "다음 분기 매출과 영업이익이 함께 감소하면 실적 판단을 한 단계 낮춥니다.",
        "반대로 다음 실적에서 매출과 영업이익이 함께 개선되고 수급도 순매수로 전환되면 현재보다 긍정적으로 다시 평가합니다.",
        "새로운 부정 뉴스나 중요 공시가 나오면 기존 긍정 근거가 그대로 유지되는지 즉시 다시 확인합니다.",
    ]
    for item in defaults:
        if len(watches) >= 6:
            break
        _append_unique(watches, item)

    return positives[:8], risks[:8], watches[:8]




def _fmt_num(value: Any, digits: int = 1) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:,.{digits}f}"


def _fmt_pct(value: Any, digits: int = 1) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:+.{digits}f}%"


def _fmt_krw_amount(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    sign = "-" if number < 0 else ""
    amount = abs(number)
    if amount >= 1_000_000_000_000:
        return f"{sign}{amount/1_000_000_000_000:.2f}조원"
    if amount >= 100_000_000:
        return f"{sign}{amount/100_000_000:,.0f}억원"
    if amount >= 10_000:
        return f"{sign}{amount/10_000:,.0f}만원"
    return f"{sign}{amount:,.0f}원"


def _quantitative_breakdown(stock_context: dict[str, Any]) -> list[dict[str, str]]:
    """Build user-facing, measurable evidence cards from StockLog facts only."""
    metrics = stock_context.get("metrics") or {}
    peer = (stock_context.get("peer") or {}).get("median") or {}
    financials = stock_context.get("financials") or []
    latest = financials[0] if financials else {}
    flow_root = stock_context.get("supply_demand") or {}
    flow = (flow_root.get("periods") or {}).get("5") or flow_root.get("latest_period") or {}
    momentum = stock_context.get("momentum") or {}
    news = stock_context.get("news") or {}
    reports = stock_context.get("reports") or {}
    disclosures = stock_context.get("disclosures") or {}
    rows: list[dict[str, str]] = []

    def add(key: str, label: str, current: str, benchmark: str, interpretation: str, view: str = "neutral"):
        if current == "-" and not interpretation:
            return
        rows.append({
            "key": key, "label": label, "current": current, "benchmark": benchmark,
            "interpretation": interpretation, "view": view if view in {"positive","neutral","negative"} else "neutral",
        })

    rg = _num(metrics.get("revenue_growth_pct"))
    opg = _num(latest.get("operating_profit_change_pct"))
    nig = _num(latest.get("net_income_change_pct"))
    roe = _num(metrics.get("roe_pct"))
    peer_rg = _num(peer.get("revenue_growth")); peer_roe = _num(peer.get("roe"))
    rev_amount=_num(latest.get("revenue")); op_amount=_num(latest.get("operating_profit")); ni_amount=_num(latest.get("net_income"))
    perf_amounts=[]
    if rev_amount is not None: perf_amounts.append(f"매출 {_fmt_krw_amount(rev_amount)}")
    if op_amount is not None: perf_amounts.append(f"영업이익 {_fmt_krw_amount(op_amount)}")
    if ni_amount is not None: perf_amounts.append(f"순이익 {_fmt_krw_amount(ni_amount)}")
    perf_current=(f"{latest.get('period') or '최근 분기'} · " if perf_amounts else "")+" · ".join(perf_amounts) if perf_amounts else "-"
    change_parts=[]
    if rg is not None: change_parts.append(f"매출성장 {_fmt_pct(rg)}")
    if opg is not None: change_parts.append(f"영업이익 {_fmt_pct(opg)}")
    if nig is not None: change_parts.append(f"순이익 {_fmt_pct(nig)}")
    if roe is not None: change_parts.append(f"ROE {roe:.1f}%")
    if peer_rg is not None: change_parts.append(f"동종 매출성장 {_fmt_pct(peer_rg)}")
    if peer_roe is not None: change_parts.append(f"동종 ROE {peer_roe:.1f}%")
    perf_bench=" · ".join(change_parts) or "비교 기준 없음"
    perf_score=sum([1 if x is not None and x>0 else -1 if x is not None and x<0 else 0 for x in (rg,opg,nig)])
    perf_view="positive" if perf_score>=2 else "negative" if perf_score<=-2 else "neutral"
    perf_text=(
        "최근 실적의 매출과 이익이 함께 증가해 실적 방향이 우호적입니다." if perf_view=="positive" else
        "최근 매출 또는 이익 감소가 함께 나타나 실적 방향을 보수적으로 봐야 합니다." if perf_view=="negative" else
        "매출과 이익의 방향이 한쪽으로 뚜렷하게 모이지 않아 다음 분기 확인이 중요합니다."
    )
    add("performance","기업 실적",perf_current,perf_bench,perf_text,perf_view)

    per=_num(metrics.get("per")); pbr=_num(metrics.get("pbr")); peer_per=_num(peer.get("per")); peer_pbr=_num(peer.get("pbr"))
    val_parts=[]
    if per is not None: val_parts.append(f"PER {per:.1f}배")
    if pbr is not None: val_parts.append(f"PBR {pbr:.2f}배")
    val_b=[]
    if peer_per is not None: val_b.append(f"동종 PER {peer_per:.1f}배")
    if peer_pbr is not None: val_b.append(f"동종 PBR {peer_pbr:.2f}배")
    val_points=0
    if per is not None and peer_per not in (None,0): val_points += 1 if per<=peer_per else -1
    if pbr is not None and peer_pbr not in (None,0): val_points += 1 if pbr<=peer_pbr else -1
    val_view="positive" if val_points>0 else "negative" if val_points<0 else "neutral"
    val_text=(
        "동종 기업의 중간 수준보다 가격 부담이 낮아 상대적으로 유리합니다." if val_view=="positive" else
        "동종 기업보다 높은 배수로 거래돼 현재 가격에는 더 높은 실적 기대가 반영돼 있습니다." if val_view=="negative" else
        "동종 기업과 비교해 가격 부담이 뚜렷하게 싸거나 비싸다고 보기 어렵습니다."
    )
    add("valuation","가격 수준"," · ".join(val_parts) or "-"," · ".join(val_b) or "동종 비교 데이터 없음",val_text,val_view)

    combined=_num(flow.get("foreign_institution_net")); foreign=_num(flow.get("foreign_net")); institution=_num(flow.get("institution_net")); days=int(_num(flow.get("days")) or 5)
    if combined is not None:
        flow_view="positive" if combined>0 else "negative" if combined<0 else "neutral"
        flow_text=(
            f"최근 {days}거래일에 외국인과 기관의 합산 매수세가 들어온 상태입니다." if flow_view=="positive" else
            f"최근 {days}거래일에 외국인과 기관의 합산 매도세가 우세합니다." if flow_view=="negative" else
            f"최근 {days}거래일 외국인·기관 수급이 한쪽으로 기울지 않았습니다."
        )
        add("flow","수급",f"외국인 {foreign or 0:,.0f}주 · 기관 {institution or 0:,.0f}주",f"합산 {combined:+,.0f}주",flow_text,flow_view)
    else:
        add("flow","수급","-","최근 5거래일","수급 데이터가 부족해 외국인·기관의 방향을 판단 근거로 강하게 사용하지 않았습니다.","neutral")

    r20=_num(momentum.get("return_20d_pct")); r60=_num(momentum.get("return_60d_pct")); ma20=str(momentum.get("price_vs_ma20") or ""); ma60=str(momentum.get("price_vs_ma60") or "")
    trend_points=(1 if r20 is not None and r20>0 else -1 if r20 is not None and r20<0 else 0)+(1 if r60 is not None and r60>0 else -1 if r60 is not None and r60<0 else 0)+(1 if ma20=="above" else -1 if ma20=="below" else 0)+(1 if ma60=="above" else -1 if ma60=="below" else 0)
    trend_view="positive" if trend_points>=2 else "negative" if trend_points<=-2 else "neutral"
    pos_label=lambda v: "위" if v=="above" else "아래" if v=="below" else "확인 불가"
    trend_current=" · ".join([x for x in [f"20일 {_fmt_pct(r20)}" if r20 is not None else "",f"60일 {_fmt_pct(r60)}" if r60 is not None else ""] if x]) or "-"
    trend_b=f"20일선 {pos_label(ma20)} · 60일선 {pos_label(ma60)}"
    trend_text=(
        "최근 수익률과 이동평균 위치가 함께 우호적이라 주가 흐름은 상승 쪽입니다." if trend_view=="positive" else
        "최근 수익률과 이동평균 위치가 약해 주가 흐름은 하락 쪽으로 기울어 있습니다." if trend_view=="negative" else
        "단기와 중기 주가 신호가 엇갈려 추세가 뚜렷하지 않습니다."
    )
    add("trend","최근 추세",trend_current,trend_b,trend_text,trend_view)

    counts=news.get("sentiment_counts") or {}; news_n=int(_num(news.get("count")) or len(news.get("items") or [])); pos_n=int(_num(counts.get("positive")) or 0); neg_n=int(_num(counts.get("negative")) or 0)
    report_items=reports.get("items") or []; report_pos=sum(1 for x in report_items if str((x or {}).get("sentiment") or "").lower()=="positive"); report_neg=sum(1 for x in report_items if str((x or {}).get("sentiment") or "").lower()=="negative")
    info_points=(1 if pos_n>neg_n else -1 if neg_n>pos_n else 0)+(1 if report_pos>report_neg else -1 if report_neg>report_pos else 0)
    info_view="positive" if info_points>0 else "negative" if info_points<0 else "neutral"
    info_current=f"뉴스 긍정 {pos_n} · 부정 {neg_n}" if news_n else "최근 뉴스 표본 없음"
    info_bench=f"리포트 긍정 {report_pos} · 부정 {report_neg} · 공시 {len(disclosures.get('items') or [])}건"
    info_text=(
        "최근 뉴스와 리포트의 방향이 전반적으로 긍정 쪽에 가깝습니다." if info_view=="positive" else
        "최근 뉴스 또는 리포트에서 부정적인 신호가 상대적으로 더 많습니다." if info_view=="negative" else
        "최근 뉴스와 리포트의 방향이 뚜렷하게 한쪽으로 모이지 않았습니다."
    )
    add("public_info","뉴스·리포트·공시",info_current,info_bench,info_text,info_view)

    return rows


def _quantitative_verdict_reason(result: dict[str, Any], stock_context: dict[str, Any], breakdown: list[dict[str, str]]) -> str:
    company=(stock_context.get("company") or {}).get("name") or "이 종목"
    verdict=result.get("verdict") or "wait"
    label=VERDICT_LABELS.get(verdict,"관망")
    parts=[]
    for row in breakdown:
        if row.get("current") and row.get("current")!="-":
            parts.append(f"{row['label']}: 현재 값은 {row['current']}이고, 비교 기준은 {row['benchmark']}입니다. {row['interpretation']}")
        else:
            parts.append(f"{row['label']}: {row['interpretation']}")
    core=" ".join(parts[:5])
    if verdict=="wait":
        close="따라서 긍정 신호만 보고 바로 매수하기에도, 부정 신호만 보고 매도하기에도 근거가 한쪽으로 충분히 모이지 않아 현재는 관망으로 판단합니다."
    elif verdict=="buy_bias":
        close="따라서 현재는 긍정 근거가 부정 근거보다 우세해 매수 추천 쪽으로 판단하지만, 가격과 수급이 불리하게 바뀌면 판단을 다시 봐야 합니다."
    else:
        close="따라서 현재는 부정·주의 근거가 긍정 근거보다 직접적이어서 매도 추천 쪽으로 판단하며, 실적과 수급이 개선되는지 확인하기 전까지 보수적으로 봅니다."
    return _clean_text(f"{company}의 현재 판단은 {label}입니다. {core} {close}",3000)




def _decision_balance(breakdown: list[dict[str, str]]) -> dict[str, int]:
    return {
        "positive": sum(1 for item in breakdown if item.get("view") == "positive"),
        "negative": sum(1 for item in breakdown if item.get("view") == "negative"),
        "neutral": sum(1 for item in breakdown if item.get("view") == "neutral"),
        "total": len(breakdown),
    }


def _decision_headline_and_summary(result: dict[str, Any], stock_context: dict[str, Any], breakdown: list[dict[str, str]]) -> tuple[str, str]:
    company=(stock_context.get("company") or {}).get("name") or "이 종목"
    verdict=result.get("verdict") or "wait"
    label=VERDICT_LABELS.get(verdict,"관망")
    balance=_decision_balance(breakdown)
    headline=(
        f"{company}: 정량 근거 {balance['positive']}개 긍정 · {balance['negative']}개 주의 · "
        f"{balance['neutral']}개 중립을 바탕으로 {label}입니다."
    )

    preferred=[]
    order=("performance","valuation","flow","trend","public_info")
    by_key={str(row.get("key")):row for row in breakdown}
    for key in order:
        row=by_key.get(key)
        if not row:
            continue
        current=str(row.get("current") or "-")
        benchmark=str(row.get("benchmark") or "")
        interp=str(row.get("interpretation") or "")
        if current and current!="-":
            preferred.append(f"{row.get('label')}: {current}. {benchmark}. {interp}")
        elif interp:
            preferred.append(f"{row.get('label')}: {interp}")
    if verdict=="buy_bias":
        closing=(
            "현재는 긍정 근거가 더 우세해 매수 추천으로 분류했습니다. 다만 매수 추천은 즉시 전액 매수를 뜻하지 않으며, "
            "아래 주의 근거와 재판단 조건을 확인한 뒤 분할 접근 여부를 결정하는 편이 안전합니다."
        )
    elif verdict=="sell_bias":
        closing=(
            "현재는 부정·주의 근거가 더 직접적이어서 매도 추천으로 분류했습니다. 실적·수급·가격 흐름 중 핵심 약점이 "
            "실제로 개선되는지가 확인되기 전에는 보수적으로 보는 편이 좋습니다."
        )
    else:
        closing=(
            "현재는 긍정과 부정 신호가 함께 존재하거나 핵심 지표가 한쪽으로 충분히 모이지 않아 관망으로 분류했습니다. "
            "아래 재판단 조건이 충족되는지 확인한 뒤 매수·매도 판단을 바꾸는 것이 좋습니다."
        )
    return _clean_text(headline,420), _clean_text(" ".join(preferred[:5])+" "+closing,3200)


def _sync_final_decision_copy(result: dict[str, Any], stock_context: dict[str, Any], breakdown: list[dict[str, str]]) -> None:
    """Keep every user-facing sentence aligned to the single final verdict.

    LLM prose is generated before deterministic consistency checks. If the
    verdict is later corrected, stale prose must never keep the old label.
    """
    headline, summary = _decision_headline_and_summary(result, stock_context, breakdown)
    result["headline"] = headline
    result["one_line"] = headline
    result["executive_summary"] = summary
    result["company_view"] = summary
    result["decision_balance"] = _decision_balance(breakdown)
    result["decision_consistency"] = "aligned"

    label = VERDICT_LABELS.get(result.get("verdict"), "관망")
    if result.get("verdict") == "buy_bias":
        result["new_investor_strategy"] = "현재 정량 근거는 매수 추천 쪽입니다. 한 번에 전액 매수하기보다 작은 비중으로 시작하고, 수급과 최근 추세가 유지되는지 확인하면서 나눠 접근하는 방식이 좋습니다."
        result["holder_strategy"] = "현재 긍정 근거가 유지되는 동안은 보유 관점이 가능합니다. 다만 실적 둔화, 외국인·기관 순매도 전환, 20일·60일 추세 훼손이 함께 나타나면 비중 축소 여부를 다시 검토합니다."
        result["entry_timing"] = "현재 가격을 무조건 추격하기보다 조정 시 수급이 유지되는지, 또는 최근 고점을 넘을 때 거래 흐름이 함께 개선되는지를 확인한 뒤 분할 접근합니다."
        result["buy_plan"] = "1차는 작은 비중으로 시작하고, 실적·수급·가격 추세 중 최소 두 가지가 계속 우호적일 때 추가 매수를 검토합니다."
    elif result.get("verdict") == "sell_bias":
        result["new_investor_strategy"] = "현재 정량 근거는 매도 추천 쪽이므로 신규 진입을 서두르지 않는 편이 좋습니다. 실적과 수급, 가격 흐름이 실제로 회복되는지 확인한 뒤 다시 평가합니다."
        result["holder_strategy"] = "현재 보유자는 부정 근거가 커지는지 먼저 확인합니다. 실적 악화와 순매도, 추세 약화가 동시에 이어지면 손실 확대 전에 비중 축소 기준을 세우는 편이 좋습니다."
        result["entry_timing"] = "신규 매수보다 회복 확인이 우선입니다. 실적 개선과 수급 전환, 20일·60일 추세 회복 중 여러 신호가 함께 확인될 때 다시 진입을 검토합니다."
        result["buy_plan"] = "현재는 추가 매수보다 관찰을 우선하고, 부정 근거가 해소된 뒤 소액부터 재진입 여부를 검토합니다."
    else:
        result["new_investor_strategy"] = "현재 정량 근거는 관망입니다. 좋은 점과 주의점이 함께 있어 즉시 매수하기보다 아래 재판단 조건 중 긍정 신호가 늘어나는지 확인한 뒤 접근하는 편이 좋습니다."
        result["holder_strategy"] = "현재 보유자는 성급히 매도하기보다 기존 매수 근거가 유지되는지 확인합니다. 부정 근거가 늘거나 핵심 추세가 무너지면 비중 조정을 검토합니다."
        result["entry_timing"] = "긍정과 부정 신호가 한쪽으로 모일 때까지 기다립니다. 실적·수급·가격 추세 중 최소 두 가지가 같은 방향으로 확인되는 시점을 우선합니다."
        result["buy_plan"] = "관망 구간에서는 첫 매수를 크게 하지 않고, 확인 신호가 생기면 작은 비중부터 단계적으로 접근합니다."
    result["decision_label"] = label

def finalize_deep_result(value: dict[str, Any], stock_context: dict[str, Any]) -> dict[str, Any]:
    result = normalize_result(value)
    ctx_pos, ctx_risk, ctx_watch = _evidence_from_context(stock_context)

    positives = _clean_list(result.get("positive_factors"), limit=8, item_limit=420)
    risks = _clean_list(result.get("risk_factors"), limit=8, item_limit=420)
    watches = _clean_list(result.get("watch_conditions"), limit=8, item_limit=420)
    # Always merge some deterministic StockLog evidence, even when the LLM
    # already returned six sentences.  This keeps premium explanations tied
    # to measurable facts instead of relying solely on prose quality.
    for item in ctx_pos:
        if len(positives) >= 8: break
        _append_unique(positives, item)
    for item in ctx_risk:
        if len(risks) >= 8: break
        _append_unique(risks, item)
    for item in ctx_watch:
        if len(watches) >= 8: break
        _append_unique(watches, item)

    result["positive_factors"] = positives[:8]
    result["risk_factors"] = risks[:8]
    result["watch_conditions"] = watches[:8]

    breakdown = _quantitative_breakdown(stock_context)
    result["quantitative_breakdown"] = breakdown

    # Prevent a confusing verdict such as "관망" when every measurable
    # dimension is currently positive (or the reverse). The LLM still supplies
    # interpretation, but StockLog enforces consistency with measured facts.
    positive_dims=sum(1 for item in breakdown if item.get("view")=="positive")
    negative_dims=sum(1 for item in breakdown if item.get("view")=="negative")
    if result.get("verdict")=="wait" and positive_dims>=4 and negative_dims==0:
        result["verdict"]="buy_bias"
    elif result.get("verdict")=="wait" and negative_dims>=3 and positive_dims<=1:
        result["verdict"]="sell_bias"
    result["verdict_label"]=VERDICT_LABELS.get(result.get("verdict"),"관망")
    result["view"]=_view_from_verdict(result.get("verdict"))
    if result.get("verdict")=="buy_bias" and result.get("buy_probability",0)<result.get("wait_probability",0):
        result["buy_probability"],result["wait_probability"]=max(55,result.get("wait_probability",0)),min(35,result.get("buy_probability",0))
    elif result.get("verdict")=="sell_bias" and result.get("sell_probability",0)<result.get("wait_probability",0):
        result["sell_probability"],result["wait_probability"]=max(55,result.get("wait_probability",0)),min(35,result.get("sell_probability",0))
    result["probabilities"]={"buy":result.get("buy_probability",0),"wait":result.get("wait_probability",0),"sell":result.get("sell_probability",0)}
    result["verdict_reason"] = _quantitative_verdict_reason(result, stock_context, breakdown)
    _sync_final_decision_copy(result, stock_context, breakdown)
    result["analysis_schema_version"] = "3.73.2"
    return result


def _deterministic_fallback(stock_context: dict[str, Any], reason: str = "fallback") -> dict[str, Any]:
    pre = stock_context.get("preanalysis") or {}
    company = stock_context.get("company") or {}
    score = pre.get("overall_score")
    try:
        score_num = float(score)
    except Exception:
        score_num = None

    if score_num is None:
        verdict = "wait"
        confidence = 35
    elif score_num >= 70:
        verdict = "buy_bias"
        confidence = 62
    elif score_num < 40:
        verdict = "sell_bias"
        confidence = 62
    else:
        verdict = "wait"
        confidence = 58

    view = _view_from_verdict(verdict)
    name = str(company.get("name") or company.get("code") or "해당 종목")
    labels = VIEW_LABELS

    def dim(pre_key: str, label: str) -> dict[str, str]:
        raw = str(pre.get(pre_key) or "neutral")
        if raw not in labels:
            raw = "neutral"
        return {
            "view": raw,
            "summary": f"현재 확인되는 {label} 흐름은 {labels[raw]}로 평가됩니다.",
        }

    supply = stock_context.get("supply_demand") or {}
    supply_view = "neutral"
    joint = bool(supply.get("latest_period", {}).get("joint_buy")) if isinstance(supply.get("latest_period"), dict) else False
    combined = None
    try:
        combined = float((supply.get("latest_period") or {}).get("foreign_net", 0)) + float((supply.get("latest_period") or {}).get("institution_net", 0))
    except Exception:
        pass
    if joint or (combined is not None and combined > 0):
        supply_view = "positive"
    elif combined is not None and combined < 0:
        supply_view = "negative"

    positives: list[str] = []
    risks: list[str] = []
    for label, item in (
        ("밸류에이션", dim("valuation_view", "밸류에이션")),
        ("재무", dim("financial_view", "재무")),
        ("모멘텀", dim("momentum_view", "가격 모멘텀")),
        ("뉴스", dim("news_view", "뉴스")),
        ("수급", {"view": supply_view}),
    ):
        if item.get("view") == "positive":
            positives.append(f"{label} 흐름이 긍정적입니다. 현재 입력된 {label} 지표가 다른 위험 신호보다 우호적으로 나타납니다.")
        elif item.get("view") == "negative":
            risks.append(f"{label} 흐름이 부정적입니다. 현재 입력된 {label} 지표가 개선되는지 확인이 필요합니다.")

    probabilities = {
        "buy_bias": (55, 35, 10),
        "wait": (25, 55, 20),
        "sell_bias": (10, 35, 55),
    }[verdict]
    score_text = f"{score_num:.1f}점" if score_num is not None else "확인 불가"
    result = {
        "verdict": verdict,
        "confidence": confidence,
        "headline": f"{name}: 현재 데이터 흐름을 종합하면 {VERDICT_LABELS[verdict]} 의견입니다.",
        "executive_summary": (
            f"{name}의 기업 실적, 가격 수준, 수급, 최근 추세와 공개 정보를 종합하면 현재 판단은 {VERDICT_LABELS[verdict]}입니다. "
            "한 가지 신호보다 여러 지표가 같은 방향을 가리키는지를 함께 확인하는 것이 중요합니다. "
            "신규 진입 전에는 최근 가격 위치와 수급 흐름을 다시 확인해 분할 접근 여부를 검토하는 편이 좋습니다."
        ),
        "valuation": dim("valuation_view", "밸류에이션"),
        "financials": dim("financial_view", "재무"),
        "supply_demand": {"view": supply_view, "summary": "최근 외국인과 기관의 매매 흐름을 기준으로 방향을 확인했습니다."},
        "momentum": dim("momentum_view", "가격 모멘텀"),
        "news": dim("news_view", "뉴스"),
        "reports": {"view": "neutral", "summary": "리포트 데이터는 보조 근거로만 반영했습니다."},
        "market_context": {"view": "neutral", "summary": "시장·테마 환경은 보조 근거로만 반영했습니다."},
        "positive_factors": positives[:5],
        "risk_factors": risks[:5],
        "new_investor_strategy": "신규 진입자는 현재 가격을 추격하기보다 핵심 지표가 같은 방향인지 확인한 뒤 분할 접근 여부를 검토하는 편이 안전합니다.",
        "holder_strategy": "기존 보유자는 현재 추세와 수급이 훼손되는지 확인하면서 보유 근거가 유지되는지를 우선 점검할 필요가 있습니다.",
        "short_term_view": "단기 판단은 가격 모멘텀과 수급 변화에 민감하게 대응해야 합니다.",
        "mid_term_view": "중기 판단은 실적 성장과 밸류에이션의 균형이 유지되는지가 핵심입니다.",
        "watch_conditions": [
            "외국인/기관 수급 방향 전환",
            "20일·60일 추세 훼손 또는 회복",
            "최근 분기 실적 방향 변화",
        ],
        "buy_probability": probabilities[0],
        "wait_probability": probabilities[1],
        "sell_probability": probabilities[2],
        "missing_data": [],
        "quant_agreement": {
            "status": "agree",
            "reason": "현재 확인되는 주요 데이터 흐름과 최종 의견이 대체로 같은 방향입니다.",
        },
        "model_consensus": {
            "status": "single_model",
            "gbot_verdict": "",
            "obot_verdict": "",
            "summary": "StockLog 정량 근거를 중심으로 현재 투자 의견을 정리했습니다.",
        },
    }
    return finalize_deep_result(result, stock_context)


def normalize_result(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value or {})
    verdict = str(result.get("verdict") or "").strip().lower()
    if verdict not in VERDICT_LABELS:
        legacy_view = str(result.get("view") or "neutral").lower()
        verdict = {"positive": "buy_bias", "negative": "sell_bias"}.get(legacy_view, "wait")
    result["verdict"] = verdict
    result["verdict_label"] = VERDICT_LABELS[verdict]
    result["view"] = _view_from_verdict(verdict)
    result["confidence"] = _clamp_int(result.get("confidence"), 50)

    buy, wait, sell = _normalize_probabilities(result, verdict)
    result["buy_probability"] = buy
    result["wait_probability"] = wait
    result["sell_probability"] = sell
    result["probabilities"] = {"buy": buy, "wait": wait, "sell": sell}

    for key in DIMENSION_KEYS:
        item = result.get(key)
        if not isinstance(item, dict):
            item = {}
        view = str(item.get("view") or "neutral").lower()
        if view not in VIEW_LABELS:
            view = "neutral"
        item["view"] = view
        item["summary"] = _clean_text(item.get("summary") or "분석할 데이터가 충분하지 않습니다.", 900)
        result[key] = item

    for key in ("positive_factors", "risk_factors", "watch_conditions", "missing_data"):
        result[key] = _clean_list(result.get(key), limit=8, item_limit=420)

    result["headline"] = _clean_text(result.get("headline") or result.get("one_line") or "AI 종합 판단을 준비했습니다.", 360)
    result["one_line"] = result["headline"]
    result["executive_summary"] = _clean_text(result.get("executive_summary") or result.get("company_view") or "분석 데이터가 충분하지 않습니다.", 3000)
    result["verdict_reason"] = _clean_text(result.get("verdict_reason"), 1800)
    result["company_view"] = result["executive_summary"]
    result["new_investor_strategy"] = _clean_text(result.get("new_investor_strategy") or "신규 진입 전략을 판단할 데이터가 충분하지 않습니다.", 1200)
    result["holder_strategy"] = _clean_text(result.get("holder_strategy") or "기존 보유자 전략을 판단할 데이터가 충분하지 않습니다.", 1200)
    result["short_term_view"] = _clean_text(result.get("short_term_view") or "단기 관점 데이터가 충분하지 않습니다.", 800)
    result["mid_term_view"] = _clean_text(result.get("mid_term_view") or "중기 관점 데이터가 충분하지 않습니다.", 800)
    result["entry_timing"] = _clean_text(result.get("entry_timing") or "최근 가격을 추격하기보다 실적과 수급이 같은 방향으로 확인되는 시점을 기다려 분할 진입을 검토합니다.", 900)
    result["buy_plan"] = _clean_text(result.get("buy_plan") or "첫 진입은 작은 비중으로 시작하고, 이후 실적·수급·가격 흐름이 유지되는지 확인한 뒤 추가 매수를 검토합니다.", 1100)

    agreement = result.get("quant_agreement") if isinstance(result.get("quant_agreement"), dict) else {}
    status = str(agreement.get("status") or "partial")
    if status not in {"agree", "partial", "disagree"}:
        status = "partial"
    result["quant_agreement"] = {
        "status": status,
        "reason": _clean_text(agreement.get("reason") or "정량 분석과 AI 의견의 관계를 확인하고 있습니다.", 700),
    }

    consensus = result.get("model_consensus") if isinstance(result.get("model_consensus"), dict) else {}
    cstatus = str(consensus.get("status") or "single_model")
    if cstatus not in {"aligned", "mixed", "single_model"}:
        cstatus = "single_model"
    result["model_consensus"] = {
        "status": cstatus,
        "gbot_verdict": str(consensus.get("gbot_verdict") or consensus.get("gemini_verdict") or ""),
        "obot_verdict": str(consensus.get("obot_verdict") or consensus.get("ollama_verdict") or ""),
        "summary": _clean_text(consensus.get("summary") or "StockLog Gbot과 Obot의 분석 의견을 비교해 최종 판단했습니다.", 900),
    }
    return result


class GeminiAnalyst:
    """Gemini free-tier analyst. Only public stock context is sent upstream."""

    def __init__(self, api_key: str, *, model: str | None = None, background_model: str | None = None):
        self.api_key = str(api_key or "").strip()
        self.model = (model or os.getenv("GEMINI_MANUAL_MODEL", "gemini-3.6-flash")).strip() or "gemini-3.6-flash"
        self.background_model = (background_model or os.getenv("GEMINI_BACKGROUND_MODEL", "gemini-3.5-flash-lite")).strip() or "gemini-3.5-flash-lite"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.timeout_seconds = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "45"))

    @staticmethod
    def _response_text(payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            feedback = payload.get("promptFeedback") or {}
            raise RuntimeError(f"Gemini 응답 후보가 없습니다. {feedback}")
        parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
        text = "".join(str((part or {}).get("text") or "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            raise RuntimeError("Gemini 응답에 분석 내용이 없습니다.")
        return text

    async def _generate_json(
        self,
        *,
        system: str,
        prompt: dict[str, Any],
        model: str,
        request_kind: str,
        stock_code: str = "",
        max_output_tokens: int = 1800,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("Gemini API Key가 설정되지 않았습니다.")
        base_contents = [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False, separators=(",", ":"), default=str)}]}]

        def _generation_config(candidate_model: str, output_tokens: int, *, retry: bool = False) -> dict[str, Any]:
            # Premium output is intentionally detailed (7 dimensions, 12 factors,
            # strategies and checkpoints). 1,900 tokens was too small and could
            # truncate an otherwise successful JSON response. Gemini 3.x also
            # thinks by default, so keep thinking low for latency while leaving
            # enough room for the actual answer.
            config: dict[str, Any] = {
                "temperature": 0.05 if retry else 0.10,
                "maxOutputTokens": int(output_tokens),
                "responseMimeType": "application/json",
            }
            model_name = str(candidate_model or "").lower()
            if model_name.startswith("gemini-3"):
                config["thinkingConfig"] = {"thinkingLevel": "low"}
            elif model_name.startswith("gemini-2.5"):
                # Flash/Flash-Lite support a zero thinking budget and this keeps
                # fallback latency predictable for a structured stock report.
                config["thinkingConfig"] = {"thinkingBudget": 0}
            return config

        # Gemini model availability can differ by project/tier and Google can
        # retire model aliases. Premium analysis must not fail immediately just
        # because one hard-coded model returns 404. Try the requested model
        # first, then current StockLog-safe Flash fallbacks.
        configured_fallbacks = os.getenv(
            "GEMINI_MODEL_FALLBACKS",
            "gemini-3.6-flash,gemini-3.5-flash-lite,gemini-2.5-flash",
        )
        candidates: list[str] = []
        for candidate in [model, *configured_fallbacks.split(",")]:
            candidate = str(candidate or "").strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        timeout = httpx.Timeout(connect=5.0, read=self.timeout_seconds, write=25.0, pool=10.0)
        last_model_error = ""
        rate_limited_models: list[str] = []
        rate_limit_waits: list[float] = []
        async with httpx.AsyncClient(timeout=timeout) as client:
            for candidate in candidates:
                url = f"{self.base_url}/models/{candidate}:generateContent"
                body = {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": base_contents,
                    "generationConfig": _generation_config(candidate, max_output_tokens),
                }
                try:
                    response = await tracked_post(
                        client,
                        PROVIDER_GEMINI,
                        f"generate/{candidate}",
                        url,
                        request_kind=request_kind,
                        stock_code=stock_code,
                        headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                        json=body,
                    )
                except RuntimeError as exc:
                    guard_text=str(exc or "")
                    if "한도" in guard_text or "quota" in guard_text.lower() or "rate limit" in guard_text.lower():
                        raise GeminiRateLimitError(
                            "StockLog Gbot 자동 분석 안전 한도에 도달했습니다. 이번 판단에서는 주문하지 않고 자동으로 다시 시도합니다.",
                            retry_after_seconds=900,
                            models=[candidate],
                        ) from exc
                    raise

                if response.status_code == 429:
                    retry_after = _gemini_retry_after_seconds(response)
                    response_preview = (response.text or "").replace("\n", " ")[:1600]
                    rate_limited_models.append(candidate)
                    rate_limit_waits.append(retry_after)
                    logger.warning(
                        "Gemini rate limited; trying alternate model=%s retry_after=%.1fs body=%s",
                        candidate, retry_after, response_preview,
                    )
                    # Gemini quotas can be model-specific. Do not make the user
                    # wait inside the HTTP request; try another configured Flash
                    # model once, then let the caller schedule a cooled-down retry.
                    continue

                if response.status_code in {404, 400}:
                    # 404 is the common MODEL_NOT_FOUND / unavailable-alias case.
                    # Some Gemini API revisions report unsupported models as 400.
                    response_preview = (response.text or "").replace("\n", " ")[:1200]
                    last_model_error = f"HTTP {response.status_code} {candidate}: {response_preview}"
                    logger.warning(
                        "Gemini model unavailable; trying fallback model=%s status=%s body=%s",
                        candidate, response.status_code, response_preview,
                    )
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    response_preview = (response.text or "").replace("\n", " ")[:2000]
                    logger.error(
                        "Gemini request failed model=%s status=%s body=%s",
                        candidate, response.status_code, response_preview,
                    )
                    raise

                raw = response.json()
                usage = raw.get("usageMetadata") or {}
                first_candidate = ((raw.get("candidates") or [{}])[0] or {})
                finish_reason = str(first_candidate.get("finishReason") or "")
                response_text = self._response_text(raw)
                try:
                    parsed = _parse_ai_json(response_text)
                except RuntimeError:
                    # HTTP 200 does not guarantee the JSON reached its closing
                    # brace. The previous 1,900-token cap commonly produced a
                    # MAX_TOKENS/truncated response. Log enough diagnostics to
                    # identify the exact reason and retry once with a larger cap.
                    preview_head = response_text[:700].replace("\n", " ")
                    preview_tail = response_text[-700:].replace("\n", " ")
                    logger.warning(
                        "Gemini JSON parse failed model=%s finish_reason=%s prompt_tokens=%s output_tokens=%s "
                        "text_chars=%s head=%s tail=%s",
                        candidate, finish_reason, usage.get("promptTokenCount"),
                        usage.get("candidatesTokenCount"), len(response_text),
                        preview_head, preview_tail,
                    )

                    retry_tokens = min(8192, max(int(max_output_tokens * 1.5), 6200))
                    retry_prompt = dict(prompt)
                    retry_prompt["output_repair_instruction"] = (
                        "직전 응답이 중간에 잘려 JSON 파싱에 실패했습니다. 설명이나 마크다운 없이 "
                        "요청된 JSON 객체를 처음부터 끝까지 완결된 형태로 반환하세요. 문장을 불필요하게 "
                        "늘리지 말고 각 필드의 핵심 근거를 유지하세요."
                    )
                    retry_body = {
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": json.dumps(retry_prompt, ensure_ascii=False, separators=(",", ":"), default=str)}]}],
                        "generationConfig": _generation_config(candidate, retry_tokens, retry=True),
                    }
                    try:
                        retry_response = await tracked_post(
                            client,
                            PROVIDER_GEMINI,
                            f"generate/{candidate}/json-retry",
                            url,
                            request_kind=request_kind,
                            stock_code=stock_code,
                            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                            json=retry_body,
                        )
                    except RuntimeError as exc:
                        guard_text=str(exc or "")
                        if "한도" in guard_text or "quota" in guard_text.lower() or "rate limit" in guard_text.lower():
                            raise GeminiRateLimitError(
                                "StockLog Gbot 자동 분석 안전 한도에 도달했습니다. 이번 판단에서는 주문하지 않고 자동으로 다시 시도합니다.",
                                retry_after_seconds=900,
                                models=[candidate],
                            ) from exc
                        raise
                    if retry_response.status_code == 429:
                        retry_after = _gemini_retry_after_seconds(retry_response)
                        response_preview = (retry_response.text or "").replace("\n", " ")[:1600]
                        rate_limited_models.append(candidate)
                        rate_limit_waits.append(retry_after)
                        logger.warning(
                            "Gemini JSON retry rate limited model=%s retry_after=%.1fs body=%s",
                            candidate, retry_after, response_preview,
                        )
                        continue
                    retry_response.raise_for_status()
                    retry_raw = retry_response.json()
                    retry_usage = retry_raw.get("usageMetadata") or {}
                    retry_candidate = ((retry_raw.get("candidates") or [{}])[0] or {})
                    retry_finish_reason = str(retry_candidate.get("finishReason") or "")
                    retry_text = self._response_text(retry_raw)
                    try:
                        parsed = _parse_ai_json(retry_text)
                    except RuntimeError:
                        logger.error(
                            "Gemini JSON retry failed model=%s finish_reason=%s prompt_tokens=%s output_tokens=%s "
                            "text_chars=%s head=%s tail=%s",
                            candidate, retry_finish_reason, retry_usage.get("promptTokenCount"),
                            retry_usage.get("candidatesTokenCount"), len(retry_text),
                            retry_text[:700].replace("\n", " "),
                            retry_text[-700:].replace("\n", " "),
                        )
                        raise
                    raw = retry_raw
                    usage = retry_usage
                    finish_reason = retry_finish_reason

                # Reflect the model that actually worked so subsequent premium
                # requests in this server process start with the known-good one.
                if request_kind.startswith("interactive"):
                    self.model = candidate
                elif request_kind == "background":
                    self.background_model = candidate

                return parsed, {
                    "provider": "gemini",
                    "model": candidate,
                    "fallback": candidate != model,
                    "requested_model": model,
                    "prompt_tokens": usage.get("promptTokenCount"),
                    "output_tokens": usage.get("candidatesTokenCount"),
                    "total_tokens": usage.get("totalTokenCount"),
                }

        if rate_limited_models:
            retry_after = max(rate_limit_waits or [300.0])
            models_text = ", ".join(dict.fromkeys(rate_limited_models))
            raise GeminiRateLimitError(
                "StockLog Gbot 요청 한도에 일시적으로 도달했습니다. 이번 판단에서는 주문하지 않고 자동으로 다시 시도합니다.",
                retry_after_seconds=retry_after,
                models=list(dict.fromkeys(rate_limited_models)),
            )
        raise RuntimeError(
            "Gemini에서 사용 가능한 Flash 모델을 찾지 못했습니다. "
            + (last_model_error or "모델 목록/프로젝트 권한을 확인해주세요.")
        )

    async def analyze(self, stock_context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        company = stock_context.get("company") or {}
        parsed, meta = await self._generate_json(
            system=DEEP_SYSTEM_PROMPT,
            prompt={
                "role": "StockLog Gbot 독립 분석가",
                "stocklog_context": _context_for_llm(stock_context),
                "instruction": "다른 AI의 의견을 보지 말고 정량 데이터만으로 독립 판단한다.",
            },
            model=self.model,
            request_kind="interactive_independent",
            stock_code=str(company.get("code") or ""),
            max_output_tokens=4800,
        )
        return finalize_deep_result(parsed, stock_context), meta

    async def synthesize(
        self,
        stock_context: dict[str, Any],
        gemini_opinion: dict[str, Any],
        ollama_opinion: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        company = stock_context.get("company") or {}
        parsed, meta = await self._generate_json(
            system=SYNTHESIS_SYSTEM_PROMPT,
            prompt={
                "stocklog_context": _context_for_llm(stock_context),
                "gbot_independent_opinion": gemini_opinion,
                "obot_independent_opinion": ollama_opinion,
                "instruction": "원본 데이터와 두 독립 의견을 비교해 최종 하나의 투자 의견을 작성한다.",
            },
            model=self.model,
            request_kind="interactive_consensus",
            stock_code=str(company.get("code") or ""),
            max_output_tokens=5200,
        )
        result = finalize_deep_result(parsed, stock_context)
        result["model_consensus"] = {
            **(result.get("model_consensus") or {}),
            "gbot_verdict": gemini_opinion.get("verdict", ""),
            "obot_verdict": ollama_opinion.get("verdict", ""),
        }
        if not result["model_consensus"].get("summary"):
            result["model_consensus"]["summary"] = "여러 분석 관점과 주요 데이터를 다시 비교해 최종 의견을 정리했습니다."
        if result["model_consensus"].get("status") == "single_model":
            result["model_consensus"]["status"] = (
                "aligned" if gemini_opinion.get("verdict") == ollama_opinion.get("verdict") else "mixed"
            )
        return finalize_deep_result(result, stock_context), meta

    async def finalize_from_obot(
        self,
        stock_context: dict[str, Any],
        obot_opinion: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Final Gbot pass: full StockLog facts + compact Obot risk review."""
        company = stock_context.get("company") or {}
        parsed, meta = await self._generate_json(
            system=GBOT_FINAL_SYSTEM_PROMPT,
            prompt={
                "stocklog_context": _context_for_llm(stock_context),
                "obot_risk_review": _bot_public_view("StockLog Obot", obot_opinion),
                "instruction": (
                    "Obot의 의견을 그대로 따르지 말고 원본 정량 데이터와 항목별로 검증한 뒤 "
                    "매수 추천/관망/매도 추천 중 하나의 상세 최종 의견을 작성한다."
                ),
            },
            model=self.model,
            request_kind="interactive_obot_then_gbot",
            stock_code=str(company.get("code") or ""),
            max_output_tokens=5200,
        )
        result = finalize_deep_result(parsed, stock_context)
        result["model_consensus"] = {
            **(result.get("model_consensus") or {}),
            "gbot_verdict": result.get("verdict", ""),
            "obot_verdict": obot_opinion.get("verdict", ""),
        }
        if not result["model_consensus"].get("summary"):
            result["model_consensus"]["summary"] = "Obot의 위험 관점을 원본 정량 데이터와 대조해 Gbot이 최종 판단을 확정했습니다."
        return finalize_deep_result(result, stock_context), meta


    async def analyze_momentum(self, stock_context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        company = stock_context.get("company") or {}
        momentum = stock_context.get("momentum") or {}
        parsed, meta = await self._generate_json(
            system=MOMENTUM_SYSTEM_PROMPT,
            prompt={
                "company": company,
                "momentum": momentum,
                "instruction": "보유종목 목록용 빠른 모멘텀 분석. 계좌번호·보유수량·평단을 추측하지 않는다.",
            },
            model=self.background_model,
            request_kind="background",
            stock_code=str(company.get("code") or ""),
            max_output_tokens=300,
        )
        return _normalize_momentum_result(stock_context, parsed), meta


class OllamaAnalyst:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "qwen3:1.7b").strip()
        self.timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "10m").strip()
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "520"))

    async def status(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
            names = [str(item.get("name") or item.get("model") or "") for item in (data.get("models") or []) if isinstance(item, dict)]
            return {
                "ok": True,
                "base_url": self.base_url,
                "model": self.model,
                "model_installed": self.model in names or (":" not in self.model and any(name.split(":")[0] == self.model for name in names)),
                "models": names,
            }
        except Exception as exc:
            return {"ok": False, "base_url": self.base_url, "model": self.model, "model_installed": False, "models": [], "error": str(exc)}

    async def _chat_json(
        self,
        *,
        system: str,
        prompt: dict[str, Any],
        num_predict: int,
        num_ctx: int,
        read_timeout: float | None,
        stream_progress_callback=None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Call the local model with NDJSON streaming.

        v3.73.2 deliberately does not use a short HTTP read timeout for interactive
        Obot analysis.  A CPU-only Ollama instance can spend tens of seconds loading
        the model or evaluating the prompt before the first generated token.  With
        ``stream=False`` that healthy work looked identical to a dead connection and
        was incorrectly killed by the old 30~60 second read timeout.

        Streaming lets StockLog observe real output activity and expose it to the
        detail page.  ``read_timeout=None`` means there is no per-chunk timeout; the
        premium pipeline still has a much larger hard safety guard so a truly wedged
        process cannot occupy the worker forever.
        """
        timeout = httpx.Timeout(connect=6.0, read=read_timeout, write=30.0, pool=10.0)
        request_started = asyncio.get_running_loop().time()
        content_parts: list[str] = []
        final_raw: dict[str, Any] = {}
        received_chars = 0
        chunks = 0
        first_chunk_seconds = None
        last_emit = 0.0

        def emit(detail: dict[str, Any]) -> None:
            nonlocal last_emit
            if not stream_progress_callback:
                return
            now = asyncio.get_running_loop().time()
            # Avoid writing DB/progress state for every generated token.
            force = bool(detail.get("done")) or detail.get("phase") in {"connected", "first_token"}
            if not force and now - last_emit < 1.0:
                return
            last_emit = now
            try:
                stream_progress_callback(detail)
            except Exception:
                pass

        emit({"phase": "connecting", "message": "StockLog Obot 연결을 준비하고 있습니다.", "elapsed_seconds": 0})
        payload={
            "model": self.model,
            "stream": True,
            "think": False,
            "keep_alive": self.keep_alive,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, separators=(",", ":"), default=str)},
            ],
            "options": {
                "temperature": 0.08,
                "num_ctx": max(1024, int(num_ctx)),
                "num_predict": max(120, int(num_predict)),
            },
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                emit({"phase": "connected", "message": "StockLog Obot 모델이 입력 데이터를 처리하고 있습니다.", "elapsed_seconds": 0})
                async for line in response.aiter_lines():
                    line=(line or "").strip()
                    if not line:
                        continue
                    try:
                        raw=json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError("Ollama 스트리밍 응답 형식이 올바르지 않습니다.") from exc
                    if not isinstance(raw,dict):
                        continue
                    final_raw=raw
                    piece=((raw.get("message") or {}).get("content") or "")
                    if piece:
                        content_parts.append(piece)
                        received_chars += len(piece)
                        chunks += 1
                        elapsed=max(0.0, asyncio.get_running_loop().time()-request_started)
                        if first_chunk_seconds is None:
                            first_chunk_seconds=elapsed
                            emit({
                                "phase":"first_token",
                                "message":"StockLog Obot이 위험·반대 관점 결과를 생성하고 있습니다.",
                                "elapsed_seconds":round(elapsed,1),
                                "received_chars":received_chars,
                                "chunks":chunks,
                            })
                        else:
                            emit({
                                "phase":"generating",
                                "message":"StockLog Obot이 위험·반대 관점 결과를 생성하고 있습니다.",
                                "elapsed_seconds":round(elapsed,1),
                                "received_chars":received_chars,
                                "chunks":chunks,
                            })
                    if raw.get("done"):
                        elapsed=max(0.0, asyncio.get_running_loop().time()-request_started)
                        emit({
                            "phase":"done",
                            "message":"StockLog Obot 응답 생성을 완료했습니다.",
                            "elapsed_seconds":round(elapsed,1),
                            "received_chars":received_chars,
                            "chunks":chunks,
                            "done":True,
                        })

        content="".join(content_parts).strip()
        if not content:
            raise RuntimeError("Ollama 응답에 분석 내용이 없습니다.")
        return _parse_ai_json(content), {
            "provider": "ollama",
            "model": final_raw.get("model") or self.model,
            "fallback": False,
            "streaming": True,
            "first_chunk_seconds": round(first_chunk_seconds, 3) if first_chunk_seconds is not None else None,
            "received_chars": received_chars,
            "stream_chunks": chunks,
            "total_duration_ns": final_raw.get("total_duration"),
            "load_duration_ns": final_raw.get("load_duration"),
            "prompt_eval_count": final_raw.get("prompt_eval_count"),
            "eval_count": final_raw.get("eval_count"),
        }

    async def analyze(self, stock_context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        company = stock_context.get("company") or {}
        try:
            parsed, meta = await self._chat_json(
                system=DEEP_SYSTEM_PROMPT,
                prompt={
                    "role": "StockLog Obot 독립 분석가",
                    "stocklog_context": _context_for_llm(stock_context, compact=True),
                    "instruction": "StockLog Gbot의 의견을 보지 않고 독립적으로 판단한다. 핵심 근거를 연결해 충분히 설명하되 JSON만 반환한다.",
                },
                num_predict=min(max(self.num_predict, 420), 700),
                num_ctx=max(self.num_ctx, 3072),
                read_timeout=min(max(self.timeout_seconds, 45.0), 75.0),
            )
            return finalize_deep_result(parsed, stock_context), meta
        except httpx.TimeoutException:
            return _deterministic_fallback(stock_context, "ollama_timeout"), {
                "provider": "ollama",
                "model": self.model,
                "fallback": True,
                "fallback_reason": "timeout",
            }

    async def analyze_fast_risk(self, stock_context: dict[str, Any], *, progress_callback=None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fast Obot pass over compressed StockLog facts.

        Obot is only the first risk-review stage. Keep both the input and output
        intentionally small. If the local model returns truncated/invalid JSON, retry
        once with an even smaller schema instead of aborting the whole premium flow.
        """
        compact_facts = _context_for_obot_fast(stock_context)
        attempts = (
            {
                "system": OBOT_FAST_SYSTEM_PROMPT,
                "instruction": "핵심 위험과 반대 논리를 실제 입력 수치로만 짧게 점검하고 JSON 객체를 끝까지 완성한다.",
                "num_predict": min(max(int(os.getenv("OBOT_FAST_NUM_PREDICT", "280")), 220), 340),
                "num_ctx": min(max(int(os.getenv("OBOT_FAST_NUM_CTX", "1792")), 1280), 2304),
                # No short per-chunk read timeout. Streaming activity is surfaced to
                # the user and the pipeline hard guard handles truly wedged jobs.
                "read_timeout": None,
                "retry": False,
            },
            {
                "system": OBOT_ULTRA_FAST_SYSTEM_PROMPT,
                "instruction": "위험과 반대 논리만 매우 짧게 JSON으로 반환한다. JSON을 반드시 닫는다.",
                "num_predict": min(max(int(os.getenv("OBOT_RETRY_NUM_PREDICT", "190")), 150), 240),
                "num_ctx": min(max(int(os.getenv("OBOT_RETRY_NUM_CTX", "1280")), 1024), 1536),
                "read_timeout": None,
                "retry": True,
            },
        )
        errors: list[str] = []
        for attempt_index, spec in enumerate(attempts, start=1):
            if progress_callback:
                try:
                    progress_callback("obot_running", {
                        "phase":"retry" if spec["retry"] else "starting",
                        "message":(
                            "StockLog Obot 응답을 더 작은 형식으로 다시 정리하고 있습니다."
                            if spec["retry"] else
                            "StockLog Obot이 압축된 정량 데이터를 읽고 있습니다."
                        ),
                        "attempt":attempt_index,
                    })
                except Exception:
                    pass
            try:
                parsed, meta = await self._chat_json(
                    system=spec["system"],
                    prompt={
                        "role": "StockLog Obot 리스크 분석가",
                        "stocklog_compact_facts": compact_facts,
                        "instruction": spec["instruction"],
                    },
                    num_predict=int(spec["num_predict"]),
                    num_ctx=int(spec["num_ctx"]),
                    read_timeout=spec["read_timeout"],
                    stream_progress_callback=(
                        (lambda detail, attempt_index=attempt_index: progress_callback(
                            "obot_running", {**(detail or {}), "attempt":attempt_index}
                        ))
                        if progress_callback else None
                    ),
                )
                result = _normalize_obot_fast_result(parsed, stock_context)
                return result, {
                    **meta,
                    "fast_risk_pass": True,
                    "retry_used": bool(spec["retry"]),
                    "attempt_count": 2 if spec["retry"] else 1,
                }
            except Exception as exc:
                detail = f"{type(exc).__name__}: {str(exc)[:180]}"
                errors.append(detail)
                logger.warning(
                    "StockLog Obot fast pass failed attempt=%s model=%s error=%s",
                    attempt_index,
                    self.model,
                    detail,
                )
                if progress_callback and attempt_index < len(attempts):
                    try:
                        progress_callback("obot_running", {
                            "phase":"retry_pending",
                            "message":"Obot 응답을 완성하지 못해 초경량 형식으로 자동 재시도합니다.",
                            "attempt":attempt_index+1,
                        })
                    except Exception:
                        pass
                continue

        raise RuntimeError("Obot fast analysis failed after compact retry: " + " | ".join(errors[-2:]))


    async def analyze_momentum(self, stock_context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            parsed, meta = await self._chat_json(
                system=MOMENTUM_SYSTEM_PROMPT,
                prompt={
                    "company": stock_context.get("company") or {},
                    "momentum": stock_context.get("momentum") or {},
                    "instruction": "보유종목 목록용 빠른 모멘텀 분석.",
                },
                num_predict=180,
                num_ctx=1024,
                read_timeout=min(max(self.timeout_seconds, 25.0), 40.0),
            )
            return _normalize_momentum_result(stock_context, parsed), meta
        except Exception as exc:
            return _normalize_momentum_result(stock_context, {}), {
                "provider": "ollama",
                "model": self.model,
                "fallback": True,
                "fallback_reason": type(exc).__name__,
            }


def _normalize_momentum_result(stock_context: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    company = stock_context.get("company") or {}
    momentum = stock_context.get("momentum") or {}
    name = str(company.get("name") or company.get("code") or "보유종목")
    points = 0
    for key in ("price_vs_ma20", "price_vs_ma60"):
        if momentum.get(key) == "above":
            points += 1
        elif momentum.get(key) == "below":
            points -= 1
    for key, threshold in (("return_20d_pct", 3), ("return_5d_pct", 1)):
        try:
            value = float(momentum.get(key))
            if value > threshold:
                points += 1
            elif value < -threshold:
                points -= 1
        except Exception:
            pass
    view = "positive" if points >= 2 else "negative" if points <= -2 else "neutral"
    labels = {"positive": "상승 추천", "neutral": "관망", "negative": "주의"}
    result = {
        "view": view,
        "confidence": min(88, 55 + abs(points) * 8),
        "label": labels[view],
        "summary": f"{name}은 최근 수익률과 20/60일 이동평균을 함께 보면 {labels[view]} 모멘텀으로 해석됩니다.",
        "checkpoints": [],
    }
    candidate = str(parsed.get("view") or "").lower()
    if candidate in VIEW_LABELS:
        result["view"] = candidate
    result["confidence"] = _clamp_int(parsed.get("confidence"), result["confidence"])
    if _clean_text(parsed.get("label"), 30):
        result["label"] = _clean_text(parsed.get("label"), 30)
    if _clean_text(parsed.get("summary"), 500):
        result["summary"] = _clean_text(parsed.get("summary"), 500)
    result["checkpoints"] = _clean_list(parsed.get("checkpoints"), limit=3, item_limit=160)
    if not result["checkpoints"]:
        for label, key in (("5일", "return_5d_pct"), ("20일", "return_20d_pct")):
            try:
                result["checkpoints"].append(f"{label} 수익률 {float(momentum.get(key)):+.1f}%")
            except Exception:
                pass
    return result



class DualAnalysisUnavailable(RuntimeError):
    """Raised when a premium dual-bot analysis cannot obtain both independent opinions."""


def _bot_dimension_views(opinion: dict[str, Any]) -> dict[str, str]:
    views: dict[str, str] = {}
    for key in DIMENSION_KEYS:
        item = opinion.get(key)
        if isinstance(item, dict):
            view = str(item.get("view") or "neutral")
            views[key] = view if view in VIEW_LABELS else "neutral"
    return views


def _bot_public_view(label: str, opinion: dict[str, Any]) -> dict[str, Any]:
    opinion = normalize_result(opinion)
    return {
        "label": label,
        "verdict": opinion.get("verdict", "wait"),
        "verdict_label": VERDICT_LABELS.get(opinion.get("verdict"), "관망"),
        "confidence": _clamp_int(opinion.get("confidence"), 50),
        "headline": _clean_text(opinion.get("headline"), 360),
        "summary": _clean_text(opinion.get("executive_summary"), 1800),
        "positive_factors": _clean_list(opinion.get("positive_factors"), limit=4, item_limit=360),
        "risk_factors": _clean_list(opinion.get("risk_factors"), limit=4, item_limit=360),
        "dimension_views": _bot_dimension_views(opinion),
    }


def build_dual_bot_views(gbot_opinion: dict[str, Any], obot_opinion: dict[str, Any]) -> dict[str, Any]:
    g = _bot_public_view("StockLog Gbot", gbot_opinion)
    o = _bot_public_view("StockLog Obot", obot_opinion)
    aligned = g["verdict"] == o["verdict"]
    return {
        "gbot": g,
        "obot": o,
        "agreement": {
            "status": "aligned" if aligned else "mixed",
            "label": "의견 일치" if aligned else "의견 차이",
            "summary": (
                f"Gbot과 Obot 모두 {g['verdict_label']} 의견입니다."
                if aligned
                else f"Gbot은 {g['verdict_label']}, Obot은 {o['verdict_label']} 의견이어서 StockLog가 정량 데이터를 다시 대조했습니다."
            ),
        },
    }


def _merge_dimension(gbot_opinion: dict[str, Any], obot_opinion: dict[str, Any], key: str) -> dict[str, str]:
    g = gbot_opinion.get(key) if isinstance(gbot_opinion.get(key), dict) else {}
    o = obot_opinion.get(key) if isinstance(obot_opinion.get(key), dict) else {}
    gv = str(g.get("view") or "neutral")
    ov = str(o.get("view") or "neutral")
    view = gv if gv == ov and gv in VIEW_LABELS else "neutral"
    gs = _clean_text(g.get("summary"), 380)
    os = _clean_text(o.get("summary"), 380)
    summary = " / ".join(x for x in (gs, os) if x)
    return {"view": view, "summary": summary[:760] or "두 분석 관점의 방향을 함께 확인했습니다."}


def fallback_dual_consensus(stock_context: dict[str, Any], gbot_opinion: dict[str, Any], obot_opinion: dict[str, Any]) -> dict[str, Any]:
    """Deterministic StockLog consensus used only if the final synthesis stage fails.

    Both independent AI opinions must already exist. This never upgrades a single-bot
    result into a premium dual analysis.
    """
    g = normalize_result(gbot_opinion)
    o = normalize_result(obot_opinion)
    same = g.get("verdict") == o.get("verdict")
    verdict = g.get("verdict") if same else "wait"
    name = str((stock_context.get("company") or {}).get("name") or "해당 종목")
    positives: list[str] = []
    risks: list[str] = []
    watches: list[str] = []
    for src in (g, o):
        for item in src.get("positive_factors") or []:
            _append_unique(positives, item)
        for item in src.get("risk_factors") or []:
            _append_unique(risks, item)
        for item in src.get("watch_conditions") or []:
            _append_unique(watches, item)
    result: dict[str, Any] = {
        "verdict": verdict,
        "confidence": max(35, min(90, round((int(g.get("confidence",50))+int(o.get("confidence",50)))/2 - (0 if same else 10)))),
        "headline": f"{name}: Gbot과 Obot의 독립 분석을 비교한 결과 {VERDICT_LABELS.get(verdict,'관망')} 의견입니다.",
        "executive_summary": (
            "두 분석 의견이 같은 방향을 제시해 정량 데이터와 다시 대조했습니다."
            if same else
            "Gbot과 Obot의 결론이 달라 StockLog가 실적·가격·수급·추세·뉴스 데이터를 다시 대조해 보수적으로 결론을 정리했습니다."
        ),
        "verdict_reason": "두 독립 분석과 StockLog 정량 근거를 함께 비교해 최종 판단했습니다.",
        "positive_factors": positives[:8],
        "risk_factors": risks[:8],
        "watch_conditions": watches[:8],
        "new_investor_strategy": g.get("new_investor_strategy") or o.get("new_investor_strategy"),
        "holder_strategy": o.get("holder_strategy") or g.get("holder_strategy"),
        "entry_timing": g.get("entry_timing") or o.get("entry_timing"),
        "buy_plan": o.get("buy_plan") or g.get("buy_plan"),
        "short_term_view": g.get("short_term_view") or o.get("short_term_view"),
        "mid_term_view": o.get("mid_term_view") or g.get("mid_term_view"),
        "buy_probability": round((int(g.get("buy_probability",0))+int(o.get("buy_probability",0)))/2),
        "wait_probability": round((int(g.get("wait_probability",0))+int(o.get("wait_probability",0)))/2),
        "sell_probability": round((int(g.get("sell_probability",0))+int(o.get("sell_probability",0)))/2),
        "missing_data": list(dict.fromkeys((g.get("missing_data") or []) + (o.get("missing_data") or [])))[:8],
        "quant_agreement": {"status":"partial","reason":"두 독립 분석을 StockLog 정량 데이터와 교차 확인했습니다."},
        "model_consensus": {
            "status": "aligned" if same else "mixed",
            "gbot_verdict": g.get("verdict", ""),
            "obot_verdict": o.get("verdict", ""),
            "summary": "두 분석 결과와 정량 데이터를 교차 검증해 최종 의견을 정리했습니다.",
        },
        "bot_views": build_dual_bot_views(g, o),
    }
    for key in DIMENSION_KEYS:
        result[key] = _merge_dimension(g, o, key)
    final = finalize_deep_result(result, stock_context)
    final["bot_views"] = build_dual_bot_views(g, o)
    final["dual_analysis"] = True
    return final

class HybridAnalyst:
    """StockLog AI pipeline. Premium stock detail analysis uses Gbot only.

    Obot remains available for lightweight/internal compatibility paths such as
    portfolio momentum fallback, but it is intentionally not called by premium
    stock-detail analysis because CPU-only local generation was the dominant
    latency and failure source.
    """

    def __init__(self, gemini_api_key: str = ""):
        self.gemini = GeminiAnalyst(gemini_api_key) if str(gemini_api_key or "").strip() else None
        self.ollama = OllamaAnalyst()
        self.model = self.gemini.model if self.gemini else self.ollama.model
        self.provider = "gemini" if self.gemini else "ollama"
        self.gemini_stage_timeout = float(os.getenv("AI_GBOT_FINAL_TIMEOUT_SECONDS", "120"))
        self.ollama_stage_timeout = float(os.getenv("AI_OBOT_HARD_LIMIT_SECONDS", "600"))
        self.synthesis_timeout = self.gemini_stage_timeout

    @staticmethod
    def _emit_progress(progress_callback, stage: str, detail: dict[str, Any] | None = None) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(stage, detail or {})
        except TypeError:
            try:
                progress_callback(stage)
            except Exception:
                pass
        except Exception:
            pass

    async def analyze(
        self,
        stock_context: dict[str, Any],
        *,
        require_dual: bool = False,
        require_gbot: bool = False,
        progress_callback=None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Analyze a stock. Premium detail requests require StockLog Gbot only."""
        # ``require_dual`` is retained only for backwards-compatible callers.
        # New premium detail flow deliberately maps it to Gbot-only execution.
        premium_gbot = bool(require_gbot or require_dual)

        if premium_gbot and not self.gemini:
            raise DualAnalysisUnavailable("StockLog Gbot 연결 설정을 확인해주세요.")

        if self.gemini:
            self._emit_progress(progress_callback, "gbot_running", {
                "phase":"generating",
                "message":"StockLog Gbot이 전체 정량 데이터와 공개 정보를 분석하고 있습니다.",
            })
            try:
                result, meta = await asyncio.wait_for(
                    self.gemini.analyze(stock_context), timeout=self.gemini_stage_timeout
                )
            except Exception as exc:
                if premium_gbot:
                    logger.exception("StockLog Gbot premium stage failed: %s", type(exc).__name__)
                    raise DualAnalysisUnavailable("StockLog Gbot 분석을 완료하지 못했습니다. 잠시 후 다시 시도해주세요.") from exc
            else:
                self._emit_progress(progress_callback, "gbot_completed", {
                    "phase":"generated",
                    "message":"StockLog Gbot 분석을 완료했습니다.",
                })
                self._emit_progress(progress_callback, "verifying", {
                    "phase":"verifying",
                    "message":"StockLog가 Gbot 의견과 실제 정량 데이터의 일치 여부를 검증하고 있습니다.",
                })
                final = finalize_deep_result(result, stock_context)
                final.pop("bot_views", None)
                final["dual_analysis"] = False
                final["gbot_analysis"] = True
                final["analysis_pipeline"] = "gbot_only"
                consensus = final.get("model_consensus") if isinstance(final.get("model_consensus"), dict) else {}
                final["model_consensus"] = {
                    **consensus,
                    "status":"single_model",
                    "gbot_verdict":final.get("verdict", ""),
                    "obot_verdict":"",
                    "summary":"StockLog Gbot이 전체 정량 데이터와 공개 정보를 직접 분석하고 StockLog가 근거 일치 여부를 최종 검증했습니다.",
                }
                return final, {
                    **(meta or {}),
                    "provider":"gemini",
                    "model":self.gemini.model,
                    "ensemble":False,
                    "dual_complete":False,
                    "gbot_complete":True,
                    "pipeline":"gbot_only",
                }

        # Non-premium compatibility path only. This keeps existing lightweight
        # local functionality alive without putting Obot back in premium detail.
        try:
            result, meta = await asyncio.wait_for(
                self.ollama.analyze(stock_context), timeout=self.ollama_stage_timeout
            )
            final = finalize_deep_result(result, stock_context)
            final["dual_analysis"] = False
            final["gbot_analysis"] = False
            return final, {**(meta or {}), "dual_complete": False, "gbot_complete": False}
        except Exception as exc:
            return _deterministic_fallback(stock_context, type(exc).__name__), {
                "provider": "stocklog",
                "model": "deterministic",
                "fallback": True,
                "dual_complete": False,
                "gbot_complete": False,
                "fallback_reason": type(exc).__name__,
            }

    async def analyze_momentum(self, stock_context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        # Portfolio auto-analysis remains lightweight. Running two full LLMs for
        # every holding would monopolize a CPU-only server and is unnecessary.
        if self.gemini:
            try:
                return await asyncio.wait_for(self.gemini.analyze_momentum(stock_context), timeout=min(self.gemini_stage_timeout, 35.0))
            except Exception:
                pass
        return await self.ollama.analyze_momentum(stock_context)
