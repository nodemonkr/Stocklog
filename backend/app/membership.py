from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import MembershipFeaturePolicy, MembershipRefreshPolicy, User
from .db_utils import commit_or_rollback

TIERS = ("NORMAL", "PREMIUM", "EVENT", "ADMIN")
TIER_LABELS = {
    "NORMAL": "일반회원",
    "PREMIUM": "프리미엄회원",
    "EVENT": "이벤트회원",
    "ADMIN": "관리자",
}

FEATURES: dict[str, dict[str, Any]] = {
    "smart_analysis": {"label": "스마트 분석", "description": "가치·성장·AI 추천 종목과 종목 상세 분석"},
    "smart_full_market": {"label": "스마트 분석 전체 시장", "description": "스마트 분석에서 전체 분석 가능 종목 탐색·고급 필터 사용"},
    "ai_analysis": {"label": "AI 종목 분석", "description": "종목별 AI Analyst 분석", "supports_limit": True},
    "theme_analysis": {"label": "인기테마 분석", "description": "KOSPI·KOSDAQ 일반 상장종목 중심의 인기테마와 구성종목 분석"},
    "flow_analysis": {"label": "수급 분석", "description": "당일 투자자 수급 순위와 기본 수급점수"},
    "flow_advanced": {"label": "고급 수급 분석", "description": "3·5·7·20일, 기관 세부·쌍끌이·반전·연속매수 필터"},
    "mock_trading": {"label": "모의투자", "description": "키움 모의계좌 조회·주문·예약주문"},
    "live_trading": {"label": "실전투자", "description": "키움 실계좌 조회·주문·자동매매"},
    "portfolio_ai_momentum": {"label": "보유종목 AI 모멘텀", "description": "모의투자 보유종목의 추세·수익률·이동평균을 AI가 자동 해석"},
    "kiwoom_settings": {"label": "키움 설정", "description": "개인 키움 REST API 설정"},
}

# limit_value: AI daily count. -1 means unlimited; None means feature has no count limit.
DEFAULT_POLICY: dict[str, dict[str, tuple[bool, int | None]]] = {
    "NORMAL": {
        "smart_analysis": (True, None),
        "smart_full_market": (False, None),
        "ai_analysis": (True, 5),
        "theme_analysis": (True, None),
        "flow_analysis": (True, None),
        "flow_advanced": (False, None),
        "mock_trading": (True, None),
        "live_trading": (True, None),
        "portfolio_ai_momentum": (False, None),
        "kiwoom_settings": (True, None),
    },
    "PREMIUM": {
        "smart_analysis": (True, None),
        "smart_full_market": (True, None),
        "ai_analysis": (True, 30),
        "theme_analysis": (True, None),
        "flow_analysis": (True, None),
        "flow_advanced": (True, None),
        "mock_trading": (True, None),
        "live_trading": (True, None),
        "portfolio_ai_momentum": (True, None),
        "kiwoom_settings": (True, None),
    },
    "EVENT": {
        "smart_analysis": (True, None),
        "smart_full_market": (True, None),
        "ai_analysis": (True, -1),
        "theme_analysis": (True, None),
        "flow_analysis": (True, None),
        "flow_advanced": (True, None),
        "mock_trading": (True, None),
        "live_trading": (True, None),
        "portfolio_ai_momentum": (True, None),
        "kiwoom_settings": (True, None),
    },
    "ADMIN": {key: (True, -1 if key == "ai_analysis" else None) for key in FEATURES},
}


def normalize_tier(value: str | None) -> str:
    tier = str(value or "NORMAL").strip().upper()
    return tier if tier in TIERS else "NORMAL"


def user_tier(user: User) -> str:
    # Legacy flags remain authoritative for backward compatibility during migration.
    if bool(getattr(user, "is_admin", False)):
        return "ADMIN"
    raw = normalize_tier(getattr(user, "membership_tier", "NORMAL"))
    if raw == "ADMIN":
        return "ADMIN"
    if raw == "NORMAL" and bool(getattr(user, "is_test_account", False)):
        return "EVENT"
    return raw


def ensure_default_policies(db: Session) -> None:
    existing = {
        (row.tier, row.feature_key): row
        for row in db.query(MembershipFeaturePolicy).all()
    }
    changed = False
    for tier, feature_map in DEFAULT_POLICY.items():
        for feature_key, (enabled, limit_value) in feature_map.items():
            if (tier, feature_key) in existing:
                continue
            db.add(MembershipFeaturePolicy(
                tier=tier,
                feature_key=feature_key,
                enabled=enabled,
                limit_value=limit_value,
            ))
            changed = True
    if changed:
        commit_or_rollback(db)


