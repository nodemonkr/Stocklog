from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


# These labels are useful for the audit trail, but must never become a reusable
# reason to penalize a future stock.  They either describe information that was
# unavailable at entry or say that the review did not find a reliable cause.
NON_REUSABLE_FAILURE_TAGS = {
    "post_entry_event",
    "insufficient_evidence",
    "normal_variation",
    "other",
}

MATCHABLE_FAILURE_TAGS = {
    "chasing_momentum",
    "weak_flow",
    "excessive_volatility",
    "weak_fundamentals",
    "news_risk",
    "disclosure_risk",
    "low_coverage",
    "valuation_risk",
    "timing_error",
}


def clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def should_review_outcome(*, age_minutes: float, current_return_pct: float, max_drawdown_pct: float,
                          closed: bool = False, realized_return_pct: float | None = None) -> tuple[bool, str]:
    """Conservative trigger for a post-trade review.

    A temporary red tick immediately after purchase is not considered a failed trade.
    Closed losses are reviewed immediately. Open positions need enough elapsed time or
    a material drawdown before they become review candidates.
    """
    if closed and realized_return_pct is not None and realized_return_pct <= -0.5:
        return True, f"손실 청산 {realized_return_pct:.2f}%"
    if age_minutes >= 120 and current_return_pct <= -3.0:
        return True, f"매수 후 {age_minutes/60:.1f}시간 경과 · 수익률 {current_return_pct:.2f}%"
    if age_minutes >= 60 and max_drawdown_pct <= -5.0:
        return True, f"매수 후 최대낙폭 {max_drawdown_pct:.2f}%"
    return False, ""


def normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("tag") or item.get("name") or ""
        text = str(item or "").strip().lower().replace(" ", "_")[:80]
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out[:12]


def actionable_failure_tags(case: dict[str, Any]) -> list[str]:
    """Return only review findings that are safe to reuse for future entries.

    A reviewer may keep low-confidence or post-entry causes for transparency.
    Those are intentionally retained in the stored audit JSON while being
    excluded from the trading memory used by Gbot.
    """
    review = case.get("review") if isinstance(case.get("review"), dict) else {}
    verdict = str(review.get("verdict") or case.get("verdict") or "").strip().lower()
    if verdict == "normal_variation":
        return []

    causes = review.get("root_causes") if isinstance(review, dict) else None
    if isinstance(causes, list) and causes:
        reusable: list[str] = []
        for cause in causes:
            tag_list = normalize_tags([cause])
            if not tag_list:
                continue
            tag = tag_list[0]
            severity = str(cause.get("severity") or "").strip().lower() if isinstance(cause, dict) else ""
            if tag in NON_REUSABLE_FAILURE_TAGS:
                continue
            # In a mixed review, a low-severity observation is too weak to
            # generalize into a future confidence adjustment.
            if verdict == "mixed" and severity == "low":
                continue
            if tag not in reusable:
                reusable.append(tag)
        return reusable[:12]

    # Backward compatibility for reviews created before verdict/severity were
    # persisted.  Non-reusable labels are still filtered out.
    return [tag for tag in normalize_tags(case.get("failure_tags")) if tag not in NON_REUSABLE_FAILURE_TAGS]


def _episode_key(case: dict[str, Any], index: int) -> str:
    explicit = str(case.get("episode_key") or "").strip()
    if explicit:
        return explicit
    code = str(case.get("stock_code") or "").strip()
    entry = case.get("entry_at") or case.get("created_at")
    if code and entry:
        # Multiple scale-in orders for the same stock on the same trading day
        # are one correlated experience, not independent proof of a pattern.
        return f"{code}:{str(entry)[:10]}"
    return f"row:{index}"


def _case_return(case: dict[str, Any]) -> float:
    value = case.get("realized_return_pct")
    if value is None:
        value = case.get("current_return_pct")
    return clamp(value, -1000, 1000)


