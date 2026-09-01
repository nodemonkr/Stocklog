from __future__ import annotations

from typing import Any


_NUMERIC_FIELDS = (
    "price", "change_rate", "market_cap_eok", "per", "pbr", "roe",
    "revenue_growth", "operating_margin", "dividend_yield", "momentum_20d",
    "volatility", "smart_score", "coverage", "avg_volume_20d",
    "foreign_net_5d", "institution_net_5d", "bot_quantity", "bot_avg_price",
    "bot_return_rate",
)


def _short(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _compact_score_components(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    out: list[Any] = []
    allowed = ("key", "name", "label", "score", "value", "weight", "reason")
    for item in value[:6]:
        if isinstance(item, dict):
            row = {}
            for key in allowed:
                if key not in item or item[key] in (None, "", [], {}):
                    continue
                row[key] = _short(item[key], 90) if isinstance(item[key], str) else item[key]
            if row:
                out.append(row)
        elif item not in (None, ""):
            out.append(_short(item, 90))
    return out


def compact_auto_stock_context(item: dict[str, Any]) -> dict[str, Any]:
    """Keep decision-relevant facts while bounding prompt size per stock."""
    source = item if isinstance(item, dict) else {}
    out: dict[str, Any] = {
        "code": _short(source.get("code"), 12),
        "name": _short(source.get("name"), 50),
        "market": _short(source.get("market"), 16),
        "category": _short(source.get("category") or source.get("sector"), 60),
        "theme_group": _short(source.get("theme_group"), 60),
        "themes": [_short(x, 50) for x in (source.get("themes") or [])[:3] if _short(x, 50)],
    }
    for key in _NUMERIC_FIELDS:
        value = source.get(key)
        if value not in (None, ""):
            out[key] = value

    components = _compact_score_components(source.get("score_components"))
    if components:
        out["score_components"] = components

    freshness = source.get("data_freshness") if isinstance(source.get("data_freshness"), dict) else {}
    out["data_dates"] = {
        "price": _short(source.get("price_data_date"), 32) or None,
        "flow": _short(source.get("flow_data_date"), 32) or None,
        "score": _short(freshness.get("smart_score_updated_at"), 32) or None,
        "financials": _short(freshness.get("dart_financials_updated_at"), 32) or None,
    }

    out["news"] = [
        {
            "title": _short(row.get("title"), 110),
            "sentiment": _short(row.get("sentiment"), 16),
            "date": _short(row.get("published_at"), 24),
        }
        for row in (source.get("recent_news") or [])[:2]
        if isinstance(row, dict) and _short(row.get("title"), 110)
    ]
    out["reports"] = [
        {
            "title": _short(row.get("title"), 100),
            "opinion": _short(row.get("opinion"), 30),
            "target_price": row.get("target_price"),
            "summary": _short(row.get("summary"), 120),
        }
        for row in (source.get("broker_reports") or [])[:1]
        if isinstance(row, dict) and _short(row.get("title"), 100)
    ]
    out["disclosures"] = [
        {
            "name": _short(row.get("report_name"), 100),
            "date": _short(row.get("receipt_date"), 20),
            "importance": row.get("importance_score"),
        }
        for row in (source.get("recent_disclosures") or [])[:1]
        if isinstance(row, dict) and _short(row.get("report_name"), 100)
    ]

    learning = source.get("learning_risk") if isinstance(source.get("learning_risk"), dict) else {}
    if learning.get("matched"):
        out["learning_risk"] = {
            "confidence_penalty": learning.get("confidence_penalty") or 0,
            "patterns": [
                {
                    "tag": _short(row.get("tag"), 60),
                    "evidence": _short(row.get("evidence"), 100),
                    "mode": _short(row.get("mode"), 16),
                }
                for row in (learning.get("matched_patterns") or [])[:3]
                if isinstance(row, dict)
            ],
        }
    return out


def compact_learning_memory(memory: dict[str, Any]) -> dict[str, Any]:
    source = memory if isinstance(memory, dict) else {}
    return {
        "policy_version": source.get("policy_version") or 1,
        "recurring_patterns": [
            {
                "tag": _short(row.get("tag"), 60),
                "count": row.get("count") or 0,
                "stock_count": row.get("stock_count") or 0,
                "adjustment_ready": bool(row.get("adjustment_ready")),
                "validation": _short(row.get("validation"), 40),
            }
            for row in (source.get("recurring_patterns") or [])[:6]
            if isinstance(row, dict)
        ],
    }


def build_auto_decision_batches(
    owned: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    holding_review: bool,
    owned_batch_size: int = 10,
    candidate_batch_size: int = 15,
) -> list[dict[str, Any]]:
    """Split holdings and candidates so one incomplete response cannot grow unbounded."""
    owned_size = max(1, int(owned_batch_size or 10))
    candidate_size = max(1, int(candidate_batch_size or 15))
    compact_owned = [compact_auto_stock_context(row) for row in (owned or []) if isinstance(row, dict)]
    compact_candidates = [compact_auto_stock_context(row) for row in (candidates or []) if isinstance(row, dict)]
    batches: list[dict[str, Any]] = []
    for start in range(0, len(compact_owned), owned_size):
        batches.append({"kind": "owned", "owned": compact_owned[start:start + owned_size], "candidates": []})
    if not holding_review:
        for start in range(0, len(compact_candidates), candidate_size):
            batches.append({"kind": "candidates", "owned": [], "candidates": compact_candidates[start:start + candidate_size]})
    return batches


def is_recoverable_gbot_completeness_error(error: Any) -> bool:
    text = str(error or "")
    return any(fragment in text for fragment in (
        "유효한 JSON 객체를 찾지 못했습니다",
        "보유종목 판단을 누락했습니다",
        "Gbot 판단이 0건입니다",
    ))


def is_recoverable_gbot_response_error(error: Any) -> bool:
    """Return true for model-response defects that must become a safe skip.

    These are not broker, credential, or application failures. They are
    untrusted AI contract failures, so the correct operational state is a
    fail-closed cycle with zero orders and an automatic retry later.
    """
    text = str(error or "")
    return is_recoverable_gbot_completeness_error(text) or any(fragment in text for fragment in (
        "Gbot 응답 무결성 검사 실패",
        "Gbot 응답의 decisions 형식이 배열이 아닙니다",
    ))