def feature_policy(db: Session, tier: str, feature_key: str) -> dict[str, Any]:
    tier = normalize_tier(tier)
    default_enabled, default_limit = DEFAULT_POLICY.get(tier, DEFAULT_POLICY["NORMAL"]).get(
        feature_key, (False, None)
    )
    row = (
        db.query(MembershipFeaturePolicy)
        .filter(
            MembershipFeaturePolicy.tier == tier,
            MembershipFeaturePolicy.feature_key == feature_key,
        )
        .first()
    )
    return {
        "enabled": bool(row.enabled) if row else bool(default_enabled),
        "limit_value": row.limit_value if row else default_limit,
    }


def resolved_features(db: Session, user: User) -> dict[str, dict[str, Any]]:
    tier = user_tier(user)
    return {
        key: {**meta, **feature_policy(db, tier, key)}
        for key, meta in FEATURES.items()
    }


def set_user_tier(user: User, tier: str) -> None:
    tier = normalize_tier(tier)
    user.membership_tier = tier
    # Keep legacy fields synchronized so older code and stored tokens remain safe.
    user.is_admin = tier == "ADMIN"
    user.is_test_account = tier == "EVENT"


def policy_matrix(db: Session) -> dict[str, Any]:
    ensure_default_policies(db)
    rows = db.query(MembershipFeaturePolicy).all()
    by_key = {(r.tier, r.feature_key): r for r in rows}
    tiers = []
    for tier in TIERS:
        features = {}
        for key, meta in FEATURES.items():
            row = by_key.get((tier, key))
            default_enabled, default_limit = DEFAULT_POLICY[tier][key]
            features[key] = {
                **meta,
                "enabled": bool(row.enabled) if row else default_enabled,
                "limit_value": row.limit_value if row else default_limit,
            }
        tiers.append({"tier": tier, "label": TIER_LABELS[tier], "features": features})
    return {"tiers": tiers, "feature_order": list(FEATURES)}


DEFAULT_REFRESH_POLICY: dict[str, dict[str, int]] = {
    "NORMAL": {"trading_seconds": 45, "theme_seconds": 120},
    "PREMIUM": {"trading_seconds": 30, "theme_seconds": 60},
    "EVENT": {"trading_seconds": 20, "theme_seconds": 45},
    "ADMIN": {"trading_seconds": 15, "theme_seconds": 30},
}


def ensure_default_refresh_policies(db: Session) -> None:
    existing={row.tier:row for row in db.query(MembershipRefreshPolicy).all()}
    changed=False
    for tier,values in DEFAULT_REFRESH_POLICY.items():
        if tier in existing:
            continue
        db.add(MembershipRefreshPolicy(
            tier=tier,
            trading_seconds=values["trading_seconds"],
            theme_seconds=values["theme_seconds"],
        ))
        changed=True
    if changed:
        commit_or_rollback(db)


def refresh_policy_for_tier(db: Session, tier: str) -> dict[str, int | str]:
    tier=normalize_tier(tier)
    ensure_default_refresh_policies(db)
    row=(db.query(MembershipRefreshPolicy).filter(MembershipRefreshPolicy.tier==tier).first())
    defaults=DEFAULT_REFRESH_POLICY[tier]
    return {
        "tier":tier,
        "label":TIER_LABELS.get(tier,tier),
        "trading_seconds":int(row.trading_seconds if row else defaults["trading_seconds"]),
        "theme_seconds":int(row.theme_seconds if row else defaults["theme_seconds"]),
    }


def refresh_policy_matrix(db: Session) -> dict[str, Any]:
    ensure_default_refresh_policies(db)
    rows={row.tier:row for row in db.query(MembershipRefreshPolicy).all()}
    items=[]
    for tier in TIERS:
        defaults=DEFAULT_REFRESH_POLICY[tier]
        row=rows.get(tier)
        items.append({
            "tier":tier,
            "label":TIER_LABELS[tier],
            "trading_seconds":int(row.trading_seconds if row else defaults["trading_seconds"]),
            "theme_seconds":int(row.theme_seconds if row else defaults["theme_seconds"]),
        })
    return {"tiers":items,"min_seconds":10,"max_seconds":3600,"zero_disables":True}