def aggregate_learning_patterns(cases: list[dict[str, Any]], *, min_repeat: int = 2, limit: int = 8) -> list[dict[str, Any]]:
    """Aggregate independent, actionable failures into reusable patterns."""
    episodes: dict[str, set[str]] = {}
    stocks: dict[str, set[str]] = {}
    examples: dict[str, list[str]] = {}
    returns: dict[str, list[float]] = {}
    drawdowns: dict[str, list[float]] = {}
    for index, case in enumerate(cases):
        case_name = str(case.get("stock_name") or case.get("stock_code") or "")
        code = str(case.get("stock_code") or case_name or "").strip()
        episode = _episode_key(case, index)
        for tag in actionable_failure_tags(case):
            episodes.setdefault(tag, set())
            if episode in episodes[tag]:
                continue
            episodes[tag].add(episode)
            if code:
                stocks.setdefault(tag, set()).add(code)
            returns.setdefault(tag, []).append(_case_return(case))
            drawdowns.setdefault(tag, []).append(clamp(case.get("max_drawdown_pct"), -1000, 1000))
            if case_name:
                examples.setdefault(tag, [])
                if case_name not in examples[tag] and len(examples[tag]) < 3:
                    examples[tag].append(case_name)
    counts = Counter({tag: len(keys) for tag, keys in episodes.items()})
    rows = []
    for tag, count in counts.most_common():
        if count < max(1, min_repeat):
            continue
        tag_returns = returns.get(tag) or [0.0]
        tag_drawdowns = drawdowns.get(tag) or [0.0]
        stock_count = len(stocks.get(tag) or set())
        # Two independent observations remain a warning.  Deterministic
        # confidence adjustment starts only after 3 episodes across 2 stocks.
        adjustment_ready = bool(tag in MATCHABLE_FAILURE_TAGS and count >= 3 and stock_count >= 2)
        rows.append({
            "tag": tag,
            "count": count,
            "stock_count": stock_count,
            "examples": examples.get(tag, []),
            "avg_return_pct": round(sum(tag_returns) / len(tag_returns), 2),
            "avg_drawdown_pct": round(sum(tag_drawdowns) / len(tag_drawdowns), 2),
            "adjustment_ready": adjustment_ready,
        })
    return rows[:limit]


def build_learning_memory(cases: list[dict[str, Any]], *, max_recent: int = 5) -> dict[str, Any]:
    adverse = [x for x in cases if str(x.get("outcome_label") or "") in {"loss", "drawdown"}]
    closed_losses = [x for x in adverse if str(x.get("outcome_label") or "") == "loss"]
    patterns = _enrich_pattern_performance(aggregate_learning_patterns(adverse, min_repeat=2), cases)
    recent = []
    for case in adverse[:max_recent]:
        lessons = case.get("lessons") if isinstance(case.get("lessons"), list) else []
        review = case.get("review") if isinstance(case.get("review"), dict) else {}
        recent.append({
            "code": str(case.get("stock_code") or ""),
            "name": str(case.get("stock_name") or ""),
            "outcome_label": str(case.get("outcome_label") or ""),
            "return_pct": round(float(case.get("realized_return_pct") if case.get("realized_return_pct") is not None else case.get("current_return_pct") or 0), 2),
            "failure_tags": actionable_failure_tags(case)[:6],
            "lessons": [str(x)[:240] for x in lessons[:4]],
            "verdict": str(review.get("verdict") or case.get("verdict") or ""),
            "entry_at": str(case.get("entry_at") or "") or None,
        })
    return {
        "reviewed_adverse_cases": len(adverse),
        "reviewed_loss_cases": len(closed_losses),
        "actionable_cases": sum(1 for case in adverse if actionable_failure_tags(case)),
        "recurring_patterns": patterns,
        "recent_adverse_cases": recent,
        "policy_version": 2,
        "policy": (
            "과거 손실은 위험 경고 메모리일 뿐 매수 금지 규칙이 아니다. 정상 변동·매수 후 돌발정보·근거 부족은 재사용하지 않는다. "
            "같은 종목의 같은 날 분할매수는 한 사례로 세고, 3개 이상 독립 사례와 2개 이상 종목에서 반복된 패턴이 "
            "성공·회복 사례와 비교해도 불리하며 현재 후보의 최신 정량 데이터와 일치할 때만 제한적으로 확신도를 감점한다."
        ),
    }


