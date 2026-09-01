from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, Field

class KiwoomSettingsIn(BaseModel):
    app_key: str
    secret_key: str
    account_no: str = ""
    use_mock: bool = True

class OrderIn(BaseModel):
    side: str
    stock_code: str = Field(min_length=6, max_length=12)
    quantity: int = Field(gt=0, le=1000000)
    order_type: str = "market"
    price: float | None = None
    exchange: str = "KRX"


class LiveOrderIn(OrderIn):
    confirmation_text: str = Field(min_length=4, max_length=40)


class LiveTradingActivationIn(BaseModel):
    confirmation_text: str = Field(min_length=4, max_length=40)
    enabled: bool = True


class LiveAutoTradingStartIn(BaseModel):
    confirmation_text: str = Field(min_length=4, max_length=40)


class TradeReservationIn(BaseModel):
    stock_code: str = Field(min_length=6, max_length=12)
    side: str
    trigger_operator: str
    trigger_price: float = Field(gt=0)
    quantity: int = Field(gt=0, le=1000000)
    order_type: str = "market"
    order_price: float | None = None
    exchange: str = "KRX"
    expires_at: datetime | None = None


class AutoTradingSettingsIn(BaseModel):
    interval_minutes: int = Field(default=15, ge=5, le=240)
    trading_start: str = Field(default="09:05", pattern=r"^\d{2}:\d{2}$")
    trading_end: str = Field(default="15:15", pattern=r"^\d{2}:\d{2}$")
    markets: list[str] = Field(default_factory=lambda: ["KOSPI", "KOSDAQ"], min_length=1, max_length=3)
    categories: list[str] = Field(default_factory=list, max_length=30)
    themes: list[str] = Field(default_factory=list, max_length=50)
    use_all_themes: bool = True
    min_price: float = Field(default=1000, ge=0)
    max_price: float = Field(default=0, ge=0)
    min_market_cap: float = Field(default=1000, ge=0)
    max_market_cap: float = Field(default=0, ge=0)
    min_avg_volume: float = Field(default=100000, ge=0)
    min_smart_score: float = Field(default=60, ge=0, le=100)
    candidate_limit: int = Field(default=15, ge=3, le=40)
    min_confidence: float = Field(default=82, ge=0, le=100)
    max_capital: float = Field(default=10000000, ge=100000, le=10000000000)
    max_position_amount: float = Field(default=2000000, ge=10000, le=10000000000)
    max_positions: int = Field(default=8, ge=1, le=30)
    max_daily_orders: int = Field(default=8, ge=1, le=100)
    max_new_buys_per_cycle: int = Field(default=1, ge=1, le=10)
    min_cash_ratio: float = Field(default=30, ge=0, le=95)
    allow_sell_manual_holdings: bool = False
    stop_loss_pct: float = Field(default=6, ge=0, le=50)
    take_profit_pct: float = Field(default=12, ge=0, le=300)


class InvestmentProfileIn(BaseModel):
    result_code: str = Field(
        pattern=r"^[LNS][AD][GV][PH][FM]$",
        min_length=5,
        max_length=5,
    )
    answers: list[dict[str, Any]] = Field(default_factory=list)
    scores: dict[str, Any] = Field(default_factory=dict)


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)
    gender: str = Field(pattern=r"^(male|female|other|prefer_not_to_say)$")
    birth_date: date
    phone_number: str = Field(min_length=10, max_length=20)
    terms_consent: bool = False
    privacy_consent: bool = False
    investment_profile: InvestmentProfileIn


class LoginIn(BaseModel):
    username: str
    password: str


class SocialAuthSettingsIn(BaseModel):
    client_id: str = Field(default="", max_length=500)
    client_secret: str = Field(default="", max_length=500)
    redirect_uri: str = Field(min_length=8, max_length=512)
    enabled: bool = True


class SocialSessionIn(BaseModel):
    session_id: str = Field(min_length=20, max_length=120)


class SocialSignupInfoIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    gender: str = Field(pattern=r"^(male|female|other|prefer_not_to_say)$")
    birth_year: int = Field(ge=1900, le=2100)
    phone_number: str = Field(min_length=10, max_length=20)
    age_14_or_older: bool = False
    terms_consent: bool = False
    privacy_consent: bool = False


class SocialSignupCompleteIn(BaseModel):
    session_id: str = Field(min_length=20, max_length=120)
    signup_info: SocialSignupInfoIn
    investment_profile: InvestmentProfileIn


class AdminTestAccountIn(BaseModel):
    is_test_account: bool

class AdminMembershipTierIn(BaseModel):
    membership_tier: str = Field(pattern=r"^(NORMAL|PREMIUM|EVENT|ADMIN)$")


class AdminUserPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminAccessControlIn(BaseModel):
    mode: str = Field(pattern=r"^(allow_all|allowlist)$")
    allowed_ips: list[str] = Field(default_factory=list, max_length=200)


class MembershipFeaturePolicyItemIn(BaseModel):
    tier: str = Field(pattern=r"^(NORMAL|PREMIUM|EVENT|ADMIN)$")
    feature_key: str = Field(min_length=2, max_length=60)
    enabled: bool = True
    limit_value: int | None = Field(default=None, ge=-1, le=100000)


class MembershipFeaturePolicyUpdateIn(BaseModel):
    items: list[MembershipFeaturePolicyItemIn] = Field(default_factory=list, max_length=100)


class FlowSyncStartIn(BaseModel):
    universe_limit: int = Field(default=0, ge=0, le=5000)
    history_days: int = Field(default=20, ge=7, le=60)


class AdminClientDiagnosticIn(BaseModel):
    event: str = Field(default="frontend_error", min_length=1, max_length=120)
    message: str = Field(default="", max_length=12000)
    stack: str = Field(default="", max_length=30000)
    url: str = Field(default="", max_length=4000)
    method: str = Field(default="", max_length=20)
    status: int | None = Field(default=None, ge=0, le=999)
    request_id: str = Field(default="", max_length=120)
    context: dict = Field(default_factory=dict)


class MembershipRefreshPolicyItemIn(BaseModel):
    tier: str = Field(pattern=r"^(NORMAL|PREMIUM|EVENT|ADMIN)$")
    trading_seconds: int = Field(default=30, ge=0, le=3600)
    theme_seconds: int = Field(default=60, ge=0, le=3600)


class MembershipRefreshPolicyUpdateIn(BaseModel):
    items: list[MembershipRefreshPolicyItemIn] = Field(default_factory=list, max_length=10)


class UnifiedSyncStartIn(BaseModel):
    flow_universe_limit: int | None = Field(default=None, ge=0, le=5000)
    flow_history_days: int | None = Field(default=None, ge=7, le=60)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=8)


class SyncScheduleSettingsIn(BaseModel):
    enabled: bool = True
    run_times: list[str] = Field(default_factory=lambda: ["22:00"], min_length=1, max_length=6)
    flow_universe_limit: int = Field(default=0, ge=0, le=5000)
    flow_history_days: int = Field(default=20, ge=7, le=60)
    scopes: list[str] = Field(default_factory=lambda: ["kiwoom","dart","kiwoom_themes","market_themes","classification","theme_engine","flow","smart_scores"], min_length=1, max_length=8)
