from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80), default="")
    gender: Mapped[str] = mapped_column(String(20), default="")
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone_number: Mapped[str] = mapped_column(String(30), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Test accounts may use AI without daily usage limits, but never inherit admin rights.
    is_test_account: Mapped[bool] = mapped_column(Boolean, default=False)
    # v3.52: NORMAL / PREMIUM / EVENT / ADMIN. Legacy flags remain synchronized.
    membership_tier: Mapped[str] = mapped_column(String(20), default="NORMAL", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # v3.61: lightweight account activity metadata for the administrator member detail view.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_method: Mapped[str] = mapped_column(String(20), default="")
    login_count: Mapped[int] = mapped_column(Integer, default=0)
    # Incremented after an administrator changes this account's password.
    # JWTs carry the version so existing sessions are revoked immediately.
    auth_version: Mapped[int] = mapped_column(Integer, default=0)


class MembershipFeaturePolicy(Base):
    __tablename__ = "membership_feature_policies"
    __table_args__ = (
        UniqueConstraint("tier", "feature_key", name="uq_membership_feature_policy"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tier: Mapped[str] = mapped_column(String(20), index=True)
    feature_key: Mapped[str] = mapped_column(String(60), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class MembershipRefreshPolicy(Base):
    """Per-membership frontend refresh cadence managed by administrators."""
    __tablename__ = "membership_refresh_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tier: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    trading_seconds: Mapped[int] = mapped_column(Integer, default=30)
    theme_seconds: Mapped[int] = mapped_column(Integer, default=60)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class SiteAccessSetting(Base):
    """Administrator-managed IP access policy for every StockLog API client."""
    __tablename__ = "site_access_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True, default="site_access")
    mode: Mapped[str] = mapped_column(String(20), default="allow_all")
    allowed_ips_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class SocialAuthProviderConfig(Base):
    """Administrator-managed OAuth settings for social login providers.

    Client IDs and secrets are encrypted with the same server-side key used for
    Kiwoom credentials. Only masked values are ever returned to the frontend.
    """
    __tablename__ = "social_auth_provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    client_id_enc: Mapped[str] = mapped_column(Text, default="")
    client_secret_enc: Mapped[str] = mapped_column(Text, default="")
    redirect_uri: Mapped[str] = mapped_column(String(512), default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_test_status: Mapped[str] = mapped_column(String(20), default="untested")
    last_test_message: Mapped[str] = mapped_column(Text, default="")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class SocialAccount(Base):
    """Maps a Kakao/Naver/Google identity to one StockLog account."""
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_social_provider_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    provider_user_id: Mapped[str] = mapped_column(String(160), index=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    nickname: Mapped[str] = mapped_column(String(120), default="")
    profile_image: Mapped[str] = mapped_column(String(700), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class SocialAuthSession(Base):
    """Short-lived OAuth state and one-time handoff between provider callback and SPA."""
    __tablename__ = "social_auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="login", index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    return_url: Mapped[str] = mapped_column(String(700), default="")
    initiated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provider_user_id: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    nickname: Mapped[str] = mapped_column(String(120), default="")
    profile_image: Mapped[str] = mapped_column(String(700), default="")
    gender: Mapped[str] = mapped_column(String(20), default="")
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone_number: Mapped[str] = mapped_column(String(30), default="")
    provider_profile_fields: Mapped[str] = mapped_column(String(255), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class UserConsent(Base):
    """Immutable consent record captured during social signup."""
    __tablename__ = "user_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "consent_type", "policy_version", name="uq_user_consent_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    consent_type: Mapped[str] = mapped_column(String(40), index=True)
    policy_version: Mapped[str] = mapped_column(String(40))
    agreed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AiDailyUsage(Base):
    __tablename__ = "ai_daily_usage"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "usage_date",
            name="uq_ai_daily_usage_user_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    usage_date: Mapped[date] = mapped_column(Date, index=True)
    ai_queries: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )


class AiAnalysisAccess(Base):
    """Per-user entitlement to view a shared stock/mode AI analysis cache.

    The expensive AI result remains shared in ``ai_stock_analysis``. This table only
    records which member has unlocked that result, so cached inference is reused
    without leaking it to accounts that did not spend one of their daily uses.
    """
    __tablename__ = "ai_analysis_access"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "stock_code",
            "mode",
            name="uq_ai_analysis_access_user_stock_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="ai", index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class KiwoomCredential(Base):
    __tablename__ = "kiwoom_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    app_key_enc: Mapped[str] = mapped_column(Text)
    secret_key_enc: Mapped[str] = mapped_column(Text)
    account_no: Mapped[str] = mapped_column(String(40), default="")
    use_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class KiwoomLiveCredential(Base):
    """Production Kiwoom credentials, deliberately isolated from paper trading."""
    __tablename__ = "kiwoom_live_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    app_key_enc: Mapped[str] = mapped_column(Text)
    secret_key_enc: Mapped[str] = mapped_column(Text)
    account_no: Mapped[str] = mapped_column(String(40), default="")
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

class Stock(Base):
    __tablename__ = "stock_universe"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    # v3.68.4: current official listed-company name plus provenance/history.
    # Former/alternate names remain searchable after an official rename.
    name_aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    name_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    market: Mapped[str] = mapped_column(String(20), default="KOSPI")
    sector: Mapped[str] = mapped_column(String(80), default="기타")
    # Provider/legacy representative theme. Kept for compatibility.
    primary_theme: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # v3.65: official industry, actual business, and investor-facing themes are separate concepts.
    primary_business: Mapped[str | None] = mapped_column(String(160), nullable=True)
    investment_theme: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    investment_themes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v3.67 deterministic StockLog Theme Engine hierarchy. investment_theme is
    # kept as the backward-compatible primary parent theme.
    theme_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    theme_groups_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme_subthemes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme_engine_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    theme_engine_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_source_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    category: Mapped[str] = mapped_column(String(40), default="종합")
    price: Mapped[float] = mapped_column(Float, default=0)
    change_rate: Mapped[float] = mapped_column(Float, default=0)
    market_cap: Mapped[float] = mapped_column(Float, default=0)  # 억원
    per: Mapped[float | None] = mapped_column(Float, nullable=True)
    pbr: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_calculated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=50)
    # v3.66: Smart Analysis list uses synchronized/precomputed scores so premium
    # users can browse the full market without recalculating flow/news signals on
    # every page request. Detailed score evidence is still generated on demand.
    smart_ai_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    smart_ai_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    smart_score_coverage: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    smart_score_components_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    smart_score_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    corp_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # v3.30 actual OpenDART company-overview industry metadata.
    industry_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    industry_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    industry_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Raw provider rows and StockLog's public/investable universe
    # are separate. Excluded securities remain only for historical/FK safety and
    # are hidden from discovery, analysis, ranking and new automated/manual buys.
    is_analysis_eligible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    analysis_exclusion_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # v3.68.2: protect the master universe from a one-off provider omission.
    universe_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    universe_missing_count: Mapped[int] = mapped_column(Integer, default=0)
    kiwoom_metrics_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dart_financials_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

class StockInvestorFlowDaily(Base):
    __tablename__ = "stock_investor_flow_daily"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_stock_investor_flow_daily"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    close_price: Mapped[float] = mapped_column(Float, default=0)
    price_change: Mapped[float] = mapped_column(Float, default=0)
    trading_value: Mapped[float] = mapped_column(Float, default=0)
    individual_net: Mapped[float] = mapped_column(Float, default=0)
    foreign_net: Mapped[float] = mapped_column(Float, default=0)
    institution_net: Mapped[float] = mapped_column(Float, default=0)
    financial_investment_net: Mapped[float] = mapped_column(Float, default=0)
    insurance_net: Mapped[float] = mapped_column(Float, default=0)
    investment_trust_net: Mapped[float] = mapped_column(Float, default=0)
    other_finance_net: Mapped[float] = mapped_column(Float, default=0)
    bank_net: Mapped[float] = mapped_column(Float, default=0)
    pension_net: Mapped[float] = mapped_column(Float, default=0)
    private_equity_net: Mapped[float] = mapped_column(Float, default=0)
    national_net: Mapped[float] = mapped_column(Float, default=0)
    other_corp_net: Mapped[float] = mapped_column(Float, default=0)
    foreign_other_net: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(40), default="kiwoom-ka10060")
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class PriceBar(Base):
    __tablename__ = "price_bars"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0)
    __table_args__ = (UniqueConstraint("stock_code", "trade_date", name="uq_pricebar"),)

class FinancialQuarter(Base):
    __tablename__ = "financial_quarters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    period: Mapped[str] = mapped_column(String(20))
    # OpenDART does not guarantee that every account is present for every
    # issuer/filing.  Missing is semantically different from zero, so keep it
    # as NULL instead of fabricating 0 and distorting growth/margin analysis.
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    # v3.58.3: filing-native comparable values.  These prevent accidental
    # comparisons between cumulative quarter figures and unrelated periods.
    comparison_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparison_operating_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparison_net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparison_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparison_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparison_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparison_income_period: Mapped[str | None] = mapped_column(String(30), nullable=True)
    comparison_balance_period: Mapped[str | None] = mapped_column(String(30), nullable=True)
    income_basis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    __table_args__ = (UniqueConstraint("stock_code", "period", name="uq_financial_period"),)

class NewsCache(Base):
    __tablename__ = "news_cache"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    publisher: Mapped[str] = mapped_column(String(120), default="")
    published_at: Mapped[str] = mapped_column(String(80), default="")
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0)
    sentiment_reason: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # v3.39 market-intelligence metadata. published_dt is used for actual
    # chronological ordering; fetched_at only means when StockLog saw the item.
    published_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(40), default="")
    source_query: Mapped[str] = mapped_column(String(180), default="")
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    importance_score: Mapped[float] = mapped_column(Float, default=0)
    importance_reason: Mapped[str] = mapped_column(Text, default="")


class BrokerReportCache(Base):
    __tablename__ = "broker_report_cache"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(Text)
    broker: Mapped[str] = mapped_column(String(120), default="")
    report_date: Mapped[str] = mapped_column(String(20), default="")
    report_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    link: Mapped[str] = mapped_column(String(512))
    investment_opinion: Mapped[str] = mapped_column(String(80), default="")
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0)
    brief_summary: Mapped[str] = mapped_column(Text, default="")
    analysis_basis: Mapped[str] = mapped_column(String(120), default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    __table_args__ = (UniqueConstraint("stock_code", "link", name="uq_broker_report_stock_link"),)


class DisclosureCache(Base):
    __tablename__ = "disclosure_cache"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    corp_code: Mapped[str] = mapped_column(String(8), default="", index=True)
    receipt_no: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    report_name: Mapped[str] = mapped_column(Text)
    filer_name: Mapped[str] = mapped_column(String(120), default="")
    receipt_date: Mapped[str] = mapped_column(String(12), default="")
    receipt_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    remark: Mapped[str] = mapped_column(String(120), default="")
    link: Mapped[str] = mapped_column(Text, default="")
    importance_score: Mapped[float] = mapped_column(Float, default=0)
    importance_reason: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class OrderAudit(Base):
    __tablename__ = "order_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    side: Mapped[str] = mapped_column(String(10))
    stock_code: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(Integer)
    order_type: Mapped[str] = mapped_column(String(20))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    broker_order_no: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class AiStockAnalysis(Base):
    __tablename__ = "ai_stock_analysis"
    __table_args__ = (
        UniqueConstraint(
            "stock_code",
            "mode",
            name="uq_ai_stock_analysis_stock_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="ai", index=True)

    provider: Mapped[str] = mapped_column(String(30), default="ollama")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)

    context_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")

    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )


class InvestmentProfile(Base):
    __tablename__ = "investment_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    result_code: Mapped[str] = mapped_column(String(8))
    answers_json: Mapped[str] = mapped_column(Text, default="[]")
    scores_json: Mapped[str] = mapped_column(Text, default="{}")

    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )


class AutoTradingSetting(Base):
    """Per-user StockLog Gbot paper-auto-trading configuration."""
    __tablename__ = "auto_trading_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    trading_start: Mapped[str] = mapped_column(String(5), default="09:05")
    trading_end: Mapped[str] = mapped_column(String(5), default="15:15")
    markets_json: Mapped[str] = mapped_column(Text, default='["KOSPI","KOSDAQ"]')
    categories_json: Mapped[str] = mapped_column(Text, default='[]')
    themes_json: Mapped[str] = mapped_column(Text, default='[]')
    use_all_themes: Mapped[bool] = mapped_column(Boolean, default=True)
    min_price: Mapped[float] = mapped_column(Float, default=1000)
    max_price: Mapped[float] = mapped_column(Float, default=0)
    min_market_cap: Mapped[float] = mapped_column(Float, default=1000)
    max_market_cap: Mapped[float] = mapped_column(Float, default=0)
    min_avg_volume: Mapped[float] = mapped_column(Float, default=100000)
    min_smart_score: Mapped[float] = mapped_column(Float, default=60)
    candidate_limit: Mapped[int] = mapped_column(Integer, default=15)
    min_confidence: Mapped[float] = mapped_column(Float, default=82)
    max_capital: Mapped[float] = mapped_column(Float, default=10000000)
    max_position_amount: Mapped[float] = mapped_column(Float, default=2000000)
    max_positions: Mapped[int] = mapped_column(Integer, default=8)
    max_daily_orders: Mapped[int] = mapped_column(Integer, default=8)
    max_new_buys_per_cycle: Mapped[int] = mapped_column(Integer, default=1)
    min_cash_ratio: Mapped[float] = mapped_column(Float, default=30)
    allow_sell_manual_holdings: Mapped[bool] = mapped_column(Boolean, default=False)
    stop_loss_pct: Mapped[float] = mapped_column(Float, default=6)
    take_profit_pct: Mapped[float] = mapped_column(Float, default=12)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_cycle_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AutoTradingPosition(Base):
    """Quantity attributable to the automatic bot only, never manual holdings."""
    __tablename__ = "auto_trading_positions"
    __table_args__ = (UniqueConstraint("user_id", "stock_code", name="uq_auto_position_user_stock"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    stock_name: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[float] = mapped_column(Float, default=0)
    invested_amount: Mapped[float] = mapped_column(Float, default=0)
    last_buy_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sell_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AutoTradingDecision(Base):
    """Immutable-ish decision/order audit for every Gbot automatic-trading cycle."""
    __tablename__ = "auto_trading_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cycle_id: Mapped[str] = mapped_column(String(64), index=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    stock_name: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(16), default="hold", index=True)
    status: Mapped[str] = mapped_column(String(24), default="decision", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    requested_quantity: Mapped[int] = mapped_column(Integer, default=0)
    requested_price: Mapped[float] = mapped_column(Float, default=0)
    requested_amount: Mapped[float] = mapped_column(Float, default=0)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    filled_price: Mapped[float] = mapped_column(Float, default=0)
    filled_amount: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default='[]')
    risks_json: Mapped[str] = mapped_column(Text, default='[]')
    exit_plan: Mapped[str] = mapped_column(Text, default="")
    guard_message: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    broker_order_no: Mapped[str] = mapped_column(String(80), default="", index=True)
    broker_response_json: Mapped[str] = mapped_column(Text, default='{}')
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    order_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AutoTradingCycle(Base):
    """One durable row per automatic-trading cycle, including zero-decision cycles."""
    __tablename__ = "auto_trading_cycles"
    __table_args__ = (UniqueConstraint("cycle_id", name="uq_auto_trading_cycle_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cycle_id: Mapped[str] = mapped_column(String(64), index=True)
    cycle_type: Mapped[str] = mapped_column(String(24), default="scheduled", index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    trigger_reason: Mapped[str] = mapped_column(Text, default="")
    market_open: Mapped[bool] = mapped_column(Boolean, default=False)
    kiwoom_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    gbot_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    owned_count: Mapped[int] = mapped_column(Integer, default=0)
    decision_count: Mapped[int] = mapped_column(Integer, default=0)
    buy_count: Mapped[int] = mapped_column(Integer, default=0)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    hold_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AutoTradingOutcome(Base):
    """Post-trade learning case tied to one Gbot buy decision."""
    __tablename__ = "auto_trading_outcomes"
    __table_args__ = (UniqueConstraint("decision_id", name="uq_auto_trading_outcome_decision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("auto_trading_decisions.id", ondelete="CASCADE"), index=True)
    cycle_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    stock_name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(24), default="pending_fill", index=True)
    outcome_label: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    entry_price: Mapped[float] = mapped_column(Float, default=0)
    entry_quantity: Mapped[int] = mapped_column(Integer, default=0)
    entry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    current_price: Mapped[float] = mapped_column(Float, default=0)
    current_return_pct: Mapped[float] = mapped_column(Float, default=0)
    max_gain_pct: Mapped[float] = mapped_column(Float, default=0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0)
    exit_price: Mapped[float] = mapped_column(Float, default=0)
    realized_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    failure_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    lessons_json: Mapped[str] = mapped_column(Text, default="[]")
    review_json: Mapped[str] = mapped_column(Text, default="{}")
    review_reason: Mapped[str] = mapped_column(Text, default="")
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class TradeReservation(Base):
    __tablename__ = "trade_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    stock_name: Mapped[str] = mapped_column(String(120), default="")

    # buy / sell
    side: Mapped[str] = mapped_column(String(10))

    # lte: current <= trigger, gte: current >= trigger
    trigger_operator: Mapped[str] = mapped_column(String(10))
    trigger_price: Mapped[float] = mapped_column(Float)

    quantity: Mapped[int] = mapped_column(Integer)

    # market / limit
    order_type: Mapped[str] = mapped_column(String(20), default="market")
    order_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange: Mapped[str] = mapped_column(String(20), default="KRX")

    # active / executing / triggered / cancelled / expired / failed
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)

    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    broker_order_no: Mapped[str] = mapped_column(String(80), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")

    # NULL = until cancelled.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )


class KiwoomAccountSnapshot(Base):
    __tablename__ = "kiwoom_account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    account_no: Mapped[str] = mapped_column(String(40), default="")
    cash: Mapped[float] = mapped_column(Float, default=0)

    # Broker-reported amount currently available for new stock purchases.
    # This is deliberately separate from deposit/evaluation amounts.
    buying_power: Mapped[float] = mapped_column(Float, default=0)

    total_asset: Mapped[float] = mapped_column(Float, default=0)
    purchase_amount: Mapped[float] = mapped_column(Float, default=0)
    evaluation_amount: Mapped[float] = mapped_column(Float, default=0)
    profit_loss: Mapped[float] = mapped_column(Float, default=0)
    return_rate: Mapped[float] = mapped_column(Float, default=0)
    holdings_json: Mapped[str] = mapped_column(Text, default="[]")
    orders_json: Mapped[str] = mapped_column(Text, default="[]")
    diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )


class KiwoomLiveAccountSnapshot(Base):
    """Last broker-confirmed production-account state; never shared with paper."""
    __tablename__ = "kiwoom_live_account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    account_no: Mapped[str] = mapped_column(String(40), default="")
    cash: Mapped[float] = mapped_column(Float, default=0)
    buying_power: Mapped[float] = mapped_column(Float, default=0)
    total_asset: Mapped[float] = mapped_column(Float, default=0)
    purchase_amount: Mapped[float] = mapped_column(Float, default=0)
    evaluation_amount: Mapped[float] = mapped_column(Float, default=0)
    profit_loss: Mapped[float] = mapped_column(Float, default=0)
    return_rate: Mapped[float] = mapped_column(Float, default=0)
    holdings_json: Mapped[str] = mapped_column(Text, default="[]")
    orders_json: Mapped[str] = mapped_column(Text, default="[]")
    diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class LiveOrderAudit(Base):
    """Immutable audit of orders sent to the production endpoint."""
    __tablename__ = "live_order_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", index=True)
    side: Mapped[str] = mapped_column(String(10))
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    order_type: Mapped[str] = mapped_column(String(20))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    broker_order_no: Mapped[str] = mapped_column(String(80), default="", index=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    raw_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class OverseasPaperAccount(Base):
    """USD-denominated StockLog paper account for overseas equities."""
    __tablename__ = "overseas_paper_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    starting_cash: Mapped[float] = mapped_column(Float, default=100000.0)
    cash: Mapped[float] = mapped_column(Float, default=100000.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class OverseasStock(Base):
    """US-listed security master plus a free-provider quote/analysis cache."""
    __tablename__ = "overseas_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="", index=True)
    name_ko: Mapped[str] = mapped_column(String(160), default="", index=True)
    exchange: Mapped[str] = mapped_column(String(40), default="US", index=True)
    mic: Mapped[str] = mapped_column(String(16), default="")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    asset_type: Mapped[str] = mapped_column(String(24), default="stock", index=True)
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(40), default="NASDAQ_TRADER")
    priority: Mapped[int] = mapped_column(Integer, default=999999, index=True)

    quote_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_change_percent: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    quote_open: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_previous_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_provider: Mapped[str] = mapped_column(String(40), default="")
    quote_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    analysis_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    analysis_label: Mapped[str] = mapped_column(String(30), default="")
    analysis_reason: Mapped[str] = mapped_column(String(500), default="")
    analysis_components_json: Mapped[str] = mapped_column(Text, default="[]")
    analysis_coverage: Mapped[float] = mapped_column(Float, default=0)
    analysis_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    universe_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class OverseasPaperPosition(Base):
    __tablename__ = "overseas_paper_positions"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_overseas_paper_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class OverseasPaperOrder(Base):
    __tablename__ = "overseas_paper_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    side: Mapped[str] = mapped_column(String(10), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="filled", index=True)
    provider: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class LiveAutoTradingSetting(Base):
    """Production auto-trading controls; defaults fail closed."""
    __tablename__ = "live_auto_trading_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    trading_start: Mapped[str] = mapped_column(String(5), default="09:05")
    trading_end: Mapped[str] = mapped_column(String(5), default="15:15")
    markets_json: Mapped[str] = mapped_column(Text, default='["KOSPI","KOSDAQ"]')
    categories_json: Mapped[str] = mapped_column(Text, default='[]')
    themes_json: Mapped[str] = mapped_column(Text, default='[]')
    use_all_themes: Mapped[bool] = mapped_column(Boolean, default=True)
    min_price: Mapped[float] = mapped_column(Float, default=1000)
    max_price: Mapped[float] = mapped_column(Float, default=0)
    min_market_cap: Mapped[float] = mapped_column(Float, default=1000)
    max_market_cap: Mapped[float] = mapped_column(Float, default=0)
    min_avg_volume: Mapped[float] = mapped_column(Float, default=100000)
    min_smart_score: Mapped[float] = mapped_column(Float, default=60)
    candidate_limit: Mapped[int] = mapped_column(Integer, default=15)
    min_confidence: Mapped[float] = mapped_column(Float, default=75)
    max_capital: Mapped[float] = mapped_column(Float, default=1000000)
    max_position_amount: Mapped[float] = mapped_column(Float, default=300000)
    max_positions: Mapped[int] = mapped_column(Integer, default=3)
    max_daily_orders: Mapped[int] = mapped_column(Integer, default=3)
    max_new_buys_per_cycle: Mapped[int] = mapped_column(Integer, default=1)
    min_cash_ratio: Mapped[float] = mapped_column(Float, default=50)
    allow_sell_manual_holdings: Mapped[bool] = mapped_column(Boolean, default=False)
    stop_loss_pct: Mapped[float] = mapped_column(Float, default=0)
    take_profit_pct: Mapped[float] = mapped_column(Float, default=0)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_cycle_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class LiveAutoTradingPosition(Base):
    __tablename__ = "live_auto_trading_positions"
    __table_args__ = (UniqueConstraint("user_id", "stock_code", name="uq_live_auto_position_user_stock"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    stock_name: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[float] = mapped_column(Float, default=0)
    invested_amount: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class LiveAutoTradingDecision(Base):
    __tablename__ = "live_auto_trading_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cycle_id: Mapped[str] = mapped_column(String(64), index=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    stock_name: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(16), default="hold", index=True)
    status: Mapped[str] = mapped_column(String(24), default="decision", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    requested_quantity: Mapped[int] = mapped_column(Integer, default=0)
    requested_price: Mapped[float] = mapped_column(Float, default=0)
    requested_amount: Mapped[float] = mapped_column(Float, default=0)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    filled_price: Mapped[float] = mapped_column(Float, default=0)
    filled_amount: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default='[]')
    risks_json: Mapped[str] = mapped_column(Text, default='[]')
    exit_plan: Mapped[str] = mapped_column(Text, default="")
    guard_message: Mapped[str] = mapped_column(Text, default="")
    broker_order_no: Mapped[str] = mapped_column(String(80), default="", index=True)
    broker_response_json: Mapped[str] = mapped_column(Text, default='{}')
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    order_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class LiveAutoTradingCycle(Base):
    __tablename__ = "live_auto_trading_cycles"
    __table_args__ = (UniqueConstraint("cycle_id", name="uq_live_auto_trading_cycle_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cycle_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    decision_count: Mapped[int] = mapped_column(Integer, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SmartFormula(Base):
    __tablename__ = "smart_formulas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, index=True)
    per_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    pbr_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    roe_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_margin_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_20d_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    theme_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    change_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )


class StockTheme(Base):
    __tablename__ = "stock_themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    theme_code: Mapped[str] = mapped_column(String(40), index=True)
    theme_name: Mapped[str] = mapped_column(String(160), index=True)
    source: Mapped[str] = mapped_column(String(30), default="kiwoom")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )

    __table_args__ = (
        UniqueConstraint(
            "stock_code",
            "theme_code",
            name="uq_stock_theme",
        ),
    )


class FullMarketSyncState(Base):
    __tablename__ = "full_market_sync_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, default="full_market")
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    phase: Mapped[str] = mapped_column(String(40), default="idle")
    job_type: Mapped[str] = mapped_column(String(20), default="all")
    item_total: Mapped[int] = mapped_column(Integer, default=0)
    item_completed: Mapped[int] = mapped_column(Integer, default=0)
    progress_value: Mapped[float] = mapped_column(Float, default=0)
    stage_label: Mapped[str] = mapped_column(String(80), default="")
    provider_status_json: Mapped[str] = mapped_column(Text, default="{}")
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    current_code: Mapped[str] = mapped_column(String(20), default="")
    current_name: Mapped[str] = mapped_column(String(120), default="")
    current_market: Mapped[str] = mapped_column(String(20), default="")
    eta_seconds: Mapped[float] = mapped_column(Float, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    failures_json: Mapped[str] = mapped_column(Text, default="[]")
    last_error: Mapped[str] = mapped_column(Text, default="")
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SyncScheduleSetting(Base):
    """Persistent administrator configuration for the unified market sync."""
    __tablename__ = "sync_schedule_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True, default="unified_full_sync")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    run_times_json: Mapped[str] = mapped_column(Text, default='["22:00"]')
    sync_scopes_json: Mapped[str] = mapped_column(Text, default='["kiwoom","dart","kiwoom_themes","market_themes","classification","theme_engine","flow","smart_scores"]')
    flow_universe_limit: Mapped[int] = mapped_column(Integer, default=0)
    flow_history_days: Mapped[int] = mapped_column(Integer, default=20)
    updated_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

class SyncState(Base):
    __tablename__ = "sync_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class ExternalApiCredential(Base):
    """Encrypted administrator-managed credentials for external data providers."""
    __tablename__ = "external_api_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    client_id_enc: Mapped[str] = mapped_column(Text, default="")
    client_secret_enc: Mapped[str] = mapped_column(Text, default="")
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_test_status: Mapped[str] = mapped_column(String(20), default="untested")
    last_test_message: Mapped[str] = mapped_column(Text, default="")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ApiUsageDaily(Base):
    """Small daily counters so the admin dashboard never scans a large request log."""
    __tablename__ = "api_usage_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    usage_date: Mapped[str] = mapped_column(String(10), index=True)
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    successful_calls: Mapped[int] = mapped_column(Integer, default=0)
    failed_calls: Mapped[int] = mapped_column(Integer, default=0)
    background_calls: Mapped[int] = mapped_column(Integer, default=0)
    interactive_calls: Mapped[int] = mapped_column(Integer, default=0)
    manual_calls: Mapped[int] = mapped_column(Integer, default=0)
    last_request_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("provider", "usage_date", name="uq_api_usage_provider_date"),
    )


class ApiUsageLog(Base):
    """Per-call audit trail. Secrets/query parameters are deliberately not stored."""
    __tablename__ = "api_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    endpoint: Mapped[str] = mapped_column(String(120), default="", index=True)
    request_kind: Mapped[str] = mapped_column(String(20), default="system")
    stock_code: Mapped[str] = mapped_column(String(20), default="", index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