def _numeric(candidate: dict[str, Any], key: str) -> float | None:
    value = candidate.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _match_candidate_pattern(tag: str, candidate: dict[str, Any]) -> tuple[bool, str]:
    change = _numeric(candidate, "change_rate")
    momentum = _numeric(candidate, "momentum_20d")
    volatility = _numeric(candidate, "volatility")
    foreign = _numeric(candidate, "foreign_net_5d")
    institution = _numeric(candidate, "institution_net_5d")
    revenue_growth = _numeric(candidate, "revenue_growth")
    operating_margin = _numeric(candidate, "operating_margin")
    roe = _numeric(candidate, "roe")
    coverage = _numeric(candidate, "coverage")
    per = _numeric(candidate, "per")
    pbr = _numeric(candidate, "pbr")

    if tag == "chasing_momentum":
        matched = bool((change is not None and change >= 5) or (momentum is not None and momentum >= 15))
        return matched, f"당일 {change or 0:.1f}% · 20일 모멘텀 {momentum or 0:.1f}%"
    if tag == "timing_error":
        matched = bool(change is not None and momentum is not None and change >= 3 and momentum >= 10)
        return matched, f"단기 상승 {change or 0:.1f}% · 20일 모멘텀 {momentum or 0:.1f}%"
    if tag == "weak_flow":
        matched = bool(foreign is not None and institution is not None and foreign < 0 and institution < 0)
        return matched, f"외국인 5일 {foreign or 0:,.0f} · 기관 5일 {institution or 0:,.0f}"
    if tag == "excessive_volatility":
        return bool(volatility is not None and volatility >= 5), f"변동성 {volatility or 0:.1f}%"
    if tag == "weak_fundamentals":
        weak = sum(1 for value in (revenue_growth, operating_margin, roe) if value is not None and value <= 0)
        return weak >= 2, f"성장률 {revenue_growth or 0:.1f}% · 영업이익률 {operating_margin or 0:.1f}% · ROE {roe or 0:.1f}%"
    if tag == "low_coverage":
        return bool(coverage is not None and coverage < 60), f"데이터 커버리지 {coverage or 0:.0f}%"
    if tag == "valuation_risk":
        matched = bool((per is not None and per > 0 and per >= 35) or (pbr is not None and pbr > 0 and pbr >= 4))
        return matched, f"PER {per or 0:.1f} · PBR {pbr or 0:.1f}"
    if tag == "news_risk":
        news = candidate.get("recent_news") if isinstance(candidate.get("recent_news"), list) else []
        negative = sum(1 for item in news if isinstance(item, dict) and str(item.get("sentiment") or "").lower() == "negative")
        positive = sum(1 for item in news if isinstance(item, dict) and str(item.get("sentiment") or "").lower() == "positive")
        return negative > positive and negative > 0, f"최근 뉴스 긍정 {positive} · 부정 {negative}"
    if tag == "disclosure_risk":
        disclosures = candidate.get("recent_disclosures") if isinstance(candidate.get("recent_disclosures"), list) else []
        highest = max((clamp(item.get("importance_score"), 0, 100) for item in disclosures if isinstance(item, dict)), default=0)
        return highest >= 70, f"최근 공시 중요도 최고 {highest:.0f}점"
    return False, ""


