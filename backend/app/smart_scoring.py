"""Explainable Smart Analysis scoring for StockLog.

The goal of this module is to keep the score deterministic and auditable.  LLMs
may summarize the result later, but the numeric score shown to users comes from
synchronized StockLog data and can always be traced back to its components.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _linear(value: Any, low: float, high: float, *, neutral: float = 50.0) -> float:
    value = _num(value)
    if value is None or high <= low:
        return neutral
    return _clamp((value - low) / (high - low) * 100.0)


def _inverse(value: Any, good: float, bad: float, *, neutral: float = 50.0) -> float:
    value = _num(value)
    if value is None or bad <= good:
        return neutral
    return _clamp(100.0 - ((value - good) / (bad - good) * 100.0))


def _fmt(value: Any, suffix: str = "", digits: int = 1) -> str:
    value = _num(value)
    if value is None:
        return "데이터 없음"
    if suffix == "억원":
        return f"{value:,.0f}{suffix}"
    return f"{value:,.{digits}f}{suffix}"


def strategy_match(stock: Any, strategy: str) -> bool:
    """Return whether a stock matches a Smart Analysis strategy preset.

    Kept in the scoring module rather than the large FastAPI module so a UI/API
    refactor cannot accidentally delete the matcher while leaving its call site.
    ``stock`` may be an ORM object or a mapping-like object.
    """
    strategy = str(strategy or "전체").strip()
    if strategy == "전체":
        return True

    def value(name: str):
        if isinstance(stock, dict):
            return _num(stock.get(name))
        return _num(getattr(stock, name, None))

    per = value("per")
    pbr = value("pbr")
    roe = value("roe")
    growth = value("revenue_growth")
    momentum = value("momentum_20d")
    dividend = value("dividend_yield")
    volatility = value("volatility")

    if strategy == "가치":
        return bool((per is not None and 0 < per <= 18) or (pbr is not None and 0 < pbr <= 1.8))
    if strategy == "성장":
        return bool((growth is not None and growth >= 10) or (roe is not None and roe >= 12))
    if strategy == "모멘텀":
        return bool(momentum is not None and momentum >= 5)
    if strategy == "배당":
        return bool(dividend is not None and dividend >= 2)
    if strategy == "안정":
        return bool((volatility is None or volatility <= 4.5) and (roe is None or roe >= 5))
    return True


@dataclass
class Component:
    key: str
    label: str
    weight: int
    score: float
    available: bool
    evidence: list[str]
    ai_view: str
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "weight": self.weight,
            "score": round(_clamp(self.score), 1),
            "available": bool(self.available),
            "evidence": self.evidence[:5],
            "ai_view": self.ai_view,
            "source": self.source,
        }


def _financial_component(stock: dict[str, Any]) -> Component:
    roe = _num(stock.get("roe"))
    growth = _num(stock.get("revenue_growth"))
    margin = _num(stock.get("operating_margin"))
    vals = []
    evidence = []
    if roe is not None:
        vals.append((_linear(roe, 0, 22), 0.34))
        evidence.append(f"ROE {_fmt(roe, '%')} — 자기자본으로 이익을 내는 효율")
    if growth is not None:
        vals.append((_linear(growth, -10, 30), 0.34))
        evidence.append(f"매출 성장률 {_fmt(growth, '%')} — 외형 성장 속도")
    if margin is not None:
        vals.append((_linear(margin, -5, 22), 0.32))
        evidence.append(f"영업이익률 {_fmt(margin, '%')} — 본업에서 남기는 이익 수준")
    available = bool(vals)
    if available:
        total_w = sum(w for _, w in vals)
        score = sum(v * w for v, w in vals) / total_w
    else:
        score = 50.0
        evidence.append("최근 동기화된 수익성·성장 재무지표가 부족합니다.")
    if score >= 70:
        view = "수익성과 성장 지표가 전반적으로 양호해 기업 체력 측면에서 긍정적으로 봅니다."
    elif score >= 45:
        view = "좋은 지표와 아쉬운 지표가 섞여 있어 최근 실적 추세를 함께 확인할 구간입니다."
    else:
        view = "수익성 또는 성장성이 약해 실적 회복 여부를 먼저 확인할 필요가 있습니다."
    return Component("financial", "재무제표 기준 분석", 25, score, available, evidence, view, "OpenDART 재무제표")


def _valuation_component(stock: dict[str, Any]) -> Component:
    per = _num(stock.get("per"))
    pbr = _num(stock.get("pbr"))
    dividend = _num(stock.get("dividend_yield"))
    vals = []
    evidence = []
    if per is not None and per > 0:
        vals.append((_inverse(per, 8, 45), 0.48))
        evidence.append(f"PER {_fmt(per, '배')} — 이익 대비 현재 주가 수준")
    if pbr is not None and pbr > 0:
        vals.append((_inverse(pbr, 0.8, 5.0), 0.37))
        evidence.append(f"PBR {_fmt(pbr, '배', 2)} — 순자산 대비 현재 주가 수준")
    if dividend is not None:
        vals.append((_linear(dividend, 0, 5), 0.15))
        evidence.append(f"배당수익률 {_fmt(dividend, '%')} — 주가 대비 현금 환원 수준")
    available = bool(vals)
    if available:
        total_w = sum(w for _, w in vals)
        score = sum(v * w for v, w in vals) / total_w
    else:
        score = 50.0
        evidence.append("현재 가격과 비교할 수 있는 밸류에이션 지표가 부족합니다.")
    if score >= 70:
        view = "현재 이익·자산 대비 가격 부담이 비교적 낮은 편으로 평가합니다."
    elif score >= 45:
        view = "현재 가격이 특별히 싸거나 비싸다고 단정하기 어려운 중간 구간입니다."
    else:
        view = "실적·자산 대비 가격 부담이 있어 성장 기대가 실제 실적으로 이어지는지 확인이 필요합니다."
    return Component("valuation", "밸류에이션 기준 분석", 20, score, available, evidence, view, "OpenDART + 현재가 계산")


def _momentum_component(stock: dict[str, Any]) -> Component:
    momentum = _num(stock.get("momentum_20d"))
    day = _num(stock.get("change_rate"))
    vals = []
    evidence = []
    if momentum is not None:
        vals.append((_linear(momentum, -20, 25), 0.78))
        evidence.append(f"20일 주가 흐름 {_fmt(momentum, '%')} — 최근 한 달 안팎의 방향성")
    if day is not None:
        vals.append((_linear(day, -8, 8), 0.22))
        evidence.append(f"오늘 등락률 {_fmt(day, '%')} — 당일 시장 반응")
    available = bool(vals)
    if available:
        total_w = sum(w for _, w in vals)
        score = sum(v * w for v, w in vals) / total_w
    else:
        score = 50.0
        evidence.append("최근 가격 흐름 데이터가 부족합니다.")
    if score >= 70:
        view = "최근 가격 흐름이 우호적입니다. 다만 급등 직후라면 추격 매수 여부는 별도로 확인해야 합니다."
    elif score >= 45:
        view = "최근 주가가 뚜렷한 방향을 만들지 못해 확인 구간으로 봅니다."
    else:
        view = "최근 가격 흐름이 약해 진입 시점은 보수적으로 보는 편이 좋습니다."
    return Component("momentum", "주가 흐름 기준 분석", 15, score, available, evidence, view, "키움 시세 데이터")


def _stability_component(stock: dict[str, Any]) -> Component:
    volatility = _num(stock.get("volatility"))
    market_cap = _num(stock.get("market_cap"))
    dividend = _num(stock.get("dividend_yield"))
    vals = []
    evidence = []
    if volatility is not None:
        vals.append((_inverse(volatility, 1.5, 10.0), 0.55))
        evidence.append(f"변동성 {_fmt(volatility)} — 값이 낮을수록 가격 흔들림이 상대적으로 작음")
    if market_cap is not None and market_cap > 0:
        cap_score = _linear(math.log10(max(market_cap, 100.0)), 2.0, 6.7)
        vals.append((cap_score, 0.30))
        evidence.append(f"시가총액 {_fmt(market_cap, '억원', 0)} — 규모가 클수록 일반적으로 거래 기반이 안정적")
    if dividend is not None:
        vals.append((_linear(dividend, 0, 5), 0.15))
    available = bool(vals)
    if available:
        total_w = sum(w for _, w in vals)
        score = sum(v * w for v, w in vals) / total_w
    else:
        score = 50.0
        evidence.append("변동성·시가총액 등 안정성 데이터가 부족합니다.")
    if score >= 70:
        view = "가격 흔들림과 기업 규모를 함께 보면 상대적으로 안정적인 편입니다."
    elif score >= 45:
        view = "안정성은 평균적인 구간으로, 다른 강점과 함께 판단하는 편이 좋습니다."
    else:
        view = "가격 변동 또는 규모 측면에서 흔들림이 클 수 있어 비중 관리가 중요합니다."
    return Component("stability", "안정성 기준 분석", 10, score, available, evidence, view, "키움 시세 + 기업 규모")


def _flow_component(flow: dict[str, Any] | None) -> Component:
    flow = flow or {}
    days = int(flow.get("days") or 0)
    ratio = _num(flow.get("net_ratio"))
    positive_days = int(flow.get("positive_days") or 0)
    foreign = _num(flow.get("foreign_net")) or 0.0
    institution = _num(flow.get("institution_net")) or 0.0
    available = days > 0
    evidence = []
    if available:
        ratio_score = _linear(ratio, -60.0, 60.0) if ratio is not None else 50.0
        breadth = positive_days / max(days, 1) * 100.0
        score = ratio_score * 0.65 + breadth * 0.35
        evidence.append(f"최근 {days}거래일 외국인 순매수 {foreign:,.0f}")
        evidence.append(f"최근 {days}거래일 기관 순매수 {institution:,.0f}")
        evidence.append(f"외국인+기관 순매수 우위 일수 {positive_days}/{days}일")
        if ratio is not None:
            evidence.append(f"최근 수급 방향성 지표 {ratio:+.1f}% — 외국인·기관 매수/매도 강도의 균형")
    else:
        score = 50.0
        evidence.append("최근 수급 동기화 데이터가 없습니다. 관리자 수급 동기화 후 반영됩니다.")
    if score >= 70:
        view = "최근 외국인·기관 수급이 우호적인 편으로 판단합니다."
    elif score >= 45:
        view = "외국인·기관 수급이 한 방향으로 강하게 모이지 않은 상태입니다."
    else:
        view = "최근 외국인·기관 수급이 약해 수급 반전 여부를 확인할 필요가 있습니다."
    return Component("flow", "수급 기준 분석", 15, score, available, evidence, view, "키움 투자자별 수급")


def _sentiment_component(sentiment: dict[str, Any] | None) -> Component:
    sentiment = sentiment or {}
    pos = int(sentiment.get("positive") or 0)
    neu = int(sentiment.get("neutral") or 0)
    neg = int(sentiment.get("negative") or 0)
    reports = int(sentiment.get("reports") or 0)
    news = int(sentiment.get("news") or 0)
    total = pos + neu + neg
    available = total > 0
    evidence = []
    if available:
        raw = (pos - neg) / max(total, 1)
        confidence = min(1.0, total / 8.0)
        score = 50.0 + raw * 45.0 * confidence
        evidence.append(f"최근 6개월 뉴스·리포트: 긍정 {pos} / 관망 {neu} / 부정 {neg}")
        evidence.append(f"분석 대상 뉴스 {news}건 · 증권사 리포트 {reports}건")
    else:
        score = 50.0
        evidence.append("최근 6개월 뉴스·증권사 리포트 분석 데이터가 없습니다.")
    if score >= 70:
        view = "최근 뉴스와 증권사 리포트의 방향이 전반적으로 긍정적입니다."
    elif score >= 45:
        view = "긍정·관망·부정 의견이 섞여 있어 단일 방향으로 보기 어렵습니다."
    else:
        view = "최근 부정적인 뉴스·리포트 비중이 높아 이슈가 해소되는지 확인이 필요합니다."
    return Component("sentiment", "뉴스·리포트 기준 분석", 15, score, available, evidence, view, "최근 6개월 뉴스 + 증권사 리포트")


def _profile_percentages(profile_scores: dict[str, Any] | None, profile_code: str = "") -> dict[str, dict[str, float]]:
    raw = ((profile_scores or {}).get("percentages") or {})
    out: dict[str, dict[str, float]] = {}
    defaults = {
        "horizon": {"L": 34.0, "N": 33.0, "S": 33.0},
        "risk": {"A": 50.0, "D": 50.0},
        "value": {"G": 50.0, "V": 50.0},
        "profit": {"P": 50.0, "H": 50.0},
        "spread": {"F": 50.0, "M": 50.0},
    }
    code = str(profile_code or "")
    axis_positions = {"horizon": 0, "risk": 1, "value": 2, "profit": 3, "spread": 4}
    for axis, axis_defaults in defaults.items():
        current = raw.get(axis) if isinstance(raw, dict) else None
        parsed = {}
        if isinstance(current, dict):
            for key, default in axis_defaults.items():
                parsed[key] = _num(current.get(key)) if _num(current.get(key)) is not None else default
        else:
            parsed = dict(axis_defaults)
            idx = axis_positions[axis]
            if idx < len(code) and code[idx] in axis_defaults:
                parsed = {key: (100.0 if key == code[idx] else 0.0) for key in axis_defaults}
        out[axis] = parsed
    return out


PROFILE_TRAITS = {
    "growth": "성장 선호",
    "value": "가치 선호",
    "stability": "안정성 선호",
    "momentum": "주가 흐름 선호",
    "flow": "수급 민감도",
    "dividend": "배당 선호",
    "volatility": "변동성 허용",
    "long_term": "장기 보유 성향",
    "short_term": "단기 매매 성향",
    "concentration": "집중 투자 허용",
}


def user_profile_traits(profile_scores: dict[str, Any] | None, profile_code: str = "") -> dict[str, float]:
    """Translate the questionnaire result into an independent preference vector.

    These values describe *what the member prefers*, not whether a stock is good.
    Keeping this vector separate from the StockLog aggregate score prevents the
    personal-fit score from simply becoming a reweighted copy of that score.
    """
    p = _profile_percentages(profile_scores, profile_code)

    def pct(axis: str, key: str, default: float = 50.0) -> float:
        return _clamp(float((p.get(axis) or {}).get(key, default)))

    traits = {
        "growth": 0.75 * pct("value", "G") + 0.15 * pct("risk", "A") + 0.10 * pct("profit", "H"),
        "value": 0.80 * pct("value", "V") + 0.10 * pct("risk", "D") + 0.10 * pct("profit", "P"),
        "stability": 0.65 * pct("risk", "D") + 0.20 * pct("horizon", "L") + 0.15 * pct("spread", "M"),
        "momentum": 0.55 * pct("horizon", "S") + 0.25 * pct("risk", "A") + 0.20 * pct("profit", "P"),
        "flow": 0.45 * pct("horizon", "S") + 0.35 * pct("risk", "A") + 0.20 * pct("spread", "F"),
        "dividend": 0.45 * pct("risk", "D") + 0.25 * pct("horizon", "L") + 0.20 * pct("value", "V") + 0.10 * pct("profit", "P"),
        "volatility": 0.75 * pct("risk", "A") + 0.15 * pct("horizon", "S") + 0.10 * pct("spread", "F"),
        "long_term": 0.85 * pct("horizon", "L") + 0.10 * pct("risk", "D") + 0.05 * pct("profit", "H"),
        "short_term": 0.85 * pct("horizon", "S") + 0.10 * pct("risk", "A") + 0.05 * pct("profit", "P"),
        "concentration": 0.80 * pct("spread", "F") + 0.10 * pct("risk", "A") + 0.10 * pct("profit", "H"),
    }
    return {key: round(_clamp(value), 1) for key, value in traits.items()}


def _component_score_map(components: list[dict[str, Any]] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in components or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        score = _num(item.get("score"))
        if key and score is not None:
            out[key] = _clamp(score)
    return out


def build_stock_traits(stock: dict[str, Any] | None, components: list[dict[str, Any]] | None = None) -> dict[str, float]:
    """Describe the investment *character* of a stock on the same axes as a user.

    This intentionally differs from the aggregate attractiveness score. For
    example, high volatility can be a poor stability signal while still being a
    good match for a member who explicitly tolerates large price swings.
    """
    stock = stock or {}
    component_scores = _component_score_map(components)

    growth = (
        _linear(stock.get("revenue_growth"), -10, 35) * 0.55
        + _linear(stock.get("roe"), 0, 25) * 0.25
        + _linear(stock.get("operating_margin"), -5, 25) * 0.20
    )

    per_score = _inverse(stock.get("per"), 8, 42)
    pbr_score = _inverse(stock.get("pbr"), 0.8, 5.5)
    dividend = _linear(stock.get("dividend_yield"), 0, 6, neutral=25.0)
    value = per_score * 0.48 + pbr_score * 0.37 + dividend * 0.15

    volatility_raw = _linear(stock.get("volatility"), 0, 12)
    stability_vol = 100.0 - volatility_raw
    market_cap = _num(stock.get("market_cap"))
    if market_cap is None or market_cap <= 0:
        cap_stability = 45.0
    else:
        cap_stability = _clamp((math.log10(max(market_cap, 100.0)) - 2.0) / 4.7 * 100.0)
    quality = (_linear(stock.get("roe"), 0, 25) + _linear(stock.get("operating_margin"), 0, 25)) / 2.0
    stability = stability_vol * 0.48 + cap_stability * 0.32 + quality * 0.12 + dividend * 0.08

    momentum = (
        _linear(stock.get("momentum_20d"), -20, 30) * 0.75
        + _linear(stock.get("change_rate"), -10, 12) * 0.25
    )

    flow_component = component_scores.get("flow", 50.0)
    # Distance from neutral measures how strongly current foreign/institutional
    # flow is influencing the stock. Small/high-volatility names get a modest
    # additional sensitivity score.
    flow = _clamp(abs(flow_component - 50.0) * 1.55 + volatility_raw * 0.22 + (100.0 - cap_stability) * 0.18)

    long_term = _clamp(stability * 0.48 + growth * 0.28 + dividend * 0.14 + quality * 0.10)
    short_term = _clamp(momentum * 0.50 + volatility_raw * 0.25 + flow * 0.25)
    concentration_risk = _clamp(volatility_raw * 0.46 + (100.0 - cap_stability) * 0.34 + (100.0 - stability) * 0.20)

    traits = {
        "growth": growth,
        "value": value,
        "stability": stability,
        "momentum": momentum,
        "flow": flow,
        "dividend": dividend,
        "volatility": volatility_raw,
        "long_term": long_term,
        "short_term": short_term,
        "concentration": concentration_risk,
    }
    return {key: round(_clamp(value), 1) for key, value in traits.items()}


def _trait_similarity(user_value: float, stock_value: float) -> float:
    # A slightly steeper distance curve intentionally creates real separation
    # between stocks that match and conflict with a member's preferences.
    return _clamp(100.0 - abs(float(user_value) - float(stock_value)) * 1.35)


def _profile_label(score: float | None) -> str:
    if score is None:
        return "성향 미검사"
    if score >= 82:
        return "매우 잘 맞음"
    if score >= 68:
        return "잘 맞음"
    if score >= 52:
        return "보통"
    if score >= 38:
        return "다소 다름"
    return "잘 맞지 않음"


def _ai_label(score: float) -> str:
    if score >= 75:
        return "강한 추천"
    if score >= 60:
        return "추천"
    if score >= 45:
        return "관심"
    return "보수적"


def _fit_reason(label: str, user_value: float, stock_value: float, fit: float) -> str:
    if fit >= 82:
        state = "내 선호와 이 종목의 성격이 매우 비슷합니다."
    elif fit >= 68:
        state = "내 선호와 비교적 잘 맞습니다."
    elif fit >= 52:
        state = "일부는 맞지만 차이도 있습니다."
    elif fit >= 38:
        state = "내 선호와 다른 부분이 더 많습니다."
    else:
        state = "내 선호와 종목 성격의 차이가 큽니다."
    return f"{label}: 내 선호 {user_value:.0f} · 종목 성격 {stock_value:.0f}. {state}"


def _profile_fit_result(
    stock: dict[str, Any],
    components: list[dict[str, Any]],
    *,
    profile_scores: dict[str, Any] | None,
    profile_code: str,
    aggregate_score: float | None,
    stock_traits_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    if not (profile_scores or profile_code):
        return {"score": None, "label": "성향 미검사", "traits": [], "component_scores": {}}

    user_traits = user_profile_traits(profile_scores, profile_code)
    stock_traits = dict(stock_traits_override or build_stock_traits(stock, components))

    weighted_total = 0.0
    weight_total = 0.0
    trait_rows: list[dict[str, Any]] = []
    similarities: dict[str, float] = {}
    for key, label in PROFILE_TRAITS.items():
        user_value = float(user_traits.get(key, 50.0))
        stock_value = float(stock_traits.get(key, 50.0))
        fit = _trait_similarity(user_value, stock_value)
        # Strong member preferences should matter more than neutral answers.
        weight = 0.80 + abs(user_value - 50.0) / 50.0 * 0.70
        weighted_total += fit * weight
        weight_total += weight
        similarities[key] = fit
        trait_rows.append({
            "key": key,
            "label": label,
            "user_value": round(user_value, 1),
            "stock_value": round(stock_value, 1),
            "fit": round(fit, 1),
            "view": _fit_reason(label, user_value, stock_value, fit),
        })

    pure_fit = weighted_total / max(weight_total, 1.0)
    # Stock quality is only a guardrail, not the personalization engine. 12%
    # prevents extremely weak stocks from looking perfect while keeping the two
    # public scores genuinely independent.
    if aggregate_score is None:
        final_score = pure_fit
        quality_adjustment = 0.0
    else:
        final_score = pure_fit * 0.88 + _clamp(aggregate_score) * 0.12
        quality_adjustment = final_score - pure_fit

    component_trait_map = {
        "financial": ["growth", "long_term"],
        "valuation": ["value", "dividend"],
        "momentum": ["momentum", "short_term", "volatility"],
        "flow": ["flow", "short_term"],
        "sentiment": ["momentum", "short_term"],
        "stability": ["stability", "long_term", "concentration", "volatility"],
    }
    component_scores: dict[str, float] = {}
    for key, trait_keys in component_trait_map.items():
        vals = [similarities[name] for name in trait_keys if name in similarities]
        component_scores[key] = round(sum(vals) / len(vals), 1) if vals else 50.0

    trait_rows.sort(key=lambda item: abs(float(item["fit"]) - 100.0), reverse=True)
    return {
        "score": round(_clamp(final_score), 1),
        "pure_score": round(_clamp(pure_fit), 1),
        "quality_adjustment": round(quality_adjustment, 1),
        "label": _profile_label(final_score),
        "traits": trait_rows,
        "component_scores": component_scores,
        "user_traits": user_traits,
        "stock_traits": stock_traits,
    }


def build_scorecard(
    stock: dict[str, Any],
    *,
    flow: dict[str, Any] | None = None,
    sentiment: dict[str, Any] | None = None,
    profile_scores: dict[str, Any] | None = None,
    profile_code: str = "",
) -> dict[str, Any]:
    components = [
        _financial_component(stock),
        _valuation_component(stock),
        _momentum_component(stock),
        _flow_component(flow),
        _sentiment_component(sentiment),
        _stability_component(stock),
    ]

    available = [item for item in components if item.available]
    if available:
        available_weight = sum(item.weight for item in available)
        aggregate_score = sum(item.score * item.weight for item in available) / max(available_weight, 1)
        coverage = sum(item.weight for item in available)
    else:
        aggregate_score = 50.0
        coverage = 0

    raw_components = [item.as_dict() for item in components]
    cached_traits = build_stock_traits(stock, raw_components)
    if raw_components:
        # Persist enough stock-character metadata inside the existing component
        # cache so per-user fit can be reproduced without rescanning signal tables.
        raw_components[0]["_stock_traits"] = cached_traits
        raw_components[0]["_aggregate_score"] = round(_clamp(aggregate_score), 1)
    profile = _profile_fit_result(
        stock,
        raw_components,
        profile_scores=profile_scores,
        profile_code=profile_code,
        aggregate_score=aggregate_score,
        stock_traits_override=cached_traits,
    )

    result_components = []
    component_fit = profile.get("component_scores") or {}
    for item in raw_components:
        data = dict(item)
        if profile.get("score") is None:
            data["profile_importance"] = None
            data["profile_score"] = None
            data["profile_view"] = "투자성향 검사를 완료하면 종목 성격과 내 투자방식의 차이를 비교해드립니다."
        else:
            fit = float(component_fit.get(str(item.get("key") or ""), 50.0))
            data["profile_importance"] = None
            data["profile_score"] = round(fit, 1)
            if fit >= 68:
                data["profile_view"] = "이 영역과 연결된 종목 성격이 내 투자방식과 잘 맞습니다."
            elif fit >= 52:
                data["profile_view"] = "이 영역은 내 투자방식과 일부 맞지만 차이도 있습니다."
            else:
                data["profile_view"] = "이 영역의 종목 성격은 내 투자방식과 차이가 있습니다."
        result_components.append(data)

    strongest = sorted(
        [x for x in result_components if x.get("available")],
        key=lambda x: x.get("score") or 0,
        reverse=True,
    )
    weak = sorted(
        [x for x in result_components if x.get("available")],
        key=lambda x: x.get("score") or 0,
    )

    summary = []
    if strongest:
        summary.append(f"가장 강한 항목은 {strongest[0]['label'].replace(' 기준 분석','')} {strongest[0]['score']:.0f}점입니다.")
    if weak and weak[0]["score"] < 50:
        summary.append(f"반대로 {weak[0]['label'].replace(' 기준 분석','')}은 {weak[0]['score']:.0f}점으로 추가 확인이 필요합니다.")
    if coverage < 70:
        summary.append(f"현재 동기화 데이터 기준 분석 커버리지는 {coverage:.0f}%입니다. 누락 데이터가 채워지면 점수가 달라질 수 있습니다.")

    return {
        "ai_score": round(_clamp(aggregate_score), 1),
        "ai_label": _ai_label(aggregate_score),
        "profile_score": profile.get("score"),
        "profile_pure_score": profile.get("pure_score"),
        "profile_quality_adjustment": profile.get("quality_adjustment"),
        "profile_label": profile.get("label"),
        "profile_code": str(profile_code or ""),
        "profile_traits": profile.get("traits") or [],
        "coverage": round(float(coverage), 1),
        "components": result_components,
        "summary": summary,
        "method": "StockLog 종합점수는 동기화된 재무·밸류에이션·주가·수급·뉴스/리포트·안정성 데이터를 같은 기준으로 계산합니다. 내 투자성향 적합도는 별도의 종목 성격 벡터와 회원 성향 벡터의 유사도로 계산하며, 종합점수는 12%의 품질 보정에만 사용합니다.",
    }


def profile_score_from_components(
    components: list[dict[str, Any]] | None,
    *,
    stock: dict[str, Any] | None = None,
    profile_scores: dict[str, Any] | None = None,
    profile_code: str = "",
    aggregate_score: float | None = None,
) -> dict[str, Any]:
    """Calculate independent personal fit from cached aggregate-score inputs.

    No external API or flow/news table scan is performed here. Stock traits are
    derived from the already loaded Stock row and persisted aggregate components.
    """
    raw_components = [dict(item) for item in (components or []) if isinstance(item, dict)]
    if not raw_components:
        return {"score": None, "label": "성향 미검사", "components": [], "traits": []}
    cached_traits = None
    cached_aggregate = aggregate_score
    for item in raw_components:
        if cached_traits is None and isinstance(item.get("_stock_traits"), dict):
            cached_traits = {str(k): float(v) for k, v in item["_stock_traits"].items() if _num(v) is not None}
        if cached_aggregate is None and _num(item.get("_aggregate_score")) is not None:
            cached_aggregate = float(item.get("_aggregate_score"))
    profile = _profile_fit_result(
        stock or {},
        raw_components,
        profile_scores=profile_scores,
        profile_code=profile_code,
        aggregate_score=cached_aggregate,
        stock_traits_override=cached_traits,
    )
    if profile.get("score") is None:
        return {"score": None, "label": "성향 미검사", "components": [], "traits": []}

    component_fit = profile.get("component_scores") or {}
    enriched = []
    for raw in raw_components:
        item = dict(raw)
        key = str(item.get("key") or "")
        fit = float(component_fit.get(key, 50.0))
        item["profile_importance"] = None
        item["profile_score"] = round(fit, 1)
        item["profile_view"] = (
            "이 영역과 연결된 종목 성격이 내 투자방식과 잘 맞습니다."
            if fit >= 68 else
            "이 영역은 내 투자방식과 일부 맞지만 차이도 있습니다."
            if fit >= 52 else
            "이 영역의 종목 성격은 내 투자방식과 차이가 있습니다."
        )
        enriched.append(item)

    return {
        "score": profile.get("score"),
        "pure_score": profile.get("pure_score"),
        "quality_adjustment": profile.get("quality_adjustment"),
        "label": profile.get("label"),
        "components": enriched,
        "traits": profile.get("traits") or [],
    }