def _age_days(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        now = datetime.now(parsed.tzinfo or timezone.utc)
        if parsed.tzinfo is None:
            now = now.replace(tzinfo=None)
        return max(0.0, (now - parsed).total_seconds() / 86400)
    except (TypeError, ValueError):
        return None


def _candidate_pattern_data_fresh(tag: str, candidate: dict[str, Any]) -> bool:
    freshness = candidate.get("data_freshness") if isinstance(candidate.get("data_freshness"), dict) else {}

    def recent(values: list[Any], max_days: float) -> bool:
        ages = [age for age in (_age_days(value) for value in values) if age is not None]
        return bool(ages and min(ages) <= max_days)

    if tag == "weak_flow":
        return recent([candidate.get("flow_data_date"), freshness.get("kiwoom_metrics_updated_at")], 14)
    if tag in {"chasing_momentum", "timing_error", "excessive_volatility"}:
        return recent([candidate.get("price_data_date"), freshness.get("kiwoom_metrics_updated_at")], 14)
    if tag in {"weak_fundamentals", "valuation_risk"}:
        return recent([freshness.get("dart_financials_updated_at"), freshness.get("smart_score_updated_at")], 200)
    if tag == "low_coverage":
        return recent([freshness.get("smart_score_updated_at")], 30)
    if tag == "news_risk":
        news = candidate.get("recent_news") if isinstance(candidate.get("recent_news"), list) else []
        return recent([item.get("published_at") for item in news if isinstance(item, dict)], 14)
    if tag == "disclosure_risk":
        disclosures = candidate.get("recent_disclosures") if isinstance(candidate.get("recent_disclosures"), list) else []
        return recent([item.get("receipt_date") for item in disclosures if isinstance(item, dict)], 60)
    return False


def _enrich_pattern_performance(patterns: list[dict[str, Any]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Challenge each failure pattern with wins/recoveries under the same setup."""
    completed_labels = {"loss", "drawdown", "win", "flat", "recovered"}
    for pattern in patterns:
        tag = str(pattern.get("tag") or "")
        matched_cases: list[dict[str, Any]] = []
        seen_episodes: set[str] = set()
        for index, case in enumerate(cases):
            if str(case.get("outcome_label") or "") not in completed_labels:
                continue
            candidate = case.get("entry_candidate") if isinstance(case.get("entry_candidate"), dict) else {}
            matched, _ = _match_candidate_pattern(tag, candidate)
            if not matched:
                continue
            episode = _episode_key(case, index)
            if episode in seen_episodes:
                continue
            seen_episodes.add(episode)
            matched_cases.append(case)
        sample_count = len(matched_cases)
        adverse_count = sum(1 for case in matched_cases if str(case.get("outcome_label") or "") in {"loss", "drawdown"})
        average_return = round(sum(_case_return(case) for case in matched_cases) / sample_count, 2) if sample_count else None
        adverse_rate = round((adverse_count / sample_count) * 100, 1) if sample_count else None
        confirmed = bool(
            pattern.get("adjustment_ready") and sample_count >= 3
            and adverse_rate is not None and adverse_rate >= 67
            and average_return is not None and average_return < 0
        )
        pattern["matched_outcome_samples"] = sample_count
        pattern["matched_adverse_rate_pct"] = adverse_rate
        pattern["matched_avg_return_pct"] = average_return
        pattern["adjustment_ready"] = confirmed
        pattern["validation"] = (
            "confirmed" if confirmed else "counterexamples_present"
            if sample_count >= 3 else "insufficient_sample"
        )
    return patterns


def candidate_learning_risk(candidate: dict[str, Any], memory: dict[str, Any]) -> dict[str, Any]:
    """Match statistically repeated failure patterns to one current candidate."""
    matches: list[dict[str, Any]] = []
    penalty = 0.0
    for pattern in memory.get("recurring_patterns") or []:
        if not isinstance(pattern, dict):
            continue
        tag = str(pattern.get("tag") or "")
        matched, evidence = _match_candidate_pattern(tag, candidate)
        if not matched:
            continue
        count = max(0, int(pattern.get("count") or 0))
        stock_count = max(0, int(pattern.get("stock_count") or 0))
        data_fresh = _candidate_pattern_data_fresh(tag, candidate)
        ready = bool(pattern.get("adjustment_ready") and data_fresh)
        item_penalty = min(5.0, 2.0 + max(0, count - 3)) if ready else 0.0
        penalty += item_penalty
        matches.append({
            "tag": tag,
            "count": count,
            "stock_count": stock_count,
            "evidence": evidence,
            "data_fresh": data_fresh,
            "confidence_penalty": item_penalty,
            "mode": "adjust" if item_penalty else "warning",
        })
    total_penalty = round(min(12.0, penalty), 1)
    return {
        "matched": bool(matches),
        "matched_patterns": matches[:6],
        "confidence_penalty": total_penalty,
        "mode": "adjust" if total_penalty > 0 else "warning" if matches else "none",
    }


def apply_learning_risk_adjustments(decisions: list[dict[str, Any]], candidates: list[dict[str, Any]],
                                    memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply a capped, explainable confidence adjustment to BUY decisions."""
    candidate_map = {
        str(item.get("code") or ""): item
        for item in candidates
        if isinstance(item, dict) and str(item.get("code") or "")
    }
    adjusted: list[dict[str, Any]] = []
    for decision in decisions:
        row = dict(decision) if isinstance(decision, dict) else {}
        action = str(row.get("action") or "").lower()
        if action not in {"buy", "add"}:
            adjusted.append(row)
            continue
        risk = candidate_learning_risk(candidate_map.get(str(row.get("code") or ""), {}), memory)
        original = clamp(row.get("confidence"), 0, 100)
        penalty = clamp(risk.get("confidence_penalty"), 0, 12)
        row["_gbot_confidence"] = original
        row["_learning_penalty"] = penalty
        row["_learning_risk"] = risk
        row["confidence"] = round(max(0.0, original - penalty), 1)
        adjusted.append(row)
    return adjusted


def diagnostic_health(*, watcher_running: bool, heartbeat_age_seconds: float | None,
                      enabled: bool, market_open: bool, today_cycles: int, error_cycles: int,
                      last_error: str = "") -> dict[str, str]:
    if not watcher_running:
        return {"level": "error", "label": "감시 프로세스 중지", "message": "백엔드 자동매매 watcher가 실행 중이 아닙니다."}
    if heartbeat_age_seconds is not None and heartbeat_age_seconds > 120:
        return {"level": "error", "label": "감시 heartbeat 지연", "message": f"마지막 watcher 확인이 {heartbeat_age_seconds:.0f}초 전입니다."}
    if last_error:
        return {"level": "warning", "label": "최근 오류 있음", "message": last_error[:300]}
    if enabled and market_open and today_cycles == 0:
        return {"level": "warning", "label": "오늘 판단 기록 없음", "message": "장중 자동매매가 켜져 있지만 오늘 실행 회차가 아직 기록되지 않았습니다."}
    if error_cycles > 0:
        return {"level": "warning", "label": "일부 회차 오류", "message": f"오늘 오류 회차 {error_cycles}건이 기록되었습니다."}
    return {"level": "ok", "label": "정상 감시", "message": "watcher heartbeat와 자동매매 실행 기록이 정상 범위입니다."}
