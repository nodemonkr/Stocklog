import asyncio, json, os, time, math, statistics, re, httpx, hashlib, logging, uuid, secrets, threading, io, zipfile
from datetime import datetime, timezone, timedelta, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from fastapi import Request, Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, case, or_, inspect, text, event
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

try:
    from websockets.asyncio.client import connect as websocket_connect
except ImportError:
    from websockets.client import connect as websocket_connect

from .analysis import classify_stock, compute_score, enrich_financial_growth, build_deep_analysis
from .config import settings
from .database import Base, SessionLocal, MonitorSessionLocal, engine, get_db, database_pool_status, monitor_pool_status, run_monitor_blocking
from .db_utils import commit_or_rollback, flush_or_rollback, rollback_quietly
from .logging_config import configure_logging
from .deps import admin_user, admin_monitor_user, current_user
from .kiwoom import KiwoomRestClient, KiwoomError
from .models import SmartFormula, BrokerReportCache, DisclosureCache, FinancialQuarter, FullMarketSyncState, AiStockAnalysis, AiAnalysisAccess, InvestmentProfile, KiwoomAccountSnapshot, KiwoomCredential, KiwoomLiveCredential, KiwoomLiveAccountSnapshot, LiveOrderAudit, LiveAutoTradingSetting, LiveAutoTradingPosition, LiveAutoTradingDecision, LiveAutoTradingCycle, NewsCache, OrderAudit, PriceBar, Stock, AiDailyUsage, StockTheme, SyncState, Theme, TradeReservation, AutoTradingSetting, AutoTradingPosition, AutoTradingDecision, AutoTradingCycle, AutoTradingOutcome, User, ExternalApiCredential, ApiUsageDaily, ApiUsageLog, SocialAuthProviderConfig, SocialAccount, SocialAuthSession, UserConsent, MembershipFeaturePolicy, MembershipRefreshPolicy, SiteAccessSetting, StockInvestorFlowDaily, SyncScheduleSetting, OverseasPaperAccount, OverseasPaperPosition, OverseasPaperOrder
from .providers import (NaverInfoStockThemeClient, apply_dart_valuation, calculate_dart_valuation, fetch_dart_company_profile, fetch_dart_dividend_yield, fetch_dart_financials, fetch_dart_share_count, financials_from_db, get_stock_news, get_broker_reports, get_stock_disclosures, recalculate_price_multiples, sync_dart_corp_codes, upsert_financials)
from .schemas import AdminTestAccountIn, InvestmentProfileIn, KiwoomSettingsIn, LoginIn, OrderIn, LiveOrderIn, LiveTradingActivationIn, LiveAutoTradingStartIn, RegisterIn, TradeReservationIn, AutoTradingSettingsIn, SocialAuthSettingsIn, SocialSessionIn, SocialSignupCompleteIn, AdminMembershipTierIn, AdminUserPasswordIn, AdminAccessControlIn, MembershipFeaturePolicyUpdateIn, MembershipRefreshPolicyUpdateIn, FlowSyncStartIn, UnifiedSyncStartIn, SyncScheduleSettingsIn, AdminClientDiagnosticIn
from .ai_analyst import GeminiAnalyst, GeminiRateLimitError, OllamaAnalyst, HybridAnalyst, DualAnalysisUnavailable, _deterministic_fallback, finalize_deep_result
from .security import create_access_token, decode_token_claims, decrypt_secret, encrypt_secret, hash_password, verify_password
from .account_security import AccountSecurityError, membership_change_error, validate_admin_password
from .external_api import PROVIDER_DART, PROVIDER_NAVER, PROVIDER_GEMINI, PROVIDER_FINNHUB, PROVIDER_ALPHA_VANTAGE, PROVIDER_SEC_EDGAR, NAVER_API_HUB_NEWS_URL, naver_api_hub_headers, delete_provider_credentials, ensure_external_api_schema, external_api_schema_diagnostics, get_provider_credentials, provider_public_status, save_provider_credentials, set_provider_test_result, tracked_get, usage_stats
from .overseas import ensure_overseas_schema, router as overseas_router
from .seed import seed
from .membership import FEATURES as MEMBERSHIP_FEATURES, TIER_LABELS, TIERS, ensure_default_policies, ensure_default_refresh_policies, feature_policy, policy_matrix, refresh_policy_for_tier, refresh_policy_matrix, resolved_features, set_user_tier, user_tier
from .sync_policy import classify_flow_error, classify_sync_result, is_quota_like_error, normalize_run_times, provider_circuit_should_open, retry_delay_seconds, select_due_run_slot
from .sync_diagnostics import (
    activate_sync_diagnostic, append_sync_diagnostic, begin_sync_diagnostic,
    current_sync_diagnostic, deactivate_sync_diagnostic, diagnostic_path,
    install_sync_diagnostic_handler, list_sync_diagnostics, redact_diagnostic,
)
from .smart_scoring import build_scorecard, profile_score_from_components, strategy_match
from .auto_learning import (
    actionable_failure_tags,
    apply_learning_risk_adjustments,
    build_learning_memory,
    candidate_learning_risk,
    diagnostic_health,
    normalize_tags,
    should_review_outcome,
)
from .auto_trading_safety import GbotDecisionContractError, validate_gbot_decisions
from .auto_trading_metrics import auto_position_return_rates, krx_market_phase
from .auto_trading_stability import monitor_health_payload, protective_exit_assessment, recent_trade_guard_message, stable_entry_guard_message
from .live_trading_safety import (
    LIVE_ACTIVATION_TEXT, LIVE_AUTO_START_TEXT, LIVE_DEACTIVATION_TEXT, LIVE_ORDER_TEXT,
    LiveTradingSafetyError, require_confirmation, validate_live_order_limits,
)
from .auto_trading_prompt import (
    build_auto_decision_batches,
    compact_learning_memory,
    is_recoverable_gbot_completeness_error,
    is_recoverable_gbot_response_error,
)
from .access_control import (
    ACCESS_MODE_ALLOW_ALL,
    ACCESS_MODE_ALLOWLIST,
    AccessRuleError,
    access_allowed,
    normalize_access_rules,
    normalize_client_ip,
)
from .theme_classification import deterministic_business_theme as _deterministic_business_theme, normalize_ai_classification_items as _normalize_ai_classification_items
from .listing_master import fetch_kind_company_master, find_kind_company, merge_company_master
from .theme_taxonomy import (
    THEME_ENGINE_VERSION,
    canonical_group_for_theme,
    classify_stock_context,
    map_theme_name,
    normalize_stored_theme_payload,
    taxonomy_groups,
    taxonomy_tree,
    theme_alpha_key,
)

configure_logging()
install_sync_diagnostic_handler()
logger = logging.getLogger("stocklog.api")

PROJECT_VERSION_PATH=Path(__file__).resolve().parents[2]/"VERSION"
try:
    PROJECT_VERSION=PROJECT_VERSION_PATH.read_text(encoding="utf-8").strip() or "0.0.0-dev"
except OSError:
    PROJECT_VERSION="0.0.0-dev"

app = FastAPI(title=f"StockLog v{PROJECT_VERSION} API", version=PROJECT_VERSION)
app.include_router(overseas_router)

_DEFAULT_JWT_SECRETS={"", "CHANGE_THIS_TO_A_LONG_RANDOM_STRING", "CHANGE_ME", "changeme"}

# Canonical public/investable universe across StockLog.
# Raw master rows may remain in MySQL for history/FK safety, but every user-facing
# discovery, analysis, ranking and NEW buy flow uses only these rows.
STOCKLOG_PUBLIC_MARKETS=("KOSPI","KOSDAQ")

def _stocklog_public_clauses():
    return (
        Stock.is_active==True,
        Stock.is_analysis_eligible==True,
        Stock.market.in_(STOCKLOG_PUBLIC_MARKETS),
    )

def _stocklog_public_stock(db:Session, code:str):
    return (
        db.query(Stock)
        .filter(Stock.code==str(code or "").strip(), *_stocklog_public_clauses())
        .first()
    )

def _stocklog_public_code_set(db:Session, codes):
    clean=[str(x or "").strip() for x in dict.fromkeys(codes or []) if re.fullmatch(r"\d{6}",str(x or "").strip())]
    if not clean:
        return set()
    return {
        str(code) for (code,) in (
            db.query(Stock.code)
            .filter(Stock.code.in_(clean), *_stocklog_public_clauses())
            .all()
        )
    }




def _repair_v3683_lost_name_history(db: Session):
    """Repair the one rename whose former name v3.68.3 could overwrite without history.

    030520 officially changed 한글과컴퓨터 -> 한컴 in July 2026.  This is not
    a display-name rollback; it only restores the former name as a searchable
    alias because v3.68.3 did not persist name history.
    """
    st=db.query(Stock).filter(Stock.code=="030520").first()
    if not st or str(st.name or "").strip() != "한컴":
        return
    aliases=_stock_name_aliases(st)
    if "한글과컴퓨터" not in aliases:
        aliases.append("한글과컴퓨터")
        st.name_aliases_json=json.dumps(aliases,ensure_ascii=False)
        if not st.name_source:
            st.name_source="KRX_KIND"
        commit_or_rollback(db)

@app.on_event("startup")
def validate_runtime_security_settings() -> None:
    if str(settings.jwt_secret or "").strip() in _DEFAULT_JWT_SECRETS:
        message="JWT_SECRET이 기본값입니다. 외부 공개 전 긴 랜덤 값으로 변경하세요."
        if settings.is_production:
            raise RuntimeError(message)
        logger.warning(message)

@app.on_event("startup")
def reconcile_orphaned_sync_states_on_boot() -> None:
    """Close persisted in-process jobs that cannot survive a backend restart.

    Every admin synchronization worker is an asyncio task in this process.  A
    persisted ``running=true`` therefore means "orphaned" at startup, not an
    active remote job.  Clearing all such rows here prevents the browser from
    entering an endless progress loop before any status endpoint is opened.
    Per-endpoint reconciliation remains as a second line of defense.
    """
    db=SessionLocal()
    try:
        rows=(
            db.query(FullMarketSyncState)
            .filter(FullMarketSyncState.running==True)
            .all()
        )
        if not rows:
            return
        now=datetime.now()
        for row in rows:
            row.running=False
            row.phase="cancelled"
            row.stage_label="중지됨"
            row.current_code=""
            row.current_name=""
            row.eta_seconds=0
            row.finished_at=now
            row.message=(
                "백엔드 재시작으로 이전 동기화 작업을 종료 처리했습니다. "
                "저장 완료된 데이터는 유지됩니다."
            )
        commit_or_rollback(db)
        logger.warning("reconciled %s orphaned sync state(s) after backend restart",len(rows))
    except Exception:
        rollback_quietly(db)
        logger.exception("failed to reconcile orphaned sync states on startup")
    finally:
        db.close()

origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    # StockLog frontend uses Authorization Bearer token, not credential cookies.
    # Allow any development/LAN origin so 127.0.0.1, localhost, hostname,
    # and private IP access all behave consistently.
    allow_origins=origins if settings.is_production else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

_SITE_ACCESS_KEY="site_access"
_site_access_cache_lock=threading.Lock()
_site_access_cache={"loaded":False,"expires_at":0.0,"mode":ACCESS_MODE_ALLOW_ALL,"allowed_ips":[],"updated_at":None}


def _site_access_policy(*,force:bool=False):
    now=time.monotonic()
    with _site_access_cache_lock:
        if not force and _site_access_cache.get("loaded") and now<float(_site_access_cache.get("expires_at") or 0):
            return dict(_site_access_cache)
    db=SessionLocal()
    try:
        row=db.query(SiteAccessSetting).filter(SiteAccessSetting.key==_SITE_ACCESS_KEY).first()
        mode=str(row.mode or ACCESS_MODE_ALLOW_ALL) if row else ACCESS_MODE_ALLOW_ALL
        if mode not in {ACCESS_MODE_ALLOW_ALL,ACCESS_MODE_ALLOWLIST}:
            mode=ACCESS_MODE_ALLOW_ALL
        try:
            allowed_ips=normalize_access_rules(json.loads(row.allowed_ips_json or "[]") if row else [])
        except (json.JSONDecodeError,AccessRuleError,TypeError):
            allowed_ips=[]
        policy={
            "loaded":True,"expires_at":now+3.0,"mode":mode,"allowed_ips":allowed_ips,
            "updated_at":row.updated_at.isoformat() if row and row.updated_at else None,
        }
    except Exception:
        logger.exception("failed to load site access policy")
        with _site_access_cache_lock:
            if _site_access_cache.get("loaded"):
                return dict(_site_access_cache)
        # Configuration storage is part of the security boundary. On a cold
        # read failure, health/access diagnostics remain reachable but all
        # protected application requests fail closed.
        policy={"loaded":False,"expires_at":now+1.0,"mode":ACCESS_MODE_ALLOWLIST,"allowed_ips":[],"updated_at":None}
    finally:
        db.close()
    with _site_access_cache_lock:
        _site_access_cache.update(policy)
        return dict(_site_access_cache)


def _set_site_access_cache(*,mode:str,allowed_ips:list[str],updated_at:datetime|None=None):
    with _site_access_cache_lock:
        _site_access_cache.update({
            "loaded":True,"expires_at":time.monotonic()+3.0,"mode":mode,"allowed_ips":list(allowed_ips),
            "updated_at":updated_at.isoformat() if isinstance(updated_at,datetime) else updated_at,
        })


def _request_client_ip(connection) -> str:
    return normalize_client_ip(getattr(getattr(connection,"client",None),"host",None))


def _site_access_result(connection,*,force:bool=False):
    policy=_site_access_policy(force=force)
    client_ip=_request_client_ip(connection)
    allowed=access_allowed(policy.get("mode"),client_ip,policy.get("allowed_ips"),allow_loopback=True)
    return allowed,client_ip,policy


@app.middleware("http")
async def enforce_site_ip_access(request:Request,call_next):
    path=str(request.url.path or "")
    if path in {"/health","/api/access/status"}:
        return await call_next(request)
    allowed,client_ip,_policy=_site_access_result(request)
    if not allowed:
        return JSONResponse(
            status_code=403,
            content={
                "detail":"이 IP는 StockLog 접속 허용 목록에 포함되어 있지 않습니다.",
                "code":"ip_not_allowed",
                "client_ip":client_ip or "확인 불가",
            },
        )
    return await call_next(request)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(
            "unhandled request error method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )
        path=str(request.url.path or "")
        if path.startswith("/api/admin/") and any(token in path for token in ("sync","market-data","theme-normalize","classification")):
            filename=begin_sync_diagnostic(
                "backend-request",
                run_id=request_id,
                metadata={"method":request.method,"path":path,"query":str(request.url.query or "")},
            )
            append_sync_diagnostic(
                filename,"ERROR","ADMIN_SYNC_REQUEST_UNHANDLED",
                details={
                    "method":request.method,"path":path,"query":str(request.url.query or ""),
                    "request_id":request_id,
                    "client":getattr(request.client,"host",None),
                    "headers":dict(request.headers),
                },
                exc=exc,
            )
            request.state.sync_diagnostic_written=True
        raise
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def stocklog_unhandled_exception(request: Request, exc: Exception):
    """Return a stable error payload without exposing DB credentials or internals."""
    request_id = getattr(request.state,"request_id",None) or request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    logger.exception(
        "request failed method=%s path=%s request_id=%s",
        request.method,
        request.url.path,
        request_id,
        exc_info=exc,
    )
    detail = "백엔드 처리 중 오류가 발생했습니다."
    if not settings.is_production:
        detail += f" {type(exc).__name__}: {exc}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )

Base.metadata.create_all(bind=engine)
ensure_overseas_schema()


@app.get("/api/access/status")
def site_access_status(request:Request):
    allowed,client_ip,policy=_site_access_result(request)
    return {
        "allowed":bool(allowed),
        "restricted":policy.get("mode")==ACCESS_MODE_ALLOWLIST,
        "client_ip":client_ip or "확인 불가",
    }


def ensure_v345_account_schema():
    """Add the test-account flag used by AI access control."""
    inspector=inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    cols={c["name"] for c in inspector.get_columns("users")}
    if "is_test_account" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN is_test_account BOOLEAN NOT NULL DEFAULT 0"
                )
            )


ensure_v345_account_schema()


def ensure_v352_membership_schema():
    """Migrate legacy member/test/admin flags to the four-tier membership model."""
    inspector=inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("users")}
    if "membership_tier" not in cols:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN membership_tier VARCHAR(20) NOT NULL DEFAULT 'NORMAL'"
            ))
            conn.execute(text("CREATE INDEX ix_users_membership_tier ON users (membership_tier)"))
    with engine.begin() as conn:
        # Preserve all existing accounts. Former test accounts become EVENT members.
        conn.execute(text("UPDATE users SET membership_tier='ADMIN' WHERE is_admin=1"))
        conn.execute(text("UPDATE users SET membership_tier='EVENT' WHERE is_admin=0 AND is_test_account=1 AND membership_tier IN ('NORMAL','EVENT')"))
        conn.execute(text("UPDATE users SET membership_tier='NORMAL' WHERE membership_tier IS NULL OR membership_tier=''"))


ensure_v352_membership_schema()


def ensure_v359_social_profile_schema():
    """Add member profile fields used by local and social signup flows."""
    inspector=inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("users")}
    ddl=[]
    if "gender" not in cols:
        ddl.append("ALTER TABLE users ADD COLUMN gender VARCHAR(20) NOT NULL DEFAULT ''")
    if "birth_year" not in cols:
        ddl.append("ALTER TABLE users ADD COLUMN birth_year INT NULL")
    if "birth_date" not in cols:
        ddl.append("ALTER TABLE users ADD COLUMN birth_date DATE NULL")
    if "phone_number" not in cols:
        ddl.append("ALTER TABLE users ADD COLUMN phone_number VARCHAR(30) NOT NULL DEFAULT ''")
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))


ensure_v359_social_profile_schema()


def ensure_v361_member_activity_schema():
    """Add non-sensitive login activity metadata used by the admin member detail view."""
    inspector=inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("users")}
    ddl=[]
    if "last_login_at" not in cols:
        ddl.append("ALTER TABLE users ADD COLUMN last_login_at DATETIME NULL")
    if "last_login_method" not in cols:
        ddl.append("ALTER TABLE users ADD COLUMN last_login_method VARCHAR(20) NOT NULL DEFAULT ''")
    if "login_count" not in cols:
        ddl.append("ALTER TABLE users ADD COLUMN login_count INT NOT NULL DEFAULT 0")
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))


ensure_v361_member_activity_schema()


def ensure_v3808_auth_version_schema():
    """Add a token version used to revoke sessions after password changes."""
    inspector=inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("users")}
    if "auth_version" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN auth_version INT NOT NULL DEFAULT 0"))


ensure_v3808_auth_version_schema()


def ensure_v360_social_provider_profile_schema():
    """Persist provider-verified signup fields in the short-lived OAuth session."""
    inspector=inspect(engine)
    if "social_auth_sessions" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("social_auth_sessions")}
    ddl=[]
    if "gender" not in cols:
        ddl.append("ALTER TABLE social_auth_sessions ADD COLUMN gender VARCHAR(20) NOT NULL DEFAULT ''")
    if "birth_year" not in cols:
        ddl.append("ALTER TABLE social_auth_sessions ADD COLUMN birth_year INT NULL")
    if "phone_number" not in cols:
        ddl.append("ALTER TABLE social_auth_sessions ADD COLUMN phone_number VARCHAR(30) NOT NULL DEFAULT ''")
    if "provider_profile_fields" not in cols:
        ddl.append("ALTER TABLE social_auth_sessions ADD COLUMN provider_profile_fields VARCHAR(255) NOT NULL DEFAULT ''")
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))


ensure_v360_social_provider_profile_schema()


def ensure_v3583_financial_comparison_schema():
    """Persist like-for-like comparison values shipped with each filing."""
    inspector=inspect(engine)
    if "financial_quarters" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("financial_quarters")}
    ddl=[]
    for name,sqltype in [
        ("comparison_revenue","DOUBLE NULL"),
        ("comparison_operating_profit","DOUBLE NULL"),
        ("comparison_net_income","DOUBLE NULL"),
        ("comparison_assets","DOUBLE NULL"),
        ("comparison_liabilities","DOUBLE NULL"),
        ("comparison_equity","DOUBLE NULL"),
        ("comparison_income_period","VARCHAR(30) NULL"),
        ("comparison_balance_period","VARCHAR(30) NULL"),
        ("income_basis","VARCHAR(20) NULL"),
    ]:
        if name not in cols:
            ddl.append(f"ALTER TABLE financial_quarters ADD COLUMN {name} {sqltype}")
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))


ensure_v3583_financial_comparison_schema()


def ensure_v3611_nullable_financial_schema():
    """Allow filing-native missing values in the core financial columns.

    Some issuers/filings legitimately omit one or more of revenue, profit, or
    balance-sheet accounts.  Older StockLog schemas created these columns as
    NOT NULL, which caused an IntegrityError and poisoned the SQLAlchemy
    Session for the rest of a full sync.  Fresh schemas inherit nullable=True
    from the ORM model; this migration repairs existing MySQL/MariaDB tables.
    """
    inspector=inspect(engine)
    if "financial_quarters" not in inspector.get_table_names():
        return
    columns={c["name"]:c for c in inspector.get_columns("financial_quarters")}
    targets=("revenue","operating_profit","net_income","assets","liabilities","equity")
    pending=[name for name in targets if name in columns and not bool(columns[name].get("nullable",True))]
    if not pending:
        return

    dialect=engine.dialect.name.lower()
    if dialect not in {"mysql","mariadb"}:
        # SQLite test/dev databases created from the updated ORM model are
        # already nullable.  Avoid unsafe table-rebuild migrations here.
        logger.warning(
            "financial_quarters nullable migration skipped for dialect=%s columns=%s",
            dialect,
            ",".join(pending),
        )
        return

    with engine.begin() as conn:
        for name in pending:
            # Preserve the server's existing numeric type/precision and only
            # change nullability.
            sql_type=columns[name]["type"].compile(dialect=engine.dialect)
            conn.execute(text(f"ALTER TABLE financial_quarters MODIFY COLUMN `{name}` {sql_type} NULL"))
    logger.info("financial_quarters core columns changed to nullable: %s", ",".join(pending))


ensure_v3611_nullable_financial_schema()

# v3.40.x external API tables may already exist with an older/partial schema.
# create_all() does not alter existing tables, so repair them explicitly.
ensure_external_api_schema()

def ensure_v317_schema():
    inspector = inspect(engine)
    if "stock_universe" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("stock_universe")}
    ddl = []

    if "eps" not in cols:
        ddl.append("ALTER TABLE stock_universe ADD COLUMN eps DOUBLE NULL")
    if "bps" not in cols:
        ddl.append("ALTER TABLE stock_universe ADD COLUMN bps DOUBLE NULL")
    if "kiwoom_metrics_updated_at" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN kiwoom_metrics_updated_at DATETIME NULL"
        )
    if "dart_financials_updated_at" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN dart_financials_updated_at DATETIME NULL"
        )

    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))

ensure_v317_schema()


def ensure_v343_universe_schema():
    """Add analysis-universe metadata without removing the raw Kiwoom universe."""
    inspector=inspect(engine)
    if "stock_universe" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("stock_universe")}
    ddl=[]
    if "is_analysis_eligible" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN is_analysis_eligible BOOLEAN NOT NULL DEFAULT 1"
        )
    if "analysis_exclusion_reason" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN analysis_exclusion_reason VARCHAR(80) NULL"
        )
    if "universe_last_seen_at" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN universe_last_seen_at DATETIME NULL"
        )
    if "universe_missing_count" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN universe_missing_count INT NOT NULL DEFAULT 0"
        )
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))

ensure_v343_universe_schema()


def ensure_v3684_stock_name_integrity_schema():
    """Persist official-name provenance and former/alternate names."""
    inspector=inspect(engine)
    if "stock_universe" not in inspector.get_table_names():
        return
    columns={c["name"] for c in inspector.get_columns("stock_universe")}
    additions={
        "name_aliases_json":"TEXT NULL",
        "name_source":"VARCHAR(40) NULL",
        "name_verified_at":"DATETIME NULL",
        "name_changed_at":"DATETIME NULL",
    }
    ddl=[f"ALTER TABLE stock_universe ADD COLUMN {name} {spec}" for name,spec in additions.items() if name not in columns]
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))

ensure_v3684_stock_name_integrity_schema()


def ensure_v320_sync_schema():
    inspector=inspect(engine)
    if "full_market_sync_state" not in inspector.get_table_names():
        return
    cols={c["name"] for c in inspector.get_columns("full_market_sync_state")}
    ddl=[]
    for name,sqltype,default in [
        ("job_type","VARCHAR(20)","'all'"),
        ("item_total","INT","0"),
        ("item_completed","INT","0"),
        ("progress_value","DOUBLE","0"),
        ("stage_label","VARCHAR(80)","''"),
        ("provider_status_json","TEXT","NULL"),
    ]:
        if name not in cols:
            ddl.append(f"ALTER TABLE full_market_sync_state ADD COLUMN {name} {sqltype} DEFAULT {default}")
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))
ensure_v320_sync_schema()


def ensure_v3612_sync_state_payload_schema():
    """
    Keep long-running sync diagnostics from overflowing MySQL TEXT columns.

    A market-theme run can accumulate many per-theme failures.  MySQL TEXT is
    limited to about 64 KiB, which can make the *progress update itself* fail
    and leave the ORM session in PendingRollbackError.  MEDIUMTEXT gives the
    state row enough headroom; the runtime code also keeps diagnostics bounded
    so this migration is defense in depth rather than an invitation to grow
    without limit.
    """
    try:
        inspector=inspect(engine)
        if "full_market_sync_state" not in inspector.get_table_names():
            return

        with engine.connect() as conn:
            rows=conn.execute(
                text("SHOW COLUMNS FROM `full_market_sync_state`")
            ).mappings().all()

        info={str(row["Field"]):str(row.get("Type") or "").lower() for row in rows}
        ddl=[]
        for column in ("provider_status_json","failures_json"):
            column_type=info.get(column,"")
            if column_type and "mediumtext" not in column_type and "longtext" not in column_type:
                ddl.append(
                    f"ALTER TABLE `full_market_sync_state` "
                    f"MODIFY COLUMN `{column}` MEDIUMTEXT NULL"
                )

        if ddl:
            with engine.begin() as conn:
                for sql in ddl:
                    conn.execute(text(sql))
            print("[INFO] sync state diagnostic columns migrated to MEDIUMTEXT")
    except Exception as exc:
        # Runtime payload bounding below still protects legacy TEXT columns.
        print("[WARN] sync state MEDIUMTEXT migration failed:", repr(exc))


ensure_v3612_sync_state_payload_schema()


def _truncate_utf8(value, max_bytes=1400):
    text_value=str(value or "")
    raw=text_value.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return text_value
    suffix=" …(truncated)"
    suffix_raw=suffix.encode("utf-8")
    keep=max(0,max_bytes-len(suffix_raw))
    clipped=raw[:keep]
    while clipped:
        try:
            return clipped.decode("utf-8") + suffix
        except UnicodeDecodeError:
            clipped=clipped[:-1]
    return suffix.strip()


def _sync_error_text(exc, max_bytes=1400):
    if isinstance(exc, BaseException):
        active_log=current_sync_diagnostic()
        if active_log:
            append_sync_diagnostic(
                active_log,
                "ERROR",
                "SYNC_EXCEPTION_CAPTURED",
                details={"exception_type":type(exc).__name__,"message":str(exc)},
                exc=exc,
            )
    return _truncate_utf8(
        f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else exc,
        max_bytes=max_bytes,
    )


def _sync_diag(level:str,event:str,details:dict|None=None,exc:BaseException|None=None):
    """Append a concise milestone to the active synchronization diagnostic.

    This is intentionally safe/no-op outside a sync context and keeps secrets
    subject to the central diagnostic redactor.
    """
    active_log=current_sync_diagnostic()
    if not active_log:
        return
    try:
        append_sync_diagnostic(active_log,level,event,details=details or {},exc=exc)
    except Exception:
        logger.debug("sync diagnostic append failed event=%s",event,exc_info=True)


def _json_bytes(data):
    return json.dumps(data,ensure_ascii=False).encode("utf-8")


def _bounded_failures_json(failures, max_items=32, max_bytes=52000):
    compact=[]
    for item in list(failures or [])[-max_items:]:
        if isinstance(item, dict):
            row=dict(item)
            if "error" in row:
                row["error"]=_truncate_utf8(row.get("error"), 1200)
            compact.append(row)
        else:
            compact.append({"error":_truncate_utf8(item,1200)})

    while compact and len(_json_bytes(compact)) > max_bytes:
        compact.pop(0)

    return json.dumps(compact,ensure_ascii=False)


def _bounded_provider_json(provider, max_bytes=52000):
    data=dict(provider or {})
    if "current_error" in data:
        data["current_error"]=_truncate_utf8(data.get("current_error"),1200)
    if "failed_error" in data:
        data["failed_error"]=_truncate_utf8(data.get("failed_error"),1200)
    if isinstance(data.get("failures"), list):
        trimmed=[]
        for item in data["failures"][-8:]:
            if isinstance(item,dict):
                row=dict(item)
                if "error" in row:
                    row["error"]=_truncate_utf8(row.get("error"),1000)
                trimmed.append(row)
            else:
                trimmed.append({"error":_truncate_utf8(item,1000)})
        data["failures"]=trimmed

    # Bound any unexpectedly verbose top-level diagnostic strings too.
    for key,value in list(data.items()):
        if isinstance(value,str) and len(value.encode("utf-8",errors="replace")) > 4000:
            data[key]=_truncate_utf8(value,4000)

    while isinstance(data.get("failures"),list) and data["failures"] and len(_json_bytes(data)) > max_bytes:
        data["failures"].pop(0)

    if len(_json_bytes(data)) > max_bytes:
        # Last-resort summary keeps status persistence alive even if a provider
        # unexpectedly injects a giant nested diagnostics object.
        keep_keys=(
            "source","current_status","catalog_pages","catalog_count",
            "theme_count","theme_links","unique_member_stocks",
            "current_theme_no","current_theme_name","current_attempt",
            "current_member_count","failure_count","warning_count",
            "failed_stage","failed_error","trigger","last_auto_date","last_auto_slot",
            "flow_universe_limit","flow_history_days","requested_limit","history_days",
            "eligible_total","selected_total","outside_selection","selected_coverage_percent",
            "skipped","missing_data","cached_when_provider_empty","retried",
            "transient_recovered","failure_reasons","diagnostic_log",
        )
        data={key:data.get(key) for key in keep_keys if key in data}
        data["diagnostics_truncated"]=True

    return json.dumps(data,ensure_ascii=False)


# v3.61.3: Final ORM-level safety net for every sync-state flush.
# Individual sync routines already bound their diagnostics, but this hook makes
# the guarantee global: no code path can accidentally flush >TEXT-sized JSON.
@event.listens_for(Session, "before_flush")
def _bound_sync_state_payload_before_flush(session, flush_context, instances):
    candidates=set(session.new).union(session.dirty)
    for obj in candidates:
        if not isinstance(obj, FullMarketSyncState):
            continue

        try:
            raw_failures=json.loads(obj.failures_json or "[]")
            if not isinstance(raw_failures,list):
                raw_failures=[{"error":_truncate_utf8(raw_failures,1200)}]
        except Exception:
            raw_failures=[{"error":_truncate_utf8(obj.failures_json,1200)}]
        obj.failures_json=_bounded_failures_json(
            raw_failures, max_items=24, max_bytes=46000
        )

        try:
            raw_provider=json.loads(obj.provider_status_json or "{}")
            if not isinstance(raw_provider,dict):
                raw_provider={"status":_truncate_utf8(raw_provider,1200)}
        except Exception:
            raw_provider={
                "status_parse_error":True,
                "raw_preview":_truncate_utf8(obj.provider_status_json,1800),
            }
        obj.provider_status_json=_bounded_provider_json(
            raw_provider, max_bytes=46000
        )
        obj.last_error=_truncate_utf8(obj.last_error,12000)
        obj.message=_truncate_utf8(obj.message,12000)


_legacy_theme_name_required_cache=None

def _legacy_theme_name_required():
    """Return True when old themes.theme_name exists and still requires a value.

    This fallback is intentionally independent of ALTER TABLE privileges.
    """
    global _legacy_theme_name_required_cache
    if _legacy_theme_name_required_cache is not None:
        return _legacy_theme_name_required_cache
    try:
        info=_mysql_table_column_info("themes").get("theme_name")
        _legacy_theme_name_required_cache=bool(
            info and str(info.get("null") or "").upper() != "YES"
        )
    except Exception:
        _legacy_theme_name_required_cache=False
    return _legacy_theme_name_required_cache


def ensure_v321_valuation_schema():
    inspector = inspect(engine)

    if (
        "stock_universe"
        not in inspector.get_table_names()
    ):
        return

    cols = {
        c["name"]
        for c in inspector.get_columns(
            "stock_universe"
        )
    }

    ddl = []

    if "shares_outstanding" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN shares_outstanding DOUBLE NULL"
        )

    if "valuation_calculated_at" not in cols:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN valuation_calculated_at DATETIME NULL"
        )

    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(
                    text(sql)
                )

ensure_v321_valuation_schema()


def ensure_v330_classification_schema():
    inspector=inspect(engine)

    if "stock_universe" not in inspector.get_table_names():
        return

    columns={
        c["name"]
        for c in inspector.get_columns("stock_universe")
    }

    ddl=[]

    if "industry_code" not in columns:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN industry_code VARCHAR(20) NULL"
        )
    if "industry_name" not in columns:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN industry_name VARCHAR(100) NULL"
        )
    if "industry_source" not in columns:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN industry_source VARCHAR(30) NULL"
        )
    if "industry_updated_at" not in columns:
        ddl.append(
            "ALTER TABLE stock_universe "
            "ADD COLUMN industry_updated_at DATETIME NULL"
        )

    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))


ensure_v330_classification_schema()


def ensure_v3311_buying_power_schema():
    inspector=inspect(engine)

    if "kiwoom_account_snapshots" not in inspector.get_table_names():
        return

    columns={
        c["name"]
        for c in inspector.get_columns(
            "kiwoom_account_snapshots"
        )
    }

    if "buying_power" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE kiwoom_account_snapshots "
                    "ADD COLUMN buying_power DOUBLE NOT NULL DEFAULT 0"
                )
            )


ensure_v3311_buying_power_schema()


def ensure_v324_smart_formula_schema():
    inspector = inspect(engine)
    if "smart_formulas" in inspector.get_table_names():
        return

    SmartFormula.__table__.create(
        bind=engine,
        checkfirst=True,
    )

ensure_v324_smart_formula_schema()

def ensure_v325_theme_schema():
    inspector=inspect(engine)
    if "stock_universe" not in inspector.get_table_names(): return
    cols={c["name"] for c in inspector.get_columns("stock_universe")}
    if "primary_theme" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE stock_universe ADD COLUMN primary_theme VARCHAR(120) NULL"))
ensure_v325_theme_schema()


def ensure_v365_business_theme_schema():
    """Separate exchange industry metadata from actual business and investor-facing themes."""
    inspector=inspect(engine)
    if "stock_universe" not in inspector.get_table_names():
        return
    columns={c["name"] for c in inspector.get_columns("stock_universe")}
    additions={
        "primary_business":"VARCHAR(160) NULL",
        "investment_theme":"VARCHAR(120) NULL",
        "investment_themes_json":"TEXT NULL",
        "classification_confidence":"DOUBLE NULL",
        "classification_reason":"TEXT NULL",
        "classification_source_summary":"TEXT NULL",
        "classification_updated_at":"DATETIME NULL",
    }
    ddl=[f"ALTER TABLE stock_universe ADD COLUMN {name} {spec}" for name,spec in additions.items() if name not in columns]
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))
    try:
        with engine.begin() as conn:
            idx={str(row.get("Key_name") or "") for row in conn.execute(text("SHOW INDEX FROM stock_universe")).mappings().all()}
            if "ix_stock_universe_investment_theme" not in idx:
                conn.execute(text("CREATE INDEX ix_stock_universe_investment_theme ON stock_universe (investment_theme)"))
    except Exception:
        pass

ensure_v365_business_theme_schema()


def ensure_v367_theme_engine_schema():
    """Persist parent/sub-theme hierarchy generated by StockLog Theme Engine."""
    inspector=inspect(engine)
    if "stock_universe" not in inspector.get_table_names():
        return
    columns={c["name"] for c in inspector.get_columns("stock_universe")}
    additions={
        "theme_group":"VARCHAR(120) NULL",
        "theme_groups_json":"TEXT NULL",
        "theme_subthemes_json":"TEXT NULL",
        "theme_engine_version":"VARCHAR(80) NULL",
        "theme_engine_evidence_json":"TEXT NULL",
    }
    ddl=[f"ALTER TABLE stock_universe ADD COLUMN {name} {spec}" for name,spec in additions.items() if name not in columns]
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))
    try:
        with engine.begin() as conn:
            idx={str(row.get("Key_name") or "") for row in conn.execute(text("SHOW INDEX FROM stock_universe")).mappings().all()}
            if "ix_stock_universe_theme_group" not in idx:
                conn.execute(text("CREATE INDEX ix_stock_universe_theme_group ON stock_universe (theme_group)"))
    except Exception:
        pass

ensure_v367_theme_engine_schema()


def ensure_v366_smart_score_cache_schema():
    """Add persisted Smart Analysis score columns for full-market browsing.

    Existing installations are migrated in-place. The columns intentionally
    live on stock_universe because they are one current snapshot per stock and
    are refreshed after synchronization; per-user profile fit stays dynamic.
    """
    inspector=inspect(engine)
    if "stock_universe" not in inspector.get_table_names():
        return
    columns={c["name"] for c in inspector.get_columns("stock_universe")}
    additions={
        "smart_ai_score":"DOUBLE NULL",
        "smart_ai_label":"VARCHAR(40) NULL",
        "smart_score_coverage":"DOUBLE NULL",
        "smart_score_components_json":"TEXT NULL",
        "smart_score_updated_at":"DATETIME NULL",
    }
    ddl=[f"ALTER TABLE stock_universe ADD COLUMN {name} {spec}" for name,spec in additions.items() if name not in columns]
    if ddl:
        with engine.begin() as conn:
            for sql in ddl:
                conn.execute(text(sql))
    try:
        with engine.begin() as conn:
            idx={str(row.get("Key_name") or "") for row in conn.execute(text("SHOW INDEX FROM stock_universe")).mappings().all()}
            if "ix_stock_universe_smart_ai_score" not in idx:
                conn.execute(text("CREATE INDEX ix_stock_universe_smart_ai_score ON stock_universe (smart_ai_score)"))
            if "ix_stock_universe_smart_score_coverage" not in idx:
                conn.execute(text("CREATE INDEX ix_stock_universe_smart_score_coverage ON stock_universe (smart_score_coverage)"))
            if "ix_stock_universe_smart_score_updated_at" not in idx:
                conn.execute(text("CREATE INDEX ix_stock_universe_smart_score_updated_at ON stock_universe (smart_score_updated_at)"))
    except Exception as exc:
        logger.warning("smart score cache index migration skipped: %r",exc)

ensure_v366_smart_score_cache_schema()


def ensure_v374_sync_schedule_scope_schema():
    """Add selectable unified-sync scopes without requiring a manual DB migration."""
    inspector=inspect(engine)
    if "sync_schedule_settings" not in inspector.get_table_names():
        return
    columns={c["name"] for c in inspector.get_columns("sync_schedule_settings")}
    if "sync_scopes_json" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE sync_schedule_settings ADD COLUMN sync_scopes_json TEXT NULL"
            ))
            conn.execute(text(
                "UPDATE sync_schedule_settings SET sync_scopes_json='[\"kiwoom\",\"dart\",\"kiwoom_themes\",\"market_themes\",\"classification\",\"theme_engine\",\"flow\",\"smart_scores\"]' "
                "WHERE sync_scopes_json IS NULL OR sync_scopes_json=''"
            ))


ensure_v374_sync_schedule_scope_schema()


def _mysql_table_columns(table_name: str):
    """Return actual MySQL columns for a hard-coded StockLog table."""
    allowed={"themes","stock_themes"}

    if table_name not in allowed:
        raise ValueError("허용되지 않은 테이블입니다.")

    with engine.connect() as conn:
        rows=conn.execute(
            text(
                f"SHOW COLUMNS FROM `{table_name}`"
            )
        ).mappings().all()

    return {
        str(row["Field"])
        for row in rows
    }


def _mysql_table_column_info(table_name: str):
    """
    Return actual MySQL SHOW COLUMNS metadata.

    Column existence alone is not enough for StockLog migrations:
    older StockLog versions created themes.change_rate as NOT NULL,
    while the current model intentionally allows NULL when Kiwoom does
    not provide a theme change rate.
    """
    allowed={"themes","stock_themes"}

    if table_name not in allowed:
        raise ValueError("허용되지 않은 테이블입니다.")

    with engine.connect() as conn:
        rows=conn.execute(
            text(
                f"SHOW COLUMNS FROM `{table_name}`"
            )
        ).mappings().all()

    return {
        str(row["Field"]):{
            "type":str(row.get("Type") or ""),
            "null":str(row.get("Null") or ""),
            "default":row.get("Default"),
            "key":str(row.get("Key") or ""),
            "extra":str(row.get("Extra") or ""),
        }
        for row in rows
    }


def ensure_v326_theme_relation_schema():
    """
    Hard-repair theme schema directly against MySQL.

    Why this exists:
    `create(checkfirst=True)` cannot migrate an existing table, and
    inspector-based checks can make troubleshooting harder. For the two
    StockLog-owned theme tables, query SHOW COLUMNS directly and ALTER
    only fields that are truly absent.
    """
    errors=[]
    changes=[]

    try:
        Theme.__table__.create(
            bind=engine,
            checkfirst=True,
        )
    except Exception as exc:
        errors.append(
            "themes create: "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        StockTheme.__table__.create(
            bind=engine,
            checkfirst=True,
        )
    except Exception as exc:
        errors.append(
            "stock_themes create: "
            f"{type(exc).__name__}: {exc}"
        )

    required={
        "themes":{
            "id":"INT NOT NULL AUTO_INCREMENT PRIMARY KEY",
            "theme_code":"VARCHAR(40) NOT NULL",
            "name":"VARCHAR(160) NOT NULL",
            "change_rate":"DOUBLE NULL",
            "stock_count":"INT NOT NULL DEFAULT 0",
            "is_active":"TINYINT(1) NOT NULL DEFAULT 1",
            "updated_at":"DATETIME NULL",
        },
        "stock_themes":{
            "id":"INT NOT NULL AUTO_INCREMENT PRIMARY KEY",
            "stock_code":"VARCHAR(20) NOT NULL",
            "theme_code":"VARCHAR(40) NOT NULL",
            "theme_name":"VARCHAR(160) NOT NULL",
            "source":"VARCHAR(30) NOT NULL DEFAULT 'kiwoom'",
            "updated_at":"DATETIME NULL",
        },
    }

    # Repair column properties from older StockLog schemas as well.
    # Previous versions may already have `themes.change_rate`, but as
    # NOT NULL. Kiwoom can legitimately omit the rate for some themes,
    # so the database must accept NULL just like the SQLAlchemy model.
    try:
        theme_column_info=_mysql_table_column_info(
            "themes"
        )

        change_rate_info=theme_column_info.get(
            "change_rate"
        )

        if (
            change_rate_info
            and str(
                change_rate_info.get("null")
                or ""
            ).upper()
            != "YES"
        ):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE `themes` "
                        "MODIFY COLUMN `change_rate` DOUBLE NULL"
                    )
                )

            verified_info=_mysql_table_column_info(
                "themes"
            ).get(
                "change_rate"
            ) or {}

            if str(
                verified_info.get("null")
                or ""
            ).upper() != "YES":
                raise RuntimeError(
                    "themes.change_rate NULL 허용 변경 후 검증에 실패했습니다."
                )

            changes.append(
                "themes.change_rate nullable"
            )

    except Exception as exc:
        errors.append(
            "themes.change_rate nullable migration: "
            f"{type(exc).__name__}: {exc}"
        )

    # Older StockLog releases used themes.theme_name.  When that NOT NULL
    # legacy column survives next to the current themes.name column, ORM inserts
    # only populate `name` and MySQL rejects every new theme with error 1364.
    try:
        theme_column_info=_mysql_table_column_info("themes")
        legacy_info=theme_column_info.get("theme_name")
        if legacy_info:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE `themes` "
                        "SET `name` = COALESCE(NULLIF(`name`, ''), `theme_name`) "
                        "WHERE (`name` IS NULL OR `name` = '') "
                        "AND `theme_name` IS NOT NULL"
                    )
                )
                if str(legacy_info.get("null") or "").upper() != "YES":
                    conn.execute(
                        text(
                            "ALTER TABLE `themes` "
                            "MODIFY COLUMN `theme_name` VARCHAR(160) NULL"
                        )
                    )
            changes.append("themes.theme_name legacy nullable")
    except Exception as exc:
        errors.append(
            "themes.theme_name legacy migration: "
            f"{type(exc).__name__}: {exc}"
        )

    # Very old StockLog schemas also stored pre-calculated market breadth
    # counters on `themes`.  The current service calculates those values on
    # demand and no longer writes them, but a legacy NOT NULL column without a
    # default makes every new InfoStock theme INSERT fail with MySQL 1364.
    # Keep the columns for backward compatibility while making them harmless.
    legacy_counter_columns=(
        "rising_count",
        "falling_count",
        "flat_count",
        "unchanged_count",
    )
    try:
        theme_column_info=_mysql_table_column_info("themes")
        with engine.begin() as conn:
            for column_name in legacy_counter_columns:
                info=theme_column_info.get(column_name)
                if not info:
                    continue
                needs_default=(info.get("default") is None)
                is_nullable=str(info.get("null") or "").upper()=="YES"
                if not needs_default and not is_nullable:
                    continue
                # These legacy fields are counters, so zero is the only safe
                # backward-compatible default.  Preserve NOT NULL semantics.
                conn.execute(
                    text(
                        f"ALTER TABLE `themes` MODIFY COLUMN `{column_name}` "
                        "INT NOT NULL DEFAULT 0"
                    )
                )
                changes.append(f"themes.{column_name} default 0")
    except Exception as exc:
        # The sync still has a dynamic INSERT fallback below for installations
        # where the DB account cannot ALTER TABLE.
        errors.append(
            "themes legacy counter migration: "
            f"{type(exc).__name__}: {exc}"
        )

    # Tables are StockLog-owned and identifiers/DDL are hard-coded above.
    for table_name, column_defs in required.items():
        try:
            existing=_mysql_table_columns(
                table_name
            )

            for column_name, ddl in column_defs.items():
                if column_name in existing:
                    continue

                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE `{table_name}` "
                            f"ADD COLUMN `{column_name}` {ddl}"
                        )
                    )

                # Verify immediately against MySQL, not SQLAlchemy metadata.
                verified=_mysql_table_columns(
                    table_name
                )

                if column_name not in verified:
                    raise RuntimeError(
                        f"ALTER 후에도 {table_name}.{column_name} 컬럼을 확인할 수 없습니다."
                    )

                changes.append(
                    f"{table_name}.{column_name}"
                )
                existing=verified

        except Exception as exc:
            errors.append(
                f"{table_name} migration: "
                f"{type(exc).__name__}: {exc}"
            )

    final_columns={}

    for table_name in required:
        try:
            final_columns[table_name]=(
                _mysql_table_columns(
                    table_name
                )
            )
        except Exception as exc:
            final_columns[table_name]=set()
            errors.append(
                f"{table_name} verify: "
                f"{type(exc).__name__}: {exc}"
            )

    missing={
        table_name:[
            column_name
            for column_name in column_defs
            if column_name not in final_columns.get(
                table_name,
                set(),
            )
        ]
        for table_name, column_defs in required.items()
    }
    missing={
        key:value
        for key,value in missing.items()
        if value
    }

    result={
        "themes_table":bool(final_columns.get("themes")),
        "stock_themes_table":bool(final_columns.get("stock_themes")),
        "ok":not missing and bool(final_columns.get("themes")) and bool(final_columns.get("stock_themes")),
        "changes":changes,
        "missing_columns":missing,
        "actual_columns":{
            key:sorted(value)
            for key,value in final_columns.items()
        },
        "errors":errors,
    }

    if changes:
        print(
            "[INFO] theme schema hard-migrated:",
            changes,
        )

    if not result["ok"] or errors:
        print(
            "[WARN] theme hard schema status:",
            result,
        )

    return result



def _theme_canonical_column_available():
    """Return whether the optional v3.62.1 canonical theme-name column exists."""
    try:
        return "canonical_name" in _mysql_table_columns("themes")
    except Exception:
        return False


def ensure_v3621_theme_canonical_schema():
    """Best-effort durable storage for AI-normalized display names.

    The provider name remains in themes.name, while canonical_name is used by
    Smart Analysis.  Keeping the two fields separate prevents the next Kiwoom /
    InfoStock synchronization from undoing the administrator's AI grouping.
    This column is optional so older installations without ALTER permission can
    still start; the normalizer has a compatible fallback in that case.
    """
    try:
        if _theme_canonical_column_available():
            return {"ok": True, "available": True, "changed": False}
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE `themes` ADD COLUMN `canonical_name` VARCHAR(160) NULL"))
            try:
                conn.execute(text("CREATE INDEX `ix_themes_canonical_name` ON `themes` (`canonical_name`)"))
            except Exception:
                pass
        return {"ok": True, "available": _theme_canonical_column_available(), "changed": True}
    except Exception as exc:
        logger.warning("optional canonical theme schema migration failed: %r", exc)
        return {"ok": False, "available": False, "changed": False, "error": f"{type(exc).__name__}: {exc}"}


def _theme_canonical_map(db: Session):
    """theme_code -> canonical display name; empty when optional column is absent."""
    if not _theme_canonical_column_available():
        return {}
    try:
        rows=db.execute(text(
            "SELECT `theme_code`,`canonical_name` FROM `themes` "
            "WHERE `is_active`=1 AND `canonical_name` IS NOT NULL AND TRIM(`canonical_name`)<>''"
        )).mappings().all()
        return {
            str(row.get("theme_code") or ""): str(row.get("canonical_name") or "").strip()
            for row in rows
            if row.get("theme_code") and str(row.get("canonical_name") or "").strip()
        }
    except Exception as exc:
        try: db.rollback()
        except Exception: pass
        logger.warning("canonical theme map read failed: %r", exc)
        return {}


def _theme_display_rows(db: Session):
    """Return active provider rows with the durable Smart Analysis display name."""
    canonical=_theme_canonical_map(db)
    rows=db.query(Theme).filter(Theme.is_active==True).all()
    return [
        {
            "theme_code": str(row.theme_code or ""),
            "raw_name": str(row.name or "").strip(),
            "display_name": canonical.get(str(row.theme_code or "")) or str(row.name or "").strip(),
            "stock_count": int(row.stock_count or 0),
            "change_rate": row.change_rate,
        }
        for row in rows
        if str(row.name or "").strip()
    ]

def _require_theme_schema_ready():
    schema=ensure_v326_theme_relation_schema()

    required_theme={
        "id",
        "theme_code",
        "name",
        "change_rate",
        "stock_count",
        "is_active",
        "updated_at",
    }

    required_links={
        "id",
        "stock_code",
        "theme_code",
        "theme_name",
        "source",
        "updated_at",
    }

    actual=schema.get(
        "actual_columns"
    ) or {}

    themes=set(
        actual.get("themes") or []
    )
    links=set(
        actual.get("stock_themes") or []
    )

    missing={
        "themes":sorted(
            required_theme-themes
        ),
        "stock_themes":sorted(
            required_links-links
        ),
    }
    missing={
        key:value
        for key,value in missing.items()
        if value
    }

    if missing:
        raise RuntimeError(
            "테마 DB 실제 컬럼 검증 실패: "
            f"{missing}; schema={schema}"
        )

    return schema


try:
    _theme_schema_boot_status=(
        _require_theme_schema_ready()
    )
except Exception as exc:
    _theme_schema_boot_status={
        "ok":False,
        "error":f"{type(exc).__name__}: {exc}",
    }
    print(
        "[WARN] theme schema startup verification failed:",
        repr(exc),
    )

_theme_canonical_schema_status=ensure_v3621_theme_canonical_schema()


def ensure_v316_schema():
    insp=inspect(engine)
    if "news_cache" not in insp.get_table_names(): return
    cols={c["name"] for c in insp.get_columns("news_cache")}
    ddl=[]
    if "description" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN description TEXT")
    if "dedupe_key" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN dedupe_key VARCHAR(64) NULL")
    if "publisher" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN publisher VARCHAR(120) DEFAULT ''")
    if "fetched_at" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN fetched_at DATETIME NULL")
    if "sentiment_reason" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN sentiment_reason TEXT")
    if "published_dt" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN published_dt DATETIME NULL")
    if "source" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN source VARCHAR(40) DEFAULT ''")
    if "source_query" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN source_query VARCHAR(180) DEFAULT ''")
    if "relevance_score" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN relevance_score FLOAT DEFAULT 0")
    if "importance_score" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN importance_score FLOAT DEFAULT 0")
    if "importance_reason" not in cols: ddl.append("ALTER TABLE news_cache ADD COLUMN importance_reason TEXT")
    if ddl:
        with engine.begin() as conn:
            for sql in ddl: conn.execute(text(sql))
ensure_v316_schema()

SNAPSHOT_RESET_MARKER = "kiwoom_snapshot_reset_v3_10"

def reset_legacy_kiwoom_snapshots_once(db: Session):
    """
    v3.8 최초 실행 시 과거 키움 계좌 snapshot을 딱 한 번 초기화합니다.
    이후 재시작에서는 marker가 존재하므로 다시 삭제하지 않습니다.
    """
    marker = (
        db.query(SyncState)
        .filter(SyncState.key == SNAPSHOT_RESET_MARKER)
        .first()
    )

    if marker:
        return 0

    deleted = (
        db.query(KiwoomAccountSnapshot)
        .delete(synchronize_session=False)
    )

    marker = SyncState(
        key=SNAPSHOT_RESET_MARKER,
        running=False,
        last_started_at=datetime.now(),
        last_finished_at=datetime.now(),
        last_success_at=datetime.now(),
        last_error=f"legacy snapshots cleared: {deleted}",
    )
    db.add(marker)
    commit_or_rollback(db)
    return deleted

REAL_DATA_PURGE_MARKER = "remove_all_demo_market_data_v3_13"

def purge_demo_data_once(db: Session):
    marker = db.query(SyncState).filter(SyncState.key == REAL_DATA_PURGE_MARKER).first()
    if marker:
        return

    price_count = db.query(PriceBar).delete(synchronize_session=False)
    fin_count = db.query(FinancialQuarter).delete(synchronize_session=False)
    news_count = db.query(NewsCache).delete(synchronize_session=False)
    db.add(SyncState(
        key=REAL_DATA_PURGE_MARKER,
        running=False,
        last_started_at=datetime.now(),
        last_finished_at=datetime.now(),
        last_success_at=datetime.now(),
        last_error=f"removed demo rows: price={price_count}, financial={fin_count}, news={news_count}",
    ))
    commit_or_rollback(db)

NEWS_DEDUPE_MARKER="news_dedupe_cleanup_v3_16"

def cleanup_news_duplicates_once(db:Session):
    marker=db.query(SyncState).filter(SyncState.key==NEWS_DEDUPE_MARKER).first()
    if marker:return
    rows=db.query(NewsCache).order_by(NewsCache.id.asc()).all();seen=set();removed=0
    for row in rows:
        key=(row.stock_code,(row.link or "").strip())
        if key[1] and key in seen:db.delete(row);removed+=1
        else:seen.add(key)
    db.add(SyncState(key=NEWS_DEDUPE_MARKER,running=False,last_started_at=datetime.now(),last_finished_at=datetime.now(),last_success_at=datetime.now(),last_error=f"removed duplicate news rows: {removed}"));commit_or_rollback(db)

REAL_METRIC_PURGE_MARKER = "remove_seed_metrics_v3_17"

def clear_legacy_seed_metrics_once(db: Session):
    marker = (
        db.query(SyncState)
        .filter(SyncState.key == REAL_METRIC_PURGE_MARKER)
        .first()
    )
    if marker:
        return

    cleared = 0
    for stock in db.query(Stock).all():
        if stock.kiwoom_metrics_updated_at is None:
            stock.per = None
            stock.pbr = None
            stock.eps = None
            stock.bps = None
            stock.market_cap = 0
            stock.dividend_yield = None

        if stock.dart_financials_updated_at is None:
            stock.roe = None
            stock.revenue_growth = None
            stock.operating_margin = None

        cleared += 1

    db.add(
        SyncState(
            key=REAL_METRIC_PURGE_MARKER,
            running=False,
            last_started_at=datetime.now(),
            last_finished_at=datetime.now(),
            last_success_at=datetime.now(),
            last_error=f"legacy seeded metrics cleared: {cleared}",
        )
    )
    commit_or_rollback(db)

_runtime_data_initialized = False


def _enforce_local_stocklog_universe_policy(db:Session):
    """Immediately hide legacy rows that are clearly outside the new universe.

    Exact KRX-company membership is refreshed by the next Kiwoom/KRX master sync.
    This startup pass is intentionally one-way/conservative: it can exclude an
    obvious product immediately, but never re-enable a row previously excluded
    by a verified KRX snapshot. No historical data is deleted.
    """
    changed=0
    for st in db.query(Stock).filter(Stock.is_active==True).all():
        reason=_analysis_exclusion_reason({"name":st.name,"market":st.market,"strict_kind_master":False})
        if reason and (bool(st.is_analysis_eligible) or str(st.analysis_exclusion_reason or "")!=reason):
            st.is_analysis_eligible=False
            st.analysis_exclusion_reason=reason
            changed+=1
    if changed:
        commit_or_rollback(db)
    return changed


def _initialize_runtime_data_once() -> None:
    """Run idempotent seed/cleanup work during application startup, never at import time.

    Keeping this out of module import makes CLI tooling, unit tests and multi-module
    imports predictable.  Every helper called here is already designed to be
    idempotent; the process-local guard avoids duplicate work from repeated startup
    events in the same interpreter.
    """
    global _runtime_data_initialized
    if _runtime_data_initialized:
        return

    db = SessionLocal()
    try:
        seed(db)
        # Clean-install admin and legacy users are normalized after seed as well.
        for _user in db.query(User).all():
            desired = "ADMIN" if _user.is_admin else ("EVENT" if getattr(_user,"is_test_account",False) else user_tier(_user))
            if getattr(_user,"membership_tier",None) != desired:
                _user.membership_tier = desired
        commit_or_rollback(db)
        ensure_default_policies(db)
        reset_legacy_kiwoom_snapshots_once(db)
        purge_demo_data_once(db)
        clear_legacy_seed_metrics_once(db)
        cleanup_news_duplicates_once(db)
        _repair_v3683_lost_name_history(db)
        _enforce_local_stocklog_universe_policy(db)

        interrupted=db.query(FullMarketSyncState).filter(FullMarketSyncState.key=="full_market").first()
        if interrupted and interrupted.running:
            interrupted.running=False
            interrupted.phase="interrupted"
            interrupted.finished_at=datetime.now()
            interrupted.message="서버 재시작으로 이전 전체 종목 수집 작업이 중단되었습니다."
            commit_or_rollback(db)
        _runtime_data_initialized = True
    except Exception:
        rollback_quietly(db)
        logger.exception("runtime data initialization failed")
        raise
    finally:
        db.close()


@app.on_event("startup")
def initialize_runtime_data() -> None:
    _initialize_runtime_data_once()

async def _refresh_public_universe_policy_from_krx():
    """Refresh exact KRX listed-company membership before requests are served.

    This is intentionally separate from the expensive market-data sync: the
    eligibility bit is corrected at deployment while all old financial/price
    rows stay untouched. A provider failure leaves the local conservative
    policy in place and is retried by the next full sync.
    """
    try:
        kind_rows=await asyncio.to_thread(fetch_kind_company_master, force=False)
        verified={str(x.get("code") or "").strip() for x in kind_rows if bool(x.get("name_verified",True))}
        if len(verified)<1200:
            raise RuntimeError(f"KRX 상장법인 목록이 비정상적으로 적습니다: {len(verified):,}개")
        db=SessionLocal()
        try:
            changed=eligible=excluded=0
            for st in db.query(Stock).filter(Stock.is_active==True).all():
                reason=_analysis_exclusion_reason({
                    "name":st.name,
                    "market":st.market,
                    "strict_kind_master":True,
                    "kind_verified":st.code in verified,
                })
                next_eligible=not bool(reason)
                if bool(st.is_analysis_eligible)!=next_eligible or str(st.analysis_exclusion_reason or "")!=(reason or ""):
                    st.is_analysis_eligible=next_eligible
                    st.analysis_exclusion_reason=reason or None
                    changed+=1
                eligible+=int(next_eligible)
                excluded+=int(not next_eligible)
            if changed:
                commit_or_rollback(db)
            logger.info("KRX public universe policy refreshed eligible=%s excluded=%s changed=%s",eligible,excluded,changed)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("KRX public universe startup refresh skipped: %s",_sync_error_text(exc,500))

@app.on_event("startup")
async def start_public_universe_policy_refresh():
    # Complete the official membership refresh before opening the HTTP service,
    # so a legacy non-company security cannot briefly reappear after deployment.
    await _refresh_public_universe_policy_from_krx()

_sync_lock = asyncio.Lock()
_portfolio_cache = {}
_kiwoom_client_cache = {}
_live_kiwoom_client_cache = {}
_account_sync_locks = {}
_live_account_sync_locks = {}
_trade_fill_poll_cache = {}
_trade_fill_poll_locks = {}
_investor_flow_cache = {}
_chart_sync_cache = {}
_chart_sync_locks = {}
_full_market_task = None
_full_market_lock = asyncio.Lock()
_theme_sync_task = None
_theme_sync_lock = asyncio.Lock()
_flow_sync_task = None
_flow_sync_lock = asyncio.Lock()
_ai_flow_backfill_locks = {}

AI_DAILY_FREE_LIMIT=5  # legacy/default; actual limits come from membership policy
AI_USAGE_TIMEZONE=ZoneInfo("Asia/Seoul")


def _feature_access(user: User, db: Session, feature_key: str) -> dict:
    if user_tier(user)=="ADMIN":
        return {"enabled":True,"limit_value":-1 if feature_key=="ai_analysis" else None}
    return feature_policy(db,user_tier(user),feature_key)


def _require_feature(user: User, db: Session, feature_key: str):
    policy=_feature_access(user,db,feature_key)
    if not policy.get("enabled"):
        meta=MEMBERSHIP_FEATURES.get(feature_key,{})
        raise HTTPException(403,f"{meta.get('label','해당 기능')}은 현재 회원 등급에서 사용할 수 없습니다.")
    return policy



def _ai_usage_today():
    return datetime.now(AI_USAGE_TIMEZONE).date()


def _ai_usage_reset_at():
    now=datetime.now(AI_USAGE_TIMEZONE)
    tomorrow=now.date()+timedelta(days=1)
    return datetime.combine(
        tomorrow,
        dt_time.min,
        tzinfo=AI_USAGE_TIMEZONE,
    )


def _ai_limit_for(user: User, db: Session):
    policy=_feature_access(user,db,"ai_analysis")
    if not policy.get("enabled"):
        return 0
    value=policy.get("limit_value")
    if value is None:
        value=AI_DAILY_FREE_LIMIT
    return int(value)


def _ai_usage_unlimited(user: User, db: Session | None = None):
    if user_tier(user)=="ADMIN":
        return True
    if db is None:
        # Backward-safe fallback for call sites that do not have a Session.
        return user_tier(user)=="EVENT"
    return _ai_limit_for(user,db) < 0


def _ai_usage_status(user: User, db: Session):
    daily_limit=_ai_limit_for(user,db)
    unlimited=daily_limit<0
    today=_ai_usage_today()
    row=(
        db.query(AiDailyUsage)
        .filter(
            AiDailyUsage.user_id==user.id,
            AiDailyUsage.usage_date==today,
        )
        .first()
    )
    used=int(row.ai_queries or 0) if row else 0
    remaining=None if unlimited else max(0,daily_limit-used)
    return {
        "unlimited":unlimited,
        "daily_limit":None if unlimited else daily_limit,
        "used":used,
        "remaining":remaining,
        "usage_date":today.isoformat(),
        "resets_at":_ai_usage_reset_at().isoformat(),
        "account_type":(
            user_tier(user).lower()
        ),
    }


def _has_ai_analysis_access(user: User, db: Session, code: str, mode: str):
    # Admin/test accounts are intentionally unrestricted without per-stock rows.
    if _ai_usage_unlimited(user,db):
        return True
    return (
        db.query(AiAnalysisAccess.id)
        .filter(
            AiAnalysisAccess.user_id==user.id,
            AiAnalysisAccess.stock_code==code,
            AiAnalysisAccess.mode==mode,
        )
        .first()
        is not None
    )


def _grant_ai_analysis_access(user: User, db: Session, code: str, mode: str):
    if _ai_usage_unlimited(user,db):
        return False
    exists=(
        db.query(AiAnalysisAccess.id)
        .filter(
            AiAnalysisAccess.user_id==user.id,
            AiAnalysisAccess.stock_code==code,
            AiAnalysisAccess.mode==mode,
        )
        .first()
    )
    if exists:
        return False
    db.add(
        AiAnalysisAccess(
            user_id=user.id,
            stock_code=code,
            mode=mode,
        )
    )
    try:
        commit_or_rollback(db)
        return True
    except IntegrityError:
        # Two simultaneous unlock requests may race on the unique key. The
        # entitlement already existing is the desired final state.
        db.rollback()
        return False


def _granted_ai_codes(user: User, db: Session, codes: list[str], mode: str):
    if _ai_usage_unlimited(user,db):
        return set(codes)
    if not codes:
        return set()
    return {
        row[0]
        for row in (
            db.query(AiAnalysisAccess.stock_code)
            .filter(
                AiAnalysisAccess.user_id==user.id,
                AiAnalysisAccess.mode==mode,
                AiAnalysisAccess.stock_code.in_(codes),
            )
            .all()
        )
    }


def _consume_ai_usage(user: User, db: Session, query_count: int=1):
    query_count=max(1,int(query_count or 1))
    if _ai_usage_unlimited(user,db):
        return {**_ai_usage_status(user,db),"consumed":0}

    today=_ai_usage_today()
    row=(
        db.query(AiDailyUsage)
        .filter(
            AiDailyUsage.user_id==user.id,
            AiDailyUsage.usage_date==today,
        )
        .with_for_update()
        .first()
    )

    if not row:
        row=AiDailyUsage(
            user_id=user.id,
            usage_date=today,
            ai_queries=0,
        )
        db.add(row)
        flush_or_rollback(db)

    used=int(row.ai_queries or 0)
    daily_limit=max(0,_ai_limit_for(user,db))
    remaining=max(0,daily_limit-used)
    if remaining<query_count:
        if remaining:
            detail=(
                f"요청한 AI 분석 수가 오늘 남은 무료 횟수를 초과합니다. "
                f"현재 회원 등급은 하루 {daily_limit}회까지 이용할 수 있으며 현재 {remaining}회 남았습니다."
            )
        else:
            detail=(
                f"오늘 AI 분석 {daily_limit}회를 모두 사용했습니다. "
                "내일 00:00에 다시 이용할 수 있습니다."
            )
        raise HTTPException(429,detail)

    row.ai_queries=used+query_count
    row.updated_at=datetime.now()
    commit_or_rollback(db)

    return {**_ai_usage_status(user,db),"consumed":query_count}


def user_json(u, db: Session | None = None):
    tier=user_tier(u)
    payload={
        "id":u.id,
        "username":u.username,
        "display_name":u.display_name,
        "is_admin":tier=="ADMIN",
        # Legacy compatibility for old frontend caches; EVENT replaces TEST in v3.52.
        "is_test_account":tier=="EVENT",
        "membership_tier":tier,
        "membership_label":TIER_LABELS.get(tier,tier),
        "account_type":tier.lower(),
        "last_login_at":u.last_login_at.isoformat() if getattr(u,"last_login_at",None) else None,
        "last_login_method":getattr(u,"last_login_method","") or "",
        "login_count":int(getattr(u,"login_count",0) or 0),
        "member_profile":{
            "name":u.display_name or "",
            "gender":u.gender or "",
            "birth_year":u.birth_year,
            "birth_date":(u.birth_date.isoformat() if getattr(u,"birth_date",None) else None),
            "age":(
                (lambda today,born: today.year-born.year-((today.month,today.day)<(born.month,born.day)))(datetime.now(ZoneInfo("Asia/Seoul")).date(),u.birth_date)
                if getattr(u,"birth_date",None)
                else ((datetime.now(ZoneInfo("Asia/Seoul")).year-int(u.birth_year)) if u.birth_year else None)
            ),
            "phone_number_masked":(re.sub(r"(\d{3})\d+(\d{4})$",r"\1****\2",re.sub(r"\D","",u.phone_number or "")) if u.phone_number else ""),
        },
    }
    if db is not None:
        payload["features"]={
            key:{"enabled":bool(value.get("enabled")),"limit_value":value.get("limit_value")}
            for key,value in resolved_features(db,u).items()
        }
        payload["refresh_policy"]=refresh_policy_for_tier(db,tier)
        payload["has_investment_profile"]=db.query(InvestmentProfile.id).filter(InvestmentProfile.user_id==u.id).first() is not None
    return payload

def _mask_secret(value: str, head: int = 6, tail: int = 4):
    if not value:
        return ""
    if len(value) <= head + tail:
        return value[:2] + "*" * max(0, len(value) - 2)
    return f"{value[:head]}{'*' * (len(value) - head - tail)}{value[-tail:]}"

def _settings_json(c: KiwoomCredential | None):
    if not c:
        return {
            "configured": False,
            "use_mock": True,
            "account_no": "",
            "account_no_masked": "",
            "has_app_key": False,
            "has_secret_key": False,
            "app_key_masked": "",
            "secret_key_masked": "",
            "updated_at": None,
            "last_connected_at": None,
        }
    app_key = decrypt_secret(c.app_key_enc) if c.app_key_enc else ""
    secret_key = decrypt_secret(c.secret_key_enc) if c.secret_key_enc else ""
    return {
        "configured": True,
        "use_mock": c.use_mock,
        "account_no": c.account_no or "",
        "account_no_masked": _mask_secret(c.account_no or "", 4, 2),
        "has_app_key": bool(app_key),
        "has_secret_key": bool(secret_key),
        "app_key_masked": _mask_secret(app_key),
        "secret_key_masked": _mask_secret(secret_key),
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "last_connected_at": c.last_connected_at.isoformat() if c.last_connected_at else None,
    }


def _live_settings_json(c: KiwoomLiveCredential | None):
    if not c:
        return {
            "configured": False,
            "environment": "live",
            "account_no": "",
            "account_no_masked": "",
            "has_app_key": False,
            "has_secret_key": False,
            "app_key_masked": "",
            "secret_key_masked": "",
            "trading_enabled": False,
            "activated_at": None,
            "updated_at": None,
            "last_connected_at": None,
        }
    app_key=decrypt_secret(c.app_key_enc) if c.app_key_enc else ""
    secret_key=decrypt_secret(c.secret_key_enc) if c.secret_key_enc else ""
    return {
        "configured":bool(app_key and secret_key),
        "environment":"live",
        "account_no":c.account_no or "",
        "account_no_masked":_mask_secret(c.account_no or "",4,2),
        "has_app_key":bool(app_key),
        "has_secret_key":bool(secret_key),
        "app_key_masked":_mask_secret(app_key),
        "secret_key_masked":_mask_secret(secret_key),
        "trading_enabled":bool(c.trading_enabled),
        "activated_at":c.activated_at.isoformat() if c.activated_at else None,
        "updated_at":c.updated_at.isoformat() if c.updated_at else None,
        "last_connected_at":c.last_connected_at.isoformat() if c.last_connected_at else None,
    }



SOCIAL_PROVIDERS={
    "kakao":{
        "label":"카카오",
        "authorize_url":"https://kauth.kakao.com/oauth/authorize",
        "token_url":"https://kauth.kakao.com/oauth/token",
        "profile_url":"https://kapi.kakao.com/v2/user/me",
    },
    "naver":{
        "label":"네이버",
        "authorize_url":"https://nid.naver.com/oauth2.0/authorize",
        "token_url":"https://nid.naver.com/oauth2.0/token",
        "profile_url":"https://openapi.naver.com/v1/nid/me",
    },
    "google":{
        "label":"구글",
        "authorize_url":"https://accounts.google.com/o/oauth2/v2/auth",
        "token_url":"https://oauth2.googleapis.com/token",
        "profile_url":"https://openidconnect.googleapis.com/v1/userinfo",
    },
}
SOCIAL_FLOW_MINUTES=10
SOCIAL_SIGNUP_MINUTES=60


def _social_provider(provider:str):
    key=str(provider or "").strip().lower()
    if key not in SOCIAL_PROVIDERS:
        raise HTTPException(404,"지원하지 않는 소셜 로그인 제공자입니다.")
    return key,SOCIAL_PROVIDERS[key]


def _social_config(db:Session,provider:str):
    return db.query(SocialAuthProviderConfig).filter(SocialAuthProviderConfig.provider==provider).first()


def _social_config_values(row:SocialAuthProviderConfig | None):
    if not row:
        return "",""
    try:
        client_id=decrypt_secret(row.client_id_enc) if row.client_id_enc else ""
        client_secret=decrypt_secret(row.client_secret_enc) if row.client_secret_enc else ""
        return client_id,client_secret
    except Exception as exc:
        logger.warning("social credential decrypt failed provider=%s error=%s",getattr(row,'provider',''),exc)
        return "",""


def _social_public_config(row:SocialAuthProviderConfig | None):
    if not row:
        return {
            "configured":False,"enabled":False,"redirect_uri":"",
            "client_id_masked":"","has_client_secret":False,
            "last_test_status":"untested","last_test_message":"",
            "last_tested_at":None,"updated_at":None,
        }
    client_id,client_secret=_social_config_values(row)
    secret_ok=bool(client_secret) if row.provider in {"naver","google"} else True
    configured=bool(client_id and secret_ok and (row.redirect_uri or '').strip())
    return {
        "configured":configured,
        "enabled":bool(row.is_enabled),
        "redirect_uri":row.redirect_uri or "",
        "client_id_masked":_mask_secret(client_id,4,3) if client_id else "",
        "has_client_secret":bool(client_secret),
        "last_test_status":row.last_test_status or "untested",
        "last_test_message":row.last_test_message or "",
        "last_tested_at":row.last_tested_at.isoformat() if row.last_tested_at else None,
        "updated_at":row.updated_at.isoformat() if row.updated_at else None,
    }


def _social_safe_return_url(request:Request,raw:str):
    raw=str(raw or "").strip()
    origin=str(request.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        referer=str(request.headers.get("referer") or "").strip()
        if referer:
            ref=urlparse(referer)
            if ref.scheme in {"http","https"} and ref.netloc:
                origin=f"{ref.scheme}://{ref.netloc}".rstrip("/")
    candidate=raw.rstrip("/")
    parsed=urlparse(candidate)
    mobile_return=str(settings.mobile_social_return_url or "stocklog://auth").rstrip("/")
    # The installed app uses a single fixed deep link. It is intentionally
    # accepted before the HTTP(S) Origin equality check because a WebView
    # starts the request from the public StockLog origin but the system browser
    # must return to the native application.
    if candidate==mobile_return:
        return candidate
    if parsed.scheme not in {"http","https"} or not parsed.netloc:
        raise HTTPException(422,"소셜 로그인 반환 주소가 올바르지 않습니다.")
    # The SPA itself initiated this request. Requiring the requested return URL to
    # equal Origin/Referer prevents an attacker from turning OAuth into an open
    # redirect while still supporting localhost, LAN IPs and DDNS hosts.
    if origin and candidate!=origin:
        raise HTTPException(422,"소셜 로그인 반환 주소가 현재 StockLog 접속 주소와 일치하지 않습니다.")
    if not origin and settings.is_production:
        allowed={x.rstrip('/') for x in settings.cors_origins}
        if candidate not in allowed:
            raise HTTPException(422,"허용되지 않은 소셜 로그인 반환 주소입니다.")
    return candidate


def _social_redirect_with_session(return_url:str,param:str,state:str):
    parsed=urlparse(return_url)
    query=dict(parse_qsl(parsed.query,keep_blank_values=True))
    query[param]=state
    # Keep custom-scheme callbacks such as stocklog://auth without forcing a
    # trailing slash, while preserving the normal '/' root for HTTP(S) SPAs.
    path=parsed.path if parsed.scheme not in {'http','https'} else (parsed.path or '/')
    return urlunparse((parsed.scheme,parsed.netloc,path,parsed.params,urlencode(query),parsed.fragment))


def _social_authorization_url(provider:str,row:SocialAuthProviderConfig,state:str):
    client_id,_=_social_config_values(row)
    if not client_id or not (row.redirect_uri or '').strip():
        raise HTTPException(409,f"{SOCIAL_PROVIDERS[provider]['label']} 로그인 설정이 완료되지 않았습니다.")
    params={
        "response_type":"code",
        "client_id":client_id,
        "redirect_uri":row.redirect_uri.strip(),
        "state":state,
    }
    if provider=="google":
        params.update({
            # Basic identity plus provider-verified profile fields used by the
            # StockLog signup form. Google may still omit a field when the
            # account itself has no value saved, so missing fields remain
            # editable in the signup screen.
            "scope":" ".join([
                "openid","email","profile",
                "https://www.googleapis.com/auth/user.gender.read",
                "https://www.googleapis.com/auth/user.birthday.read",
                "https://www.googleapis.com/auth/user.phonenumbers.read",
            ]),
            "prompt":"select_account consent",
            "include_granted_scopes":"true",
        })
    # Kakao/Naver profile consent items are controlled in each provider's
    # developer console. Do not force unavailable scopes here: requesting a
    # scope that the production app has not been approved for can make the
    # entire login fail with invalid_scope. Once the consent items are enabled,
    # /v2/user/me and /v1/nid/me return the approved fields automatically.
    return f"{SOCIAL_PROVIDERS[provider]['authorize_url']}?{urlencode(params)}"


def _new_social_session(db:Session,provider:str,mode:str,return_url:str,initiated_by_user_id:int|None=None):
    now=datetime.now()
    # Opportunistic cleanup: these rows only exist to bridge a short OAuth round trip.
    db.query(SocialAuthSession).filter(
        SocialAuthSession.expires_at<now-timedelta(hours=1)
    ).delete(synchronize_session=False)
    state=secrets.token_urlsafe(40)
    row=SocialAuthSession(
        state=state,provider=provider,mode=mode,status="pending",
        return_url=return_url,initiated_by_user_id=initiated_by_user_id,
        expires_at=now+timedelta(minutes=SOCIAL_FLOW_MINUTES),
    )
    db.add(row);commit_or_rollback(db);db.refresh(row)
    return row


async def _social_exchange_provider(provider:str,config:SocialAuthProviderConfig,code:str,state:str):
    info=SOCIAL_PROVIDERS[provider]
    client_id,client_secret=_social_config_values(config)
    if not client_id or not (config.redirect_uri or '').strip() or (provider in {"naver","google"} and not client_secret):
        raise RuntimeError("관리자 페이지의 Client ID, Client Secret, Redirect URI 설정을 확인해주세요.")
    async with httpx.AsyncClient(timeout=15.0,follow_redirects=False) as client:
        if provider=="kakao":
            kakao_token_data={
                "grant_type":"authorization_code",
                "client_id":client_id,
                "redirect_uri":config.redirect_uri.strip(),
                "code":code,
            }
            if client_secret:
                kakao_token_data["client_secret"]=client_secret
            token_response=await client.post(
                info["token_url"],
                data=kakao_token_data,
                headers={"Content-Type":"application/x-www-form-urlencoded;charset=utf-8"},
            )
        elif provider=="google":
            token_response=await client.post(
                info["token_url"],
                data={
                    "grant_type":"authorization_code",
                    "client_id":client_id,
                    "client_secret":client_secret,
                    "redirect_uri":config.redirect_uri.strip(),
                    "code":code,
                },
                headers={"Content-Type":"application/x-www-form-urlencoded"},
            )
        else:
            token_response=await client.post(
                info["token_url"],
                data={
                    "grant_type":"authorization_code",
                    "client_id":client_id,
                    "client_secret":client_secret,
                    "redirect_uri":config.redirect_uri.strip(),
                    "code":code,
                    "state":state,
                },
                headers={"Content-Type":"application/x-www-form-urlencoded"},
            )
        token_response.raise_for_status()
        token_data=token_response.json()
        access_token=str(token_data.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("OAuth 액세스 토큰이 반환되지 않았습니다.")
        profile_response=await client.get(
            info["profile_url"],
            headers={"Authorization":f"Bearer {access_token}"},
        )
        profile_response.raise_for_status()
        payload=profile_response.json()
        google_people={}
        if provider=="google":
            # Extra People API fields are optional at runtime. Never break
            # login just because an account does not expose one of them.
            try:
                people_response=await client.get(
                    "https://people.googleapis.com/v1/people/me",
                    params={"personFields":"names,genders,birthdays,phoneNumbers"},
                    headers={"Authorization":f"Bearer {access_token}"},
                )
                if people_response.status_code==200:
                    google_people=people_response.json() or {}
                else:
                    logger.info("google people profile unavailable status=%s",people_response.status_code)
            except Exception as exc:
                logger.info("google people profile optional lookup failed error=%s",exc)

    if provider=="kakao":
        provider_user_id=str(payload.get("id") or "").strip()
        account=payload.get("kakao_account") or {}
        profile=account.get("profile") or {}
        properties=payload.get("properties") or {}
        email=str(account.get("email") or "").strip()
        # Prefer the Kakao Account real-name field when permission is granted;
        # nickname is only a fallback because StockLog stores this as the member
        # name and locks provider-supplied values against client-side editing.
        nickname=str(account.get("name") or profile.get("nickname") or properties.get("nickname") or "").strip()
        profile_image=str(profile.get("profile_image_url") or properties.get("profile_image") or "").strip()
        raw_gender=str(account.get("gender") or "").lower().strip()
        gender={"male":"male","female":"female"}.get(raw_gender,"")
        try:
            birth_year=int(str(account.get("birthyear") or "").strip()) if account.get("birthyear") else None
        except Exception:
            birth_year=None
        phone_number=str(account.get("phone_number") or "").strip()
    elif provider=="google":
        provider_user_id=str(payload.get("sub") or "").strip()
        email=str(payload.get("email") or "").strip()
        names=google_people.get("names") or []
        primary_name=next((x for x in names if (x.get("metadata") or {}).get("primary")),names[0] if names else {})
        nickname=str(primary_name.get("displayName") or payload.get("name") or payload.get("given_name") or "").strip()
        profile_image=str(payload.get("picture") or "").strip()

        genders=google_people.get("genders") or []
        primary_gender=next((x for x in genders if (x.get("metadata") or {}).get("primary")),genders[0] if genders else {})
        raw_gender=str(primary_gender.get("value") or "").lower().strip()
        gender={"male":"male","female":"female","other":"other"}.get(raw_gender,"")

        birthdays=google_people.get("birthdays") or []
        primary_birthday=next((x for x in birthdays if (x.get("metadata") or {}).get("primary")),birthdays[0] if birthdays else {})
        birth_date=primary_birthday.get("date") or {}
        try:
            birth_year=int(birth_date.get("year")) if birth_date.get("year") else None
        except Exception:
            birth_year=None

        phone_rows=google_people.get("phoneNumbers") or []
        primary_phone=next((x for x in phone_rows if (x.get("metadata") or {}).get("primary")),phone_rows[0] if phone_rows else {})
        phone_number=str(primary_phone.get("value") or primary_phone.get("canonicalForm") or "").strip()
    else:
        if str(payload.get("resultcode") or "00")!="00":
            raise RuntimeError(str(payload.get("message") or "네이버 사용자 프로필 조회에 실패했습니다."))
        profile=payload.get("response") or {}
        provider_user_id=str(profile.get("id") or "").strip()
        email=str(profile.get("email") or "").strip()
        # Naver exposes the real-name profile field separately from nickname.
        nickname=str(profile.get("name") or profile.get("nickname") or "").strip()
        profile_image=str(profile.get("profile_image") or "").strip()
        raw_gender=str(profile.get("gender") or "").upper().strip()
        gender={"M":"male","F":"female"}.get(raw_gender,"")
        try:
            birth_year=int(str(profile.get("birthyear") or "").strip()) if profile.get("birthyear") else None
        except Exception:
            birth_year=None
        phone_number=str(profile.get("mobile") or "").strip()

    if not provider_user_id:
        raise RuntimeError("소셜 로그인 고유 사용자 ID를 확인할 수 없습니다.")
    provider_fields=[]
    if nickname:
        provider_fields.append("name")
    if gender:
        provider_fields.append("gender")
    if birth_year:
        provider_fields.append("birth_year")
    if phone_number:
        provider_fields.append("phone_number")
    return {
        "provider_user_id":provider_user_id,
        "email":email,
        "nickname":nickname,
        "profile_image":profile_image,
        "gender":gender,
        "birth_year":birth_year,
        "phone_number":phone_number,
        "provider_profile_fields":provider_fields,
    }


TERMS_POLICY_VERSION="2026-08-21-v1"
PRIVACY_POLICY_VERSION="2026-08-21-v1"


def _normalize_signup_phone(raw:str):
    digits=re.sub(r"\D","",str(raw or ""))
    # Google/Kakao may return Korean numbers in +82 10-1234-5678 form.
    if digits.startswith("82") and len(digits) in {11,12}:
        digits="0"+digits[2:]
    if len(digits) not in {10,11}:
        raise HTTPException(422,"휴대폰 번호를 정확히 입력해주세요.")
    if len(digits)==11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def _validate_social_signup_info(info,flow:SocialAuthSession|None=None):
    locked={x for x in str(getattr(flow,"provider_profile_fields","") or "").split(",") if x}
    name=str((flow.nickname if flow and "name" in locked else info.name) or "").strip()
    gender=str((flow.gender if flow and "gender" in locked else info.gender) or "").strip()
    birth_year=(flow.birth_year if flow and "birth_year" in locked else info.birth_year)
    phone_number=(flow.phone_number if flow and "phone_number" in locked else info.phone_number)
    if len(name)<2:
        raise HTTPException(422,"이름을 2자 이상 입력해주세요.")
    if gender not in {"male","female","other","prefer_not_to_say"}:
        raise HTTPException(422,"성별 항목을 확인해주세요.")
    now_year=datetime.now(ZoneInfo("Asia/Seoul")).year
    if int(birth_year)>now_year-14 or int(birth_year)<now_year-120:
        raise HTTPException(422,"출생연도를 확인해주세요. StockLog는 만 14세 이상만 가입할 수 있습니다.")
    if not info.age_14_or_older:
        raise HTTPException(422,"만 14세 이상 확인이 필요합니다.")
    if not info.terms_consent or not info.privacy_consent:
        raise HTTPException(422,"필수 약관과 개인정보 수집/이용에 동의해주세요.")
    return {
        "name":name[:80],
        "gender":gender,
        "birth_year":int(birth_year),
        "phone_number":_normalize_signup_phone(phone_number),
    }


def _validate_investment_profile_for_signup(profile:InvestmentProfileIn):
    question_ids=[str(item.get("question_id") or "").strip() for item in profile.answers if isinstance(item,dict)]
    answered_values=[str(item.get("value") or "").strip() for item in profile.answers if isinstance(item,dict)]
    expected_question_ids={str(i) for i in range(1,31)}
    valid_answer_values={f"{i}{letter}" for i in range(1,31) for letter in "abcd"}
    if (
        len(profile.answers)!=30
        or set(question_ids)!=expected_question_ids
        or any(not item for item in answered_values)
        or any(value not in valid_answer_values for value in answered_values)
        or any(not re.fullmatch(rf"{re.escape(question_id)}[a-d]",value) for question_id,value in zip(question_ids,answered_values))
    ):
        raise HTTPException(422,"회원가입 전 투자 성향 검사 30문항을 모두 완료해주세요.")


def _social_generated_username(db:Session,provider:str,provider_user_id:str):
    digest=hashlib.sha256(f"{provider}:{provider_user_id}".encode()).hexdigest()[:14]
    base=f"{provider}_{digest}"[:60]
    if not db.query(User).filter(User.username==base).first():
        return base
    for idx in range(2,1000):
        suffix=f"_{idx}"
        value=f"{base[:60-len(suffix)]}{suffix}"
        if not db.query(User).filter(User.username==value).first():
            return value
    raise HTTPException(500,"소셜 계정 아이디를 생성하지 못했습니다.")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": f"StockLog v{PROJECT_VERSION}",
        "environment": settings.app_env,
        "database": "mysql" if settings.database_url.startswith("mysql") else "sqlite",
    }


@app.get("/health/ready")
def health_ready():
    """Readiness probe: process is alive *and* the primary database is usable."""
    db=SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {
            "ok": True,
            "service": f"StockLog v{PROJECT_VERSION}",
            "database": "ready",
        }
    except Exception:
        rollback_quietly(db)
        logger.exception("readiness database check failed")
        return JSONResponse(
            status_code=503,
            content={"ok":False,"service":f"StockLog v{PROJECT_VERSION}","database":"unavailable"},
        )
    finally:
        db.close()

@app.post("/api/auth/register")
def register(body: RegisterIn, db: Session=Depends(get_db)):
    """Create a normal StockLog account using the public ID/password signup flow."""
    username=str(body.username or "").strip()
    display_name=str(body.display_name or "").strip()
    gender=str(body.gender or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,60}",username):
        raise HTTPException(422,"아이디는 영문, 숫자, ., _, - 조합으로 3자 이상 입력해주세요.")
    if len(display_name)<2:
        raise HTTPException(422,"이름을 2자 이상 입력해주세요.")
    if gender not in {"male","female","other","prefer_not_to_say"}:
        raise HTTPException(422,"성별 항목을 확인해주세요.")
    if not body.terms_consent or not body.privacy_consent:
        raise HTTPException(422,"필수 약관과 개인정보 수집/이용에 동의해주세요.")

    today=datetime.now(ZoneInfo("Asia/Seoul")).date()
    born=body.birth_date
    age=today.year-born.year-((today.month,today.day)<(born.month,born.day))
    if age<14 or age>120:
        raise HTTPException(422,"생년월일을 확인해주세요. StockLog는 만 14세 이상만 가입할 수 있습니다.")

    _validate_investment_profile_for_signup(body.investment_profile)
    phone_number=_normalize_signup_phone(body.phone_number)
    if db.query(User).filter(User.username==username).first():
        raise HTTPException(409,"이미 사용 중인 아이디입니다.")

    now=datetime.now()
    user=User(
        username=username,
        password_hash=hash_password(body.password),
        display_name=display_name[:80],
        gender=gender,
        birth_year=born.year,
        birth_date=born,
        phone_number=phone_number,
        is_admin=False,is_test_account=False,is_active=True,
        last_login_at=now,last_login_method="local",login_count=1,
    )
    db.add(user);flush_or_rollback(db)
    profile=body.investment_profile
    db.add(InvestmentProfile(
        user_id=user.id,result_code=profile.result_code,
        answers_json=json.dumps(profile.answers,ensure_ascii=False),
        scores_json=json.dumps(profile.scores,ensure_ascii=False),
        completed_at=now,updated_at=now,
    ))
    db.add(UserConsent(user_id=user.id,consent_type="terms",policy_version=TERMS_POLICY_VERSION,agreed_at=now))
    db.add(UserConsent(user_id=user.id,consent_type="privacy",policy_version=PRIVACY_POLICY_VERSION,agreed_at=now))
    db.add(UserConsent(user_id=user.id,consent_type="age_14_plus",policy_version="2026-08-21-v1",agreed_at=now))
    try:
        commit_or_rollback(db);db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"이미 사용 중인 아이디입니다.")
    return {"token":create_access_token(user.username,user.auth_version),"user":user_json(user,db),"ai_usage":_ai_usage_status(user,db)}

@app.get("/api/auth/check-username")
def check_username_availability(
    username:str=Query("",max_length=60),
    db:Session=Depends(get_db),
):
    value=str(username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,60}",value):
        return {"valid":False,"available":False,"message":"아이디 형식을 확인해주세요."}
    exists=db.query(User.id).filter(User.username==value).first() is not None
    return {
        "valid":True,
        "available":not exists,
        "message":"사용 가능한 아이디입니다." if not exists else "이미 사용 중인 아이디입니다.",
    }


@app.post("/api/auth/login")
def login(body: LoginIn, db: Session=Depends(get_db)):
    u=db.query(User).filter(User.username==body.username,User.is_active==True).first()
    if not u or not verify_password(body.password,u.password_hash):
        raise HTTPException(401,"아이디 또는 비밀번호가 올바르지 않습니다.")
    u.last_login_at=datetime.now()
    u.last_login_method="local"
    u.login_count=int(getattr(u,"login_count",0) or 0)+1
    commit_or_rollback(db);db.refresh(u)
    return {"token":create_access_token(u.username,u.auth_version),"user":user_json(u,db)}


@app.post("/api/auth/admin-login")
def admin_local_login(body: LoginIn, db: Session=Depends(get_db)):
    """Break-glass local admin login; not used by the public member UI."""
    u=db.query(User).filter(User.username==body.username).first()
    if not u or not verify_password(body.password,u.password_hash):
        raise HTTPException(401,"아이디 또는 비밀번호가 올바르지 않습니다.")
    if not u.is_admin and user_tier(u)!="ADMIN":
        raise HTTPException(403,"관리자 계정만 사용할 수 있습니다.")
    u.last_login_at=datetime.now()
    u.last_login_method="admin"
    u.login_count=int(getattr(u,"login_count",0) or 0)+1
    commit_or_rollback(db);db.refresh(u)
    return {"token":create_access_token(u.username,u.auth_version),"user":user_json(u,db)}


@app.get("/api/auth/social/providers")
def social_auth_providers(db:Session=Depends(get_db)):
    """Public social-login visibility.

    The administrator's `enabled` checkbox is the source of truth for whether
    a configured provider is shown on the login page. The connection-test
    result is returned as diagnostic metadata, but it must not silently hide a
    provider that the administrator explicitly chose to expose.
    """
    result={}
    for provider,info in SOCIAL_PROVIDERS.items():
        row=_social_config(db,provider)
        public=_social_public_config(row)
        visible=bool(public["configured"] and public["enabled"])
        result[provider]={
            "label":info["label"],
            "available":visible,
            "verified":bool(public["last_test_status"]=="success"),
        }
    return JSONResponse(
        content=result,
        headers={
            "Cache-Control":"no-store, no-cache, must-revalidate, max-age=0",
            "Pragma":"no-cache",
        },
    )


@app.get("/api/auth/social/{provider}/start")
def social_auth_start(provider:str,request:Request,return_url:str=Query(...,max_length=700),db:Session=Depends(get_db)):
    provider,info=_social_provider(provider)
    config=_social_config(db,provider)
    public=_social_public_config(config)
    if not config or not public["configured"] or not public["enabled"]:
        raise HTTPException(409,f"{info['label']} 로그인이 현재 활성화되어 있지 않습니다.")
    # The end-to-end test is an administrator diagnostic, not a second hidden
    # enable switch. If the provider is configured and explicitly exposed,
    # allow the real OAuth round trip; provider errors are handled by callback.
    safe_return=_social_safe_return_url(request,return_url)
    flow=_new_social_session(db,provider,"login",safe_return)
    return {"authorization_url":_social_authorization_url(provider,config,flow.state)}


@app.get("/api/auth/social/{provider}/callback")
async def social_auth_callback(provider:str,request:Request,code:str=Query(""),state:str=Query(""),error:str=Query(""),error_description:str=Query(""),db:Session=Depends(get_db)):
    provider,info=_social_provider(provider)
    flow=db.query(SocialAuthSession).filter(SocialAuthSession.state==state,SocialAuthSession.provider==provider).first()
    if not flow:
        raise HTTPException(400,"소셜 로그인 요청을 찾을 수 없거나 만료되었습니다.")
    if flow.expires_at<datetime.now():
        flow.status="expired";flow.error_message="소셜 로그인 요청이 만료되었습니다.";commit_or_rollback(db)
        return RedirectResponse(_social_redirect_with_session(flow.return_url,"social_session" if flow.mode=="login" else "social_test_session",flow.state),status_code=302)
    config=_social_config(db,provider)
    try:
        if error:
            raise RuntimeError(error_description or error)
        if not code:
            raise RuntimeError("OAuth 인가 코드가 전달되지 않았습니다.")
        if not config:
            raise RuntimeError("관리자 소셜 로그인 설정을 찾을 수 없습니다.")
        # OAuth token/profile exchange is external I/O. The flow/config SELECTs
        # must not reserve a DB connection while the provider responds.
        commit_or_rollback(db)
        profile=await _social_exchange_provider(provider,config,code,state)
        flow.provider_user_id=profile["provider_user_id"]
        flow.email=profile["email"]
        flow.nickname=profile["nickname"]
        flow.profile_image=profile["profile_image"]
        flow.gender=profile.get("gender") or ""
        flow.birth_year=profile.get("birth_year")
        flow.phone_number=profile.get("phone_number") or ""
        flow.provider_profile_fields=",".join(profile.get("provider_profile_fields") or [])
        flow.error_message=""
        now=datetime.now()

        if flow.mode=="test":
            admin=db.query(User).filter(User.id==flow.initiated_by_user_id).first() if flow.initiated_by_user_id else None
            if not admin or not admin.is_admin:
                raise RuntimeError("연결 테스트를 요청한 관리자 계정을 확인할 수 없습니다.")
            flow.status="test_success"
            config.last_test_status="success"
            received_labels={"name":"이름","gender":"성별","birth_year":"출생연도","phone_number":"휴대폰"}
            received=[received_labels[x] for x in (profile.get("provider_profile_fields") or []) if x in received_labels]
            received_text=" / ".join(received) if received else "추가 회원정보 없음"
            config.last_test_message=f"{info['label']} OAuth 인증 · 토큰 발급 · 사용자 프로필 조회 성공 · 수신: {received_text}"
            config.last_tested_at=now
        else:
            social=(db.query(SocialAccount).filter(SocialAccount.provider==provider,SocialAccount.provider_user_id==profile["provider_user_id"]).first())
            if social:
                user=db.query(User).filter(User.id==social.user_id,User.is_active==True).first()
                if not user:
                    raise RuntimeError("연결된 StockLog 계정이 비활성 상태입니다.")
                social.email=profile["email"] or social.email
                social.nickname=profile["nickname"] or social.nickname
                social.profile_image=profile["profile_image"] or social.profile_image
                social.last_login_at=now
                flow.user_id=user.id
                flow.status="login_ready"
            else:
                flow.status="signup_required"
                # New members still need to enter profile information and finish
                # the 30-question investment-style test. Ten minutes is too
                # short for that flow, so extend only the post-OAuth signup
                # handoff while keeping the initial OAuth round trip short-lived.
                flow.expires_at=now+timedelta(minutes=SOCIAL_SIGNUP_MINUTES)
        commit_or_rollback(db)
    except Exception as exc:
        logger.warning("social auth callback failed provider=%s mode=%s error=%s",provider,flow.mode,exc)
        flow.status="test_failed" if flow.mode=="test" else "failed"
        flow.error_message=str(exc)[:1000]
        if flow.mode=="test" and config:
            config.last_test_status="failed"
            config.last_test_message=str(exc)[:1000]
            config.last_tested_at=datetime.now()
        commit_or_rollback(db)

    param="social_test_session" if flow.mode=="test" else "social_session"
    return RedirectResponse(_social_redirect_with_session(flow.return_url,param,flow.state),status_code=302)


@app.post("/api/auth/social/exchange")
def social_auth_exchange(body:SocialSessionIn,db:Session=Depends(get_db)):
    flow=db.query(SocialAuthSession).filter(SocialAuthSession.state==body.session_id,SocialAuthSession.mode=="login").first()
    if not flow or flow.expires_at<datetime.now():
        raise HTTPException(400,"소셜 로그인 요청이 만료되었습니다. 다시 로그인해주세요.")
    if flow.consumed_at:
        raise HTTPException(409,"이미 처리된 소셜 로그인 요청입니다.")
    if flow.status=="failed":
        raise HTTPException(400,flow.error_message or "소셜 로그인에 실패했습니다.")
    if flow.status=="login_ready" and flow.user_id:
        user=db.query(User).filter(User.id==flow.user_id,User.is_active==True).first()
        if not user:
            raise HTTPException(401,"연결된 StockLog 계정을 사용할 수 없습니다.")
        now=datetime.now()
        user.last_login_at=now
        user.last_login_method=flow.provider or "social"
        user.login_count=int(getattr(user,"login_count",0) or 0)+1
        flow.consumed_at=now;flow.status="completed";commit_or_rollback(db);db.refresh(user)
        return {"token":create_access_token(user.username,user.auth_version),"user":user_json(user,db),"needs_profile":False}
    if flow.status=="signup_required":
        return {
            "needs_profile":True,
            "session_id":flow.state,
            "provider":flow.provider,
            "provider_label":SOCIAL_PROVIDERS[flow.provider]["label"],
            "display_name":flow.nickname or f"{SOCIAL_PROVIDERS[flow.provider]['label']} 회원",
            "email":flow.email,
            "gender":flow.gender or "",
            "birth_year":flow.birth_year,
            "phone_number":flow.phone_number or "",
            "locked_fields":[x for x in str(flow.provider_profile_fields or "").split(",") if x],
        }
    raise HTTPException(409,"소셜 로그인 인증 처리가 아직 완료되지 않았습니다.")


@app.post("/api/auth/social/complete")
def social_signup_complete(body:SocialSignupCompleteIn,db:Session=Depends(get_db)):
    flow=db.query(SocialAuthSession).filter(SocialAuthSession.state==body.session_id,SocialAuthSession.mode=="login").with_for_update().first()
    if not flow or flow.expires_at<datetime.now():
        raise HTTPException(400,"소셜 회원가입 요청이 만료되었습니다. 다시 로그인해주세요.")
    if flow.consumed_at:
        raise HTTPException(409,"이미 처리된 소셜 회원가입 요청입니다.")
    if flow.status!="signup_required" or not flow.provider_user_id:
        raise HTTPException(409,"소셜 인증을 먼저 완료해주세요.")
    _validate_investment_profile_for_signup(body.investment_profile)
    signup_info=_validate_social_signup_info(body.signup_info,flow)

    existing=db.query(SocialAccount).filter(SocialAccount.provider==flow.provider,SocialAccount.provider_user_id==flow.provider_user_id).first()
    if existing:
        user=db.query(User).filter(User.id==existing.user_id,User.is_active==True).first()
        if not user:
            raise HTTPException(409,"이미 연결된 소셜 계정이 있으나 StockLog 계정을 사용할 수 없습니다.")
        now=datetime.now()
        user.last_login_at=now
        user.last_login_method=flow.provider or "social"
        user.login_count=int(getattr(user,"login_count",0) or 0)+1
        flow.user_id=user.id;flow.status="completed";flow.consumed_at=now;commit_or_rollback(db);db.refresh(user)
        return {"token":create_access_token(user.username,user.auth_version),"user":user_json(user,db),"ai_usage":_ai_usage_status(user,db)}

    username=_social_generated_username(db,flow.provider,flow.provider_user_id)
    display_name=signup_info["name"]
    user=User(
        username=username,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        display_name=display_name,
        gender=signup_info["gender"],
        birth_year=signup_info["birth_year"],
        phone_number=signup_info["phone_number"],
        is_admin=False,is_test_account=False,is_active=True,
        last_login_at=datetime.now(),last_login_method=flow.provider or "social",login_count=1,
    )
    db.add(user);flush_or_rollback(db)
    now=datetime.now()
    profile=body.investment_profile
    db.add(InvestmentProfile(
        user_id=user.id,result_code=profile.result_code,
        answers_json=json.dumps(profile.answers,ensure_ascii=False),
        scores_json=json.dumps(profile.scores,ensure_ascii=False),
        completed_at=now,updated_at=now,
    ))
    db.add(SocialAccount(
        user_id=user.id,provider=flow.provider,provider_user_id=flow.provider_user_id,
        email=flow.email or "",nickname=flow.nickname or "",profile_image=flow.profile_image or "",
        last_login_at=now,
    ))
    db.add(UserConsent(user_id=user.id,consent_type="terms",policy_version=TERMS_POLICY_VERSION,agreed_at=now))
    db.add(UserConsent(user_id=user.id,consent_type="privacy",policy_version=PRIVACY_POLICY_VERSION,agreed_at=now))
    db.add(UserConsent(user_id=user.id,consent_type="age_14_plus",policy_version="2026-08-21-v1",agreed_at=now))
    flow.user_id=user.id;flow.status="completed";flow.consumed_at=now
    try:
        commit_or_rollback(db);db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"소셜 계정 생성 중 중복 데이터가 확인되었습니다. 다시 로그인해주세요.")
    return {"token":create_access_token(user.username,user.auth_version),"user":user_json(user,db),"ai_usage":_ai_usage_status(user,db)}

@app.get("/api/investment-profile")
def investment_profile_get(
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    row=(
        db.query(InvestmentProfile)
        .filter(
            InvestmentProfile.user_id
            == u.id
        )
        .first()
    )

    if not row:
        return {
            "exists":False,
            "profile":None,
        }

    try:
        answers=json.loads(
            row.answers_json
            or "[]"
        )
    except Exception:
        answers=[]

    try:
        scores=json.loads(
            row.scores_json
            or "{}"
        )
    except Exception:
        scores={}

    return {
        "exists":True,
        "profile":{
            "result_code":
                row.result_code,
            "answers":
                answers,
            "scores":
                scores,
            "completed_at":
                row.completed_at.isoformat()
                if row.completed_at
                else None,
            "updated_at":
                row.updated_at.isoformat()
                if row.updated_at
                else None,
        },
    }


@app.post("/api/investment-profile")
def investment_profile_save(
    body:InvestmentProfileIn,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    row=(
        db.query(InvestmentProfile)
        .filter(
            InvestmentProfile.user_id
            == u.id
        )
        .first()
    )

    now=datetime.now()

    if not row:
        row=InvestmentProfile(
            user_id=u.id,
            result_code=body.result_code,
            completed_at=now,
        )
        db.add(row)

    row.result_code=body.result_code
    row.answers_json=json.dumps(
        body.answers,
        ensure_ascii=False,
    )
    row.scores_json=json.dumps(
        body.scores,
        ensure_ascii=False,
    )
    row.completed_at=now
    row.updated_at=now

    commit_or_rollback(db)
    db.refresh(row)

    return {
        "ok":True,
        "message":"투자 성향 분석 결과를 저장했습니다.",
        "profile":{
            "result_code":
                row.result_code,
            "answers":
                body.answers,
            "scores":
                body.scores,
            "completed_at":
                row.completed_at.isoformat(),
            "updated_at":
                row.updated_at.isoformat(),
        },
    }


@app.get("/api/auth/me")
def me(u:User=Depends(current_user),db:Session=Depends(get_db)):
    return user_json(u,db)


@app.get("/api/ai-usage")
def ai_usage(
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    return _ai_usage_status(u,db)




def _admin_access_control_payload(row:SiteAccessSetting|None,request:Request):
    mode=str(row.mode or ACCESS_MODE_ALLOW_ALL) if row else ACCESS_MODE_ALLOW_ALL
    if mode not in {ACCESS_MODE_ALLOW_ALL,ACCESS_MODE_ALLOWLIST}:
        mode=ACCESS_MODE_ALLOW_ALL
    try:
        allowed_ips=normalize_access_rules(json.loads(row.allowed_ips_json or "[]") if row else [])
    except (json.JSONDecodeError,AccessRuleError,TypeError):
        allowed_ips=[]
    client_ip=_request_client_ip(request)
    return {
        "mode":mode,"allowed_ips":allowed_ips,"current_ip":client_ip or "확인 불가",
        "current_ip_allowed":access_allowed(mode,client_ip,allowed_ips,allow_loopback=True),
        "loopback_recovery":True,"updated_at":row.updated_at.isoformat() if row and row.updated_at else None,
    }


@app.get("/api/admin/access-control")
def admin_access_control(request:Request,_:User=Depends(admin_user),db:Session=Depends(get_db)):
    row=db.query(SiteAccessSetting).filter(SiteAccessSetting.key==_SITE_ACCESS_KEY).first()
    return _admin_access_control_payload(row,request)


@app.put("/api/admin/access-control")
def admin_save_access_control(body:AdminAccessControlIn,request:Request,admin:User=Depends(admin_user),db:Session=Depends(get_db)):
    mode=str(body.mode or ACCESS_MODE_ALLOW_ALL)
    try:
        allowed_ips=normalize_access_rules(body.allowed_ips)
    except AccessRuleError as exc:
        raise HTTPException(400,str(exc))
    client_ip=_request_client_ip(request)
    if mode==ACCESS_MODE_ALLOWLIST:
        if not allowed_ips:
            raise HTTPException(400,"허용 IP만 접속 모드에서는 IP 또는 CIDR을 1개 이상 등록해야 합니다.")
        if not access_allowed(mode,client_ip,allowed_ips,allow_loopback=True):
            raise HTTPException(
                400,
                f"현재 접속 IP {client_ip or '확인 불가'}가 허용 목록에 없습니다. 현재 IP를 추가한 뒤 저장해주세요.",
            )
    row=db.query(SiteAccessSetting).filter(SiteAccessSetting.key==_SITE_ACCESS_KEY).first()
    if not row:
        row=SiteAccessSetting(key=_SITE_ACCESS_KEY)
        db.add(row)
    row.mode=mode
    row.allowed_ips_json=json.dumps(allowed_ips,ensure_ascii=False)
    row.updated_by_user_id=admin.id
    row.updated_at=datetime.now()
    commit_or_rollback(db);db.refresh(row)
    _set_site_access_cache(mode=mode,allowed_ips=allowed_ips,updated_at=row.updated_at)
    logger.info(
        "site access policy updated admin_id=%s mode=%s rule_count=%s client_ip=%s",
        admin.id,mode,len(allowed_ips),client_ip or "unknown",
    )
    return {**_admin_access_control_payload(row,request),"message":"접속 IP 설정을 저장했습니다."}


@app.get("/api/admin/social-auth")
def admin_social_auth_settings(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    return {
        provider:{"label":info["label"],**_social_public_config(_social_config(db,provider))}
        for provider,info in SOCIAL_PROVIDERS.items()
    }


@app.put("/api/admin/social-auth/{provider}")
def admin_save_social_auth(provider:str,body:SocialAuthSettingsIn,admin:User=Depends(admin_user),db:Session=Depends(get_db)):
    provider,info=_social_provider(provider)
    redirect_uri=str(body.redirect_uri or "").strip()
    parsed=urlparse(redirect_uri)
    if parsed.scheme not in {"http","https"} or not parsed.netloc:
        raise HTTPException(422,"Redirect URI는 http:// 또는 https://로 시작하는 전체 주소를 입력해주세요.")
    row=_social_config(db,provider)
    if not row:
        row=SocialAuthProviderConfig(provider=provider)
        db.add(row);flush_or_rollback(db)
    current_id,current_secret=_social_config_values(row)
    current_redirect=str(row.redirect_uri or "").strip()
    client_id=str(body.client_id or "").strip() or current_id
    client_secret=str(body.client_secret or "").strip() or current_secret
    if not client_id:
        raise HTTPException(422,f"{info['label']} Client ID를 입력해주세요.")
    if provider in {"naver","google"} and not client_secret:
        raise HTTPException(422,f"{info['label']} Client Secret을 입력해주세요.")
    credentials_changed=(
        client_id!=current_id
        or client_secret!=current_secret
        or redirect_uri!=current_redirect
    )
    row.client_id_enc=encrypt_secret(client_id)
    row.client_secret_enc=encrypt_secret(client_secret) if client_secret else ""
    row.redirect_uri=redirect_uri
    row.is_enabled=bool(body.enabled)
    row.updated_by_user_id=admin.id
    if credentials_changed:
        # A key/secret/redirect change invalidates the previous end-to-end result.
        row.last_test_status="untested"
        row.last_test_message="설정을 저장했습니다. 실제 OAuth 연결 테스트를 진행해주세요."
        row.last_tested_at=None
    commit_or_rollback(db);db.refresh(row)
    return {"ok":True,"message":f"{info['label']} 로그인 설정을 암호화하여 저장했습니다.","settings":_social_public_config(row)}


@app.delete("/api/admin/social-auth/{provider}")
def admin_delete_social_auth(provider:str,_:User=Depends(admin_user),db:Session=Depends(get_db)):
    provider,info=_social_provider(provider)
    row=_social_config(db,provider)
    if row:
        db.delete(row);commit_or_rollback(db)
    return {"ok":True,"message":f"{info['label']} 로그인 설정을 삭제했습니다."}


@app.get("/api/admin/social-auth/{provider}/test/start")
def admin_social_auth_test_start(provider:str,request:Request,return_url:str=Query(...,max_length=700),admin:User=Depends(admin_user),db:Session=Depends(get_db)):
    provider,info=_social_provider(provider)
    config=_social_config(db,provider)
    public=_social_public_config(config)
    if not config or not public["configured"]:
        raise HTTPException(409,f"{info['label']} Client ID/Secret/Redirect URI를 먼저 저장해주세요.")
    safe_return=_social_safe_return_url(request,return_url)
    flow=_new_social_session(db,provider,"test",safe_return,admin.id)
    return {"authorization_url":_social_authorization_url(provider,config,flow.state),"message":f"{info['label']} 실제 OAuth 연결 테스트를 시작합니다."}


@app.get("/api/admin/social-auth/test-result/{session_id}")
def admin_social_auth_test_result(session_id:str,admin:User=Depends(admin_user),db:Session=Depends(get_db)):
    flow=db.query(SocialAuthSession).filter(SocialAuthSession.state==session_id,SocialAuthSession.mode=="test",SocialAuthSession.initiated_by_user_id==admin.id).first()
    if not flow:
        raise HTTPException(404,"연결 테스트 결과를 찾을 수 없습니다.")
    if flow.expires_at<datetime.now() and flow.status=="pending":
        flow.status="test_failed";flow.error_message="연결 테스트가 만료되었습니다.";commit_or_rollback(db)
    ok=flow.status=="test_success"
    if flow.status=="pending":
        raise HTTPException(409,"연결 테스트가 아직 완료되지 않았습니다.")
    message=(f"{SOCIAL_PROVIDERS[flow.provider]['label']} OAuth 연결 테스트에 성공했습니다." if ok else (flow.error_message or "연결 테스트에 실패했습니다."))
    return {"ok":ok,"provider":flow.provider,"status":flow.status,"message":message}


@app.get("/api/admin/users")
def admin_users(
    page:int=Query(1,ge=1),
    page_size:int=Query(20,ge=10,le=100),
    q:str=Query("",max_length=80),
    account_type:str=Query("all"),
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    """Server-side account search/pagination for large member bases."""
    query=db.query(User)
    keyword=str(q or "").strip()
    if keyword:
        like=f"%{keyword}%"
        query=query.filter(
            or_(
                User.username.ilike(like),
                User.display_name.ilike(like),
            )
        )

    kind=str(account_type or "all").lower().strip()
    tier_map={
        "normal":"NORMAL","member":"NORMAL",
        "premium":"PREMIUM",
        "event":"EVENT","test":"EVENT",
        "admin":"ADMIN",
    }
    if kind in tier_map:
        wanted=tier_map[kind]
        if wanted=="ADMIN":
            query=query.filter(or_(User.membership_tier=="ADMIN",User.is_admin==True))
        elif wanted=="EVENT":
            query=query.filter(User.is_admin==False,or_(User.membership_tier=="EVENT",User.is_test_account==True))
        else:
            query=query.filter(User.is_admin==False,User.membership_tier==wanted)

    total=query.count()
    pages=max(1,math.ceil(total/page_size))
    safe_page=min(page,pages)
    rows=(
        query.order_by(User.id.desc())
        .offset((safe_page-1)*page_size)
        .limit(page_size)
        .all()
    )

    # One usage query per page instead of one query per account. This keeps the
    # admin browser predictable even when the member table grows very large.
    today=_ai_usage_today()
    user_ids=[row.id for row in rows]
    usage_by_user={}
    if user_ids:
        usage_by_user={
            usage.user_id:int(usage.ai_queries or 0)
            for usage in (
                db.query(AiDailyUsage)
                .filter(
                    AiDailyUsage.user_id.in_(user_ids),
                    AiDailyUsage.usage_date==today,
                )
                .all()
            )
        }

    def page_usage(row):
        daily_limit=_ai_limit_for(row,db)
        unlimited=daily_limit<0
        used=usage_by_user.get(row.id,0)
        return {
            "unlimited":unlimited,
            "daily_limit":None if unlimited else daily_limit,
            "used":used,
            "remaining":None if unlimited else max(0,daily_limit-used),
            "usage_date":today.isoformat(),
            "resets_at":_ai_usage_reset_at().isoformat(),
            "account_type":user_tier(row).lower(),
        }

    return {
        "items":[
            {
                **user_json(row),
                "is_active":bool(row.is_active),
                "created_at":row.created_at.isoformat() if row.created_at else None,
                "ai_usage":page_usage(row),
            }
            for row in rows
        ],
        "page":safe_page,
        "page_size":page_size,
        "pages":pages,
        "total":total,
        "query":keyword,
        "account_type":kind,
        "tier_counts":{
            "NORMAL":db.query(User).filter(User.is_admin==False,User.membership_tier=="NORMAL").count(),
            "PREMIUM":db.query(User).filter(User.is_admin==False,User.membership_tier=="PREMIUM").count(),
            "EVENT":db.query(User).filter(User.is_admin==False,or_(User.membership_tier=="EVENT",User.is_test_account==True)).count(),
            "ADMIN":db.query(User).filter(or_(User.membership_tier=="ADMIN",User.is_admin==True)).count(),
        },
    }


def _admin_mask_account_no(value:str):
    digits=re.sub(r"\D","",str(value or ""))
    if not digits:
        return ""
    if len(digits)<=4:
        return "*"*len(digits)
    return f"{digits[:3]}{'*'*max(3,len(digits)-7)}{digits[-4:]}"


def _admin_holding_payload(item):
    if not isinstance(item,dict):
        return None
    qty=float(item.get("quantity") or 0)
    avg=float(item.get("avg_price") or 0)
    current=float(item.get("current_price") or item.get("price") or 0)
    purchase=float(item.get("purchase_amount") or (qty*avg))
    evaluation=float(item.get("evaluation_amount") or (qty*current))
    pnl=float(item.get("profit_loss") or (evaluation-purchase))
    rate=item.get("return_rate")
    try:
        rate=float(rate)
    except Exception:
        rate=(pnl/purchase*100.0) if purchase else 0.0
    return {
        "code":str(item.get("code") or item.get("stock_code") or ""),
        "name":str(item.get("name") or item.get("stock_name") or item.get("code") or ""),
        "market":str(item.get("market") or ""),
        "sector":str(item.get("sector") or ""),
        "portfolio_category":str(item.get("portfolio_category") or ""),
        "quantity":qty,
        "avg_price":avg,
        "current_price":current,
        "purchase_amount":purchase,
        "evaluation_amount":evaluation,
        "profit_loss":pnl,
        "return_rate":rate,
    }


@app.get("/api/admin/users/{user_id}/detail")
def admin_user_detail(
    user_id:int,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    """Read one member's account-scoped operational summary without triggering broker API calls."""
    target=db.query(User).filter(User.id==user_id).first()
    if not target:
        raise HTTPException(404,"계정을 찾을 수 없습니다.")

    now=datetime.now(ZoneInfo("Asia/Seoul"))
    profile_row=db.query(InvestmentProfile).filter(InvestmentProfile.user_id==target.id).first()
    profile=_investment_profile_payload(profile_row)
    if profile is not None:
        try:
            answers=json.loads(profile_row.answers_json or "[]")
        except Exception:
            answers=[]
        profile["answers_count"]=len(answers) if isinstance(answers,list) else 0
        profile["updated_at"]=profile_row.updated_at.isoformat() if profile_row.updated_at else None

    social_rows=(
        db.query(SocialAccount)
        .filter(SocialAccount.user_id==target.id)
        .order_by(SocialAccount.updated_at.desc())
        .all()
    )
    social_accounts=[{
        "provider":row.provider,
        "email":row.email or "",
        "nickname":row.nickname or "",
        "last_login_at":row.last_login_at.isoformat() if row.last_login_at else None,
        "connected_at":row.created_at.isoformat() if row.created_at else None,
    } for row in social_rows]

    credential=db.query(KiwoomCredential).filter(KiwoomCredential.user_id==target.id).first()
    snapshot=db.query(KiwoomAccountSnapshot).filter(KiwoomAccountSnapshot.user_id==target.id).first()
    portfolio=None
    if snapshot:
        payload=_snapshot_to_payload(snapshot) or {}
        payload=_enrich_portfolio_holdings(payload,db)
        holdings=[]
        for item in payload.get("holdings") or []:
            normalized=_admin_holding_payload(item)
            if normalized and normalized["code"]:
                holdings.append(normalized)
        holdings.sort(key=lambda x:x["evaluation_amount"],reverse=True)
        summary=payload.get("summary") or {}
        portfolio={
            "connected":bool(credential),
            "account_no_masked":_admin_mask_account_no(snapshot.account_no or (credential.account_no if credential else "")),
            "summary":{
                "total_asset":float(summary.get("total_asset") or 0),
                "cash":float(summary.get("cash") or 0),
                "buying_power":float(summary.get("buying_power") or 0),
                "purchase_amount":float(summary.get("purchase_amount") or 0),
                "evaluation_amount":float(summary.get("evaluation_amount") or 0),
                "profit_loss":float(summary.get("profit_loss") or 0),
                "return_rate":float(summary.get("return_rate") or 0),
                "holding_count":len(holdings),
            },
            "holdings":holdings,
            "last_success_at":snapshot.last_success_at.isoformat() if snapshot.last_success_at else None,
            "updated_at":snapshot.updated_at.isoformat() if snapshot.updated_at else None,
        }
    else:
        portfolio={
            "connected":bool(credential),
            "account_no_masked":_admin_mask_account_no(credential.account_no if credential else ""),
            "summary":{"total_asset":0,"cash":0,"buying_power":0,"purchase_amount":0,"evaluation_amount":0,"profit_loss":0,"return_rate":0,"holding_count":0},
            "holdings":[],
            "last_success_at":None,
            "updated_at":None,
        }

    recent_orders=(
        db.query(OrderAudit)
        .filter(OrderAudit.user_id==target.id)
        .order_by(OrderAudit.id.desc())
        .limit(20)
        .all()
    )
    total_orders=db.query(OrderAudit).filter(OrderAudit.user_id==target.id).count()
    buy_orders=db.query(OrderAudit).filter(OrderAudit.user_id==target.id,OrderAudit.side=="buy").count()
    sell_orders=db.query(OrderAudit).filter(OrderAudit.user_id==target.id,OrderAudit.side=="sell").count()
    order_codes={str(row.stock_code or "") for row in recent_orders if row.stock_code}
    order_name_map={row.code:row.name for row in db.query(Stock).filter(Stock.code.in_(order_codes)).all()} if order_codes else {}
    order_items=[{
        "id":row.id,
        "side":row.side,
        "stock_code":row.stock_code,
        "stock_name":order_name_map.get(str(row.stock_code or ""),str(row.stock_code or "")),
        "quantity":row.quantity,
        "order_type":row.order_type,
        "price":row.price,
        "status":row.status,
        "broker_order_no":row.broker_order_no or "",
        "created_at":row.created_at.isoformat() if row.created_at else None,
    } for row in recent_orders]

    reservation_rows=(
        db.query(TradeReservation)
        .filter(TradeReservation.user_id==target.id)
        .order_by(TradeReservation.id.desc())
        .limit(12)
        .all()
    )
    reservation_total=db.query(TradeReservation).filter(TradeReservation.user_id==target.id).count()
    reservation_active=db.query(TradeReservation).filter(TradeReservation.user_id==target.id,TradeReservation.status.in_(["active","executing"])).count()
    reservation_items=[{
        "id":row.id,
        "stock_code":row.stock_code,
        "stock_name":row.stock_name or row.stock_code,
        "side":row.side,
        "quantity":row.quantity,
        "trigger_operator":row.trigger_operator,
        "trigger_price":row.trigger_price,
        "order_type":row.order_type,
        "order_price":row.order_price,
        "status":row.status,
        "created_at":row.created_at.isoformat() if row.created_at else None,
    } for row in reservation_rows]

    usage_rows=(
        db.query(AiDailyUsage)
        .filter(AiDailyUsage.user_id==target.id)
        .order_by(AiDailyUsage.usage_date.asc())
        .all()
    )
    usage_map={row.usage_date:int(row.ai_queries or 0) for row in usage_rows}
    today=now.date()
    ai_14=[]
    for offset in range(13,-1,-1):
        d=today-timedelta(days=offset)
        ai_14.append({"date":d.isoformat(),"queries":usage_map.get(d,0)})
    thirty_start=today-timedelta(days=29)
    ai_30=sum(v for d,v in usage_map.items() if d>=thirty_start)
    ai_total=sum(usage_map.values())

    consents=(
        db.query(UserConsent)
        .filter(UserConsent.user_id==target.id)
        .order_by(UserConsent.agreed_at.desc())
        .all()
    )
    consent_items=[{
        "type":row.consent_type,
        "policy_version":row.policy_version,
        "agreed_at":row.agreed_at.isoformat() if row.agreed_at else None,
    } for row in consents]

    formula=db.query(SmartFormula).filter(SmartFormula.user_id==target.id).first()
    smart_formula=None
    if formula:
        smart_formula={
            "per_max":formula.per_max,"pbr_max":formula.pbr_max,"roe_min":formula.roe_min,
            "revenue_growth_min":formula.revenue_growth_min,"operating_margin_min":formula.operating_margin_min,
            "dividend_yield_min":formula.dividend_yield_min,"momentum_20d_min":formula.momentum_20d_min,
            "market_cap_min":formula.market_cap_min,
            "updated_at":formula.updated_at.isoformat() if formula.updated_at else None,
        }

    created_at=target.created_at
    signup_method="social" if social_accounts else "local"
    return {
        "user":{
            **user_json(target,db),
            "is_active":bool(target.is_active),
            "created_at":created_at.isoformat() if created_at else None,
            "signup_method":signup_method,
            "days_since_signup":max(0,(now.replace(tzinfo=None)-created_at).days) if created_at else None,
        },
        "investment_profile":profile,
        "portfolio":portfolio,
        "trading":{
            "total_orders":total_orders,
            "buy_orders":buy_orders,
            "sell_orders":sell_orders,
            "recent_orders":order_items,
            "reservation_total":reservation_total,
            "reservation_active":reservation_active,
            "recent_reservations":reservation_items,
        },
        "ai_usage":{
            "today":_ai_usage_status(target,db),
            "last_30_days":ai_30,
            "total":ai_total,
            "history_14_days":ai_14,
        },
        "connections":{
            "social_accounts":social_accounts,
            "kiwoom":{
                "configured":bool(credential),
                "mock":bool(credential.use_mock) if credential else True,
                "account_no_masked":_admin_mask_account_no(credential.account_no if credential else ""),
                "last_connected_at":credential.last_connected_at.isoformat() if credential and credential.last_connected_at else None,
                "updated_at":credential.updated_at.isoformat() if credential and credential.updated_at else None,
            },
        },
        "consents":consent_items,
        "smart_formula":smart_formula,
    }


@app.get("/api/membership/me")
def membership_me(u:User=Depends(current_user),db:Session=Depends(get_db)):
    return {
        "tier":user_tier(u),
        "label":TIER_LABELS.get(user_tier(u),user_tier(u)),
        "features":resolved_features(db,u),
        "ai_usage":_ai_usage_status(u,db),
    }


@app.get("/api/membership/refresh-policy")
def membership_refresh_policy(u:User=Depends(current_user),db:Session=Depends(get_db)):
    return refresh_policy_for_tier(db,user_tier(u))


@app.get("/api/admin/membership/refresh-policy")
def admin_membership_refresh_policy(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    return refresh_policy_matrix(db)


@app.put("/api/admin/membership/refresh-policy")
def admin_update_membership_refresh_policy(
    body:MembershipRefreshPolicyUpdateIn,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    ensure_default_refresh_policies(db)
    changed=0
    for item in body.items:
        tier=str(item.tier).upper()
        if tier not in TIERS:
            raise HTTPException(422,"지원하지 않는 회원 등급입니다.")
        trading=int(item.trading_seconds)
        theme=int(item.theme_seconds)
        # 0 disables automatic refresh. Non-zero values are clamped to a safe
        # minimum so one browser tab cannot hammer account/theme endpoints.
        if 0<trading<10 or 0<theme<10:
            raise HTTPException(422,"자동 새로고침은 0(사용 안 함) 또는 10초 이상으로 설정해주세요.")
        row=(db.query(MembershipRefreshPolicy).filter(MembershipRefreshPolicy.tier==tier).first())
        if not row:
            row=MembershipRefreshPolicy(tier=tier)
            db.add(row)
        row.trading_seconds=trading
        row.theme_seconds=theme
        row.updated_at=datetime.now()
        changed+=1
    commit_or_rollback(db)
    return {"ok":True,"changed":changed,"policy":refresh_policy_matrix(db)}


@app.get("/api/admin/membership/features")
def admin_membership_features(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    return policy_matrix(db)


@app.put("/api/admin/membership/features")
def admin_update_membership_features(
    body:MembershipFeaturePolicyUpdateIn,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    ensure_default_policies(db)
    changed=0
    for item in body.items:
        tier=str(item.tier).upper()
        key=str(item.feature_key)
        if tier not in TIERS or key not in MEMBERSHIP_FEATURES:
            raise HTTPException(422,"알 수 없는 회원 등급 또는 기능입니다.")
        if tier=="ADMIN":
            # Administrator access is intentionally non-configurable to prevent lockout.
            continue
        if key=="portfolio_ai_momentum" and tier=="NORMAL":
            # Portfolio auto-AI is a premium-and-above product entitlement.
            row=(db.query(MembershipFeaturePolicy).filter(
                MembershipFeaturePolicy.tier==tier,
                MembershipFeaturePolicy.feature_key==key,
            ).first())
            if not row:
                row=MembershipFeaturePolicy(tier=tier,feature_key=key)
                db.add(row)
            row.enabled=False;row.limit_value=None;row.updated_at=datetime.now();changed+=1
            continue
        row=(db.query(MembershipFeaturePolicy).filter(
            MembershipFeaturePolicy.tier==tier,
            MembershipFeaturePolicy.feature_key==key,
        ).first())
        if not row:
            row=MembershipFeaturePolicy(tier=tier,feature_key=key)
            db.add(row)
        row.enabled=bool(item.enabled)
        if key=="ai_analysis":
            row.limit_value=int(item.limit_value if item.limit_value is not None else AI_DAILY_FREE_LIMIT)
        else:
            row.limit_value=None
        row.updated_at=datetime.now()
        changed+=1
    commit_or_rollback(db)
    return {"ok":True,"changed":changed,"policy":policy_matrix(db)}


@app.patch("/api/admin/users/{user_id}/membership")
def admin_set_membership(
    user_id:int,
    body:AdminMembershipTierIn,
    admin:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    target=db.query(User).filter(User.id==user_id).first()
    if not target:
        raise HTTPException(404,"계정을 찾을 수 없습니다.")
    tier=str(body.membership_tier).upper()
    if tier not in TIERS:
        raise HTTPException(422,"지원하지 않는 회원 등급입니다.")
    current=user_tier(target)
    admin_count=(
        db.query(User).filter(or_(User.is_admin==True,User.membership_tier=="ADMIN")).count()
        if current=="ADMIN" and tier!="ADMIN" else 2
    )
    guard_error=membership_change_error(
        acting_admin_id=admin.id,target_user_id=target.id,current_tier=current,
        next_tier=tier,admin_count=admin_count,
    )
    if guard_error:
        raise HTTPException(400,guard_error)
    set_user_tier(target,tier)
    commit_or_rollback(db);db.refresh(target)
    return {
        "ok":True,
        "message":f"{target.display_name or target.username} 회원을 {TIER_LABELS[tier]} 등급으로 변경했습니다.",
        "user":{**user_json(target,db),"ai_usage":_ai_usage_status(target,db)},
    }


@app.put("/api/admin/users/{user_id}/password")
def admin_change_user_password(
    user_id:int,
    body:AdminUserPasswordIn,
    admin:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    target=db.query(User).filter(User.id==user_id).first()
    if not target:
        raise HTTPException(404,"계정을 찾을 수 없습니다.")
    try:
        new_password=validate_admin_password(body.new_password,target.username)
    except AccountSecurityError as exc:
        raise HTTPException(400,str(exc))
    if verify_password(new_password,target.password_hash):
        raise HTTPException(400,"현재 비밀번호와 다른 새 비밀번호를 입력해주세요.")

    target.password_hash=hash_password(new_password)
    target.auth_version=max(0,int(getattr(target,"auth_version",0) or 0))+1
    commit_or_rollback(db);db.refresh(target)
    is_self=target.id==admin.id
    replacement_token=create_access_token(target.username,target.auth_version) if is_self else None
    logger.info(
        "admin changed account password admin_id=%s target_user_id=%s target_is_admin=%s sessions_revoked=true",
        admin.id,target.id,user_tier(target)=="ADMIN",
    )
    return {
        "ok":True,
        "message":f"{target.display_name or target.username} 계정의 비밀번호를 변경했습니다. 기존 로그인은 모두 종료됩니다.",
        "sessions_revoked":True,
        "current_session_token":replacement_token,
    }


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(
    user_id:int,
    admin:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    """Permanently remove a member and their account-scoped data.

    Shared market/AI cache data is intentionally retained because it is not
    owned by one user. Provider mappings are removed so the same social account
    can sign up again later.
    """
    target=db.query(User).filter(User.id==user_id).first()
    if not target:
        raise HTTPException(404,"계정을 찾을 수 없습니다.")
    if target.id==admin.id:
        raise HTTPException(400,"현재 로그인한 관리자 본인 계정은 탈퇴시킬 수 없습니다.")
    if user_tier(target)=="ADMIN":
        admin_count=db.query(User).filter(or_(User.is_admin==True,User.membership_tier=="ADMIN")).count()
        if admin_count<=1:
            raise HTTPException(400,"최소 1명의 관리자 계정은 유지되어야 합니다.")

    target_label=target.display_name or target.username
    try:
        # SET NULL audit/config references that should survive account deletion.
        db.query(SocialAuthProviderConfig).filter(SocialAuthProviderConfig.updated_by_user_id==target.id).update({SocialAuthProviderConfig.updated_by_user_id:None},synchronize_session=False)
        db.query(SocialAuthSession).filter(SocialAuthSession.initiated_by_user_id==target.id).update({SocialAuthSession.initiated_by_user_id:None},synchronize_session=False)
        db.query(SocialAuthSession).filter(SocialAuthSession.user_id==target.id).update({SocialAuthSession.user_id:None},synchronize_session=False)

        # Explicit deletes keep behavior correct even on older MySQL schemas that
        # may have been created before ON DELETE CASCADE was added.
        for model in (
            SocialAccount,UserConsent,AiDailyUsage,AiAnalysisAccess,KiwoomCredential,KiwoomLiveCredential,
            LiveOrderAudit,LiveAutoTradingDecision,LiveAutoTradingPosition,LiveAutoTradingSetting,LiveAutoTradingCycle,KiwoomLiveAccountSnapshot,
            OrderAudit,InvestmentProfile,TradeReservation,AutoTradingDecision,AutoTradingPosition,AutoTradingSetting,KiwoomAccountSnapshot,SmartFormula,
            OverseasPaperOrder,OverseasPaperPosition,OverseasPaperAccount,
        ):
            db.query(model).filter(model.user_id==target.id).delete(synchronize_session=False)
        db.delete(target)
        commit_or_rollback(db)
    except Exception:
        db.rollback()
        logger.exception("admin user delete failed target_user_id=%s admin_user_id=%s",user_id,admin.id)
        raise HTTPException(500,"회원 탈퇴 처리 중 오류가 발생했습니다. 서버 로그를 확인해주세요.")
    return {"ok":True,"message":f"{target_label} 회원을 탈퇴 처리했습니다."}


@app.patch("/api/admin/users/{user_id}/test-account")
def admin_set_test_account(
    user_id:int,
    body:AdminTestAccountIn,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    target=db.query(User).filter(User.id==user_id).first()
    if not target:
        raise HTTPException(404,"계정을 찾을 수 없습니다.")
    # Legacy compatibility endpoint only. Never let an older client bypass the
    # membership endpoint's administrator-safety rules by demoting an admin.
    if user_tier(target)=="ADMIN":
        raise HTTPException(400,"관리자 계정의 등급은 회원 등급 관리 기능에서만 변경할 수 있습니다.")

    set_user_tier(target,"EVENT" if body.is_test_account else "NORMAL")
    commit_or_rollback(db)
    db.refresh(target)
    return {
        "ok":True,
        "message":(
            f"{target.display_name or target.username} 계정을 이벤트회원으로 설정했습니다."
            if user_tier(target)=="EVENT"
            else f"{target.display_name or target.username} 계정을 일반회원으로 변경했습니다."
        ),
        "user":{
            **user_json(target,db),
            "ai_usage":_ai_usage_status(target,db),
        },
    }

@app.get("/api/trading/connection")
@app.get("/api/kiwoom/settings")
def kiwoom_settings(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"kiwoom_settings")
    c=db.query(KiwoomCredential).filter(KiwoomCredential.user_id==u.id).first()
    return _settings_json(c)

@app.put("/api/trading/connection")
@app.put("/api/kiwoom/settings")
async def save_kiwoom(
    body:KiwoomSettingsIn,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"kiwoom_settings")
    """
    사용자는 App Key / Secret Key만 입력합니다.

    저장 흐름:
    1) 키 암호화 저장
    2) 키움 모의투자 토큰 발급
    3) ka00001로 현재 토큰의 계좌번호 자동 조회
    4) 첫 번째 계좌번호를 사용자 DB에 자동 저장
    """
    if not body.use_mock:
        raise HTTPException(
            400,
            "현재 StockLog UI에서는 안전을 위해 모의투자만 저장할 수 있습니다.",
        )

    c = (
        db.query(KiwoomCredential)
        .filter(KiwoomCredential.user_id == u.id)
        .first()
    )

    if not c:
        c = KiwoomCredential(
            user_id=u.id,
            app_key_enc="",
            secret_key_enc="",
            account_no="",
            use_mock=True,
        )
        db.add(c)

    new_app_key = (body.app_key or "").strip()
    new_secret_key = (body.secret_key or "").strip()

    # 입력하지 않으면 기존 키 유지
    if new_app_key:
        c.app_key_enc = encrypt_secret(new_app_key)
    elif not c.app_key_enc:
        raise HTTPException(400, "App Key를 입력해주세요.")

    if new_secret_key:
        c.secret_key_enc = encrypt_secret(new_secret_key)
    elif not c.secret_key_enc:
        raise HTTPException(400, "Secret Key를 입력해주세요.")

    c.use_mock = True
    commit_or_rollback(db)
    db.refresh(c)

    app_key = decrypt_secret(c.app_key_enc)
    secret_key = decrypt_secret(c.secret_key_enc)
    # db.refresh() above starts a new SELECT transaction; release it before
    # token/account network calls.
    commit_or_rollback(db)

    # 키 변경 후 기존 클라이언트/토큰 캐시는 무효화
    _kiwoom_client_cache.pop(u.id, None)

    cli = KiwoomRestClient(
        app_key,
        secret_key,
        True,
    )

    try:
        await cli.issue_token()
        accounts = await cli.account_numbers()

        if not accounts:
            raise HTTPException(
                502,
                "App Key/Secret Key는 저장됐지만 키움에서 모의투자 계좌번호를 반환하지 않았습니다. "
                "키움 REST API 모의투자 신청 상태를 확인해주세요.",
            )

        c.account_no = accounts[0]
        c.last_connected_at = datetime.now()
        commit_or_rollback(db)
        db.refresh(c)
        commit_or_rollback(db)

        # 방금 발급한 토큰을 이후 잔고/주문에서도 재사용
        _kiwoom_client_cache[u.id] = {
            "client": cli,
            "app_key": app_key,
            "secret_key": secret_key,
        }

        return {
            "ok": True,
            "message": "키 저장과 모의투자 계좌번호 자동 등록이 완료되었습니다.",
            "accounts": accounts,
            "account_no": c.account_no,
            "settings": _settings_json(c),
        }

    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)

        if "429" in msg:
            raise HTTPException(
                429,
                "App Key/Secret Key는 DB에 저장됐지만 키움 호출 제한(HTTP 429) 때문에 "
                "계좌번호 자동 조회를 완료하지 못했습니다. 잠시 후 '계좌 다시 찾기'를 눌러주세요.",
            )

        raise HTTPException(
            502,
            f"App Key/Secret Key는 저장됐지만 모의투자 계좌번호 자동 조회에 실패했습니다: {e}",
        )


def client_for(u,db):
    c = (
        db.query(KiwoomCredential)
        .filter(KiwoomCredential.user_id == u.id)
        .first()
    )

    if not c:
        raise HTTPException(
            400,
            "키움 모의투자 설정을 먼저 저장하세요.",
        )

    app_key = decrypt_secret(c.app_key_enc) if c.app_key_enc else ""
    secret_key = decrypt_secret(c.secret_key_enc) if c.secret_key_enc else ""

    if not app_key or not secret_key:
        raise HTTPException(
            400,
            "저장된 키움 App Key 또는 Secret Key가 비어 있습니다. "
            "키움 설정 페이지에서 다시 저장해주세요.",
        )

    cached = _kiwoom_client_cache.get(u.id)
    if (
        cached
        and cached.get("app_key") == app_key
        and cached.get("secret_key") == secret_key
    ):
        cli = cached["client"]
    else:
        cli = KiwoomRestClient(app_key, secret_key, True)
        _kiwoom_client_cache[u.id] = {
            "client": cli,
            "app_key": app_key,
            "secret_key": secret_key,
        }

    return c, cli

@app.post("/api/trading/connection/test")
@app.post("/api/kiwoom/connect")
async def connect_kiwoom(
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"kiwoom_settings")
    c,cli = client_for(u,db)
    # Connection test is network-bound; finish feature/credential reads first.
    commit_or_rollback(db)

    try:
        # issue_token() is cache-aware and also refreshes near-expiry tokens.
        token = await cli.issue_token()

        accounts = await cli.account_numbers()

        if not accounts:
            raise HTTPException(
                502,
                "키움에서 모의투자 계좌번호를 반환하지 않았습니다. "
                "REST API 모의투자 신청 상태를 확인해주세요.",
            )

        # 사용자가 입력하지 않음. 항상 API 결과로 자동 저장.
        c.account_no = accounts[0]
        c.last_connected_at = datetime.now()
        commit_or_rollback(db)
        db.refresh(c)

        return {
            "ok": True,
            "message": "모의투자 계좌번호를 자동으로 확인해 DB에 저장했습니다.",
            "accounts": accounts,
            "account_no": c.account_no,
            "expires_dt": token.get("expires_dt"),
            "settings": _settings_json(c),
        }

    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)

        if "429" in msg:
            raise HTTPException(
                429,
                "키움 모의투자 API 호출이 너무 잦아 일시적으로 제한되었습니다(HTTP 429). "
                "잠시 후 다시 계좌 확인을 시도해주세요.",
            )

        raise HTTPException(
            502,
            f"키움 모의투자 연결 실패: {e}",
        )


def live_client_for(u:User,db:Session):
    c=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==u.id).first()
    if not c:
        raise HTTPException(400,"키움 실전투자 연결 정보를 먼저 저장해주세요.")
    app_key=decrypt_secret(c.app_key_enc) if c.app_key_enc else ""
    secret_key=decrypt_secret(c.secret_key_enc) if c.secret_key_enc else ""
    if not app_key or not secret_key:
        raise HTTPException(400,"저장된 실전투자 App Key 또는 Secret Key가 비어 있습니다.")
    cached=_live_kiwoom_client_cache.get(u.id)
    if cached and cached.get("app_key")==app_key and cached.get("secret_key")==secret_key:
        cli=cached["client"]
    else:
        cli=KiwoomRestClient(app_key,secret_key,False)
        _live_kiwoom_client_cache[u.id]={"client":cli,"app_key":app_key,"secret_key":secret_key}
    if cli.use_mock:
        raise HTTPException(500,"실전투자 클라이언트 환경 검증에 실패했습니다.")
    return c,cli


@app.get("/api/live-trading/connection")
def live_kiwoom_settings(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"kiwoom_settings")
    _require_feature(u,db,"live_trading")
    row=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==u.id).first()
    return _live_settings_json(row)


@app.put("/api/live-trading/connection")
async def save_live_kiwoom(body:KiwoomSettingsIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"kiwoom_settings")
    _require_feature(u,db,"live_trading")
    if body.use_mock:
        raise HTTPException(400,"실전투자 연결에는 실전용 키만 저장할 수 있습니다.")
    row=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==u.id).first()
    if not row:
        row=KiwoomLiveCredential(user_id=u.id,app_key_enc="",secret_key_enc="",account_no="",trading_enabled=False)
        db.add(row)
    new_app=(body.app_key or "").strip()
    new_secret=(body.secret_key or "").strip()
    credentials_changed=bool(new_app or new_secret)
    if new_app:row.app_key_enc=encrypt_secret(new_app)
    elif not row.app_key_enc:raise HTTPException(400,"실전용 App Key를 입력해주세요.")
    if new_secret:row.secret_key_enc=encrypt_secret(new_secret)
    elif not row.secret_key_enc:raise HTTPException(400,"실전용 Secret Key를 입력해주세요.")
    if credentials_changed:
        row.trading_enabled=False
        row.activated_at=None
        row.account_no=""
    commit_or_rollback(db);db.refresh(row)
    app_key=decrypt_secret(row.app_key_enc);secret_key=decrypt_secret(row.secret_key_enc)
    commit_or_rollback(db)
    _live_kiwoom_client_cache.pop(u.id,None)
    cli=KiwoomRestClient(app_key,secret_key,False)
    try:
        token=await cli.issue_token()
        accounts=await cli.account_numbers()
        if not accounts:
            raise HTTPException(502,"키움에서 실전 계좌번호를 반환하지 않았습니다. 실전 REST API 사용 신청 상태를 확인해주세요.")
        row.account_no=accounts[0]
        row.last_connected_at=datetime.now()
        commit_or_rollback(db);db.refresh(row);commit_or_rollback(db)
        _live_kiwoom_client_cache[u.id]={"client":cli,"app_key":app_key,"secret_key":secret_key}
        return {"ok":True,"message":"실전용 키와 실계좌 연결을 확인했습니다. 주문 기능은 별도로 활성화해야 합니다.",
                "accounts":accounts,"account_no":row.account_no,"expires_dt":token.get("expires_dt"),"settings":_live_settings_json(row)}
    except HTTPException:raise
    except Exception as exc:
        if "429" in str(exc):
            raise HTTPException(429,"실전용 키는 저장했지만 키움 호출 제한으로 계좌 확인을 완료하지 못했습니다.") from exc
        raise HTTPException(502,f"실전용 키는 저장했지만 실계좌 확인에 실패했습니다: {exc}") from exc


@app.post("/api/live-trading/connection/test")
async def test_live_kiwoom(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"kiwoom_settings");_require_feature(u,db,"live_trading")
    row,cli=live_client_for(u,db);commit_or_rollback(db)
    try:
        token=await cli.issue_token();accounts=await cli.account_numbers()
        if not accounts:raise HTTPException(502,"키움에서 연결 가능한 실계좌를 반환하지 않았습니다.")
        row.account_no=accounts[0];row.last_connected_at=datetime.now()
        commit_or_rollback(db);db.refresh(row)
        return {"ok":True,"message":"실전 인증 서버와 실계좌 연결을 확인했습니다. 주문은 전송하지 않았습니다.",
                "accounts":accounts,"account_no":row.account_no,"expires_dt":token.get("expires_dt"),"settings":_live_settings_json(row)}
    except HTTPException:raise
    except Exception as exc:
        raise HTTPException(502,f"키움 실전 계좌 연결 확인에 실패했습니다: {exc}") from exc


@app.put("/api/live-trading/activation")
def set_live_trading_activation(body:LiveTradingActivationIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    row=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==u.id).first()
    if not row or not row.account_no or not row.last_connected_at:
        raise HTTPException(400,"실전 계좌 연결 테스트를 먼저 완료해주세요.")
    required=LIVE_ACTIVATION_TEXT if body.enabled else LIVE_DEACTIVATION_TEXT
    try:require_confirmation(body.confirmation_text,required)
    except LiveTradingSafetyError as exc:raise HTTPException(400,str(exc)) from exc
    row.trading_enabled=bool(body.enabled);row.activated_at=datetime.now() if body.enabled else None
    if not body.enabled:
        auto=db.query(LiveAutoTradingSetting).filter(LiveAutoTradingSetting.user_id==u.id).first()
        if auto:auto.enabled=False;auto.next_cycle_at=None;auto.last_message="실전 주문 기능이 비활성화되어 자동매매를 중지했습니다."
    commit_or_rollback(db);db.refresh(row)
    return {"ok":True,"message":"실전 주문 기능을 활성화했습니다." if body.enabled else "실전 주문 기능을 비활성화했습니다.","settings":_live_settings_json(row)}


def _account_lock(user_id: int):
    lock = _account_sync_locks.get(user_id)
    if not lock:
        lock = asyncio.Lock()
        _account_sync_locks[user_id] = lock
    return lock


def _snapshot_to_payload(snapshot: KiwoomAccountSnapshot | None):
    if not snapshot:
        return None

    try:
        holdings = json.loads(snapshot.holdings_json or "[]")
    except Exception:
        holdings = []

    try:
        orders = json.loads(snapshot.orders_json or "[]")
    except Exception:
        orders = []

    try:
        diagnostics = json.loads(snapshot.diagnostics_json or "{}")
    except Exception:
        diagnostics = {}

    return {
        "account_no": snapshot.account_no,
        "summary": {
            "total_asset": snapshot.total_asset,
            "cash": snapshot.cash,
            "buying_power": snapshot.buying_power,
            "buying_power_available": bool(
                diagnostics
                .get("summary_sources", {})
                .get("buying_power", {})
                .get("available")
            ),
            "purchase_amount": snapshot.purchase_amount,
            "evaluation_amount": snapshot.evaluation_amount,
            "profit_loss": snapshot.profit_loss,
            "return_rate": snapshot.return_rate,
        },
        "holdings": holdings,
        "orders": orders,
        "diagnostics": diagnostics,
        "_meta": {
            "cached": True,
            "source": "kiwoom-mock",
            "last_success_at": (
                snapshot.last_success_at.isoformat()
                if snapshot.last_success_at
                else None
            ),
        },
    }


def _save_snapshot(
    user_id: int,
    account_no: str,
    payload: dict,
    db: Session,
):
    snap = (
        db.query(KiwoomAccountSnapshot)
        .filter(
            KiwoomAccountSnapshot.user_id == user_id
        )
        .first()
    )

    if not snap:
        snap = KiwoomAccountSnapshot(
            user_id=user_id,
        )
        db.add(snap)

    summary = payload.get("summary", {})

    snap.account_no = account_no or payload.get("account_no", "")
    snap.cash = float(summary.get("cash") or 0)
    snap.buying_power = float(summary.get("buying_power") or 0)
    snap.total_asset = float(summary.get("total_asset") or 0)
    snap.purchase_amount = float(summary.get("purchase_amount") or 0)
    snap.evaluation_amount = float(summary.get("evaluation_amount") or 0)
    snap.profit_loss = float(summary.get("profit_loss") or 0)
    snap.return_rate = float(summary.get("return_rate") or 0)
    snap.holdings_json = json.dumps(
        payload.get("holdings", []),
        ensure_ascii=False,
    )
    snap.orders_json = json.dumps(
        payload.get("orders", []),
        ensure_ascii=False,
    )
    snap.diagnostics_json = json.dumps(
        payload.get("diagnostics", {}),
        ensure_ascii=False,
    )
    snap.last_success_at = datetime.now()

    commit_or_rollback(db)
    db.refresh(snap)

    return snap


async def _sync_kiwoom_account(
    u: User,
    db: Session,
    force: bool = False,
):
    c, cli = client_for(u, db)
    attempted_at = datetime.now()
    # client_for() performs a credential SELECT. Do not pin that connection
    # while Kiwoom token/account HTTP requests are in flight.
    commit_or_rollback(db)

    if not c.account_no:
        await cli.issue_token()

        accounts = await cli.account_numbers()

        if not accounts:
            raise HTTPException(
                502,
                "키움 모의투자 계좌번호를 찾지 못했습니다.",
            )

        c.account_no = accounts[0]
        c.last_connected_at = datetime.now()
        commit_or_rollback(db)
        db.refresh(c)

    min_interval = float(
        os.getenv(
            "KIWOOM_ACCOUNT_SYNC_MIN_INTERVAL_SECONDS",
            "20",
        )
    )

    snap = (
        db.query(KiwoomAccountSnapshot)
        .filter(
            KiwoomAccountSnapshot.user_id == u.id
        )
        .first()
    )

    cached_payload=(
        _snapshot_to_payload(snap)
        if snap
        else None
    )

    buying_power_resolved=bool(
        cached_payload
        and cached_payload.get("summary", {})
        .get("buying_power_available")
    )

    if (
        not force
        and snap
        and snap.last_success_at
        and buying_power_resolved
        and (
            datetime.now() - snap.last_success_at
        ).total_seconds() < min_interval
    ):
        payload = cached_payload
        payload["_meta"]["message"] = (
            f"키움 호출 제한 방지를 위해 {int(min_interval)}초 이내에는 "
            "최근 동기화 결과를 표시합니다."
        )
        payload["_meta"]["attempted_at"] = attempted_at.isoformat()
        payload["_meta"]["forced"] = False
        # Snapshot SELECT is finished; callers may perform other async work.
        commit_or_rollback(db)
        return payload

    lock = _account_lock(u.id)

    async with lock:
        # 강제 동기화는 과거 snapshot을 먼저 삭제합니다.
        # 실패해도 이전 snapshot으로 fallback하지 않습니다.
        if force:
            (
                db.query(KiwoomAccountSnapshot)
                .filter(
                    KiwoomAccountSnapshot.user_id == u.id
                )
                .delete(synchronize_session=False)
            )
            commit_or_rollback(db)
            snap = None
        else:
            snap = (
                db.query(KiwoomAccountSnapshot)
                .filter(
                    KiwoomAccountSnapshot.user_id == u.id
                )
                .first()
            )

            cached_payload=(
                _snapshot_to_payload(snap)
                if snap
                else None
            )

            buying_power_resolved=bool(
                cached_payload
                and cached_payload.get("summary", {})
                .get("buying_power_available")
            )

            if (
                snap
                and snap.last_success_at
                and buying_power_resolved
                and (
                    datetime.now() - snap.last_success_at
                ).total_seconds() < min_interval
            ):
                payload = cached_payload
                payload["_meta"]["attempted_at"] = attempted_at.isoformat()
                payload["_meta"]["forced"] = False
                commit_or_rollback(db)
                return payload

        # All cache/credential reads above are complete. Release the SELECT
        # transaction before the potentially slow Kiwoom account synchronization.
        commit_or_rollback(db)
        try:
            payload = await cli.sync_account(
                c.account_no
            )
        except Exception as e:
            msg = str(e)

            # 일반 조회만 마지막 성공 snapshot fallback 허용.
            if not force and snap:
                cached = _snapshot_to_payload(snap)
                cached["_meta"]["sync_error"] = msg
                cached["_meta"]["attempted_at"] = attempted_at.isoformat()
                cached["_meta"]["forced"] = False
                cached["_meta"]["message"] = (
                    "키움 실시간 동기화에 실패해 마지막 성공 데이터를 표시합니다."
                )
                return cached

            if "429" in msg:
                raise HTTPException(
                    429,
                    "키움 모의투자 API 호출 제한(HTTP 429)입니다. "
                    "강제 동기화에서는 과거 캐시를 사용하지 않습니다. "
                    "잠시 후 다시 시도해주세요.",
                )

            raise HTTPException(
                502,
                "키움 모의계좌 강제 동기화 실패: "
                f"{e}. 과거 snapshot은 표시하지 않습니다.",
            )

        # Reconcile the fresh Kiwoom snapshot before persisting it so every
        # consumer (manual trading, auto trading, portfolio, admin) sees the
        # same valuation/account totals.  This prevents the dedicated
        # Portfolio page from showing corrected numbers while other pages keep
        # stale/raw TR mixtures.
        payload = _portfolio_apply_live_metrics(payload, db)

        snap = _save_snapshot(
            u.id,
            c.account_no,
            payload,
            db,
        )

        result = _snapshot_to_payload(snap)
        result["_meta"]["cached"] = False
        result["_meta"]["forced"] = force
        result["_meta"]["attempted_at"] = attempted_at.isoformat()
        result["_meta"]["last_success_at"] = snap.last_success_at.isoformat()
        result["_meta"]["message"] = (
            "키움 모의계좌에서 최신 계좌정보를 강제로 다시 동기화했습니다."
            if force
            else "키움 모의계좌에서 계좌정보를 다시 동기화했습니다."
        )

        return result


def _live_snapshot_to_payload(snapshot:KiwoomLiveAccountSnapshot|None):
    if not snapshot:return None
    try:holdings=json.loads(snapshot.holdings_json or "[]")
    except Exception:holdings=[]
    try:orders=json.loads(snapshot.orders_json or "[]")
    except Exception:orders=[]
    try:diagnostics=json.loads(snapshot.diagnostics_json or "{}")
    except Exception:diagnostics={}
    return {
        "account_no":snapshot.account_no,
        "summary":{
            "total_asset":snapshot.total_asset,"cash":snapshot.cash,"buying_power":snapshot.buying_power,
            "buying_power_available":bool((diagnostics.get("summary_sources",{}).get("buying_power",{}) or {}).get("available")),
            "purchase_amount":snapshot.purchase_amount,"evaluation_amount":snapshot.evaluation_amount,
            "profit_loss":snapshot.profit_loss,"return_rate":snapshot.return_rate,
        },
        "holdings":holdings,"orders":orders,"diagnostics":diagnostics,
        "_meta":{"cached":True,"source":"kiwoom-live","environment":"live",
                 "last_success_at":snapshot.last_success_at.isoformat() if snapshot.last_success_at else None},
    }


def _save_live_snapshot(user_id:int,account_no:str,payload:dict,db:Session):
    snap=db.query(KiwoomLiveAccountSnapshot).filter(KiwoomLiveAccountSnapshot.user_id==user_id).first()
    if not snap:
        snap=KiwoomLiveAccountSnapshot(user_id=user_id);db.add(snap)
    summary=payload.get("summary") or {}
    snap.account_no=account_no or payload.get("account_no") or ""
    snap.cash=float(summary.get("cash") or 0);snap.buying_power=float(summary.get("buying_power") or 0)
    snap.total_asset=float(summary.get("total_asset") or 0);snap.purchase_amount=float(summary.get("purchase_amount") or 0)
    snap.evaluation_amount=float(summary.get("evaluation_amount") or 0);snap.profit_loss=float(summary.get("profit_loss") or 0)
    snap.return_rate=float(summary.get("return_rate") or 0)
    snap.holdings_json=json.dumps(payload.get("holdings") or [],ensure_ascii=False)
    snap.orders_json=json.dumps(payload.get("orders") or [],ensure_ascii=False)
    snap.diagnostics_json=json.dumps(payload.get("diagnostics") or {},ensure_ascii=False)
    snap.last_success_at=datetime.now();commit_or_rollback(db);db.refresh(snap)
    return snap


async def _sync_live_kiwoom_account(u:User,db:Session,force:bool=False):
    cred,cli=live_client_for(u,db)
    attempted_at=datetime.now();commit_or_rollback(db)
    if not cred.account_no:
        await cli.issue_token();accounts=await cli.account_numbers()
        if not accounts:raise HTTPException(502,"키움 실계좌 번호를 찾지 못했습니다.")
        cred.account_no=accounts[0];cred.last_connected_at=datetime.now();commit_or_rollback(db);db.refresh(cred)
    min_interval=float(os.getenv("KIWOOM_LIVE_ACCOUNT_SYNC_MIN_INTERVAL_SECONDS","20"))
    snap=db.query(KiwoomLiveAccountSnapshot).filter(KiwoomLiveAccountSnapshot.user_id==u.id).first()
    if not force and snap and snap.last_success_at and (datetime.now()-snap.last_success_at).total_seconds()<min_interval:
        result=_live_snapshot_to_payload(snap);result["_meta"].update({"attempted_at":attempted_at.isoformat(),"forced":False,
            "message":f"실전 API 호출 보호를 위해 {int(min_interval)}초 이내에는 최근 확인 결과를 표시합니다."})
        commit_or_rollback(db);return result
    lock=_live_account_sync_locks.setdefault(u.id,asyncio.Lock())
    async with lock:
        snap=db.query(KiwoomLiveAccountSnapshot).filter(KiwoomLiveAccountSnapshot.user_id==u.id).first()
        if not force and snap and snap.last_success_at and (datetime.now()-snap.last_success_at).total_seconds()<min_interval:
            result=_live_snapshot_to_payload(snap);result["_meta"].update({"attempted_at":attempted_at.isoformat(),"forced":False})
            commit_or_rollback(db);return result
        commit_or_rollback(db)
        try:
            payload=await cli.sync_account(cred.account_no)
        except Exception as exc:
            if not force and snap:
                result=_live_snapshot_to_payload(snap);result["_meta"].update({"sync_error":str(exc),"attempted_at":attempted_at.isoformat(),
                    "forced":False,"message":"실계좌 동기화가 잠시 실패해 마지막 성공 데이터를 표시합니다."})
                return result
            if "429" in str(exc):raise HTTPException(429,"키움 실전 API 호출 제한입니다. 잠시 후 다시 시도해주세요.") from exc
            raise HTTPException(502,f"키움 실계좌 동기화 실패: {exc}") from exc
        payload=_portfolio_apply_live_metrics(payload,db)
        snap=_save_live_snapshot(u.id,cred.account_no,payload,db)
        result=_live_snapshot_to_payload(snap);result["_meta"].update({"cached":False,"forced":force,
            "attempted_at":attempted_at.isoformat(),"message":"키움 실계좌에서 최신 계좌정보를 확인했습니다."})
        return result


def _normalize_domestic_stock_code(value):
    code=str(value or "").strip()
    if code.startswith("A") and len(code)==7 and code[1:].isdigit():
        code=code[1:]
    return code if re.fullmatch(r"\d{6}",code) else ""


def _ws_number(value, *, absolute=False):
    if value in (None,"","-","--"):
        return 0.0
    try:
        number=float(str(value).replace(",","").replace("%","").strip())
        return abs(number) if absolute else number
    except Exception:
        return 0.0


def _kiwoom_realtime_ticks(payload):
    """Normalize Kiwoom domestic stock-trade REAL 0B packets."""
    if not isinstance(payload,dict):
        return []
    data=payload.get("data")
    if isinstance(data,dict):
        data=[data]
    if not isinstance(data,list):
        return []
    ticks=[]
    for item in data:
        if not isinstance(item,dict) or str(item.get("type") or "").upper()!="0B":
            continue
        code=_normalize_domestic_stock_code(item.get("item") or item.get("code"))
        values=item.get("values")
        if not code or not isinstance(values,dict):
            continue
        current=_ws_number(values.get("10"),absolute=True)
        if current<=0:
            continue
        ticks.append({
            "code":code,
            "current_price":current,
            "change":_ws_number(values.get("11")),
            "change_rate":_ws_number(values.get("12")),
            "trade_quantity":abs(_ws_number(values.get("15"))),
            "volume":abs(_ws_number(values.get("13"))),
            "trade_time":str(values.get("20") or ""),
        })
    return ticks


async def _kiwoom_ws_recv(ws):
    while True:
        raw=await ws.recv()
        if isinstance(raw,bytes):
            raw=raw.decode("utf-8",errors="replace")
        try:
            payload=json.loads(raw)
        except Exception:
            payload=raw
        is_ping=(
            isinstance(payload,str) and payload.strip().upper()=="PING"
        ) or (
            isinstance(payload,dict) and str(payload.get("trnm") or "").upper()=="PING"
        )
        if is_ping:
            await ws.send(raw if isinstance(raw,str) else json.dumps(payload,ensure_ascii=False))
            continue
        return payload


async def _portfolio_ws_auth(browser_ws:WebSocket):
    allowed,client_ip,_policy=_site_access_result(browser_ws)
    if not allowed:
        await browser_ws.accept()
        await browser_ws.send_json({
            "type":"error","code":"ip_not_allowed","client_ip":client_ip or "확인 불가",
            "message":"이 IP는 StockLog 접속 허용 목록에 포함되어 있지 않습니다.",
        })
        await browser_ws.close(code=4403)
        return None,None
    await browser_ws.accept()
    try:
        raw=await asyncio.wait_for(browser_ws.receive_text(),timeout=7)
        packet=json.loads(raw)
    except Exception:
        await browser_ws.send_json({"type":"error","message":"실시간 연결 인증 패킷을 확인하지 못했습니다."})
        await browser_ws.close(code=4401)
        return None,None
    if not isinstance(packet,dict) or packet.get("type")!="auth":
        await browser_ws.send_json({"type":"error","message":"실시간 연결 인증 형식이 올바르지 않습니다."})
        await browser_ws.close(code=4401)
        return None,None
    claims=decode_token_claims(str(packet.get("token") or ""))
    if not claims:
        await browser_ws.send_json({"type":"error","message":"로그인 정보가 만료되었습니다."})
        await browser_ws.close(code=4401)
        return None,None
    username,token_auth_version=claims
    db=SessionLocal()
    user=db.query(User).filter(User.username==username,User.is_active==True).first()
    if not user:
        db.close()
        await browser_ws.send_json({"type":"error","message":"사용자를 찾을 수 없습니다."})
        await browser_ws.close(code=4401)
        return None,None
    if int(getattr(user,"auth_version",0) or 0)!=int(token_auth_version):
        db.close()
        await browser_ws.send_json({"type":"error","message":"비밀번호가 변경되어 다시 로그인해야 합니다."})
        await browser_ws.close(code=4401)
        return None,None
    return user,db


@app.websocket("/ws/trading/portfolio-live")
@app.websocket("/ws/kiwoom/portfolio-live")
async def kiwoom_portfolio_live(browser_ws:WebSocket):
    """Proxy actual Kiwoom REAL 0B ticks for the user's current holdings."""
    user,db=await _portfolio_ws_auth(browser_ws)
    if not user:
        return
    upstream=None
    try:
        environment=str(browser_ws.query_params.get("environment") or "mock").strip().lower()
        is_live=environment=="live"
        credential_model=KiwoomLiveCredential if is_live else KiwoomCredential
        snapshot_model=KiwoomLiveAccountSnapshot if is_live else KiwoomAccountSnapshot
        cred=db.query(credential_model).filter(credential_model.user_id==user.id).first()
        if not cred or not cred.app_key_enc or not cred.secret_key_enc:
            await browser_ws.send_json({"type":"error","message":f"키움 {'실전' if is_live else '모의'} App Key / Secret Key 설정이 필요합니다."})
            return
        snap=db.query(snapshot_model).filter(snapshot_model.user_id==user.id).first()
        if not snap:
            await browser_ws.send_json({"type":"error","message":"먼저 키움 계좌 동기화를 한 번 실행해주세요."})
            return
        try:
            holdings=json.loads(snap.holdings_json or "[]")
        except Exception:
            holdings=[]
        codes=[]
        for h in holdings:
            if not isinstance(h,dict):
                continue
            code=_normalize_domestic_stock_code(h.get("code") or h.get("stock_code"))
            qty=_ws_number(h.get("quantity"),absolute=True)
            if code and qty>0:
                codes.append(code)
        codes=list(dict.fromkeys(codes))
        truncated=len(codes)>200
        codes=codes[:200]
        if not codes:
            # An idle websocket can also live indefinitely; return the DB
            # connection before entering its heartbeat loop.
            commit_or_rollback(db)
            db.close()
            db=None
            await browser_ws.send_json({"type":"status","state":"idle","source":"kiwoom-0B","subscribed":0,"message":"현재 보유종목이 없어 실시간 시세 구독을 대기합니다."})
            while True:
                await asyncio.sleep(20)
                await browser_ws.send_json({"type":"heartbeat","at":datetime.now().isoformat()})
        # Reuse the same per-user Kiwoom client/token as REST requests. Creating
        # a fresh OAuth client for every browser websocket causes unnecessary
        # token issuance and can race with long-running REST sync work.
        _,cli=live_client_for(user,db) if is_live else client_for(user,db)
        use_mock=bool(cli.use_mock)
        # A websocket can live for hours. Never keep its authentication/holding
        # SELECT transaction checked out for the lifetime of the connection.
        commit_or_rollback(db)
        db.close()
        db=None
        await cli.issue_token()
        ws_host="wss://mockapi.kiwoom.com:10000" if use_mock else "wss://api.kiwoom.com:10000"
        upstream=await websocket_connect(
            ws_host+"/api/dostk/websocket",
            open_timeout=15,
            close_timeout=5,
            ping_interval=None,
        )
        await upstream.send(json.dumps({"trnm":"LOGIN","token":cli.token},ensure_ascii=False))
        deadline=time.monotonic()+12
        while True:
            reply=await asyncio.wait_for(_kiwoom_ws_recv(upstream),timeout=max(.1,deadline-time.monotonic()))
            if isinstance(reply,dict) and str(reply.get("trnm") or "").upper()=="LOGIN":
                rc=int(reply.get("return_code") or 0)
                if rc!=0:
                    raise RuntimeError("키움 실시간 LOGIN 실패: "+str(reply.get("return_msg") or rc))
                break
        await upstream.send(json.dumps({
            "trnm":"REG",
            "grp_no":"1",
            "refresh":"1",
            "data":[{"item":codes,"type":["0B"]}],
        },ensure_ascii=False))
        await browser_ws.send_json({
            "type":"status","state":"live","source":"kiwoom-0B",
            "subscribed":len(codes),"truncated":truncated,
            "message":f"키움 주식체결(0B) 실시간 연결 · {len(codes)}종목 구독",
        })
        while True:
            try:
                payload=await asyncio.wait_for(_kiwoom_ws_recv(upstream),timeout=25)
            except asyncio.TimeoutError:
                await browser_ws.send_json({"type":"heartbeat","state":"live","at":datetime.now().isoformat()})
                continue
            if isinstance(payload,dict) and str(payload.get("trnm") or "").upper()=="REG" and int(payload.get("return_code") or 0)!=0:
                raise RuntimeError("키움 실시간 종목 등록 실패: "+str(payload.get("return_msg") or payload.get("return_code")))
            ticks=_kiwoom_realtime_ticks(payload)
            if ticks:
                await browser_ws.send_json({"type":"tick_batch","source":"kiwoom-0B","ticks":ticks,"received_at":datetime.now().isoformat()})
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    except Exception as exc:
        try:
            await browser_ws.send_json({"type":"error","message":f"키움 실시간 시세 연결 오류: {type(exc).__name__}: {exc}"})
        except Exception:
            pass
    finally:
        try:
            if upstream is not None:
                await upstream.close()
        except Exception:
            pass
        try:
            if db is not None:
                db.close()
        except Exception:
            pass
        try:
            await browser_ws.close()
        except Exception:
            pass


def _enrich_portfolio_holdings(
    payload: dict,
    db: Session,
):
    """Attach StockLog classification metadata to actual Kiwoom holdings."""
    holdings=payload.get("holdings")
    if not isinstance(holdings,list) or not holdings:
        return payload

    codes=[]
    for holding in holdings:
        if not isinstance(holding,dict):
            continue
        code=str(
            holding.get("code")
            or holding.get("stock_code")
            or ""
        ).strip()
        if re.fullmatch(r"\d{6}",code):
            codes.append(code)

    codes=list(dict.fromkeys(codes))
    if not codes:
        return payload

    stocks={
        row.code:row
        for row in (
            db.query(Stock)
            .filter(Stock.code.in_(codes))
            .all()
        )
    }

    theme_map=_theme_map_for_codes(
        db,
        codes,
        limit=3,
    )

    for holding in holdings:
        if not isinstance(holding,dict):
            continue

        code=str(
            holding.get("code")
            or holding.get("stock_code")
            or ""
        ).strip()
        stock=stocks.get(code)
        if not stock:
            holding["portfolio_category"]=(
                holding.get("portfolio_category")
                or "기타"
            )
            continue

        themes=theme_map.get(code,[])
        market_theme=next(
            (
                item
                for item in themes
                if item.get("source")
                == "infostock"
            ),
            None,
        )
        representative=(
            market_theme
            or (themes[0] if themes else None)
        )

        if representative and representative.get("name"):
            category=representative["name"]
            category_source="theme"
        elif stock.industry_name:
            category=stock.industry_name
            category_source="industry"
        elif _meaningful_sector(stock):
            category=_meaningful_sector(stock)
            category_source="sector"
        elif _stock_name_business_hint(stock):
            category=_stock_name_business_hint(stock)
            category_source="name_hint"
        else:
            category="기타 사업"
            category_source="other"

        holding.update({
            "name":holding.get("name") or stock.name,
            "market":stock.market,
            "sector":stock.sector,
            "industry_name":stock.industry_name,
            "industry_source":stock.industry_source,
            "category":stock.category,
            "themes":themes,
            "theme_fallback":_stock_theme_fallback(stock),
            "portfolio_category":category,
            "portfolio_category_source":category_source,
        })

    return payload


@app.get("/api/live-trading/portfolio")
async def live_portfolio(force:bool=Query(False),u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    payload=await _sync_live_kiwoom_account(u,db,force=force)
    payload=_enrich_portfolio_holdings(payload,db)
    payload=_portfolio_apply_live_metrics(payload,db)
    broker_orders=payload.get("orders") or []
    if broker_orders:
        audits=(db.query(LiveOrderAudit).filter(LiveOrderAudit.user_id==u.id)
                .order_by(LiveOrderAudit.id.desc()).limit(300).all())
        sides={str(x.broker_order_no or "").strip():("매수" if x.side=="buy" else "매도")
               for x in audits if str(x.broker_order_no or "").strip()}
        for item in broker_orders:
            if isinstance(item,dict) and str(item.get("order_no") or "").strip() in sides:
                item["side"]=sides[str(item.get("order_no") or "").strip()]
    payload["environment"]="live"
    return payload


@app.get("/api/live-trading/buying-power")
async def live_kiwoom_buying_power(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    snap=db.query(KiwoomLiveAccountSnapshot).filter(KiwoomLiveAccountSnapshot.user_id==u.id).first()
    try:
        _,cli=live_client_for(u,db);commit_or_rollback(db)
        result=await cli.current_buying_power();observed_at=datetime.now(ZoneInfo("Asia/Seoul"))
        if snap:
            try:diagnostics=json.loads(snap.diagnostics_json or "{}")
            except Exception:diagnostics={}
            diagnostics.setdefault("summary_sources",{})["buying_power"]={
                "tr":result.get("api_id") or "","field":result.get("field") or "",
                "value":round(float(result.get("amount") or 0),2),"available":True,
                "dedicated_tr_success":bool(result.get("api_id")=="kt00001"),"live_checked_at":observed_at.isoformat(),
            }
            snap.buying_power=float(result.get("amount") or 0)
            if result.get("cash_field"):snap.cash=float(result.get("cash") or 0)
            snap.diagnostics_json=json.dumps(diagnostics,ensure_ascii=False);commit_or_rollback(db)
        return {"available":True,"amount":round(float(result.get("amount") or 0),2),
                "cash":round(float(result.get("cash") or 0),2),"source":result.get("api_id") or "",
                "field":result.get("field") or "","stale":bool(result.get("stale")),
                "observed_at":observed_at.isoformat(),"message":"키움 실계좌에서 주문가능금액을 확인했습니다."}
    except Exception as exc:
        if snap:
            try:diagnostics=json.loads(snap.diagnostics_json or "{}")
            except Exception:diagnostics={}
            source=diagnostics.get("summary_sources",{}).get("buying_power",{}) or {}
            if source.get("available"):
                return {"available":True,"amount":round(float(snap.buying_power or 0),2),"cash":round(float(snap.cash or 0),2),
                        "source":source.get("tr") or "snapshot","field":source.get("field") or "","stale":True,
                        "observed_at":source.get("live_checked_at"),"message":"실시간 조회 실패로 마지막 실계좌 확인 금액을 표시합니다."}
        if "429" in str(exc):raise HTTPException(429,"키움 실전 주문가능금액 조회가 일시적으로 제한되었습니다.") from exc
        raise HTTPException(502,"키움 실계좌 주문가능금액을 확인하지 못했습니다.") from exc


def _live_order_reference_price(db:Session,user_id:int,stock_code:str,price:float|None):
    if price and float(price)>0:return float(price)
    snap=db.query(KiwoomLiveAccountSnapshot).filter(KiwoomLiveAccountSnapshot.user_id==user_id).first()
    if snap:
        try:
            for item in json.loads(snap.holdings_json or "[]"):
                if isinstance(item,dict) and str(item.get("code") or item.get("stock_code") or "").strip()==stock_code:
                    found=float(item.get("current_price") or item.get("price") or 0)
                    if found>0:return found
        except Exception:pass
    stock=db.query(Stock).filter(Stock.code==stock_code).first()
    return float(stock.price or 0) if stock else 0.0


async def _submit_stocklog_live_order(*,db:Session,user:User,side:str,stock_code:str,quantity:int,
                                      order_type:str,price:float|None,exchange:str="KRX",source:str="manual"):
    if side not in ("buy","sell"):raise HTTPException(400,"매수/매도 구분이 올바르지 않습니다.")
    if order_type not in ("market","limit"):raise HTTPException(400,"시장가 또는 지정가 주문만 지원합니다.")
    if exchange not in ("KRX","NXT","SOR"):raise HTTPException(400,"실전 주문 거래소는 KRX, NXT, SOR만 선택할 수 있습니다.")
    if order_type=="limit" and (price is None or float(price)<=0):raise HTTPException(400,"지정가 주문 가격을 입력해주세요.")
    if side=="buy" and not _stocklog_public_stock(db,stock_code):
        raise HTTPException(400,"StockLog 분석 대상인 KOSPI·KOSDAQ 일반 상장종목만 새로 매수할 수 있습니다.")
    cred,cli=live_client_for(user,db)
    if not cred.trading_enabled:raise HTTPException(403,"실전 주문 기능이 잠겨 있습니다. 계정 연동에서 먼저 활성화해주세요.")
    reference=_live_order_reference_price(db,user.id,stock_code,price)
    max_amount=max(10000,float(os.getenv("STOCKLOG_LIVE_MAX_ORDER_AMOUNT","5000000") or 5000000))
    snap=db.query(KiwoomLiveAccountSnapshot).filter(KiwoomLiveAccountSnapshot.user_id==user.id).first()
    snapshot=_live_snapshot_to_payload(snap) or {"summary":{},"holdings":[]}
    available=float((snapshot.get("summary") or {}).get("buying_power") or 0)
    holding=next((x for x in snapshot.get("holdings") or [] if str(x.get("code") or x.get("stock_code") or "").strip()==stock_code),None)
    held=max(0,int(float((holding or {}).get("quantity") or 0)))
    try:
        validate_live_order_limits(side=side,quantity=quantity,reference_price=reference,max_order_amount=max_amount,
                                   buying_power=available,held_quantity=held)
    except LiveTradingSafetyError as exc:
        status=409 if "최신 가격" in str(exc) else 422
        raise HTTPException(status,str(exc)) from exc
    commit_or_rollback(db)
    try:
        data=await cli.order(side,stock_code,quantity,order_type,price,exchange)
    except Exception as exc:
        db.add(LiveOrderAudit(user_id=user.id,source=source,side=side,stock_code=stock_code,quantity=quantity,
                              order_type=order_type,price=price,status="failed",raw_response=json.dumps({"error":str(exc)[:1000]},ensure_ascii=False)))
        commit_or_rollback(db);raise
    order_no=str(data.get("ord_no") or data.get("ordNo") or data.get("order_no") or "")
    db.add(LiveOrderAudit(user_id=user.id,source=source,side=side,stock_code=stock_code,quantity=quantity,
                          order_type=order_type,price=price,broker_order_no=order_no,status="accepted",
                          raw_response=json.dumps(data,ensure_ascii=False)))
    commit_or_rollback(db)
    return data,order_no


@app.post("/api/live-trading/order")
async def live_order(body:LiveOrderIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    try:require_confirmation(body.confirmation_text,LIVE_ORDER_TEXT)
    except LiveTradingSafetyError as exc:raise HTTPException(400,str(exc)) from exc
    try:
        data,order_no=await _submit_stocklog_live_order(db=db,user=u,side=body.side,stock_code=body.stock_code,
            quantity=body.quantity,order_type=body.order_type,price=body.price,exchange=body.exchange,source="manual")
        return {"ok":True,"message":"키움 실계좌로 주문을 전송했습니다. 주문번호와 체결 상태를 반드시 확인해주세요.",
                "broker_order_no":order_no,"broker":data}
    except HTTPException:raise
    except Exception as exc:
        if "429" in str(exc):raise HTTPException(429,"키움 실전 주문 호출 제한입니다. 중복 주문하지 말고 잠시 후 주문내역을 확인해주세요.") from exc
        raise HTTPException(502,"키움 실전 주문 전송 결과를 확인하지 못했습니다. 재주문 전에 키움 주문내역을 확인해주세요.") from exc


@app.get("/api/trading/buying-power")
@app.get("/api/kiwoom/buying-power")
async def kiwoom_buying_power(
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    """Lightweight live broker query for cash currently available to buy stocks."""
    snap=(
        db.query(KiwoomAccountSnapshot)
        .filter(KiwoomAccountSnapshot.user_id==u.id)
        .first()
    )
    try:
        _,cli=client_for(u,db)
        # Live broker I/O must not pin the snapshot/credential SELECT transaction.
        commit_or_rollback(db)
        result=await cli.current_buying_power()
        observed_at=datetime.now(ZoneInfo("Asia/Seoul"))

        if snap:
            try:
                diagnostics=json.loads(snap.diagnostics_json or "{}")
            except Exception:
                diagnostics={}
            summary_sources=diagnostics.setdefault("summary_sources",{})
            summary_sources["buying_power"]={
                "tr":result.get("api_id") or "",
                "field":result.get("field") or "",
                "value":round(float(result.get("amount") or 0),2),
                "available":True,
                "semantic_candidates":[],
                "dedicated_tr_success":bool(result.get("api_id") == "kt00001"),
                "live_checked_at":observed_at.isoformat(),
            }
            snap.buying_power=float(result.get("amount") or 0)
            if result.get("cash_field"):
                snap.cash=float(result.get("cash") or 0)
            snap.diagnostics_json=json.dumps(diagnostics,ensure_ascii=False)
            commit_or_rollback(db)

        return {
            "available":True,
            "amount":round(float(result.get("amount") or 0),2),
            "cash":round(float(result.get("cash") or 0),2),
            "source":result.get("api_id") or "",
            "field":result.get("field") or "",
            "stale":bool(result.get("stale")),
            "observed_at":observed_at.isoformat(),
            "message":"키움 모의계좌에서 주문가능금액을 실시간 조회했습니다.",
        }
    except Exception as exc:
        # Never fabricate account money. If a live call fails, only the last
        # broker-confirmed value is allowed as a clearly marked fallback.
        if snap:
            try:
                diagnostics=json.loads(snap.diagnostics_json or "{}")
            except Exception:
                diagnostics={}
            source=(diagnostics.get("summary_sources",{}).get("buying_power",{}) or {})
            if source.get("available"):
                return {
                    "available":True,
                    "amount":round(float(snap.buying_power or 0),2),
                    "cash":round(float(snap.cash or 0),2),
                    "source":source.get("tr") or "snapshot",
                    "field":source.get("field") or "",
                    "stale":True,
                    "observed_at":source.get("live_checked_at") or (
                        snap.last_success_at.isoformat() if snap.last_success_at else None
                    ),
                    "message":"실시간 조회가 잠시 실패해 마지막 키움 확인 금액을 표시합니다.",
                }
        msg=str(exc)
        if "429" in msg:
            raise HTTPException(429,"키움 주문가능금액 조회가 일시적으로 제한되었습니다.") from exc
        raise HTTPException(502,"키움 모의계좌 주문가능금액을 확인하지 못했습니다.") from exc


@app.get("/api/kiwoom/buying-power/status")
def buying_power_status(
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    snap=(
        db.query(
            KiwoomAccountSnapshot
        )
        .filter(
            KiwoomAccountSnapshot.user_id
            == u.id
        )
        .first()
    )

    if not snap:
        return {
            "available":False,
            "message":"계좌 동기화 전입니다.",
        }

    try:
        diagnostics=json.loads(
            snap.diagnostics_json
            or "{}"
        )
    except Exception:
        diagnostics={}

    source=(
        diagnostics
        .get("summary_sources", {})
        .get("buying_power", {})
    )

    return {
        "available":bool(
            source.get(
                "available"
            )
        ),
        "source_found":bool(
            source.get(
                "tr"
            )
            and source.get(
                "field"
            )
        ),
        "dedicated_account_response":bool(
            source.get(
                "dedicated_tr_success"
            )
        ),
        "field_detected":str(
            source.get(
                "field"
            )
            or ""
        ),
        "last_success_at":(
            snap.last_success_at.isoformat()
            if snap.last_success_at
            else None
        ),
        "message":(
            "키움 주문가능금액을 정상 확인했습니다."
            if source.get("available")
            else (
                "키움 주문인출가능금액 응답은 받았지만 "
                "주문가능금액 필드를 아직 확인하지 못했습니다."
                if source.get("dedicated_tr_success")
                else "키움 주문인출가능금액 응답을 아직 받지 못했습니다."
            )
        ),
    }


def _portfolio_apply_live_metrics(payload:dict,db:Session):
    """Normalize the portfolio around Kiwoom's own account semantics.

    - kt00004 ``prsm_dpst_aset_amt`` is the authoritative total account asset.
    - kt00004 ``tot_est_amt`` / current price x quantity is the securities
      market value shown in the portfolio.
    - Per-stock ``pl_amt`` / ``pl_rt`` are Kiwoom P/L values and can include
      mock-trading commissions/taxes. They are intentionally *not* forced to
      equal ``current_price * quantity - purchase_amount``.
    - Today's account P/L uses Kiwoom ``tdy_lspft`` when available. Per-stock
      day movement remains a market-move reference based on previous close.
    """
    holdings=payload.get("holdings") or []
    if not isinstance(holdings,list):
        return payload
    codes=[str(x.get("code") or x.get("stock_code") or "").strip() for x in holdings if isinstance(x,dict)]
    codes=[x for x in dict.fromkeys(codes) if x]
    stocks={x.code:x for x in db.query(Stock).filter(Stock.code.in_(codes)).all()} if codes else {}
    bars_by_code={}
    if codes:
        rows=(db.query(PriceBar).filter(PriceBar.stock_code.in_(codes)).order_by(PriceBar.stock_code.asc(),PriceBar.trade_date.desc()).all())
        for row in rows:
            bucket=bars_by_code.setdefault(str(row.stock_code),[])
            if len(bucket)<2:bucket.append(row)
    today=_auto_trade_now().date()

    # Build today's executed buy/sell quantities from Kiwoom executions.
    # This is critical for same-day positions: a stock that was bought today
    # must not inherit the move from yesterday's close as the user's P/L.
    today_exec_by_code={}
    for order in (payload.get("orders") or []):
        if not isinstance(order,dict):
            continue
        code=str(order.get("code") or order.get("stock_code") or "").strip()
        if not code:
            continue
        qty=max(0.0,float(order.get("filled_qty") or order.get("quantity") or 0))
        if qty<=0:
            continue
        side=str(order.get("side") or "").strip().lower()
        bucket=today_exec_by_code.setdefault(code,{"buy":0.0,"sell":0.0})
        if side in ("매수","buy","b","2"):
            bucket["buy"]+=qty
        elif side in ("매도","sell","s","1"):
            bucket["sell"]+=qty

    market_eval=total_purchase=total_pnl=total_fee=market_day=account_day=prev_value=day_basis_value=0.0
    for holding in holdings:
        if not isinstance(holding,dict):continue
        code=str(holding.get("code") or holding.get("stock_code") or "").strip()
        stock=stocks.get(code)
        qty=max(0.0,float(holding.get("quantity") or 0))
        avg=max(0.0,float(holding.get("avg_price") or 0))
        current=max(0.0,float(holding.get("current_price") or holding.get("price") or 0))
        if current<=0 and stock:current=max(0.0,float(stock.price or 0))
        if current<=0 and avg>0:current=avg

        broker_purchase=max(0.0,float(holding.get("purchase_amount") or 0))
        broker_evaluation=max(0.0,float(holding.get("evaluation_amount") or 0))
        purchase=broker_purchase if broker_purchase>0 else (qty*avg if qty>0 and avg>0 else 0.0)
        # kt00004.evlt_amt is Kiwoom's per-position evaluation amount.  On the
        # mock account it can be lower than current_price*quantity because the
        # broker's account P/L model reflects simulated costs.  Portfolio money
        # must match Kiwoom, so preserve that value as the displayed 평가금액 and
        # keep gross market value separately for allocation/diagnostics.
        market_value=(qty*current) if qty>0 and current>0 else broker_evaluation
        evaluation=broker_evaluation if broker_evaluation>0 else market_value

        broker_pnl=float(holding.get("broker_profit_loss",holding.get("profit_loss") or 0) or 0)
        broker_rate=float(holding.get("broker_return_rate",holding.get("return_rate") or 0) or 0)
        # kt00004 P/L is the broker truth, including mock-account costs.  A
        # positive price move can therefore coexist with a small negative net
        # P/L immediately after a market-order buy.
        pnl=broker_pnl
        rate=broker_rate if abs(broker_rate)>0.000001 else ((pnl/purchase*100.0) if purchase>0 else 0.0)
        # Kiwoom's per-position net P/L includes mock-account trading costs but
        # the holding row does not expose a stable fee field across TR families.
        # Derive the already-reflected cost adjustment from gross market value,
        # purchase principal and broker net P/L. This is display-only and never
        # used for order sizing or risk enforcement.
        explicit_fee=max(0.0,float(holding.get("fee_amount") or holding.get("commission") or holding.get("fee") or 0))
        implied_fee=max(0.0,market_value-purchase-pnl) if market_value>0 and purchase>0 else 0.0
        fee_amount=explicit_fee if explicit_fee>0 else implied_fee
        fee_estimated=bool(explicit_fee<=0 and fee_amount>0)

        prev_close=0.0
        bars=bars_by_code.get(code) or []
        if bars:
            latest=bars[0];raw=str(latest.trade_date or "").replace("-","")
            if raw==today.strftime("%Y%m%d") and len(bars)>1:prev_close=max(0.0,float(bars[1].close or 0))
            else:prev_close=max(0.0,float(latest.close or 0))
        if prev_close<=0 and stock and current>0:
            change=float(stock.change_rate or 0)
            if abs(change)<99.9 and abs(1+change/100.0)>0.0001:prev_close=current/(1+change/100.0)
        if prev_close<=0:prev_close=current
        market_day_profit=(current-prev_close)*qty if current>0 and prev_close>0 else 0.0
        market_day_rate=((current/prev_close)-1)*100.0 if current>0 and prev_close>0 else 0.0

        execs=today_exec_by_code.get(code) or {"buy":0.0,"sell":0.0}
        today_buy=max(0.0,float(execs.get("buy") or 0))
        today_sell=max(0.0,float(execs.get("sell") or 0))
        # current = opening + buys - sells -> opening = current - buys + sells
        opening_qty=max(0.0,qty-today_buy+today_sell)
        acquired_today=bool(today_buy>0 and opening_qty<=0.000001)

        if acquired_today:
            # All currently held shares were opened today.  Kiwoom's net P/L
            # is the correct investor P/L; yesterday-close movement happened
            # before the user owned the shares and must not be counted.
            day_profit=pnl
            day_rate=rate
            day_basis="today_acquired_kiwoom_net"
            basis_amount=purchase
        else:
            # Existing holdings: day P/L means today's price move on shares
            # already carried into the session.  Keep the market move as the
            # best available basis when the mock API does not expose a reliable
            # account-level daily P/L field.
            day_profit=market_day_profit
            day_rate=market_day_rate
            day_basis="previous_close_market_move"
            basis_amount=prev_close*qty if prev_close>0 else purchase

        holding.update({
            "current_price":current,
            "purchase_amount":purchase,
            "evaluation_amount":evaluation,
            "market_value":market_value,
            "broker_evaluation_amount":broker_evaluation,
            "profit_loss":pnl,
            "return_rate":rate,
            "previous_close":prev_close,
            "day_profit":day_profit,
            "day_return_rate":day_rate,
            "day_profit_basis":day_basis,
            "market_day_profit":market_day_profit,
            "market_day_return_rate":market_day_rate,
            "today_buy_quantity":today_buy,
            "today_sell_quantity":today_sell,
            "opening_quantity":opening_qty,
            "pnl_basis":"kiwoom_net",
            "broker_profit_loss":broker_pnl,
            "broker_return_rate":broker_rate,
            "fee_amount":fee_amount,
            "fee_estimated":fee_estimated,
            "profit_loss_after_fee":pnl,
        })
        market_eval+=market_value
        total_purchase+=purchase
        total_pnl+=pnl
        total_fee+=fee_amount
        market_day+=market_day_profit
        account_day+=day_profit
        prev_value+=prev_close*qty
        day_basis_value+=max(0.0,basis_amount)

    summary=payload.setdefault("summary",{})
    if holdings:
        diagnostics=(payload.get("diagnostics") or {}).get("summary_sources") or {}
        broker_market_eval=max(0.0,float((diagnostics.get("evaluation_amount") or {}).get("value") or 0))
        broker_purchase=max(0.0,float((diagnostics.get("purchase_amount") or {}).get("value") or 0))
        explicit_total=max(0.0,float((diagnostics.get("total_asset") or {}).get("value") or summary.get("total_asset") or 0))
        total_field=str((diagnostics.get("total_asset") or {}).get("field") or "")
        broker_day=float((diagnostics.get("day_profit") or {}).get("value") or summary.get("day_profit") or 0)
        broker_day_rate=float((diagnostics.get("day_return_rate") or {}).get("value") or summary.get("day_return_rate") or 0)

        summary["evaluation_amount"]=broker_market_eval if broker_market_eval>0 else market_eval
        summary["purchase_amount"]=broker_purchase if broker_purchase>0 else total_purchase

        # v3.75.17: headline P/L must mirror Kiwoom's kt00004 summary exactly.
        # ``lspft`` / ``lspft_rt`` are the values shown as 총손익 / 총수익률
        # in 영웅문.  Summing each holding's pl_amt can legitimately differ
        # because the account headline includes Kiwoom's cumulative/realized
        # investment P/L semantics.  Only fall back to holding sums when the
        # broker summary field was truly absent.
        pnl_diag=diagnostics.get("profit_loss") or {}
        rate_diag=diagnostics.get("return_rate") or {}
        broker_total_pnl=float(pnl_diag.get("value") or 0)
        broker_total_rate=float(rate_diag.get("value") or 0)
        has_broker_total=bool(pnl_diag.get("field") in ("lspft", "tot_evlt_pl", "tot_pl_amt"))
        has_broker_rate=bool(rate_diag.get("field") in ("lspft_rt", "tot_prft_rt", "tot_pl_rt"))
        summary["profit_loss"]=broker_total_pnl if has_broker_total else total_pnl
        summary["return_rate"]=broker_total_rate if has_broker_rate else ((summary["profit_loss"]/summary["purchase_amount"]*100.0) if summary["purchase_amount"]>0 else 0.0)
        summary["profit_loss_basis"]="kiwoom_kt00004_lspft" if has_broker_total else "holdings_sum_fallback"
        summary["fee_amount"]=total_fee
        summary["profit_loss_after_fee"]=summary["profit_loss"]

        summary["market_day_profit"]=market_day
        summary["market_day_return_rate"]=(market_day/prev_value*100.0) if prev_value>0 else 0.0

        day_diag=diagnostics.get("day_profit") or {}
        day_rate_diag=diagnostics.get("day_return_rate") or {}
        has_broker_day=bool(day_diag.get("field")=="tdy_lspft")
        has_broker_day_rate=bool(day_rate_diag.get("field")=="tdy_lspft_rt")
        summary["broker_day_profit_raw"]=broker_day
        summary["broker_day_return_rate_raw"]=broker_day_rate

        # v3.75.18: On some Kiwoom mock-account responses kt00004 exposes
        # tdy_lspft/tdy_lspft_rt as literal zero even while the currently held
        # positions have a non-zero intraday investment P/L. Zero is therefore
        # not sufficient evidence that today's portfolio P/L is truly zero.
        # Prefer the broker value when it is non-zero; otherwise use the
        # reconciled per-position daily P/L calculated above. This preserves
        # negative days as negative instead of rendering a misleading +0원.
        broker_day_usable=has_broker_day and abs(broker_day)>0.000001
        broker_day_rate_usable=has_broker_day_rate and abs(broker_day_rate)>0.000001
        if broker_day_usable or abs(account_day)<=0.000001:
            final_day_profit=broker_day if has_broker_day else account_day
            final_day_rate=(
                broker_day_rate
                if broker_day_rate_usable
                else ((final_day_profit/day_basis_value*100.0) if day_basis_value>0 else 0.0)
            )
            final_day_basis="kiwoom_kt00004_tdy_lspft" if broker_day_usable else "zero_day"
        else:
            final_day_profit=account_day
            final_day_rate=(account_day/day_basis_value*100.0) if day_basis_value>0 else 0.0
            final_day_basis="holdings_reconciled_zero_broker_fallback"

        summary["day_profit"]=final_day_profit
        summary["day_return_rate"]=final_day_rate
        summary["day_profit_basis"]=final_day_basis
        summary["holding_count"]=len([x for x in holdings if isinstance(x,dict) and float(x.get("quantity") or 0)>0])

        # Never add 'entr' to securities evaluation. Same-day purchases settle
        # later, so doing so double-counts unsettled cash.  Trust Kiwoom's
        # explicit estimated-deposit-assets field when present.
        if explicit_total>0 and total_field in ("prsm_dpst_aset_amt","prsm_dpst_asset_amt"):
            summary["total_asset"]=explicit_total
            summary["total_asset_basis"]="kiwoom_prsm_dpst_aset_amt"
        elif explicit_total>0:
            summary["total_asset"]=explicit_total
            summary["total_asset_basis"]="kiwoom_fallback"
        else:
            # No reliable broker total: don't manufacture a total from unsettled
            # deposit. Expose the securities value only and mark the fallback.
            summary["total_asset"]=summary["evaluation_amount"]
            summary["total_asset_basis"]="securities_only_fallback"
        summary["account_reconciled"]=False
    return payload


@app.get("/api/trading/portfolio")
@app.get("/api/kiwoom/portfolio")
async def portfolio(
    force: bool = Query(False),
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    payload=await _sync_kiwoom_account(
        u,
        db,
        force=force,
    )
    payload=_enrich_portfolio_holdings(
        payload,
        db,
    )
    payload=_portfolio_apply_live_metrics(payload,db)
    _auto_rebuild_positions_from_fills(db,u.id,payload)
    _auto_cap_positions_to_account(db,u.id,payload)

    # v3.75.8: expose how much of each *current* holding belongs to the
    # automatic Gbot ledger.  The broker remains the source of truth for the
    # total quantity; AutoTradingPosition only attributes part of that total
    # to Gbot.  This lets the dedicated portfolio page show manual / Gbot /
    # mixed ownership without changing any order or settlement behavior.
    try:
        holdings_for_source=payload.get("holdings") or []
        source_codes=[
            str(x.get("code") or x.get("stock_code") or "").strip()
            for x in holdings_for_source if isinstance(x,dict)
        ]
        source_codes=[x for x in dict.fromkeys(source_codes) if x]
        auto_rows=(
            db.query(AutoTradingPosition)
            .filter(
                AutoTradingPosition.user_id==u.id,
                AutoTradingPosition.stock_code.in_(source_codes),
            )
            .all()
            if source_codes else []
        )
        # The position table is the fast current ledger, but older StockLog
        # versions did not always backfill it when an automatic order filled.
        # Reconstruct an additional net quantity from the immutable Gbot fill
        # audit so portfolio attribution remains correct for historical buys.
        # We take the larger of the persisted position and reconstructed net
        # quantity, then cap it by the broker's *current* holding below.
        position_qty_map={str(x.stock_code):max(0,int(x.quantity or 0)) for x in auto_rows}
        decision_qty_map={code:0 for code in source_codes}
        decision_cost_map={code:0.0 for code in source_codes}
        latest_auto_buy_map={}
        if source_codes:
            filled_auto_decisions=(
                db.query(AutoTradingDecision)
                .filter(
                    AutoTradingDecision.user_id==u.id,
                    AutoTradingDecision.stock_code.in_(source_codes),
                    AutoTradingDecision.action.in_(["buy","sell"]),
                    AutoTradingDecision.filled_quantity>0,
                )
                .order_by(AutoTradingDecision.id.asc())
                .limit(5000)
                .all()
            )
            for decision in filled_auto_decisions:
                code=str(decision.stock_code or "").strip()
                if not code:
                    continue
                qty=max(0,int(decision.filled_quantity or 0))
                fill_price=max(0.0,float(decision.filled_price or decision.requested_price or 0))
                if decision.action=="buy":
                    decision_qty_map[code]=decision_qty_map.get(code,0)+qty
                    decision_cost_map[code]=decision_cost_map.get(code,0.0)+(qty*fill_price)
                    latest_auto_buy_map[code]=decision
                elif decision.action=="sell":
                    old_qty=max(0,int(decision_qty_map.get(code,0)))
                    sell_qty=min(old_qty,qty)
                    avg=(decision_cost_map.get(code,0.0)/old_qty) if old_qty>0 else 0.0
                    decision_qty_map[code]=max(0,old_qty-sell_qty)
                    decision_cost_map[code]=max(0.0,avg*decision_qty_map[code])
        position_row_codes={str(x.stock_code or "").strip() for x in auto_rows}
        auto_qty_map={
            code:max(int(position_qty_map.get(code,0)),int(decision_qty_map.get(code,0)))
            for code in source_codes
        }

        # Latest StockLog-originated order for each holding, labelled as Gbot
        # when its broker order number belongs to an AutoTradingDecision.
        latest_trade_map={}
        if source_codes:
            audits=(
                db.query(OrderAudit)
                .filter(OrderAudit.user_id==u.id,OrderAudit.stock_code.in_(source_codes))
                .order_by(OrderAudit.id.desc())
                .limit(600)
                .all()
            )
            order_numbers=[str(x.broker_order_no or "").strip() for x in audits if str(x.broker_order_no or "").strip()]
            auto_order_numbers=set()
            if order_numbers:
                auto_order_numbers={
                    str(x[0] or "").strip()
                    for x in db.query(AutoTradingDecision.broker_order_no).filter(
                        AutoTradingDecision.user_id==u.id,
                        AutoTradingDecision.broker_order_no.in_(order_numbers),
                    ).all()
                    if str(x[0] or "").strip()
                }
            for audit in audits:
                code=str(audit.stock_code or "").strip()
                if not code or code in latest_trade_map:
                    continue
                no=str(audit.broker_order_no or "").strip()
                latest_trade_map[code]={
                    "source":"auto" if no and no in auto_order_numbers else "manual",
                    "side":str(audit.side or ""),
                    "at":audit.created_at.isoformat() if audit.created_at else None,
                    "order_no":no,
                }

        for holding in holdings_for_source:
            if not isinstance(holding,dict):
                continue
            code=str(holding.get("code") or holding.get("stock_code") or "").strip()
            total_qty=max(0,int(float(holding.get("quantity") or 0)))
            auto_qty=min(total_qty,max(0,int(auto_qty_map.get(code,0))))
            manual_qty=max(0,total_qty-auto_qty)
            # Self-heal legacy accounts where Gbot fills exist but an older
            # version never created the automatic position ledger row.  The
            # broker holding is always the upper bound, so this cannot claim
            # more bot-owned shares than the account actually owns.
            if code and auto_qty>0 and int(position_qty_map.get(code,0))<auto_qty:
                inferred_cost=max(0.0,float(decision_cost_map.get(code,0.0)))
                inferred_decision_qty=max(0,int(decision_qty_map.get(code,0)))
                inferred_avg=(inferred_cost/inferred_decision_qty) if inferred_decision_qty>0 else 0.0
                existing_auto=next((x for x in auto_rows if str(x.stock_code or '').strip()==code),None)
                if existing_auto is None:
                    existing_auto=AutoTradingPosition(
                        user_id=u.id,stock_code=code,stock_name=str(holding.get("name") or code),
                        quantity=auto_qty,avg_price=inferred_avg,invested_amount=inferred_avg*auto_qty,
                        last_buy_at=(latest_auto_buy_map.get(code).filled_at if latest_auto_buy_map.get(code) else None),
                    )
                    db.add(existing_auto);auto_rows.append(existing_auto)
                else:
                    existing_auto.quantity=auto_qty
                    if inferred_avg>0: existing_auto.avg_price=inferred_avg
                    existing_auto.invested_amount=float(existing_auto.avg_price or 0)*auto_qty
                    if latest_auto_buy_map.get(code): existing_auto.last_buy_at=latest_auto_buy_map[code].filled_at or existing_auto.last_buy_at
                position_row_codes.add(code);position_qty_map[code]=auto_qty
            if auto_qty>0 and manual_qty>0:
                source_key="mixed";source_label="직접 + Gbot"
            elif auto_qty>0:
                source_key="auto";source_label="Gbot 자동매수"
            else:
                source_key="manual";source_label="직접 매수"
            recent_trade=latest_trade_map.get(code) or {}
            auto_reason=latest_auto_buy_map.get(code) if auto_qty>0 else None
            holding.update({
                "auto_quantity":auto_qty,
                "manual_quantity":manual_qty,
                "acquisition_source":source_key,
                "acquisition_source_label":source_label,
                "attribution_position_quantity":int(position_qty_map.get(code,0)),
                "attribution_decision_quantity":int(decision_qty_map.get(code,0)),
                "last_trade_source":recent_trade.get("source") or "",
                "last_trade_side":recent_trade.get("side") or "",
                "last_trade_at":recent_trade.get("at"),
                "auto_trade_reason":_auto_decision_json(auto_reason) if auto_reason else None,
            })
        if db.new or db.dirty:
            commit_or_rollback(db)
    except Exception:
        logger.exception("portfolio ownership attribution failed user_id=%s",u.id)
        rollback_quietly(db)

    # StockLog-created orders have an exact buy/sell side in OrderAudit.
    # Use it to make executions unambiguous even if a broker status row has
    # a generic numeric transaction field.
    broker_orders=payload.get(
        "orders"
    )

    if isinstance(broker_orders,list) and broker_orders:
        audits=(
            db.query(OrderAudit)
            .filter(
                OrderAudit.user_id
                == u.id
            )
            .order_by(
                OrderAudit.id.desc()
            )
            .limit(200)
            .all()
        )

        audit_side={
            str(
                row.broker_order_no
                or ""
            ).strip():(
                "매수"
                if row.side=="buy"
                else "매도"
                if row.side=="sell"
                else row.side
            )
            for row in audits
            if str(
                row.broker_order_no
                or ""
            ).strip()
        }

        for item in broker_orders:
            if not isinstance(item,dict):
                continue

            order_no=str(
                item.get(
                    "order_no"
                )
                or ""
            ).strip()

            if order_no in audit_side:
                item[
                    "side"
                ]=audit_side[
                    order_no
                ]

    return payload


@app.get("/api/kiwoom/sync-status")
def kiwoom_sync_status(
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    snap = (
        db.query(KiwoomAccountSnapshot)
        .filter(KiwoomAccountSnapshot.user_id == u.id)
        .first()
    )

    marker = (
        db.query(SyncState)
        .filter(SyncState.key == SNAPSHOT_RESET_MARKER)
        .first()
    )

    return {
        "snapshot_exists": bool(snap),
        "snapshot_last_success_at": (
            snap.last_success_at.isoformat()
            if snap and snap.last_success_at
            else None
        ),
        "v38_auto_reset_done": bool(marker),
        "v38_auto_reset_at": (
            marker.last_success_at.isoformat()
            if marker and marker.last_success_at
            else None
        ),
    }


@app.get("/api/kiwoom/sync-diagnostics")
async def kiwoom_sync_diagnostics(
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    snap = (
        db.query(KiwoomAccountSnapshot)
        .filter(
            KiwoomAccountSnapshot.user_id == u.id
        )
        .first()
    )

    if not snap:
        return {
            "available": False,
            "message": "아직 계좌 동기화를 수행하지 않았습니다.",
        }

    payload = _snapshot_to_payload(snap)

    return {
        "available": True,
        "account_no": payload.get("account_no"),
        "last_success_at": payload["_meta"].get("last_success_at"),
        "diagnostics": payload.get("diagnostics", {}),
    }


async def _submit_stocklog_mock_order(
    *,
    db:Session,
    user:User,
    side:str,
    stock_code:str,
    quantity:int,
    order_type:str,
    price:float|None,
    exchange:str="KRX",
):
    if side not in ("buy","sell"):
        raise HTTPException(
            400,
            "매수/매도 구분이 올바르지 않습니다.",
        )

    if side=="buy" and not _stocklog_public_stock(db,stock_code):
        raise HTTPException(
            400,
            "StockLog 분석 대상인 KOSPI·KOSDAQ 일반 상장종목만 새로 매수할 수 있습니다.",
        )

    _,cli=client_for(
        user,
        db,
    )
    # Credential lookup is complete; broker I/O must not hold a DB checkout.
    commit_or_rollback(db)

    data=await cli.order(
        side,
        stock_code,
        quantity,
        order_type,
        price,
        exchange,
    )

    broker_order_no=str(
        data.get("ord_no")
        or data.get("ordNo")
        or data.get("order_no")
        or ""
    )

    db.add(
        OrderAudit(
            user_id=user.id,
            side=side,
            stock_code=stock_code,
            quantity=quantity,
            order_type=order_type,
            price=price,
            broker_order_no=broker_order_no,
            status="accepted",
            raw_response=json.dumps(
                data,
                ensure_ascii=False,
            ),
        )
    )
    commit_or_rollback(db)

    return data,broker_order_no


@app.post("/api/trading/order")
@app.post("/api/kiwoom/order")
async def order(
    body:OrderIn,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    try:
        data,broker_order_no=(
            await _submit_stocklog_mock_order(
                db=db,
                user=u,
                side=body.side,
                stock_code=body.stock_code,
                quantity=body.quantity,
                order_type=body.order_type,
                price=body.price,
                exchange=body.exchange,
            )
        )

        return {
            "ok":
                True,
            "message":
                (
                    "키움 모의투자 주문을 전송했습니다. "
                    "잠시 후 계좌 상태에 조용히 반영됩니다."
                ),
            "broker_order_no":
                broker_order_no,
            "broker":
                data,
        }

    except HTTPException:
        raise

    except Exception as exc:
        msg=str(exc)

        if "429" in msg:
            raise HTTPException(
                429,
                "키움 주문 호출 제한입니다. 잠시 후 다시 주문해주세요.",
            )

        raise HTTPException(
            502,
            "키움 모의투자 주문을 전송하지 못했습니다.",
        ) from exc


_KST=ZoneInfo("Asia/Seoul")
_RESERVATION_POLL_SECONDS=max(
    2.0,
    float(
        os.getenv(
            "STOCKLOG_RESERVATION_POLL_SECONDS",
            "3",
        )
    ),
)
_reservation_monitor_task=None


def _reservation_local_datetime(
    value:datetime|None,
):
    if value is None:
        return None

    if value.tzinfo is not None:
        return (
            value.astimezone(
                _KST
            )
            .replace(
                tzinfo=None
            )
        )

    return value


def _reservation_json(
    row:TradeReservation,
):
    now_kst=datetime.now(
        _KST
    )

    in_regular_session=(
        now_kst.weekday()<5
        and dt_time(
            9,
            0,
        )
        <= now_kst.time()
        <= dt_time(
            15,
            30,
        )
    )

    status_label={
        "active":"감시 중",
        "executing":"주문 전송 중",
        "triggered":"조건 충족 · 주문 전송",
        "cancelled":"예약 취소",
        "expired":"기간 만료",
        "failed":"실행 실패",
    }.get(
        row.status,
        row.status,
    )

    if (
        row.status=="active"
        and not in_regular_session
    ):
        status_label="장외 대기"

    return {
        "id":
            row.id,
        "stock_code":
            row.stock_code,
        "stock_name":
            row.stock_name,
        "side":
            row.side,
        "side_label":
            (
                "매수"
                if row.side=="buy"
                else "매도"
            ),
        "trigger_operator":
            row.trigger_operator,
        "trigger_operator_label":
            (
                "이하 도달"
                if row.trigger_operator=="lte"
                else "이상 도달"
            ),
        "trigger_price":
            row.trigger_price,
        "quantity":
            row.quantity,
        "order_type":
            row.order_type,
        "order_type_label":
            (
                "시장가"
                if row.order_type=="market"
                else "지정가"
            ),
        "order_price":
            row.order_price,
        "exchange":
            row.exchange,
        "status":
            row.status,
        "status_label":
            status_label,
        "last_price":
            row.last_price,
        "last_checked_at":
            (
                row.last_checked_at.isoformat()
                if row.last_checked_at
                else None
            ),
        "triggered_at":
            (
                row.triggered_at.isoformat()
                if row.triggered_at
                else None
            ),
        "broker_order_no":
            row.broker_order_no,
        "error_message":
            row.error_message,
        "expires_at":
            (
                row.expires_at.isoformat()
                if row.expires_at
                else None
            ),
        "created_at":
            row.created_at.isoformat(),
        "updated_at":
            row.updated_at.isoformat(),
    }


def _validate_reservation_body(
    body:TradeReservationIn,
    user:User,
    db:Session,
):
    side=str(
        body.side
        or ""
    ).lower().strip()

    if side not in (
        "buy",
        "sell",
    ):
        raise HTTPException(
            400,
            "예약 주문은 매수 또는 매도만 가능합니다.",
        )

    operator=str(
        body.trigger_operator
        or ""
    ).lower().strip()

    if operator not in (
        "lte",
        "gte",
    ):
        raise HTTPException(
            400,
            "가격 조건은 이하 또는 이상 중 하나여야 합니다.",
        )

    order_type=str(
        body.order_type
        or "market"
    ).lower().strip()

    if order_type not in (
        "market",
        "limit",
    ):
        raise HTTPException(
            400,
            "실행 주문은 시장가 또는 지정가만 가능합니다.",
        )

    if (
        order_type=="limit"
        and (
            body.order_price is None
            or float(
                body.order_price
            )<=0
        )
    ):
        raise HTTPException(
            400,
            "지정가 실행 예약은 주문가격이 필요합니다.",
        )

    stock=(
        db.query(Stock)
        .filter(
            Stock.code
            == body.stock_code
        )
        .first()
    )

    if not stock:
        raise HTTPException(
            404,
            "예약할 종목을 찾을 수 없습니다.",
        )
    if side=="buy" and not (bool(stock.is_active) and bool(stock.is_analysis_eligible) and str(stock.market or "").upper() in STOCKLOG_PUBLIC_MARKETS):
        raise HTTPException(
            400,
            "StockLog 분석 대상인 KOSPI·KOSDAQ 일반 상장종목만 매수 예약할 수 있습니다.",
        )

    expires_at=(
        _reservation_local_datetime(
            body.expires_at
        )
    )

    if (
        expires_at
        and expires_at
        <= datetime.now()
    ):
        raise HTTPException(
            400,
            "예약 만료시간은 현재 이후여야 합니다.",
        )

    # Sell reservations must be backed by an actual synchronized holding.
    if side=="sell":
        snap=(
            db.query(
                KiwoomAccountSnapshot
            )
            .filter(
                KiwoomAccountSnapshot.user_id
                == user.id
            )
            .first()
        )

        if not snap:
            raise HTTPException(
                400,
                "매도 예약 전에 모의투자 계좌를 한 번 동기화해주세요.",
            )

        try:
            holdings=json.loads(
                snap.holdings_json
                or "[]"
            )
        except Exception:
            holdings=[]

        holding_qty=sum(
            float(
                item.get(
                    "quantity"
                )
                or 0
            )
            for item in holdings
            if isinstance(
                item,
                dict,
            )
            and str(
                item.get(
                    "code"
                )
                or ""
            )==body.stock_code
        )

        if holding_qty<float(
            body.quantity
        ):
            raise HTTPException(
                400,
                (
                    f"실제 보유수량 {int(holding_qty):,}주보다 "
                    f"많은 수량을 매도 예약할 수 없습니다."
                ),
            )

    return {
        "stock":
            stock,
        "side":
            side,
        "operator":
            operator,
        "order_type":
            order_type,
        "expires_at":
            expires_at,
    }


@app.get("/api/trading/reservations")
@app.get("/api/kiwoom/reservations")
def reservation_list(
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    rows=(
        db.query(
            TradeReservation
        )
        .filter(
            TradeReservation.user_id
            == u.id
        )
        .order_by(
            TradeReservation.id.desc()
        )
        .limit(200)
        .all()
    )

    return {
        "items":[
            _reservation_json(
                row
            )
            for row in rows
        ],
        "monitor_interval_seconds":
            _RESERVATION_POLL_SECONDS,
    }


@app.post("/api/trading/reservations")
@app.post("/api/kiwoom/reservations")
def reservation_create(
    body:TradeReservationIn,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    validated=_validate_reservation_body(
        body,
        u,
        db,
    )

    row=TradeReservation(
        user_id=u.id,
        stock_code=body.stock_code,
        stock_name=validated[
            "stock"
        ].name,
        side=validated[
            "side"
        ],
        trigger_operator=validated[
            "operator"
        ],
        trigger_price=float(
            body.trigger_price
        ),
        quantity=int(
            body.quantity
        ),
        order_type=validated[
            "order_type"
        ],
        order_price=(
            float(
                body.order_price
            )
            if body.order_price
            is not None
            else None
        ),
        exchange=body.exchange
        or "KRX",
        status="active",
        expires_at=validated[
            "expires_at"
        ],
    )

    db.add(
        row
    )
    commit_or_rollback(db)
    db.refresh(
        row
    )

    return {
        "ok":
            True,
        "message":
            (
                f"{row.stock_name} "
                f"{'매수' if row.side=='buy' else '매도'} "
                "가격감시 예약을 등록했습니다."
            ),
        "item":
            _reservation_json(
                row
            ),
    }


@app.put("/api/trading/reservations/{reservation_id}")
@app.put("/api/kiwoom/reservations/{reservation_id}")
def reservation_update(
    reservation_id:int,
    body:TradeReservationIn,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    row=(
        db.query(
            TradeReservation
        )
        .filter(
            TradeReservation.id
            == reservation_id,
            TradeReservation.user_id
            == u.id,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            404,
            "예약을 찾을 수 없습니다.",
        )

    if row.status!="active":
        raise HTTPException(
            409,
            "감시 중인 예약만 편집할 수 있습니다.",
        )

    validated=_validate_reservation_body(
        body,
        u,
        db,
    )

    row.stock_code=body.stock_code
    row.stock_name=validated[
        "stock"
    ].name
    row.side=validated[
        "side"
    ]
    row.trigger_operator=validated[
        "operator"
    ]
    row.trigger_price=float(
        body.trigger_price
    )
    row.quantity=int(
        body.quantity
    )
    row.order_type=validated[
        "order_type"
    ]
    row.order_price=(
        float(
            body.order_price
        )
        if body.order_price
        is not None
        else None
    )
    row.exchange=body.exchange or "KRX"
    row.expires_at=validated[
        "expires_at"
    ]
    row.error_message=""
    row.updated_at=datetime.now()

    commit_or_rollback(db)
    db.refresh(
        row
    )

    return {
        "ok":
            True,
        "message":
            "가격감시 예약을 수정했습니다.",
        "item":
            _reservation_json(
                row
            ),
    }


@app.post("/api/trading/reservations/{reservation_id}/cancel")
@app.post("/api/kiwoom/reservations/{reservation_id}/cancel")
def reservation_cancel(
    reservation_id:int,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    row=(
        db.query(
            TradeReservation
        )
        .filter(
            TradeReservation.id
            == reservation_id,
            TradeReservation.user_id
            == u.id,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            404,
            "예약을 찾을 수 없습니다.",
        )

    if row.status!="active":
        raise HTTPException(
            409,
            "감시 중인 예약만 취소할 수 있습니다.",
        )

    row.status="cancelled"
    row.updated_at=datetime.now()
    commit_or_rollback(db)

    return {
        "ok":
            True,
        "message":
            "가격감시 예약을 취소했습니다.",
    }


async def _reservation_monitor_once():
    db=SessionLocal()

    try:
        now=datetime.now()

        # Reset reservations left in executing state by an abrupt restart.
        recovery_before=(
            now
            - timedelta(
                minutes=2
            )
        )

        stuck=(
            db.query(
                TradeReservation
            )
            .filter(
                TradeReservation.status
                == "executing",
                TradeReservation.updated_at
                < recovery_before,
            )
            .all()
        )

        for row in stuck:
            row.status="active"
            row.error_message=(
                "백엔드 재시작 후 가격감시를 다시 시작했습니다."
            )

        expired=(
            db.query(
                TradeReservation
            )
            .filter(
                TradeReservation.status
                == "active",
                TradeReservation.expires_at
                .isnot(
                    None
                ),
                TradeReservation.expires_at
                <= now,
            )
            .all()
        )

        for row in expired:
            row.status="expired"
            row.updated_at=now

        if stuck or expired:
            commit_or_rollback(db)

        now_kst=datetime.now(
            _KST
        )

        # Price-trigger reservations only fire during the regular KRX session.
        # This avoids using a stale closing price overnight.
        in_regular_session=(
            now_kst.weekday()<5
            and dt_time(
                9,
                0,
            )
            <= now_kst.time()
            <= dt_time(
                15,
                30,
            )
        )

        if not in_regular_session:
            return

        rows=(
            db.query(
                TradeReservation
            )
            .filter(
                TradeReservation.status
                == "active"
            )
            .order_by(
                TradeReservation.user_id.asc(),
                TradeReservation.stock_code.asc(),
                TradeReservation.id.asc(),
            )
            .all()
        )

        if not rows:
            return

        grouped={}

        for row in rows:
            grouped.setdefault(
                (
                    row.user_id,
                    row.stock_code,
                ),
                [],
            ).append(
                row
            )

        for (
            user_id,
            stock_code,
        ),reservations in grouped.items():

            user=(
                db.query(User)
                .filter(
                    User.id
                    == user_id,
                    User.is_active
                    == True,
                )
                .first()
            )

            if not user:
                continue

            try:
                _,cli=client_for(
                    user,
                    db,
                )
                # Do not retain the user/credential SELECT transaction while
                # waiting for a market quote.
                commit_or_rollback(db)

                metrics=await cli.stock_basic_metrics(
                    stock_code
                )

                current_price=float(
                    metrics.get(
                        "price"
                    )
                    or 0
                )

                if current_price<=0:
                    continue

            except Exception as exc:
                message=(
                    "실제 시세 확인 실패"
                )

                for row in reservations:
                    row.error_message=message
                    row.last_checked_at=datetime.now()

                commit_or_rollback(db)

                print(
                    "[WARN] reservation quote check failed:",
                    user_id,
                    stock_code,
                    repr(
                        exc
                    ),
                )
                continue

            for row in reservations:
                row.last_price=current_price
                row.last_checked_at=datetime.now()
                row.error_message=""

                matched=(
                    current_price
                    <= float(
                        row.trigger_price
                    )
                    if row.trigger_operator=="lte"
                    else current_price
                    >= float(
                        row.trigger_price
                    )
                )

                if not matched:
                    continue

                # Claim this reservation before network I/O.
                row.status="executing"
                row.updated_at=datetime.now()
                commit_or_rollback(db)

                try:
                    order_price=(
                        row.order_price
                        if row.order_type=="limit"
                        else None
                    )

                    _,broker_order_no=(
                        await _submit_stocklog_mock_order(
                            db=db,
                            user=user,
                            side=row.side,
                            stock_code=row.stock_code,
                            quantity=row.quantity,
                            order_type=row.order_type,
                            price=order_price,
                            exchange=row.exchange,
                        )
                    )

                    row.status="triggered"
                    row.triggered_at=datetime.now()
                    row.broker_order_no=broker_order_no
                    row.error_message=""
                    row.updated_at=datetime.now()
                    commit_or_rollback(db)

                except Exception as exc:
                    row.status="failed"
                    row.error_message=(
                        "조건은 충족됐지만 주문 전송에 실패했습니다."
                    )
                    row.updated_at=datetime.now()
                    commit_or_rollback(db)

                    print(
                        "[ERROR] reservation execution failed:",
                        row.id,
                        repr(
                            exc
                        ),
                    )

    finally:
        db.close()


async def _reservation_monitor_loop():
    while True:
        try:
            await _reservation_monitor_once()

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                "[ERROR] reservation monitor:",
                repr(
                    exc
                ),
            )

        await asyncio.sleep(
            _RESERVATION_POLL_SECONDS
        )


@app.on_event("startup")
async def start_reservation_monitor():
    global _reservation_monitor_task

    if (
        _reservation_monitor_task is None
        or _reservation_monitor_task.done()
    ):
        _reservation_monitor_task=asyncio.create_task(
            _reservation_monitor_loop()
        )


@app.on_event("shutdown")
async def stop_reservation_monitor():
    global _reservation_monitor_task

    if (
        _reservation_monitor_task
        and not _reservation_monitor_task.done()
    ):
        _reservation_monitor_task.cancel()

        try:
            await _reservation_monitor_task
        except BaseException:
            pass


@app.get("/api/orders")
def orders(u:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.query(OrderAudit).filter(OrderAudit.user_id==u.id).order_by(OrderAudit.id.desc()).limit(50).all()
    return [{"id":x.id,"side":x.side,"stock_code":x.stock_code,"quantity":x.quantity,
             "order_type":x.order_type,"price":x.price,"broker_order_no":x.broker_order_no,
             "status":x.status,"created_at":x.created_at.isoformat()} for x in rows]


# ---------------------------------------------------------------------------
# v3.75 StockLog Gbot automatic paper trading
# ---------------------------------------------------------------------------
_AUTO_TRADE_DEFAULTS={
    "interval_minutes":15,"trading_start":"09:05","trading_end":"15:15",
    "markets":["KOSPI","KOSDAQ"],"categories":[],"themes":[],"use_all_themes":True,
    "min_price":1000.0,"max_price":0.0,"min_market_cap":1000.0,"max_market_cap":0.0,
    "min_avg_volume":100000.0,"min_smart_score":60.0,"candidate_limit":15,"min_confidence":82.0,
    "max_capital":10000000.0,"max_position_amount":2000000.0,"max_positions":8,
    "max_daily_orders":8,"max_new_buys_per_cycle":1,"min_cash_ratio":30.0,
    "allow_sell_manual_holdings":False,"stop_loss_pct":6.0,"take_profit_pct":12.0,
}
_auto_trade_watcher_task=None
_auto_trade_running_users:set[int]=set()
_auto_trade_task_lock=asyncio.Lock()
_live_auto_trade_watcher_task=None
_live_auto_trade_running_users:set[int]=set()
_live_auto_trade_task_lock=asyncio.Lock()
# v3.76 - lightweight holding monitor. This state is intentionally in-memory:
# it is rebuilt from broker/account truth within a minute after backend restart.
_auto_monitor_state:dict[int,dict[str,dict]]={}
_auto_monitor_last_check:dict[int,float]={}
_auto_monitor_last_gbot:dict[int,float]={}
_auto_monitor_health:dict[int,dict]={}
_AUTO_MONITOR_SECONDS=max(30,int(os.getenv("AUTO_HOLDING_MONITOR_SECONDS","30") or 30))
_AUTO_GBOT_REVIEW_SECONDS=max(120,int(os.getenv("AUTO_HOLDING_GBOT_REVIEW_SECONDS","600") or 600))
_AUTO_ORDER_COOLDOWN_MINUTES=max(10,int(os.getenv("AUTO_ORDER_COOLDOWN_MINUTES","30") or 30))
_AUTO_MAX_ENTRY_RISE_PCT=max(1.0,float(os.getenv("AUTO_MAX_ENTRY_RISE_PCT","5.0") or 5.0))
_AUTO_MAX_ENTRY_FALL_PCT=max(1.0,float(os.getenv("AUTO_MAX_ENTRY_FALL_PCT","4.0") or 4.0))
_AUTO_MAX_ADD_LOSS_PCT=max(0.5,float(os.getenv("AUTO_MAX_ADD_LOSS_PCT","1.5") or 1.5))
_auto_watcher_heartbeat_at:datetime|None=None
_auto_watcher_last_error:str=""
_auto_watcher_last_scan:dict[str,int]={"enabled_users":0,"due_users":0,"monitor_due_users":0,"pending_users":0}
_auto_learning_running_users:set[int]=set()
_auto_learning_lock=asyncio.Lock()
_auto_learning_last_scan:dict[int,float]={}
_AUTO_LEARNING_SCAN_SECONDS=max(300,int(os.getenv("AUTO_LEARNING_SCAN_SECONDS","900") or 900))


def _auto_trade_now():
    return datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)


def _safe_json_dict(value):
    try:
        parsed=json.loads(value or "{}")
        return parsed if isinstance(parsed,dict) else {}
    except Exception:
        return {}


def _auto_cycle_type(*,manual:bool=False,review_only:bool=False):
    if review_only:return "holding_review"
    if manual:return "manual"
    return "scheduled"


def _auto_cycle_start(db:Session,*,user_id:int,cycle_id:str,manual:bool=False,review_only:bool=False,trigger_reason:str=""):
    row=AutoTradingCycle(
        user_id=user_id,cycle_id=cycle_id,cycle_type=_auto_cycle_type(manual=manual,review_only=review_only),
        status="running",trigger_reason=str(trigger_reason or "")[:4000],started_at=_auto_trade_now(),
    )
    db.add(row);flush_or_rollback(db)
    return row


def _auto_cycle_finish(db:Session,row:AutoTradingCycle|None,*,status:str,message:str="",error:str="",
                       market_open:bool|None=None,kiwoom_ok:bool|None=None,gbot_ok:bool|None=None,
                       candidate_count:int|None=None,owned_count:int|None=None,decision_count:int|None=None,
                       buy_count:int|None=None,sell_count:int|None=None,hold_count:int|None=None,
                       blocked_count:int|None=None,order_count:int|None=None):
    if not row:return
    row.status=str(status or "success")[:24]
    if message is not None:row.message=str(message or "")[:4000]
    if error is not None:row.error_message=str(error or "")[:8000]
    if market_open is not None:row.market_open=bool(market_open)
    if kiwoom_ok is not None:row.kiwoom_ok=bool(kiwoom_ok)
    if gbot_ok is not None:row.gbot_ok=bool(gbot_ok)
    if candidate_count is not None:row.candidate_count=max(0,int(candidate_count))
    if owned_count is not None:row.owned_count=max(0,int(owned_count))
    if decision_count is not None:row.decision_count=max(0,int(decision_count))
    if buy_count is not None:row.buy_count=max(0,int(buy_count))
    if sell_count is not None:row.sell_count=max(0,int(sell_count))
    if hold_count is not None:row.hold_count=max(0,int(hold_count))
    if blocked_count is not None:row.blocked_count=max(0,int(blocked_count))
    if order_count is not None:row.order_count=max(0,int(order_count))
    row.finished_at=_auto_trade_now()
    commit_or_rollback(db)


def _auto_cycle_decision_counts(db:Session,user_id:int,cycle_id:str):
    rows=db.query(AutoTradingDecision).filter(AutoTradingDecision.user_id==user_id,AutoTradingDecision.cycle_id==cycle_id).all()
    return {
        "decision_count":len(rows),
        "buy_count":sum(1 for x in rows if x.action=="buy"),
        "sell_count":sum(1 for x in rows if x.action=="sell"),
        "hold_count":sum(1 for x in rows if x.action=="hold"),
        "blocked_count":sum(1 for x in rows if x.status in {"blocked","order_failed"}),
        "order_count":sum(1 for x in rows if _auto_order_attempted(x)),
    }


def _auto_cycle_json(row:AutoTradingCycle):
    return _sanitize_public_ai_result({
        "id":row.id,"cycle_id":row.cycle_id,"cycle_type":row.cycle_type,"status":row.status,
        "trigger_reason":row.trigger_reason or "","market_open":bool(row.market_open),
        "kiwoom_ok":bool(row.kiwoom_ok),"gbot_ok":bool(row.gbot_ok),
        "candidate_count":int(row.candidate_count or 0),"owned_count":int(row.owned_count or 0),
        "decision_count":int(row.decision_count or 0),"buy_count":int(row.buy_count or 0),
        "sell_count":int(row.sell_count or 0),"hold_count":int(row.hold_count or 0),
        "blocked_count":int(row.blocked_count or 0),"order_count":int(row.order_count or 0),
        "message":row.message or "","error":row.error_message or "",
        "started_at":row.started_at.isoformat() if row.started_at else None,
        "finished_at":row.finished_at.isoformat() if row.finished_at else None,
    })


def _auto_learning_case_json(row:AutoTradingOutcome):
    snapshot=_safe_json_dict(row.snapshot_json)
    review=_safe_json_dict(row.review_json)
    # Provider/model metadata is retained in the private review record for
    # operations, but it is not part of the member-facing learning history.
    review.pop("model",None)
    return _sanitize_public_ai_result({
        "id":row.id,"decision_id":row.decision_id,"cycle_id":row.cycle_id,"stock_code":row.stock_code,"stock_name":row.stock_name,
        "status":row.status,"outcome_label":row.outcome_label,"entry_price":float(row.entry_price or 0),
        "entry_quantity":int(row.entry_quantity or 0),"entry_at":row.entry_at.isoformat() if row.entry_at else None,
        "current_price":float(row.current_price or 0),"current_return_pct":float(row.current_return_pct or 0),
        "max_gain_pct":float(row.max_gain_pct or 0),"max_drawdown_pct":float(row.max_drawdown_pct or 0),
        "exit_price":float(row.exit_price or 0),"realized_return_pct":row.realized_return_pct,
        "failure_tags":_safe_json_list(row.failure_tags_json),"lessons":_safe_json_list(row.lessons_json),
        "reusable_failure_tags":actionable_failure_tags({"failure_tags":_safe_json_list(row.failure_tags_json),"review":review}),
        "review_reason":row.review_reason or "","review":review,
        "snapshot_summary":{
            "confidence":snapshot.get("confidence"),"smart_score":snapshot.get("candidate",{}).get("smart_score") if isinstance(snapshot.get("candidate"),dict) else None,
            "change_rate":snapshot.get("candidate",{}).get("change_rate") if isinstance(snapshot.get("candidate"),dict) else None,
            "foreign_net_5d":snapshot.get("candidate",{}).get("foreign_net_5d") if isinstance(snapshot.get("candidate"),dict) else None,
            "institution_net_5d":snapshot.get("candidate",{}).get("institution_net_5d") if isinstance(snapshot.get("candidate"),dict) else None,
        },
        "review_due_at":row.review_due_at.isoformat() if row.review_due_at else None,
        "last_evaluated_at":row.last_evaluated_at.isoformat() if row.last_evaluated_at else None,
        "reviewed_at":row.reviewed_at.isoformat() if row.reviewed_at else None,
        "closed_at":row.closed_at.isoformat() if row.closed_at else None,
    })


def _auto_learning_memory(db:Session,user_id:int):
    cutoff=_auto_trade_now()-timedelta(days=180)
    rows=(db.query(AutoTradingOutcome)
          .filter(
              AutoTradingOutcome.user_id==user_id,
              or_(
                  and_(AutoTradingOutcome.outcome_label.in_(["loss","drawdown","recovered"]),AutoTradingOutcome.reviewed_at.isnot(None)),
                  and_(AutoTradingOutcome.outcome_label.in_(["win","flat"]),AutoTradingOutcome.closed_at.isnot(None)),
              ),
              or_(AutoTradingOutcome.reviewed_at>=cutoff,AutoTradingOutcome.closed_at>=cutoff),
          )
          .order_by(AutoTradingOutcome.id.desc()).limit(120).all())
    cases=[]
    for row in rows:
        snapshot=_safe_json_dict(row.snapshot_json)
        cases.append({
            "stock_code":row.stock_code,"stock_name":row.stock_name,"outcome_label":row.outcome_label,
            "current_return_pct":float(row.current_return_pct or 0),"realized_return_pct":row.realized_return_pct,
            "max_drawdown_pct":float(row.max_drawdown_pct or 0),
            "failure_tags":_safe_json_list(row.failure_tags_json),"lessons":_safe_json_list(row.lessons_json),
            "review":_safe_json_dict(row.review_json),
            "entry_candidate":snapshot.get("candidate") if isinstance(snapshot.get("candidate"),dict) else {},
            "entry_at":row.entry_at.isoformat() if row.entry_at else None,
        })
    return build_learning_memory(cases)


def _safe_json_list(value):
    try:
        parsed=json.loads(value or "[]")
        return parsed if isinstance(parsed,list) else []
    except Exception:
        return []


def _auto_setting(db:Session,user_id:int,create:bool=True):
    row=db.query(AutoTradingSetting).filter(AutoTradingSetting.user_id==user_id).first()
    if not row and create:
        row=AutoTradingSetting(user_id=user_id)
        db.add(row);commit_or_rollback(db);db.refresh(row)
    return row


def _auto_setting_json(row:AutoTradingSetting|None):
    if not row:
        return {**_AUTO_TRADE_DEFAULTS,"enabled":False,"last_cycle_at":None,"next_cycle_at":None,"last_error":"","last_message":""}
    return {
        "enabled":bool(row.enabled),"interval_minutes":int(row.interval_minutes or 30),
        "trading_start":row.trading_start or "09:05","trading_end":row.trading_end or "15:15",
        "markets":_safe_json_list(row.markets_json) or ["KOSPI","KOSDAQ"],
        "categories":_safe_json_list(row.categories_json),"themes":_safe_json_list(row.themes_json),
        "use_all_themes":bool(row.use_all_themes),"min_price":float(row.min_price or 0),
        "max_price":float(row.max_price or 0),"min_market_cap":float(row.min_market_cap or 0),
        "max_market_cap":float(row.max_market_cap or 0),"min_avg_volume":float(row.min_avg_volume or 0),
        "min_smart_score":float(row.min_smart_score or 0),"candidate_limit":int(row.candidate_limit or 15),
        "min_confidence":float(row.min_confidence or 0),"max_capital":float(row.max_capital or 0),
        "max_position_amount":float(row.max_position_amount or 0),"max_positions":int(row.max_positions or 1),
        "max_daily_orders":int(row.max_daily_orders or 1),"max_new_buys_per_cycle":int(row.max_new_buys_per_cycle or 1),
        "min_cash_ratio":float(row.min_cash_ratio or 0),"allow_sell_manual_holdings":bool(row.allow_sell_manual_holdings),
        "stop_loss_pct":float(row.stop_loss_pct or 0),"take_profit_pct":float(row.take_profit_pct or 0),
        "last_cycle_at":row.last_cycle_at.isoformat() if row.last_cycle_at else None,
        "next_cycle_at":row.next_cycle_at.isoformat() if row.next_cycle_at else None,
        "last_error":_sanitize_public_ai_result(row.last_error or ""),"last_message":_sanitize_public_ai_result(row.last_message or ""),
        "updated_at":row.updated_at.isoformat() if row.updated_at else None,
    }


def _auto_market_open(row:AutoTradingSetting,now:datetime|None=None):
    now=now or _auto_trade_now()
    if now.weekday()>=5:return False
    hhmm=now.strftime("%H:%M")
    return str(row.trading_start or "09:05")<=hhmm<=str(row.trading_end or "15:15")


def _auto_order_cash(summary:dict|None):
    """Return the amount the auto trader may treat as orderable cash.

    A numeric ``buying_power`` of zero is not enough to decide that the account
    has no orderable cash.  Kiwoom snapshots carry ``buying_power_available``
    so we only trust the dedicated value when that flag is true; otherwise the
    cash balance is the safe fallback.
    """
    summary=summary or {}
    buying_power_available=bool(summary.get("buying_power_available"))
    if buying_power_available:
        return max(0.0,float(summary.get("buying_power") or 0)),"buying_power"
    return max(0.0,float(summary.get("cash") or 0)),"cash_fallback"


def _auto_account_value_reference(summary:dict|None,order_cash:float=0.0):
    """Choose a conservative account-value base for the cash reserve rule.

    Prefer Kiwoom's explicit total asset when present.  Never add deposit/cash
    to securities evaluation here: same-day settlement means that sum can
    double-count capital.  When an explicit total is unavailable, orderable
    cash/cash/evaluation are conservative independent fallbacks.
    """
    summary=summary or {}
    total_asset=max(0.0,float(summary.get("total_asset") or 0))
    cash=max(0.0,float(summary.get("cash") or 0))
    evaluation=max(0.0,float(summary.get("evaluation_amount") or 0))
    order_cash=max(0.0,float(order_cash or 0))
    return max(total_asset,cash,order_cash,evaluation)


def _auto_buy_strength(confidence:float):
    """Translate Gbot confidence into a predictable target-position strength.

    ``allocation_pct`` from the model remains advisory context only.  It must
    not shrink a valid BUY to less than one share.  Hard limits (capital, cash,
    per-position ceiling) are enforced separately after this target is chosen.
    """
    score=max(0.0,min(100.0,float(confidence or 0)))
    if score>=90:return 1.00
    if score>=85:return 0.75
    if score>=80:return 0.50
    return 0.25


_AUTO_ORDER_ATTEMPT_STATUSES={"submitting","accepted","partial","filled","order_failed","cancelled"}

def _auto_order_attempted(row:AutoTradingDecision):
    """True only after StockLog actually entered the broker-order path.

    A Gbot BUY/SELL opinion that was rejected by a pre-order safety guard is
    still useful in the full decision audit, but it is *not* an order attempt.
    Keeping this distinction prevents guard-blocked decisions from looking like
    broker orders in the user-facing order history.
    """
    return bool(
        row.order_submitted_at
        or str(row.broker_order_no or "").strip()
        or str(row.status or "") in _AUTO_ORDER_ATTEMPT_STATUSES
    )

def _auto_order_history_filter(query):
    """Restrict a decision query to rows that reached broker submission."""
    return query.filter(
        AutoTradingDecision.action.in_(["buy","sell"]),
        or_(
            AutoTradingDecision.order_submitted_at.isnot(None),
            AutoTradingDecision.broker_order_no != "",
            AutoTradingDecision.status.in_(sorted(_AUTO_ORDER_ATTEMPT_STATUSES)),
        ),
    )

def _auto_decision_json(row:AutoTradingDecision):
    filled_time=row.filled_at or (row.updated_at if row.status=="filled" and int(row.filled_quantity or 0)>0 else None)
    return _sanitize_public_ai_result({
        "id":row.id,"cycle_id":row.cycle_id,"code":row.stock_code,"name":row.stock_name,
        "action":row.action,"status":row.status,"confidence":float(row.confidence or 0),
        "requested_quantity":int(row.requested_quantity or 0),"requested_price":float(row.requested_price or 0),
        "requested_amount":float(row.requested_amount or 0),"filled_quantity":int(row.filled_quantity or 0),
        "filled_price":float(row.filled_price or 0),"filled_amount":float(row.filled_amount or 0),
        "reason":row.reason or "","evidence":_safe_json_list(row.evidence_json),"risks":_safe_json_list(row.risks_json),
        "exit_plan":row.exit_plan or "","guard_message":row.guard_message or "",
        "decision_source":("risk_guard" if str(row.model_name or "").strip()=="StockLog Risk Guard" else "gbot"),
        "broker_order_no":row.broker_order_no or "","order_attempted":_auto_order_attempted(row),
        "decided_at":row.decided_at.isoformat() if row.decided_at else None,
        "order_submitted_at":row.order_submitted_at.isoformat() if row.order_submitted_at else None,
        "filled_at":filled_time.isoformat() if filled_time else None,
        "updated_at":row.updated_at.isoformat() if row.updated_at else None,
    })


def _auto_position_json(row:AutoTradingPosition,stock:Stock|None=None):
    price=float(stock.price or 0) if stock else float(row.avg_price or 0)
    qty=int(row.quantity or 0)
    avg=float(row.avg_price or 0)
    pnl=(price-avg)*qty if qty and avg else 0
    rate=((price/avg)-1)*100 if qty and avg and price else 0
    return {"code":row.stock_code,"name":row.stock_name or (stock.name if stock else row.stock_code),"quantity":qty,
            "avg_price":avg,"current_price":price,"evaluation_amount":price*qty,"profit_loss":pnl,"return_rate":rate,
            "last_buy_at":row.last_buy_at.isoformat() if row.last_buy_at else None,
            "last_sell_at":row.last_sell_at.isoformat() if row.last_sell_at else None}


def _auto_broker_fill_time(broker:dict|None):
    """Best-effort KST execution timestamp from Kiwoom's HHMMSS time field."""
    now=_auto_trade_now()
    raw=re.sub(r"[^0-9]","",str((broker or {}).get("time") or ""))
    if len(raw)>=6:
        try:
            return now.replace(hour=int(raw[-6:-4]),minute=int(raw[-4:-2]),second=int(raw[-2:]),microsecond=0)
        except Exception:
            pass
    return now


def _auto_reconcile_orders(db:Session,user_id:int,portfolio_payload:dict|None):
    """Reconcile cumulative broker fills into the original decision/order card."""
    orders=(portfolio_payload or {}).get("orders") or []
    grouped={}
    for item in orders:
        if not isinstance(item,dict):continue
        order_no=str(item.get("order_no") or "").strip()
        if not order_no:continue
        grouped.setdefault(order_no,[]).append(item)
    by_no={}
    for order_no,items in grouped.items():
        executions=[x for x in items if str(x.get("source_tr") or "")=="ka10076" and float(x.get("filled_qty") or 0)>0]
        if executions:
            fill_qty=sum(max(0,int(float(x.get("filled_qty") or 0))) for x in executions)
            fill_value=sum(max(0,float(x.get("price") or 0))*max(0,int(float(x.get("filled_qty") or 0))) for x in executions)
            exemplar=executions[-1]
            by_no[order_no]={**exemplar,"filled_qty":fill_qty,"price":(fill_value/fill_qty if fill_qty else float(exemplar.get("price") or 0))}
        else:
            exemplar=max(items,key=lambda x:int(float(x.get("filled_qty") or 0)))
            by_no[order_no]=exemplar
    pending=(db.query(AutoTradingDecision).filter(
        AutoTradingDecision.user_id==user_id,
        AutoTradingDecision.broker_order_no!="",
        AutoTradingDecision.status.in_(["accepted","partial","filled"]),
    ).order_by(AutoTradingDecision.id.asc()).all())
    changed=0
    for event in pending:
        broker=by_no.get(str(event.broker_order_no or "").strip())
        if not broker:continue
        cumulative=max(0,int(float(broker.get("filled_qty") or 0)))
        prev=max(0,int(event.filled_quantity or 0))
        fill_price=max(0.0,float(broker.get("price") or 0))
        # Repair legacy market-order fills that were stored at the Gbot
        # decision price because ord_prc=0 hid ka10076.cntr_pric.  Price-only
        # repair must not add the same quantity to AutoTradingPosition again.
        if cumulative<=prev:
            if cumulative>0 and fill_price>0 and abs(float(event.filled_price or 0)-fill_price)>=0.5:
                event.filled_price=fill_price
                event.filled_amount=cumulative*fill_price
                event.filled_at=event.filled_at or _auto_broker_fill_time(broker)
                _auto_update_learning_fill(db,event)
                changed+=1
            continue
        delta=cumulative-prev
        if fill_price<=0:
            fill_price=float(event.requested_price or event.filled_price or 0)
        event.filled_quantity=cumulative
        event.filled_price=fill_price
        event.filled_amount=cumulative*fill_price
        event.filled_at=_auto_broker_fill_time(broker)
        event.status="filled" if cumulative>=int(event.requested_quantity or 0) else "partial"
        pos=db.query(AutoTradingPosition).filter(AutoTradingPosition.user_id==user_id,AutoTradingPosition.stock_code==event.stock_code).first()
        if not pos:
            pos=AutoTradingPosition(user_id=user_id,stock_code=event.stock_code,stock_name=event.stock_name,quantity=0,avg_price=0,invested_amount=0)
            db.add(pos);flush_or_rollback(db)
        if event.action=="buy":
            old_qty=int(pos.quantity or 0);old_cost=float(pos.invested_amount or 0)
            add_cost=delta*fill_price
            pos.quantity=old_qty+delta;pos.invested_amount=old_cost+add_cost
            pos.avg_price=(pos.invested_amount/pos.quantity) if pos.quantity else 0
            pos.stock_name=event.stock_name or pos.stock_name;pos.last_buy_at=_auto_trade_now()
            _auto_update_learning_fill(db,event)
        elif event.action=="sell":
            sell_qty=min(delta,int(pos.quantity or 0))
            if sell_qty>0:
                remaining=max(0,int(pos.quantity or 0)-sell_qty)
                pos.quantity=remaining
                pos.invested_amount=float(pos.avg_price or 0)*remaining
                _auto_apply_learning_sell_fill(
                    db,user_id,event.stock_code,exit_price=fill_price,exit_quantity=sell_qty,
                    closed_at=event.filled_at or _auto_trade_now(),
                )
                if remaining==0:
                    pos.avg_price=0;pos.invested_amount=0
                    # Legacy outcome rows can be missing their original fill
                    # quantity. Close only those leftovers after FIFO allocation.
                    _auto_close_learning_cases(db,user_id,event.stock_code,exit_price=fill_price,closed_at=event.filled_at or _auto_trade_now())
                pos.last_sell_at=_auto_trade_now()
        changed+=1
    if changed:commit_or_rollback(db)
    return changed


def _auto_recent_volume_and_flow(db:Session,codes:list[str]):
    result={code:{"avg_volume_20d":0.0,"foreign_net_5d":0.0,"institution_net_5d":0.0,
                  "price_data_date":None,"flow_data_date":None} for code in codes}
    if not codes:return result
    cutoff=(datetime.now().date()-timedelta(days=50)).strftime("%Y-%m-%d")
    bars=(db.query(PriceBar).filter(PriceBar.stock_code.in_(codes),PriceBar.trade_date>=cutoff)
          .order_by(PriceBar.stock_code.asc(),PriceBar.trade_date.desc()).all())
    vols={code:[] for code in codes}
    for row in bars:
        arr=vols.setdefault(row.stock_code,[])
        if len(arr)<20:
            arr.append(float(row.volume or 0))
            if not result[row.stock_code].get("price_data_date"):
                result[row.stock_code]["price_data_date"]=str(row.trade_date or "") or None
    flow_cut=datetime.now().date()-timedelta(days=20)
    flows=(db.query(StockInvestorFlowDaily).filter(StockInvestorFlowDaily.stock_code.in_(codes),StockInvestorFlowDaily.trade_date>=flow_cut)
           .order_by(StockInvestorFlowDaily.stock_code.asc(),StockInvestorFlowDaily.trade_date.desc()).all())
    flow_seen={code:0 for code in codes}
    for row in flows:
        if flow_seen.get(row.stock_code,0)>=5:continue
        result[row.stock_code]["foreign_net_5d"]+=float(row.foreign_net or 0)
        result[row.stock_code]["institution_net_5d"]+=float(row.institution_net or 0)
        if not result[row.stock_code].get("flow_data_date"):
            raw_date=row.trade_date
            result[row.stock_code]["flow_data_date"]=raw_date.isoformat() if hasattr(raw_date,"isoformat") else str(raw_date or "") or None
        flow_seen[row.stock_code]=flow_seen.get(row.stock_code,0)+1
    for code,arr in vols.items():
        result[code]["avg_volume_20d"]=(sum(arr)/len(arr)) if arr else 0
    return result


def _auto_candidate_rows(db:Session,setting:AutoTradingSetting,owned_codes:list[str]):
    markets=_safe_json_list(setting.markets_json) or ["KOSPI","KOSDAQ"]
    categories=set(str(x) for x in _safe_json_list(setting.categories_json) if str(x).strip())
    themes=set(str(x) for x in _safe_json_list(setting.themes_json) if str(x).strip())
    q=db.query(Stock).filter(*_stocklog_public_clauses(),Stock.market.in_(markets),Stock.price>0)
    if float(setting.min_price or 0)>0:q=q.filter(Stock.price>=float(setting.min_price))
    if float(setting.max_price or 0)>0:q=q.filter(Stock.price<=float(setting.max_price))
    if float(setting.min_market_cap or 0)>0:q=q.filter(Stock.market_cap>=float(setting.min_market_cap))
    if float(setting.max_market_cap or 0)>0:q=q.filter(Stock.market_cap<=float(setting.max_market_cap))
    if float(setting.min_smart_score or 0)>0:q=q.filter(Stock.smart_ai_score>=float(setting.min_smart_score))
    if categories:
        q=q.filter(or_(Stock.category.in_(categories),Stock.sector.in_(categories),Stock.industry_name.in_(categories),Stock.theme_group.in_(categories)))
    theme_codes=None
    if not setting.use_all_themes and themes:
        rows=db.query(StockTheme.stock_code).filter(StockTheme.theme_name.in_(themes)).distinct().all()
        theme_codes={r[0] for r in rows}
        extra=db.query(Stock.code).filter(or_(Stock.investment_theme.in_(themes),Stock.theme_group.in_(themes))).all()
        theme_codes.update(r[0] for r in extra)
        if not theme_codes:return []
        q=q.filter(Stock.code.in_(theme_codes))
    pool=q.order_by(Stock.smart_ai_score.desc(),Stock.market_cap.desc()).limit(max(60,int(setting.candidate_limit or 15)*6)).all()
    # Holdings must always be visible to the sell model even if they no longer pass buy filters.
    if owned_codes:
        extras=db.query(Stock).filter(Stock.code.in_(owned_codes),*_stocklog_public_clauses()).all()
        seen={x.code for x in pool}
        pool.extend(x for x in extras if x.code not in seen)
    codes=[x.code for x in pool]
    metrics=_auto_recent_volume_and_flow(db,codes)
    theme_map=_theme_map_for_codes(db,codes,limit=4) if pool else {}
    news_map={code:[] for code in codes};report_map={code:[] for code in codes};disclosure_map={code:[] for code in codes}
    if codes:
        news_rows=(db.query(NewsCache).filter(NewsCache.stock_code.in_(codes)).order_by(NewsCache.published_dt.desc(),NewsCache.id.desc()).limit(500).all())
        for row in news_rows:
            bucket=news_map.setdefault(row.stock_code,[])
            if len(bucket)<3:bucket.append({"title":str(row.title or "")[:180],"sentiment":row.sentiment or "neutral","score":float(row.sentiment_score or 0),"published_at":row.published_at or (row.published_dt.isoformat() if row.published_dt else "")})
        report_rows=(db.query(BrokerReportCache).filter(BrokerReportCache.stock_code.in_(codes)).order_by(BrokerReportCache.report_dt.desc(),BrokerReportCache.id.desc()).limit(300).all())
        for row in report_rows:
            bucket=report_map.setdefault(row.stock_code,[])
            if len(bucket)<2:bucket.append({"title":str(row.title or "")[:180],"broker":row.broker or "","opinion":row.investment_opinion or "","target_price":row.target_price,"summary":str(row.brief_summary or "")[:240]})
        disclosure_rows=(db.query(DisclosureCache).filter(DisclosureCache.stock_code.in_(codes)).order_by(DisclosureCache.receipt_dt.desc(),DisclosureCache.id.desc()).limit(300).all())
        for row in disclosure_rows:
            bucket=disclosure_map.setdefault(row.stock_code,[])
            if len(bucket)<2:bucket.append({"report_name":str(row.report_name or "")[:180],"receipt_date":row.receipt_date or "","importance_score":float(row.importance_score or 0),"reason":str(row.importance_reason or "")[:220]})
    buy=[];owned=[]
    owned_set=set(owned_codes)
    for st in pool:
        m=metrics.get(st.code,{})
        payload={
            "code":st.code,"name":st.name,"market":st.market,"category":st.category,"sector":st.sector,
            "theme_group":st.theme_group or st.investment_theme or "",
            "themes":[x.get("name") for x in (theme_map.get(st.code) or []) if x.get("name")][:4],
            "price":float(st.price or 0),"change_rate":float(st.change_rate or 0),"market_cap_eok":float(st.market_cap or 0),
            "per":st.per,"pbr":st.pbr,"roe":st.roe,"revenue_growth":st.revenue_growth,"operating_margin":st.operating_margin,
            "dividend_yield":st.dividend_yield,"momentum_20d":st.momentum_20d,"volatility":st.volatility,
            "smart_score":st.smart_ai_score,"smart_label":st.smart_ai_label,"coverage":st.smart_score_coverage,
            "score_components":_safe_json_list(st.smart_score_components_json),
            "data_freshness":{
                "smart_score_updated_at":st.smart_score_updated_at.isoformat() if st.smart_score_updated_at else None,
                "kiwoom_metrics_updated_at":st.kiwoom_metrics_updated_at.isoformat() if st.kiwoom_metrics_updated_at else None,
                "dart_financials_updated_at":st.dart_financials_updated_at.isoformat() if st.dart_financials_updated_at else None,
            },
            "recent_news":news_map.get(st.code,[]),"broker_reports":report_map.get(st.code,[]),"recent_disclosures":disclosure_map.get(st.code,[]),
            **m,
        }
        if st.code in owned_set:owned.append(payload)
        if st.code not in owned_set and float(m.get("avg_volume_20d") or 0)>=float(setting.min_avg_volume or 0):buy.append(payload)
    buy=buy[:int(setting.candidate_limit or 15)]
    return buy,owned


def _auto_account_holdings_map(portfolio:dict):
    out={}
    for h in (portfolio or {}).get("holdings") or []:
        if not isinstance(h,dict):continue
        code=str(h.get("code") or h.get("stock_code") or "").strip()
        if code:out[code]=h
    return out


def _auto_rebuild_positions_from_fills(db:Session,user_id:int,portfolio:dict):
    """Repair legacy/stale bot position rows from actual filled Gbot decisions.

    Older releases could persist a completed automatic order in AutoTradingDecision
    without increasing AutoTradingPosition (or only partially increase it).  The
    dedicated portfolio page already reconstructs this attribution, but the auto
    trading status previously read the position table directly.  That made the
    two pages disagree.

    Rebuild the *net* Gbot quantity/cost from fills, preserve any larger valid
    persisted quantity for very old orders whose decision rows may be absent, and
    finally cap the result to the broker's current holding.
    """
    holdings=_auto_account_holdings_map(portfolio)
    if not holdings:
        return 0
    codes=list(holdings.keys())
    rows=(db.query(AutoTradingPosition)
          .filter(AutoTradingPosition.user_id==user_id,AutoTradingPosition.stock_code.in_(codes))
          .all())
    pos_map={str(x.stock_code):x for x in rows}
    decisions=(db.query(AutoTradingDecision)
               .filter(AutoTradingDecision.user_id==user_id,
                       AutoTradingDecision.stock_code.in_(codes),
                       AutoTradingDecision.action.in_(["buy","sell"]),
                       AutoTradingDecision.filled_quantity>0)
               .order_by(AutoTradingDecision.id.asc()).limit(10000).all())
    qty_map={code:0 for code in codes}
    cost_map={code:0.0 for code in codes}
    last_buy={}; last_sell={}; name_map={}
    for d in decisions:
        code=str(d.stock_code or '').strip()
        if code not in holdings: continue
        qty=max(0,int(d.filled_quantity or 0))
        px=max(0.0,float(d.filled_price or d.requested_price or 0))
        name_map[code]=str(d.stock_name or name_map.get(code) or code)
        if d.action=='buy':
            qty_map[code]=qty_map.get(code,0)+qty
            cost_map[code]=cost_map.get(code,0.0)+qty*px
            last_buy[code]=d.filled_at or d.updated_at or d.decided_at
        else:
            old=max(0,int(qty_map.get(code,0)))
            sold=min(old,qty)
            avg=(cost_map.get(code,0.0)/old) if old>0 else 0.0
            qty_map[code]=max(0,old-sold)
            cost_map[code]=avg*qty_map[code]
            last_sell[code]=d.filled_at or d.updated_at or d.decided_at
    changed=0
    for code,h in holdings.items():
        actual=max(0,int(float((h or {}).get('quantity') or 0)))
        if actual<=0: continue
        reconstructed=max(0,int(qty_map.get(code,0)))
        row=pos_map.get(code)
        persisted=max(0,int(row.quantity or 0)) if row else 0
        target=min(actual,max(persisted,reconstructed))
        if target<=0: continue
        reconstructed_avg=(cost_map.get(code,0.0)/reconstructed) if reconstructed>0 else 0.0
        if row is None:
            row=AutoTradingPosition(user_id=user_id,stock_code=code,
                stock_name=str((h or {}).get('name') or name_map.get(code) or code),
                quantity=target,avg_price=reconstructed_avg,invested_amount=reconstructed_avg*target,
                last_buy_at=last_buy.get(code),last_sell_at=last_sell.get(code))
            db.add(row); pos_map[code]=row; changed+=1
            continue
        # Heal quantity upward here. Downward changes are handled by
        # _auto_cap_positions_to_account against the broker truth.
        if target>persisted:
            avg=reconstructed_avg or float(row.avg_price or 0)
            row.quantity=target
            row.avg_price=avg
            row.invested_amount=avg*target
            if last_buy.get(code): row.last_buy_at=last_buy[code]
            if last_sell.get(code): row.last_sell_at=last_sell[code]
            changed+=1
        # If every currently held share is attributed to Gbot, the broker's
        # account average is authoritative and can safely repair legacy
        # decision-price fills.  For mixed manual/Gbot holdings we keep the
        # reconstructed bot cost because the broker average is aggregate.
        if target==actual and actual>0:
            broker_avg=max(0.0,float((h or {}).get('avg_price') or 0))
            broker_purchase=max(0.0,float((h or {}).get('purchase_amount') or 0))
            if broker_avg>0 and (abs(float(row.avg_price or 0)-broker_avg)>=0.5 or abs(float(row.invested_amount or 0)-(broker_purchase or broker_avg*actual))>=1):
                row.avg_price=broker_avg
                row.invested_amount=broker_purchase if broker_purchase>0 else broker_avg*actual
                row.quantity=actual
                changed+=1
    if changed:
        commit_or_rollback(db)
    return changed


def _auto_cap_positions_to_account(db:Session,user_id:int,portfolio:dict):
    """If the user manually sold stock, never let bot-owned quantity exceed the real account holding."""
    holdings=_auto_account_holdings_map(portfolio)
    rows=db.query(AutoTradingPosition).filter(AutoTradingPosition.user_id==user_id,AutoTradingPosition.quantity>0).all()
    changed=0
    for pos in rows:
        actual=max(0,int(float((holdings.get(pos.stock_code) or {}).get("quantity") or 0)))
        if actual<int(pos.quantity or 0):
            pos.quantity=actual
            pos.invested_amount=float(pos.avg_price or 0)*actual
            if actual==0:pos.avg_price=0;pos.invested_amount=0
            changed+=1
    if changed:commit_or_rollback(db)
    return changed


def _auto_pending_codes(db:Session,user_id:int):
    rows=db.query(AutoTradingDecision.stock_code).filter(AutoTradingDecision.user_id==user_id,AutoTradingDecision.status.in_(["accepted","partial"])).all()
    return {str(x[0]) for x in rows}


def _auto_history_start(now:datetime):
    return now.replace(hour=0,minute=0,second=0,microsecond=0)


async def _auto_gbot_decisions(db:Session,user_id:int,setting:AutoTradingSetting,buy_candidates:list[dict],owned_context:list[dict],positions:list[AutoTradingPosition],account_summary:dict,*,holding_review:bool=False,trigger_reason:str="",learning_memory_override:dict|None=None):

    creds=get_provider_credentials(PROVIDER_GEMINI,db)
    api_key=creds.get("api_key","") if creds.get("source") not in {"none","disabled"} else ""
    if not api_key:raise RuntimeError("StockLog Gbot 연결 정보가 설정되지 않았습니다.")
    learning_memory=learning_memory_override if learning_memory_override is not None else _auto_learning_memory(db,user_id)
    # Credential/candidate reads are finished. Gemini can take seconds; return
    # the connection now and reacquire only when persisting the decision.
    commit_or_rollback(db)
    analyst=GeminiAnalyst(api_key)
    pos_map={p.stock_code:p for p in positions if int(p.quantity or 0)>0}
    owned=[]
    for item in owned_context:
        pos=pos_map.get(item["code"])
        if not pos:continue
        price=float(item.get("price") or 0);avg=float(pos.avg_price or 0)
        owned.append({**item,"bot_quantity":int(pos.quantity or 0),"bot_avg_price":avg,"bot_return_rate":((price/avg)-1)*100 if price and avg else 0})
    learning_candidates=[
        {**item,"learning_risk":candidate_learning_risk(item,learning_memory)}
        for item in (buy_candidates or []) if isinstance(item,dict)
    ]
    owned_batch_size=max(5,min(12,int(os.getenv("AUTO_GBOT_OWNED_BATCH_SIZE","10") or 10)))
    candidate_batch_size=max(5,min(15,int(os.getenv("AUTO_GBOT_CANDIDATE_BATCH_SIZE","15") or 15)))
    batches=build_auto_decision_batches(
        owned,learning_candidates,holding_review=holding_review,
        owned_batch_size=owned_batch_size,candidate_batch_size=candidate_batch_size,
    )
    if not batches:
        return [],{"provider":"gemini","model":analyst.background_model,"contract_ok":True,
                   "contract":{"candidate_count":0,"owned_count":0,"returned_count":0,"owned_covered":0,
                               "whitelist_enforced":True,"fail_closed":True},"batch_count":0}

    compact_memory=compact_learning_memory(learning_memory)
    collected=[]
    batch_metas=[]
    coverage={"candidate_count":0,"owned_count":0,"returned_count":0,"owned_covered":0,
              "whitelist_enforced":True,"fail_closed":True}

    def _safe_skip_meta(exc:Exception,batch_index:int):
        detail=str(exc or "")[:800]
        logger.warning(
            "auto Gbot response incomplete; safely skipping cycle user_id=%s batch=%s/%s detail=%s",
            user_id,batch_index,len(batches),detail,
        )
        return {
            "provider":"gemini","model":analyst.background_model,"safe_skip":True,
            "safe_skip_detail":detail,"batch_count":len(batches),"completed_batches":max(0,batch_index-1),
            "safe_skip_reason":(
                "Gbot 응답이 주문 안전 기준을 완전히 충족하지 못해 이번 회차를 안전하게 건너뛰었습니다. "
                "주문은 전송하지 않았으며 다음 회차에 자동으로 다시 판단합니다."
            ),
            "contract_ok":False,"contract":{**coverage,"fail_closed":True},
        }

    for batch_index,batch in enumerate(batches,start=1):
        kind=str(batch.get("kind") or "owned")
        batch_owned=batch.get("owned") or []
        batch_candidates=batch.get("candidates") or []
        if holding_review:
            system=(
                "당신은 StockLog Gbot의 자동보유 종목 전용 포트폴리오 매니저다. 제공된 모든 보유종목에 "
                "add/hold/watch/reduce/sell 중 하나를 반드시 반환한다. hold/watch의 reason은 한국어 한 문장으로 짧게 쓰고 "
                "evidence와 risks는 빈 배열이어도 된다. add/reduce/sell은 reason 최대 두 문장, 서로 다른 evidence 정확히 3개, "
                "risks 최대 2개, exit_plan 한 문장으로 쓴다. reduce_pct는 25/50/75 중 하나다. 데이터가 충돌하면 hold/watch를 우선한다. "
                "모든 항목은 code, action, confidence, reason, evidence, risks, exit_plan을 반드시 포함하고 confidence는 문자열이나 퍼센트가 아닌 "
                "0~100 범위의 JSON 숫자로 쓴다. hold/watch에도 confidence 숫자를 반드시 넣는다. "
                "설명·마크다운 없이 decisions 배열을 가진 완결된 JSON 객체 하나만 반환한다."
            )
        elif kind=="owned":
            system=(
                "당신은 StockLog Gbot의 자동보유 종목 관리자다. 제공된 모든 보유종목에 buy/sell/hold 중 하나를 반드시 반환한다. "
                "hold의 reason은 한국어 한 문장으로 짧게 쓰고 evidence와 risks는 빈 배열이어도 된다. buy/sell은 reason 최대 두 문장, "
                "서로 다른 evidence 정확히 3개, risks 최대 2개, exit_plan 한 문장으로 쓴다. 수익만으로 성급히 매도하지 말고 "
                "핵심 투자 논리 훼손과 최신 데이터 충돌을 우선 확인한다. 모든 항목은 code, action, confidence, reason, evidence, risks, exit_plan을 "
                "반드시 포함하고 confidence는 문자열이나 퍼센트가 아닌 0~100 범위의 JSON 숫자로 쓴다. hold에도 confidence 숫자를 반드시 넣는다. "
                "설명·마크다운 없이 decisions 배열을 가진 완결된 JSON 객체 하나만 반환한다."
            )
        else:
            system=(
                "당신은 StockLog Gbot의 신규 자동매수 후보 심사역이다. 제공된 후보 중 정량·수급·뉴스를 교차검증해 "
                "실제로 buy할 가치가 충분한 종목만 최대 3개 반환한다. 적합한 후보가 없으면 decisions를 빈 배열로 반환한다. "
                "각 buy는 reason 최대 두 문장, 서로 다른 evidence 정확히 3개, 반대 risks 1~2개, exit_plan 한 문장, "
                "confidence와 allocation_pct를 포함한다. confidence와 allocation_pct는 문자열이나 퍼센트가 아닌 0~100 범위의 JSON 숫자로 쓴다. "
                "모든 항목은 code, action, confidence, allocation_pct, reason, evidence, risks, exit_plan을 반드시 포함한다. "
                "hold나 sell은 반환하지 않는다. smart_score 하나만으로 매수하지 않는다. "
                "설명·마크다운 없이 decisions 배열을 가진 완결된 JSON 객체 하나만 반환한다."
            )
        prompt={
            "account":{"total_asset":float(account_summary.get("total_asset") or 0),"cash":float(account_summary.get("cash") or 0),"buying_power":float(account_summary.get("buying_power") or 0)},
            "risk_settings":{"max_capital":setting.max_capital,"max_position_amount":setting.max_position_amount,"max_positions":setting.max_positions,
                             "min_cash_ratio":setting.min_cash_ratio,"min_confidence":setting.min_confidence,"stop_loss_pct":setting.stop_loss_pct,"take_profit_pct":setting.take_profit_pct},
            "batch":{"index":batch_index,"total":len(batches),"kind":kind},
            "bot_owned_positions":batch_owned,
            "buy_candidates":batch_candidates,
            "learning_memory":compact_memory if kind=="candidates" else {},
            "monitor_trigger":str(trigger_reason or "정기 재평가")[:300],
            "response_contract":{
                "root":"{decisions:[...]}","code":"현재 배치에 제공된 6자리 문자열",
                "confidence":"필수 JSON number, 0~100","no_markdown":True,
            },
        }
        output_cap=3200 if kind=="candidates" else min(4200,max(2600,len(batch_owned)*320))
        try:
            parsed,batch_meta=await analyst._generate_json(
                system=system,prompt=prompt,model=analyst.background_model,
                request_kind="background",max_output_tokens=output_cap,
            )
        except RuntimeError as exc:
            if is_recoverable_gbot_completeness_error(exc):
                return [],_safe_skip_meta(exc,batch_index)
            raise

        def _validate_batch_response(value):
            if not isinstance(value,dict) or not isinstance(value.get("decisions"),list):
                raise GbotDecisionContractError("Gbot 응답의 decisions 형식이 배열이 아닙니다. 주문하지 않습니다.")
            rows=value.get("decisions")
            if kind=="candidates" and not rows:
                return [],{"candidate_count":len(batch_candidates),"owned_count":0,"returned_count":0,"owned_covered":0,
                           "whitelist_enforced":True,"fail_closed":True}
            result=validate_gbot_decisions(
                rows,candidate_codes=[x.get("code") for x in batch_candidates],
                owned_codes=[x.get("code") for x in batch_owned],holding_review=holding_review,
            )
            return result.decisions,result.coverage

        try:
            validated,batch_coverage=_validate_batch_response(parsed)
        except GbotDecisionContractError as first_contract_error:
            # The broker path remains closed while Gemini gets one tightly
            # scoped chance to correct its JSON contract. No partial batch is
            # ever returned or recorded.
            logger.warning(
                "auto Gbot contract repair requested user_id=%s batch=%s/%s detail=%s",
                user_id,batch_index,len(batches),str(first_contract_error)[:800],
            )
            repair_prompt={**prompt,"contract_repair":{
                "previous_error":str(first_contract_error)[:800],
                "instruction":(
                    "이전 응답은 주문 안전 계약을 위반했다. 원래 배치 데이터만 다시 검토해 decisions 전체를 새로 작성한다. "
                    "제공된 종목코드만 사용하고 중복 없이 모든 필수 필드를 넣는다. confidence는 모든 항목에 0~100 JSON 숫자로 넣는다."
                ),
                "required_owned_codes":[str(x.get("code") or "") for x in batch_owned],
            }}
            repair_system=(
                system+" 직전 응답의 계약 위반을 교정하는 재시도다. 이전 형식을 복사하지 말고 필수 스키마에 맞는 JSON 전체를 다시 반환한다."
            )
            try:
                repaired,repaired_meta=await analyst._generate_json(
                    system=repair_system,prompt=repair_prompt,model=analyst.background_model,
                    request_kind="background",max_output_tokens=max(output_cap,3600),
                )
            except RuntimeError as exc:
                if is_recoverable_gbot_response_error(exc):
                    return [],_safe_skip_meta(exc,batch_index)
                raise
            try:
                validated,batch_coverage=_validate_batch_response(repaired)
            except GbotDecisionContractError as repair_error:
                return [],_safe_skip_meta(repair_error,batch_index)
            first_batch_meta=batch_meta or {}
            second_batch_meta=repaired_meta or {}
            batch_meta={
                **second_batch_meta,
                "prompt_tokens":int(first_batch_meta.get("prompt_tokens") or 0)+int(second_batch_meta.get("prompt_tokens") or 0),
                "output_tokens":int(first_batch_meta.get("output_tokens") or 0)+int(second_batch_meta.get("output_tokens") or 0),
                "total_tokens":int(first_batch_meta.get("total_tokens") or 0)+int(second_batch_meta.get("total_tokens") or 0),
                "contract_retries":1,
            }
        collected.extend(validated)
        batch_metas.append(batch_meta or {})
        for key in ("candidate_count","owned_count","returned_count","owned_covered"):
            coverage[key]+=int(batch_coverage.get(key) or 0)

    adjusted=apply_learning_risk_adjustments(collected,learning_candidates,learning_memory)
    adjusted_count=sum(1 for row in adjusted if float(row.get("_learning_penalty") or 0)>0)
    first_meta=batch_metas[0] if batch_metas else {}
    meta={**first_meta,"contract_ok":True,"contract":coverage,"batch_count":len(batches),
          "prompt_tokens":sum(int(x.get("prompt_tokens") or 0) for x in batch_metas),
          "output_tokens":sum(int(x.get("output_tokens") or 0) for x in batch_metas),
          "learning_policy_version":learning_memory.get("policy_version",1),"learning_adjusted_buys":adjusted_count}
    return adjusted,meta


def _auto_record_decision(db:Session,*,user_id:int,cycle_id:str,stock:Stock|None,raw:dict,model:str,status:str="decision",guard_message:str=""):
    action=str(raw.get("action") or "hold").lower().strip()
    if action not in {"buy","sell","hold"}:action="hold"
    row=AutoTradingDecision(user_id=user_id,cycle_id=cycle_id,stock_code=str(raw.get("code") or (stock.code if stock else "")),
        stock_name=(stock.name if stock else str(raw.get("name") or "")),action=action,status=status,
        confidence=max(0,min(100,float(raw.get("confidence") or 0))),reason=str(raw.get("reason") or "")[:12000],
        evidence_json=json.dumps(raw.get("evidence") or [],ensure_ascii=False),risks_json=json.dumps(raw.get("risks") or [],ensure_ascii=False),
        exit_plan=str(raw.get("exit_plan") or "")[:6000],guard_message=str(guard_message or "")[:4000],model_name=str(model or ""),decided_at=_auto_trade_now())
    db.add(row);flush_or_rollback(db);return row


def _auto_create_learning_case(db:Session,decision:AutoTradingDecision,*,candidate:dict|None=None,raw:dict|None=None,setting:AutoTradingSetting|None=None):
    if not decision or decision.action!="buy":return None
    existing=db.query(AutoTradingOutcome).filter(AutoTradingOutcome.decision_id==decision.id).first()
    if existing:return existing
    raw=raw or {};candidate=candidate or {}
    snapshot={
        "decision_id":decision.id,"cycle_id":decision.cycle_id,"stock_code":decision.stock_code,"stock_name":decision.stock_name,
        "confidence":float(decision.confidence or 0),"reason":decision.reason or "",
        "evidence":_safe_json_list(decision.evidence_json),"risks":_safe_json_list(decision.risks_json),"exit_plan":decision.exit_plan or "",
        "candidate":candidate,
        "gbot_signal":str(raw.get("_signal") or raw.get("action") or "buy"),
        "allocation_pct":float(raw.get("allocation_pct") or 0),
        "learning_adjustment":{
            "policy_version":2,
            "gbot_confidence":float(raw.get("_gbot_confidence") if raw.get("_gbot_confidence") is not None else decision.confidence or 0),
            "confidence_penalty":float(raw.get("_learning_penalty") or 0),
            "risk":raw.get("_learning_risk") if isinstance(raw.get("_learning_risk"),dict) else {},
        },
        "risk_settings":({
            "min_confidence":float(setting.min_confidence or 0),"max_capital":float(setting.max_capital or 0),
            "max_position_amount":float(setting.max_position_amount or 0),"stop_loss_pct":float(setting.stop_loss_pct or 0),
            "take_profit_pct":float(setting.take_profit_pct or 0),"min_cash_ratio":float(setting.min_cash_ratio or 0),
        } if setting else {}),
        "captured_at":_auto_trade_now().isoformat(),
    }
    row=AutoTradingOutcome(
        user_id=decision.user_id,decision_id=decision.id,cycle_id=decision.cycle_id,stock_code=decision.stock_code,stock_name=decision.stock_name,
        status="pending_fill",outcome_label="pending",entry_price=float(decision.requested_price or 0),entry_quantity=0,
        snapshot_json=json.dumps(snapshot,ensure_ascii=False),review_due_at=_auto_trade_now()+timedelta(hours=2),created_at=_auto_trade_now(),
    )
    db.add(row);flush_or_rollback(db)
    return row


def _auto_update_learning_fill(db:Session,decision:AutoTradingDecision):
    if not decision:return None
    row=db.query(AutoTradingOutcome).filter(AutoTradingOutcome.decision_id==decision.id).first()
    if decision.action!="buy":return row
    if not row:
        row=_auto_create_learning_case(db,decision)
    if not row:return None
    if int(decision.filled_quantity or 0)>0:
        row.entry_price=float(decision.filled_price or decision.requested_price or row.entry_price or 0)
        row.entry_quantity=int(decision.filled_quantity or row.entry_quantity or 0)
        row.entry_at=decision.filled_at or decision.updated_at or decision.decided_at or _auto_trade_now()
        row.status="observing" if row.status in {"pending_fill","pending"} else row.status
        row.review_due_at=row.entry_at+timedelta(hours=2) if row.entry_at else _auto_trade_now()+timedelta(hours=2)
    return row


def _auto_apply_learning_sell_fill(db:Session,user_id:int,stock_code:str,*,exit_price:float,
                                   exit_quantity:int|None,closed_at:datetime|None=None):
    """Allocate a sell fill FIFO to its originating BUY learning cases.

    The previous implementation waited for the whole bot position to reach
    zero and then assigned the final sell price to every scale-in order.  That
    lost partial-loss information and distorted the realized return.  The
    execution ledger lives inside review_json so this remains backward
    compatible without an unsafe production-table ALTER.
    """
    closed_at=closed_at or _auto_trade_now()
    price=max(0.0,float(exit_price or 0))
    remaining=None if exit_quantity is None else max(0,int(exit_quantity or 0))
    rows=(db.query(AutoTradingOutcome).filter(
        AutoTradingOutcome.user_id==user_id,AutoTradingOutcome.stock_code==stock_code,
        AutoTradingOutcome.status.in_(["pending_fill","observing","review_ready","reviewed"]),
    ).order_by(AutoTradingOutcome.entry_at.asc(),AutoTradingOutcome.id.asc()).all())
    allocated=0
    touched=[]
    for row in rows:
        if remaining is not None and remaining<=0:break
        review=_safe_json_dict(row.review_json)
        execution=review.get("_execution") if isinstance(review.get("_execution"),dict) else {}
        already=max(0,int(execution.get("exit_quantity") or 0))
        entry_qty=max(0,int(row.entry_quantity or 0))
        available=max(0,entry_qty-already)
        if available<=0:
            # A legacy pending-fill case may not have quantity. Only the final
            # position-close fallback may close it, without inventing a return.
            if remaining is None and entry_qty<=0:
                row.status="closed";row.closed_at=closed_at;row.last_evaluated_at=closed_at
                touched.append(row)
            continue
        take=available if remaining is None else min(available,remaining)
        if take<=0:continue
        prior_value=max(0.0,float(execution.get("exit_value") or 0))
        exit_value=prior_value+(take*price)
        exited=already+take
        avg_exit=(exit_value/exited) if exited>0 else 0.0
        fills=execution.get("fills") if isinstance(execution.get("fills"),list) else []
        fills.append({"quantity":take,"price":price,"filled_at":closed_at.isoformat()})
        execution.update({
            "exit_quantity":exited,"exit_value":exit_value,"remaining_quantity":max(0,entry_qty-exited),
            "average_exit_price":avg_exit,"fills":fills[-20:],"updated_at":closed_at.isoformat(),
        })
        review["_execution"]=execution
        row.review_json=json.dumps(review,ensure_ascii=False)
        row.exit_price=avg_exit
        if row.entry_price>0 and avg_exit>0:
            row.realized_return_pct=((avg_exit/float(row.entry_price))-1)*100
            row.max_gain_pct=max(float(row.max_gain_pct or 0),float(row.realized_return_pct or 0))
            row.max_drawdown_pct=min(float(row.max_drawdown_pct or 0),float(row.realized_return_pct or 0))
        complete=exited>=entry_qty
        if complete:
            row.current_price=avg_exit;row.current_return_pct=float(row.realized_return_pct or 0)
            row.closed_at=closed_at;row.last_evaluated_at=closed_at
            row.outcome_label="loss" if float(row.realized_return_pct or 0)<=-0.5 else "win" if float(row.realized_return_pct or 0)>=0.5 else "flat"
            row.status="closed"
        elif row.realized_return_pct is not None and row.realized_return_pct<=-0.5:
            # A partial loss is still a concrete realized outcome worth review,
            # while the unsold remainder continues to be marked in execution.
            row.outcome_label="loss"
        ready,reason=should_review_outcome(
            age_minutes=999999,current_return_pct=float(row.current_return_pct or 0),
            max_drawdown_pct=float(row.max_drawdown_pct or 0),closed=True,
            realized_return_pct=row.realized_return_pct,
        )
        if ready and not row.reviewed_at:
            row.status="review_ready";row.review_reason=("부분 " if not complete else "")+reason;row.review_due_at=closed_at
        allocated+=take
        if remaining is not None:remaining-=take
        touched.append(row)
    return {"allocated_quantity":allocated,"rows":touched}


def _auto_close_learning_cases(db:Session,user_id:int,stock_code:str,*,exit_price:float,closed_at:datetime|None=None):
    """Backward-compatible final-close fallback for legacy quantity gaps."""
    result=_auto_apply_learning_sell_fill(
        db,user_id,stock_code,exit_price=exit_price,exit_quantity=None,closed_at=closed_at,
    )
    return result["rows"]


def _auto_refresh_learning_outcomes(db:Session,user_id:int,portfolio:dict|None=None):
    rows=(db.query(AutoTradingOutcome).filter(
        AutoTradingOutcome.user_id==user_id,
        AutoTradingOutcome.status.in_(["pending_fill","observing","review_ready","reviewed","closed"]),
    ).order_by(AutoTradingOutcome.id.desc()).limit(300).all())
    if not rows:return 0
    holdings=_auto_account_holdings_map(portfolio or {})
    codes={row.stock_code for row in rows}
    stocks={x.code:x for x in db.query(Stock).filter(Stock.code.in_(codes)).all()} if codes else {}
    now=_auto_trade_now();changed=0
    for row in rows:
        if row.entry_price<=0 or not row.entry_at:continue
        if row.last_evaluated_at and (now-row.last_evaluated_at).total_seconds()<30 and row.status!="review_ready":
            continue
        h=holdings.get(row.stock_code) or {}
        current=max(0.0,float(h.get("current_price") or h.get("price") or 0))
        if current<=0 and stocks.get(row.stock_code):current=max(0.0,float(stocks[row.stock_code].price or 0))
        if row.status=="closed" and row.exit_price>0:current=float(row.exit_price)
        if current<=0:continue
        ret=((current/float(row.entry_price))-1)*100
        row.current_price=current;row.current_return_pct=ret
        row.max_gain_pct=max(float(row.max_gain_pct or 0),ret)
        row.max_drawdown_pct=min(float(row.max_drawdown_pct or 0),ret)
        row.last_evaluated_at=now
        age_minutes=max(0,(now-row.entry_at).total_seconds()/60)
        if row.status not in {"review_ready","closed"} and not row.reviewed_at:
            ready,reason=should_review_outcome(age_minutes=age_minutes,current_return_pct=ret,max_drawdown_pct=float(row.max_drawdown_pct or 0))
            if ready:
                row.status="review_ready";row.outcome_label="drawdown";row.review_reason=reason;row.review_due_at=now
        elif row.reviewed_at and row.outcome_label=="drawdown" and ret>=0.5:
            # A reviewed open drawdown that later recovered is kept for audit,
            # but removed from future adverse-memory retrieval.
            row.outcome_label="recovered"
        changed+=1
    if changed:commit_or_rollback(db)
    return changed


def _auto_learning_summary(db:Session,user_id:int):
    rows=(db.query(AutoTradingOutcome).filter(AutoTradingOutcome.user_id==user_id)
          .order_by(AutoTradingOutcome.id.desc()).limit(200).all())
    cases=[_auto_learning_case_json(x) for x in rows]
    reviewed_adverse=[x for x in cases if x.get("outcome_label") in {"loss","drawdown"} and x.get("reviewed_at")]
    reviewed_losses=[x for x in reviewed_adverse if x.get("outcome_label")=="loss"]
    # Use the exact 180-day memory (including successful counterexamples) that
    # the next Gbot BUY decision receives, so UI and execution cannot disagree.
    memory=_auto_learning_memory(db,user_id)
    patterns=memory.get("recurring_patterns") or []
    return {
        "total_cases":len(cases),
        "observing":sum(1 for x in cases if x.get("status")=="observing"),
        "review_ready":sum(1 for x in cases if x.get("status")=="review_ready"),
        "reviewed_adverse":len(reviewed_adverse),"reviewed_losses":len(reviewed_losses),
        "actionable_cases":int(memory.get("actionable_cases") or 0),
        "adjustment_ready_patterns":sum(1 for x in patterns if x.get("adjustment_ready")),
        "policy_version":2,
        "recurring_patterns":patterns,
        "recent_cases":cases[:8],
        "guardrail":"정상 변동·돌발정보·같은 날 분할매수 중복을 제외합니다. 3개 이상 독립 사례와 2개 이상 종목에서 반복되고 현재 후보 데이터에도 일치할 때만 최대 12점까지 확신도를 낮춥니다.",
    }


def _auto_learning_post_entry_events(db:Session,row:AutoTradingOutcome):
    """Events seen after entry. They are separated from entry-time evidence so
    the reviewer does not punish Gbot for information that did not exist yet.
    """
    if not row.entry_at:
        return {"news":[],"disclosures":[]}
    news=(db.query(NewsCache).filter(
        NewsCache.stock_code==row.stock_code,
        NewsCache.published_dt.isnot(None),
        NewsCache.published_dt>=row.entry_at,
    ).order_by(NewsCache.published_dt.asc()).limit(8).all())
    disclosures=(db.query(DisclosureCache).filter(
        DisclosureCache.stock_code==row.stock_code,
        DisclosureCache.receipt_dt.isnot(None),
        DisclosureCache.receipt_dt>=row.entry_at,
    ).order_by(DisclosureCache.receipt_dt.asc()).limit(8).all())
    return {
        "news":[{
            "published_at":x.published_dt.isoformat() if x.published_dt else x.published_at,
            "title":x.title,"sentiment":x.sentiment,"sentiment_score":float(x.sentiment_score or 0),
            "importance_score":float(x.importance_score or 0),"importance_reason":x.importance_reason or "",
        } for x in news],
        "disclosures":[{
            "received_at":x.receipt_dt.isoformat() if x.receipt_dt else x.receipt_date,
            "report_name":x.report_name,"remark":x.remark or "",
            "importance_score":float(x.importance_score or 0),"importance_reason":x.importance_reason or "",
        } for x in disclosures],
    }


async def _auto_review_learning_case(db:Session,user_id:int,row:AutoTradingOutcome):
    creds=get_provider_credentials(PROVIDER_GEMINI,db)
    api_key=creds.get("api_key","") if creds.get("source") not in {"none","disabled"} else ""
    if not api_key:return False
    snapshot=_safe_json_dict(row.snapshot_json)
    payload={
        "trade":{
            "code":row.stock_code,"name":row.stock_name,"entry_price":float(row.entry_price or 0),
            "entry_at":row.entry_at.isoformat() if row.entry_at else None,"current_price":float(row.current_price or 0),
            "current_return_pct":float(row.current_return_pct or 0),"max_gain_pct":float(row.max_gain_pct or 0),
            "max_drawdown_pct":float(row.max_drawdown_pct or 0),"realized_return_pct":row.realized_return_pct,
            "review_reason":row.review_reason or "",
        },
        "entry_snapshot":snapshot,
        "post_entry_events":_auto_learning_post_entry_events(db,row),
        "instruction":(
            "매수 당시 정보로 판단 가능했던 진입 오류와, 매수 뒤 새로 발생해 당시에는 알 수 없었던 뉴스/공시를 반드시 분리한다. "
            "결과를 알고 있다는 이유로 억지 인과관계를 만들지 말고 일반 시장 변동/불운과 실제 반복 가능한 판단 오류를 구분한다. "
            "post_entry_events만이 주된 원인이라면 avoidable_error로 분류하지 않는다. 단일 사례를 영구 매수금지 규칙으로 만들지 않는다."
        ),
    }
    system=(
        "당신은 StockLog 자동매매 사후감사 전용 Gbot reviewer다. 손실을 무조건 AI 실패라고 단정하지 않는다. "
        "매수 당시 저장된 정량 데이터, 수급, 변동성, 뉴스/공시, 스마트점수, 최초 Gbot 근거와 실제 사후 성과를 비교한다. "
        "반드시 JSON 객체 하나만 반환한다. root_causes는 tag,severity(low|medium|high),evidence,explanation을 가진 배열, "
        "missed_signals 배열, false_assumptions 배열, reusable_lessons 배열, verdict(normal_variation|avoidable_error|mixed), summary를 포함한다. "
        "tag는 chasing_momentum, weak_flow, excessive_volatility, weak_fundamentals, news_risk, disclosure_risk, low_coverage, valuation_risk, "
        "market_regime, timing_error, post_entry_event, insufficient_evidence, other 중 가장 가까운 값을 우선 사용한다. "
        "post_entry_event는 매수 뒤 새로 나온 정보가 손실의 주요 원인일 때만 사용한다."
    )
    commit_or_rollback(db)
    analyst=GeminiAnalyst(api_key)
    parsed,meta=await analyst._generate_json(
        system=system,prompt=payload,model=analyst.background_model,request_kind="background",max_output_tokens=2200,
    )
    row=db.query(AutoTradingOutcome).filter(AutoTradingOutcome.id==row.id,AutoTradingOutcome.user_id==user_id).first()
    if not row:return False
    causes=parsed.get("root_causes") if isinstance(parsed,dict) else []
    tags=normalize_tags(causes)
    lessons=parsed.get("reusable_lessons") if isinstance(parsed,dict) else []
    if not isinstance(lessons,list):lessons=[]
    row.failure_tags_json=json.dumps(tags,ensure_ascii=False)
    row.lessons_json=json.dumps([str(x)[:500] for x in lessons[:8]],ensure_ascii=False)
    existing_review=_safe_json_dict(row.review_json)
    review_payload=dict(parsed) if isinstance(parsed,dict) else {}
    if isinstance(existing_review.get("_execution"),dict):
        # Partial/full sell fills are operational facts, not model output.
        # Preserve them when the AI review JSON is refreshed.
        review_payload["_execution"]=existing_review["_execution"]
    review_payload["model"]=(meta or {}).get("model","") if isinstance(meta,dict) else ""
    row.review_json=json.dumps(review_payload,ensure_ascii=False)
    row.reviewed_at=_auto_trade_now()
    row.status="reviewed" if row.closed_at is None else "closed"
    if row.outcome_label=="pending":row.outcome_label="drawdown"
    commit_or_rollback(db)
    return True


async def _auto_review_learning_cases_once(user_id:int,max_cases:int=3):
    async with _auto_learning_lock:
        if user_id in _auto_learning_running_users:return 0
        _auto_learning_running_users.add(user_id)
    db=SessionLocal();processed=0
    try:
        for _ in range(max(1,min(5,int(max_cases or 1)))):
            now=_auto_trade_now()
            row=(db.query(AutoTradingOutcome).filter(
                AutoTradingOutcome.user_id==user_id,AutoTradingOutcome.status=="review_ready",
                AutoTradingOutcome.reviewed_at.is_(None),
                or_(AutoTradingOutcome.review_due_at.is_(None),AutoTradingOutcome.review_due_at<=now),
            ).order_by(AutoTradingOutcome.id.asc()).first())
            if not row:break
            try:
                if await _auto_review_learning_case(db,user_id,row):processed+=1
            except GeminiRateLimitError as exc:
                rollback_quietly(db)
                row=db.query(AutoTradingOutcome).filter(AutoTradingOutcome.id==row.id).first()
                if row:
                    row.review_due_at=_auto_trade_now()+timedelta(seconds=max(900,min(3600,int(exc.retry_after_seconds or 900))))
                    commit_or_rollback(db)
                break
            except Exception as exc:
                rollback_quietly(db)
                logger.warning("auto learning review failed user_id=%s outcome_id=%s error=%s",user_id,getattr(row,"id",None),_sync_error_text(exc,500))
                row=db.query(AutoTradingOutcome).filter(AutoTradingOutcome.id==getattr(row,"id",0)).first()
                if row:
                    row.review_due_at=_auto_trade_now()+timedelta(hours=1)
                    commit_or_rollback(db)
                break
        return processed
    finally:
        db.close()
        async with _auto_learning_lock:
            _auto_learning_running_users.discard(user_id)



def _auto_guard_cooldown_row(db:Session,user_id:int,code:str,action:str,setting:AutoTradingSetting,now:datetime):
    """Suppress repeated automatic BUY/SELL attempts after a recent guard block.

    Manual 'run once' bypasses this.  The bot still re-evaluates after the
    cooldown, but a persistent safety condition no longer produces a new audit
    card every watcher cycle.
    """
    minutes=max(15,min(90,int(setting.interval_minutes or 30)*2))
    cutoff=now-timedelta(minutes=minutes)
    row=(db.query(AutoTradingDecision)
         .filter(
             AutoTradingDecision.user_id==user_id,
             AutoTradingDecision.stock_code==code,
             AutoTradingDecision.action==action,
             AutoTradingDecision.status=="blocked",
             AutoTradingDecision.decided_at>=cutoff,
         )
         .order_by(AutoTradingDecision.id.desc()).first())
    if not row:
        return None
    if setting.updated_at and row.decided_at and row.decided_at < setting.updated_at:
        return None
    msg=str(row.guard_message or "")
    persistent=(
        "자금 안전장치" in msg or "목표 보유금액" in msg or
        "자동 보유 종목 수 한도" in msg or "오늘 자동 주문 최대 횟수" in msg or
        "신규 매수 개수 한도" in msg or "매도 가능 수량이 없습니다" in msg or
        "최소" in msg and "확신도" in msg
    )
    return row if persistent else None


def _auto_recent_filled_action_times(db:Session,user_id:int,code:str,now:datetime):
    """Return the newest BUY/SELL fill times used by execution churn guards."""
    cutoff=now-timedelta(days=3)
    rows=(db.query(AutoTradingDecision)
          .filter(
              AutoTradingDecision.user_id==user_id,
              AutoTradingDecision.stock_code==code,
              AutoTradingDecision.action.in_(["buy","sell"]),
              AutoTradingDecision.filled_quantity>0,
              or_(AutoTradingDecision.filled_at>=cutoff,AutoTradingDecision.updated_at>=cutoff),
          )
          .order_by(AutoTradingDecision.id.desc()).limit(80).all())
    result={"buy":None,"sell":None}
    for item in rows:
        action=str(item.action or "").lower()
        if action in result and result[action] is None:
            result[action]=item.filled_at or item.updated_at
        if result["buy"] and result["sell"]:break
    return result


def _auto_committed_capital(portfolio:dict,positions:list[AutoTradingPosition],pending_buy_amount:float=0.0):
    """Conservative principal committed by Gbot.

    Use the larger of the bot ledger cost and the broker-attributed purchase
    amount for each holding.  This prevents a stale/legacy AutoTradingPosition
    row from making a 1,000,000 won hard cap look like only 600,000 won is used.
    Pending buy reservation is added on top.
    """
    holdings=_auto_account_holdings_map(portfolio)
    committed=0.0
    parts=[]
    for p in positions:
        bot_qty=max(0,int(p.quantity or 0))
        if bot_qty<=0: continue
        h=holdings.get(p.stock_code) or {}
        actual=max(0,int(float(h.get("quantity") or 0)))
        ratio=min(1.0,bot_qty/actual) if actual>0 else 1.0
        broker_purchase=max(0.0,float(h.get("purchase_amount") or 0))*ratio if actual>0 else 0.0
        ledger=max(0.0,float(p.invested_amount or 0))
        value=max(ledger,broker_purchase)
        committed+=value
        parts.append({"code":p.stock_code,"amount":value,"ledger":ledger,"broker":broker_purchase})
    pending=max(0.0,float(pending_buy_amount or 0))
    return committed+pending,{"filled_principal":committed,"pending_buy":pending,"parts":parts}


def _auto_monitor_public_state(user_id:int,positions:list[AutoTradingPosition]):
    state=_auto_monitor_state.get(user_id) or {}
    out=[]
    now=_auto_trade_now()
    stale_after=max(180,_AUTO_MONITOR_SECONDS*3)
    for p in positions:
        item=dict(state.get(p.stock_code) or {})
        item.setdefault("code",p.stock_code);item.setdefault("name",p.stock_name or p.stock_code)
        item.setdefault("quantity",int(p.quantity or 0));item.setdefault("avg_price",float(p.avg_price or 0))
        item.setdefault("signal","HOLD")
        item.setdefault("last_checked_at",None);item.setdefault("last_gbot_at",None)
        checked_at=None
        if item.get("last_checked_at"):
            try:checked_at=datetime.fromisoformat(str(item["last_checked_at"]))
            except Exception:checked_at=None
        checked_age=max(0,(now-checked_at).total_seconds()) if checked_at else None
        if checked_at and checked_age<=stale_after:
            item["verification_status"]="verified"
            item.setdefault("reason","정상 범위 · 키움 시세 확인 완료")
        elif checked_at:
            item["verification_status"]="delayed"
            item["reason"]="최근 종목 시세 확인이 지연되고 있습니다."
        else:
            item["verification_status"]="waiting"
            item.setdefault("reason","첫 키움 시세 확인 대기")
        item["checked_age_seconds"]=int(checked_age) if checked_age is not None else None
        if item.get("last_gbot_at"):
            try:
                dt=datetime.fromisoformat(str(item["last_gbot_at"]));item["next_gbot_at"]=(dt+timedelta(seconds=_AUTO_GBOT_REVIEW_SECONDS)).isoformat()
            except Exception:item["next_gbot_at"]=None
        else:item["next_gbot_at"]=None
        item["monitor_interval_seconds"]=_AUTO_MONITOR_SECONDS
        item["gbot_review_seconds"]=_AUTO_GBOT_REVIEW_SECONDS
        out.append(item)
    return out


def _auto_monitor_health_payload(user_id:int,setting:AutoTradingSetting,position_count:int):
    raw=_auto_monitor_health.get(user_id) or {}
    return monitor_health_payload(
        enabled=bool(setting.enabled),market_open=_auto_market_open(setting),
        interval_seconds=_AUTO_MONITOR_SECONDS,position_count=position_count,
        last_started_at=raw.get("last_started_at"),last_success_at=raw.get("last_success_at"),
        last_failure_at=raw.get("last_failure_at"),last_error=str(raw.get("last_error") or ""),
        checked_positions=int(raw.get("checked_positions") or 0),check_count=int(raw.get("check_count") or 0),
        now=_auto_trade_now(),
    )


def _auto_update_monitor_from_gbot(user_id:int,raw:dict,canonical_action:str,now:datetime):
    code=str(raw.get("code") or "").strip()
    if not code:return
    raw_signal=str(raw.get("_signal") or raw.get("action") or canonical_action or "hold").upper()
    signal_map={"BUY":"ADD","ADD":"ADD","HOLD":"HOLD","WATCH":"WATCH","REDUCE":"REDUCE","SELL":"SELL"}
    signal=signal_map.get(raw_signal,"HOLD")
    state=_auto_monitor_state.setdefault(user_id,{})
    item=state.setdefault(code,{"code":code})
    item.update({"signal":signal,"reason":str(raw.get("reason") or "")[:500],"confidence":float(raw.get("confidence") or 0),
                 "last_gbot_at":now.isoformat(),"event_trigger":str(raw.get("_trigger_reason") or "")[:300]})


async def _auto_monitor_positions_once(user_id:int):
    """Lightweight account monitor. Gemini is called only on events or every 10 min."""
    db=SessionLocal()
    trigger_reason=""
    should_review=False
    health=_auto_monitor_health.setdefault(user_id,{"check_count":0})
    health["last_started_at"]=_auto_trade_now()
    try:
        user=db.query(User).filter(User.id==user_id,User.is_active==True).first()
        setting=_auto_setting(db,user_id,create=False)
        if not user or not setting or not setting.enabled or not _auto_market_open(setting):return
        portfolio=await _sync_kiwoom_account(user,db,force=False)
        portfolio=_enrich_portfolio_holdings(portfolio,db)
        _auto_reconcile_orders(db,user_id,portfolio)
        _auto_refresh_learning_outcomes(db,user_id,portfolio)
        _auto_rebuild_positions_from_fills(db,user_id,portfolio)
        _auto_cap_positions_to_account(db,user_id,portfolio)
        positions=db.query(AutoTradingPosition).filter(AutoTradingPosition.user_id==user_id,AutoTradingPosition.quantity>0).all()
        eligible_position_codes=_stocklog_public_code_set(db,[p.stock_code for p in positions])
        positions=[p for p in positions if p.stock_code in eligible_position_codes]
        if not positions:
            _auto_monitor_state[user_id]={}
            checked_at=_auto_trade_now()
            health.update({"last_success_at":checked_at,"last_error":"","checked_positions":0,
                           "check_count":int(health.get("check_count") or 0)+1})
            if int(health["check_count"])==1 or int(health["check_count"])%10==0:
                logger.info("auto holding monitor verified user_id=%s positions=0 checks=%s",user_id,health["check_count"])
            _auto_monitor_last_check[user_id]=time.monotonic()
            return
        holdings=_auto_account_holdings_map(portfolio)
        now=_auto_trade_now();state=_auto_monitor_state.setdefault(user_id,{})
        event_reasons=[]
        for p in positions:
            h=holdings.get(p.stock_code) or {}
            current=max(0.0,float(h.get("current_price") or h.get("price") or 0))
            if current<=0:
                stock_row=db.query(Stock).filter(Stock.code==p.stock_code).first()
                current=max(0.0,float(stock_row.price or 0)) if stock_row else 0.0
            avg=max(0.0,float(p.avg_price or 0));risk_rule=protective_exit_assessment(
                current_price=current,average_price=avg,
                stop_loss_pct=float(setting.stop_loss_pct or 0),take_profit_pct=float(setting.take_profit_pct or 0),
            );ret=float(risk_rule.get("return_rate") or 0)
            prev=dict(state.get(p.stock_code) or {})
            prev_price=max(0.0,float(prev.get("current_price") or 0));move=((current/prev_price)-1)*100 if current>0 and prev_price>0 else 0.0
            peak=max(current,max(0.0,float(prev.get("peak_price") or 0)))
            drawdown=((current/peak)-1)*100 if current>0 and peak>0 else 0.0
            crossed=set(prev.get("crossed_levels") or [])
            new_cross=[]
            for level in (3,5,8,10,15):
                if ret>=level and level not in crossed:new_cross.append(level);crossed.add(level)
            latest_news=db.query(NewsCache.id).filter(NewsCache.stock_code==p.stock_code).order_by(NewsCache.id.desc()).first()
            latest_disclosure=db.query(DisclosureCache.id).filter(DisclosureCache.stock_code==p.stock_code).order_by(DisclosureCache.id.desc()).first()
            news_id=int(latest_news[0]) if latest_news else 0
            disclosure_id=int(latest_disclosure[0]) if latest_disclosure else 0
            reasons=[]
            if abs(move)>=2.0:reasons.append(f"1분 가격변동 {move:+.2f}%")
            if drawdown<=-2.0:reasons.append(f"감시 고점 대비 {drawdown:.2f}%")
            if new_cross:reasons.append("수익구간 "+", ".join(f"+{x}%" for x in new_cross)+" 진입")
            if prev.get("latest_news_id") is not None and news_id>int(prev.get("latest_news_id") or 0):reasons.append("새 종목 뉴스 감지")
            if prev.get("latest_disclosure_id") is not None and disclosure_id>int(prev.get("latest_disclosure_id") or 0):reasons.append("새 공시 감지")
            if risk_rule.get("status")=="stop_triggered":reasons.append(f"손절 기준 도달 {ret:+.2f}%")
            elif risk_rule.get("status")=="stop_approaching":reasons.append(f"손절 기준 접근 {ret:+.2f}% (실행 -{float(setting.stop_loss_pct):g}%)")
            if risk_rule.get("status")=="take_triggered":reasons.append(f"익절 기준 도달 {ret:+.2f}%")
            elif risk_rule.get("status")=="take_approaching":reasons.append(f"익절 기준 접근 {ret:+.2f}% (실행 +{float(setting.take_profit_pct):g}%)")
            signal=str(prev.get("signal") or "HOLD")
            reason=str(prev.get("reason") or "정상 감시 중")
            if reasons:
                signal="WATCH";reason=" · ".join(reasons);event_reasons.append(f"{p.stock_name or p.stock_code}: {reason}")
            state[p.stock_code]={**prev,"code":p.stock_code,"name":p.stock_name or p.stock_code,"quantity":int(p.quantity or 0),
                "avg_price":avg,"current_price":current,"return_rate":ret,"one_minute_move":move,"peak_price":peak,
                "drawdown_pct":drawdown,"signal":signal,"reason":reason,"risk_rule":risk_rule,"crossed_levels":sorted(crossed),
                "latest_news_id":news_id,"latest_disclosure_id":disclosure_id,"last_checked_at":now.isoformat()}
        last_gbot=float(_auto_monitor_last_gbot.get(user_id) or 0)
        elapsed=time.monotonic()-last_gbot if last_gbot else 10**9
        if event_reasons and elapsed>=90:
            should_review=True;trigger_reason=" / ".join(event_reasons[:4])
        elif elapsed>=_AUTO_GBOT_REVIEW_SECONDS:
            should_review=True;trigger_reason="10분 정기 보유종목 재평가"
        _auto_monitor_last_check[user_id]=time.monotonic()
        health.update({"last_success_at":now,"last_error":"","checked_positions":len(positions),
                       "check_count":int(health.get("check_count") or 0)+1})
        if int(health["check_count"])==1 or int(health["check_count"])%10==0:
            logger.info("auto holding monitor verified user_id=%s positions=%s checks=%s",user_id,len(positions),health["check_count"])
    except Exception as exc:
        rollback_quietly(db)
        failure_at=_auto_trade_now();error_text=_sync_error_text(exc,400)
        health.update({"last_failure_at":failure_at,"last_error":error_text})
        logger.warning("auto holding monitor failed user_id=%s error=%s",user_id,error_text)
    finally:
        db.close()
    if should_review and user_id not in _auto_trade_running_users:
        asyncio.create_task(_run_auto_trade_cycle(user_id,review_only=True,trigger_reason=trigger_reason))


async def _run_auto_trade_cycle(user_id:int,*,manual:bool=False,review_only:bool=False,trigger_reason:str=""):
    async with _auto_trade_task_lock:
        if user_id in _auto_trade_running_users:return {"ok":False,"message":"이미 자동매매 판단이 진행 중입니다."}
        _auto_trade_running_users.add(user_id)
    db=SessionLocal();cycle_id=f"{_auto_trade_now().strftime('%Y%m%d%H%M%S')}-{user_id}-{uuid.uuid4().hex[:6]}"
    cycle_row=None;market_open=False;kiwoom_ok=False;gbot_ok=False;candidate_count=0;owned_count=0
    try:
        user=db.query(User).filter(User.id==user_id,User.is_active==True).first()
        if not user:return {"ok":False,"message":"사용자를 찾을 수 없습니다."}
        setting=_auto_setting(db,user_id)
        cycle_row=_auto_cycle_start(db,user_id=user_id,cycle_id=cycle_id,manual=manual,review_only=review_only,trigger_reason=trigger_reason)
        if not manual and not setting.enabled:
            _auto_cycle_finish(db,cycle_row,status="skipped",message="자동매매가 중지 상태입니다.")
            return {"ok":False,"message":"자동매매가 중지 상태입니다."}
        if feature_policy(db,user_tier(user),"mock_trading").get("enabled") is False:
            setting.enabled=False;setting.last_error="모의투자 기능 권한이 비활성화되었습니다.";commit_or_rollback(db)
            _auto_cycle_finish(db,cycle_row,status="error",message=setting.last_error,error=setting.last_error)
            return {"ok":False,"message":setting.last_error}
        cred=db.query(KiwoomCredential).filter(KiwoomCredential.user_id==user_id).first()
        if not cred or not cred.use_mock:
            setting.enabled=False;setting.last_error="자동매매는 키움 모의투자 연결에서만 사용할 수 있습니다.";commit_or_rollback(db)
            _auto_cycle_finish(db,cycle_row,status="error",message=setting.last_error,error=setting.last_error)
            return {"ok":False,"message":setting.last_error}
        now=_auto_trade_now();market_open=_auto_market_open(setting,now)
        cycle_row.market_open=market_open;commit_or_rollback(db)
        portfolio=await _sync_kiwoom_account(user,db,force=True)
        kiwoom_ok=True
        portfolio=_enrich_portfolio_holdings(portfolio,db)
        _auto_reconcile_orders(db,user_id,portfolio)
        # Critical hard-cap repair: reconstruct legacy/missed bot fills before
        # calculating exposure. v3.75.x could skip this in the trade cycle and
        # therefore believe only ~600k was committed while broker holdings
        # already represented >1m of Gbot purchases.
        _auto_rebuild_positions_from_fills(db,user_id,portfolio)
        _auto_cap_positions_to_account(db,user_id,portfolio)
        positions=db.query(AutoTradingPosition).filter(AutoTradingPosition.user_id==user_id,AutoTradingPosition.quantity>0).all()
        eligible_position_codes=_stocklog_public_code_set(db,[p.stock_code for p in positions])
        trade_positions=[p for p in positions if p.stock_code in eligible_position_codes]
        owned_codes=[p.stock_code for p in trade_positions]
        buy_candidates,owned_context=_auto_candidate_rows(db,setting,owned_codes)
        if review_only:buy_candidates=[]
        candidate_count=len(buy_candidates);owned_count=len(owned_context)
        cycle_row.candidate_count=candidate_count;cycle_row.owned_count=owned_count;cycle_row.kiwoom_ok=True;commit_or_rollback(db)
        decisions,meta=await _auto_gbot_decisions(db,user_id,setting,buy_candidates,owned_context,trade_positions,(portfolio or {}).get("summary") or {},holding_review=review_only,trigger_reason=trigger_reason)
        if bool((meta or {}).get("safe_skip")):
            # An incomplete AI response is not an executable decision. Finish
            # this cycle before deterministic exits or any broker order path.
            now_skip=_auto_trade_now();setting=_auto_setting(db,user_id)
            if not review_only:
                setting.last_cycle_at=now_skip
                setting.next_cycle_at=now_skip+timedelta(minutes=int(setting.interval_minutes or 30))
            _auto_monitor_last_gbot[user_id]=time.monotonic()
            setting.last_error=""
            setting.last_message=str((meta or {}).get("safe_skip_reason") or "Gbot 응답을 완결하지 못해 이번 회차를 건너뛰었습니다. 주문은 전송하지 않았습니다.")[:4000]
            commit_or_rollback(db)
            counts=_auto_cycle_decision_counts(db,user_id,cycle_id)
            _auto_cycle_finish(
                db,cycle_row,status="skipped",message=setting.last_message,error="",
                market_open=market_open,kiwoom_ok=kiwoom_ok,gbot_ok=False,
                candidate_count=candidate_count,owned_count=owned_count,**counts,
            )
            return {"ok":True,"skipped":True,"message":setting.last_message,"cycle_id":cycle_id,
                    "decisions":0,"orders":0,"market_open":market_open,"review_only":review_only}
        gbot_ok=True;cycle_row.gbot_ok=True;commit_or_rollback(db)
        stock_codes={str(x.get("code") or "") for x in decisions if isinstance(x,dict)}
        stocks={x.code:x for x in db.query(Stock).filter(Stock.code.in_(stock_codes),*_stocklog_public_clauses()).all()} if stock_codes else {}
        decision_map={str(x.get("code") or ""):x for x in decisions if isinstance(x,dict) and str(x.get("code") or "")}
        # Deterministic optional exits are safety rules configured by the user.
        # Use the same fresh broker holding price as the visible monitor.  The
        # stock master may lag intraday and must never disagree with a hard exit.
        holdings_map=_auto_account_holdings_map(portfolio)
        context_map={x["code"]:x for x in owned_context}
        learning_context_map={x["code"]:x for x in [*(buy_candidates or []),*(owned_context or [])] if isinstance(x,dict) and x.get("code")}
        for pos in trade_positions:
            ctx=context_map.get(pos.stock_code) or {};holding=holdings_map.get(pos.stock_code) or {}
            price=float(holding.get("current_price") or holding.get("price") or ctx.get("price") or 0);avg=float(pos.avg_price or 0)
            risk_rule=protective_exit_assessment(current_price=price,average_price=avg,
                stop_loss_pct=float(setting.stop_loss_pct or 0),take_profit_pct=float(setting.take_profit_pct or 0))
            trigger=str(risk_rule.get("trigger") or "")
            if trigger:
                decision_map[pos.stock_code]={"code":pos.stock_code,"action":"sell","confidence":100,"allocation_pct":100,"_decision_source":"risk_guard",
                    "reason":f"{trigger}. 키움 계좌 현재가를 기준으로 사용자가 저장한 리스크 규칙을 우선 적용해 자동 보유수량을 정리합니다.",
                    "evidence":[trigger,"키움 계좌 현재가 기준","StockLog 자동 보유수량에만 적용"],"risks":["시장가 주문은 실제 체결가격이 달라질 수 있음"],"exit_plan":"전량 정리 후 다음 자동 판단에서 재진입 여부를 새로 평가"}
        pending_rows=db.query(AutoTradingDecision).filter(AutoTradingDecision.user_id==user_id,AutoTradingDecision.status.in_(["accepted","partial"])).all()
        pending_codes={str(x.stock_code or "") for x in pending_rows}
        pending_buy_amount=sum(max(0,float(x.requested_amount or 0)-float(x.filled_amount or 0)) for x in pending_rows if x.action=="buy")
        today_orders=db.query(AutoTradingDecision).filter(AutoTradingDecision.user_id==user_id,AutoTradingDecision.order_submitted_at>=_auto_history_start(now)).count()
        summary=(portfolio or {}).get("summary") or {}
        order_cash,cash_source=_auto_order_cash(summary)
        account_value_reference=_auto_account_value_reference(summary,order_cash)
        cash=max(0,order_cash-pending_buy_amount)
        min_cash_amount=max(0,account_value_reference*float(setting.min_cash_ratio or 0)/100.0)
        position_by_code={p.stock_code:p for p in trade_positions}
        auto_exposure,capital_meta=_auto_committed_capital(portfolio,positions,pending_buy_amount)
        held_codes={p.stock_code for p in trade_positions if int(p.quantity or 0)>0}
        eligible_pending_codes=_stocklog_public_code_set(db,[x.stock_code for x in pending_rows if x.action=="buy"])
        pending_new_codes={x.stock_code for x in pending_rows if x.action=="buy" and x.stock_code in eligible_pending_codes and x.stock_code not in held_codes}
        active_positions=len(held_codes|pending_new_codes)
        new_buys=0;submitted=0;recorded=0
        # Record owned holds/sells first, then strongest buys.
        ordered=list(decision_map.values())
        ordered.sort(key=lambda x:(0 if str(x.get("action") or "").lower()=="sell" else 1 if str(x.get("action") or "").lower()=="buy" else 2,-float(x.get("confidence") or 0)))
        for raw in ordered:
            if not isinstance(raw,dict):continue
            code=str(raw.get("code") or "").strip();stock=stocks.get(code) or _stocklog_public_stock(db,code)
            if not stock:continue
            raw_signal=str(raw.get("action") or "hold").lower().strip()
            signal_map={"add":"buy","reduce":"sell","watch":"hold","buy":"buy","sell":"sell","hold":"hold"}
            action=signal_map.get(raw_signal,"hold")
            decision_source=str(raw.get("_decision_source") or "gbot")
            raw_for_record={**raw,"_signal":raw_signal,"_trigger_reason":trigger_reason,"_decision_source":decision_source,"action":action}
            confidence=float(raw.get("confidence") or 0)
            if decision_source=="gbot":
                _auto_update_monitor_from_gbot(user_id,raw_for_record,action,now)
            if not manual and action in {"buy","sell"}:
                prior_block=_auto_guard_cooldown_row(db,user_id,code,action,setting,now)
                if prior_block:
                    continue
            decision_model=("StockLog Risk Guard" if decision_source=="risk_guard" else (meta.get("model","") if isinstance(meta,dict) else ""))
            row=_auto_record_decision(db,user_id=user_id,cycle_id=cycle_id,stock=stock,raw=raw_for_record,model=decision_model)
            recorded+=1
            guard=""
            qty=0;price=max(0,float(stock.price or 0));amount=0
            if action=="hold":row.status="hold";commit_or_rollback(db);continue
            if not manual:
                db.refresh(setting)
                if not setting.enabled:
                    row.status="blocked";row.guard_message="사용자가 거래 중지를 요청해 신규 자동주문을 중단했습니다.";commit_or_rollback(db);continue
            if not market_open:
                row.status="blocked";row.guard_message="거래 가능 시간이 아니어서 판단만 기록했습니다.";commit_or_rollback(db);continue
            if confidence<float(setting.min_confidence or 0):
                learning_penalty=max(0.0,float(raw.get("_learning_penalty") or 0))
                original_confidence=max(confidence,float(raw.get("_gbot_confidence") or confidence))
                learning_matches=(raw.get("_learning_risk") or {}).get("matched_patterns") if isinstance(raw.get("_learning_risk"),dict) else []
                learning_tags=[str(x.get("tag") or "") for x in (learning_matches or []) if isinstance(x,dict) and x.get("tag")]
                learning_note=(
                    f" (원점수 {original_confidence:.0f}점, 검증된 반복실패 감점 -{learning_penalty:g}점"
                    + (f", 일치: {', '.join(learning_tags[:3])}" if learning_tags else "") + ")"
                    if learning_penalty>0 else ""
                )
                row.status="blocked";row.guard_message=f"Gbot 위험조정 확신도 {confidence:.0f}점이 최소 {float(setting.min_confidence):.0f}점보다 낮습니다.{learning_note}";commit_or_rollback(db);continue
            if code in pending_codes:
                row.status="blocked";row.guard_message="같은 종목의 자동 주문이 아직 체결 대기 중입니다.";commit_or_rollback(db);continue
            recent_fill_times=_auto_recent_filled_action_times(db,user_id,code,now)
            churn_guard=recent_trade_guard_message(
                action=action,now=now,
                recent_same_action_at=recent_fill_times.get(action),
                recent_opposite_action_at=recent_fill_times.get("sell" if action=="buy" else "buy"),
                risk_guard=decision_source=="risk_guard",
                cooldown_minutes=_AUTO_ORDER_COOLDOWN_MINUTES,
            )
            if churn_guard:
                row.status="blocked";row.guard_message=churn_guard;commit_or_rollback(db);continue
            # A user-configured hard stop reduces exposure and must not be
            # disabled by a quota intended to limit ordinary automated orders.
            if today_orders+submitted>=int(setting.max_daily_orders or 1) and decision_source!="risk_guard":
                row.status="blocked";row.guard_message="오늘 자동 주문 최대 횟수에 도달했습니다.";commit_or_rollback(db);continue
            if action=="sell":
                pos=position_by_code.get(code);bot_qty=int(pos.quantity or 0) if pos else 0
                account_qty=int(float((holdings_map.get(code) or {}).get("quantity") or 0))
                max_sell=(account_qty if setting.allow_sell_manual_holdings else min(bot_qty,account_qty))
                if raw_signal=="reduce" and max_sell>0:
                    reduce_pct=max(25,min(75,int(float(raw.get("reduce_pct") or 50))))
                    qty=max(1,min(max_sell,math.ceil(max_sell*reduce_pct/100)))
                    row.guard_message=f"Gbot REDUCE 신호 · 자동보유 {reduce_pct}% 비중축소"
                else:
                    qty=max_sell
                if qty<=0:
                    row.status="blocked";row.guard_message="자동매매가 소유한 매도 가능 수량이 없습니다.";commit_or_rollback(db);continue
                amount=qty*price
            elif action=="buy":
                if new_buys>=int(setting.max_new_buys_per_cycle or 1):
                    row.status="blocked";row.guard_message="이번 판단 주기의 신규 매수 개수 한도에 도달했습니다.";commit_or_rollback(db);continue
                pos=position_by_code.get(code);is_new=not pos or int(pos.quantity or 0)<=0
                if is_new and active_positions+new_buys>=int(setting.max_positions or 1):
                    row.status="blocked";row.guard_message="자동 보유 종목 수 한도에 도달했습니다.";commit_or_rollback(db);continue
                if price<=0:
                    row.status="blocked";row.guard_message="유효한 최근 주가가 없어 주문 수량을 계산할 수 없습니다.";commit_or_rollback(db);continue
                entry_context=learning_context_map.get(code) or {}
                raw_change_rate=entry_context.get("change_rate")
                if raw_change_rate is None:raw_change_rate=getattr(stock,"change_rate",None)
                try:entry_change_rate=float(raw_change_rate) if raw_change_rate is not None else None
                except (TypeError,ValueError):entry_change_rate=None
                current_return_pct=None
                if pos and float(pos.avg_price or 0)>0:
                    current_return_pct=((price/float(pos.avg_price))-1)*100
                entry_guard=stable_entry_guard_message(
                    change_rate=entry_change_rate,current_return_pct=current_return_pct,is_new_position=is_new,
                    max_rise_pct=_AUTO_MAX_ENTRY_RISE_PCT,max_fall_pct=_AUTO_MAX_ENTRY_FALL_PCT,
                    max_add_loss_pct=_AUTO_MAX_ADD_LOSS_PCT,
                )
                if entry_guard:
                    row.status="blocked";row.guard_message=entry_guard;commit_or_rollback(db);continue
                # Position sizing is driven by Gbot confidence, while every
                # monetary setting remains a hard ceiling.  The model's
                # allocation_pct is kept as advisory metadata only: v3.75.1
                # multiplied a 10% hint by a 200,000-won position ceiling and
                # produced 20,000 won, blocking a perfectly valid 44,200-won
                # one-share order.
                strength=_auto_buy_strength(confidence)
                strength_pct=int(round(strength*100))
                gbot_allocation_hint=max(0,min(100,float(raw.get("allocation_pct") or 0)))
                remaining_capital=max(0,float(setting.max_capital or 0)-auto_exposure)
                current_pos_amount=float(pos.invested_amount or 0) if pos else 0
                position_ceiling=max(0,float(setting.max_position_amount or 0))
                remaining_position=max(0,position_ceiling-current_pos_amount)
                cash_available=max(0,cash-min_cash_amount)
                hard_capacity=min(remaining_position,remaining_capital,cash_available)
                target_position=max(0,position_ceiling*strength)
                target_gap=max(0,target_position-current_pos_amount)
                reserve_pct=max(0.0,min(10.0,float(os.getenv("AUTO_MARKET_BUY_RESERVE_PCT","2.0") or 2.0)))
                guarded_price=price*(1.0+reserve_pct/100.0)
                desired=min(target_gap,hard_capacity)

                # If BUY cleared every hard guard but the confidence target is
                # smaller than one share, allow exactly one share only when the
                # buffered market-order cost still fits every hard ceiling.
                minimum_one_share=False
                if 0<target_gap<guarded_price and hard_capacity>=guarded_price:
                    desired=guarded_price
                    minimum_one_share=True

                qty=int(desired//guarded_price);amount=qty*price
                reserved_amount=qty*guarded_price
                learning_penalty=max(0.0,float(raw.get("_learning_penalty") or 0))
                original_confidence=max(confidence,float(raw.get("_gbot_confidence") or confidence))
                learning_matches=(raw.get("_learning_risk") or {}).get("matched_patterns") if isinstance(raw.get("_learning_risk"),dict) else []
                learning_tags=[str(x.get("tag") or "") for x in (learning_matches or []) if isinstance(x,dict) and x.get("tag")]
                sizing_note=(
                    (f"Gbot 확신도 {original_confidence:.0f}점 · 반복실패 감점 -{learning_penalty:g}점 → {confidence:.0f}점 · 매수강도 {strength_pct}%"
                     if learning_penalty>0 else f"Gbot 확신도 {confidence:.0f}점 → 매수강도 {strength_pct}%")
                    + (f" (일치: {', '.join(learning_tags[:3])})" if learning_tags else "")
                    + (f" (Gbot 제안비중 {gbot_allocation_hint:.0f}%는 참고값)" if gbot_allocation_hint else "")
                    + (" · 최소 1주 보정" if minimum_one_share else "")
                )
                if qty<=0:
                    cash_label="키움 주문가능금액" if cash_source=="buying_power" else "계좌 현금(주문가능금액 조회 미지원 fallback)"
                    row.status="blocked"
                    prefix=("확신도 기반 목표 보유금액을 이미 충족했습니다. " if target_gap<=0 else "자금 안전장치 적용 후 1주 이상 매수할 수 없습니다. ")
                    row.guard_message=(
                        f"{prefix}{sizing_note} / {cash_label} {order_cash:,.0f}원 / 미체결매수 {pending_buy_amount:,.0f}원 / "
                        f"현금보유 기준금액 {account_value_reference:,.0f}원 / 최소현금유지 {min_cash_amount:,.0f}원 / "
                        f"자동운용 잔여 {remaining_capital:,.0f}원 / 종목한도 잔여 {remaining_position:,.0f}원 / "
                        f"하드가용금액 {hard_capacity:,.0f}원 / 목표매수금액 {desired:,.0f}원 / 현재가 {price:,.0f}원"
                    )
                    commit_or_rollback(db);continue
                row.guard_message=sizing_note
            row.status="submitting";row.requested_quantity=qty;row.requested_price=price;row.requested_amount=amount
            commit_or_rollback(db)
            row_id=row.id
            try:
                broker,order_no=await _submit_stocklog_mock_order(db=db,user=user,side=action,stock_code=code,quantity=qty,order_type="market",price=None,exchange="KRX")
                row=db.query(AutoTradingDecision).filter(AutoTradingDecision.id==row_id).first()
                if row:
                    row.status="accepted";row.broker_order_no=order_no;row.broker_response_json=json.dumps(broker,ensure_ascii=False);row.order_submitted_at=_auto_trade_now()
                    if action=="buy":
                        _auto_create_learning_case(db,row,candidate=learning_context_map.get(code) or {},raw=raw_for_record,setting=setting)
                    commit_or_rollback(db)
                submitted+=1;pending_codes.add(code)
                if action=="buy":
                    new_buys+=1
                    exposure_reserve=(reserved_amount if 'reserved_amount' in locals() else amount)
                    auto_exposure+=exposure_reserve;cash=max(0,cash-exposure_reserve)
            except Exception as exc:
                rollback_quietly(db);row=db.query(AutoTradingDecision).filter(AutoTradingDecision.id==row_id).first()
                if row:row.status="order_failed";row.guard_message=f"키움 모의주문 전송 실패: {str(exc)[:1000]}";commit_or_rollback(db)
        setting=_auto_setting(db,user_id)
        _auto_monitor_last_gbot[user_id]=time.monotonic()
        if review_only:
            setting.last_error=""
            setting.last_message=f"보유종목 Gbot 재평가 {recorded}건 · 주문 {submitted}건"
        else:
            setting.last_cycle_at=now;setting.next_cycle_at=now+timedelta(minutes=int(setting.interval_minutes or 30));setting.last_error=""
            setting.last_message=f"Gbot 판단 {recorded}건 · 모의주문 {submitted}건"
        commit_or_rollback(db)
        counts=_auto_cycle_decision_counts(db,user_id,cycle_id)
        _auto_cycle_finish(db,cycle_row,status="success",message=setting.last_message,market_open=market_open,kiwoom_ok=kiwoom_ok,gbot_ok=gbot_ok,
                           candidate_count=candidate_count,owned_count=owned_count,**counts)
        return {"ok":True,"message":setting.last_message,"cycle_id":cycle_id,"decisions":recorded,"orders":submitted,"market_open":market_open,"review_only":review_only}
    except GeminiRateLimitError as exc:
        # A 429 must never turn into a broker order made without a fresh Gbot
        # decision. Cool down instead of hammering Gemini every watcher tick.
        logger.warning(
            "auto paper trading Gbot rate limited user_id=%s retry_after=%.1fs models=%s",
            user_id, exc.retry_after_seconds, ",".join(exc.models),
        )
        rollback_quietly(db)
        try:
            now_retry=_auto_trade_now()
            setting=_auto_setting(db,user_id)
            normal_wait=max(5,int(setting.interval_minutes or 30))*60
            cooldown=max(60,min(3600,int(math.ceil(exc.retry_after_seconds))))
            wait_seconds=max(cooldown,min(normal_wait,900))
            if not review_only:
                setting.last_cycle_at=now_retry
                setting.next_cycle_at=now_retry+timedelta(seconds=wait_seconds)
            _auto_monitor_last_gbot[user_id]=time.monotonic()
            setting.last_error=(
                f"StockLog Gbot 요청 한도에 일시적으로 도달해 이번 회차 주문을 건너뛰었습니다. "
                f"약 {max(1,math.ceil(wait_seconds/60))}분 뒤 자동으로 다시 판단합니다."
            )
            setting.last_message="Gbot 호출 한도 대기 · 주문 없음"
            commit_or_rollback(db)
            counts=_auto_cycle_decision_counts(db,user_id,cycle_id)
            _auto_cycle_finish(db,cycle_row,status="rate_limited",message=setting.last_message,error=setting.last_error,market_open=market_open,kiwoom_ok=kiwoom_ok,gbot_ok=False,
                               candidate_count=candidate_count,owned_count=owned_count,**counts)
            friendly=setting.last_error
        except Exception:
            rollback_quietly(db)
            friendly="StockLog Gbot 요청 한도에 일시적으로 도달했습니다. 잠시 후 자동으로 다시 판단합니다."
        return {"ok":False,"message":friendly,"rate_limited":True}
    except Exception as exc:
        logger.exception("auto paper trading cycle failed user_id=%s",user_id)
        rollback_quietly(db)
        try:
            setting=_auto_setting(db,user_id)
            if not review_only:
                setting.last_cycle_at=_auto_trade_now();setting.next_cycle_at=_auto_trade_now()+timedelta(minutes=int(setting.interval_minutes or 30))
            setting.last_error=str(exc)[:3000];setting.last_message=("보유종목 재평가 중 오류가 발생했습니다." if review_only else "자동매매 판단 중 오류가 발생했습니다.");commit_or_rollback(db)
            counts=_auto_cycle_decision_counts(db,user_id,cycle_id)
            _auto_cycle_finish(db,cycle_row,status="error",message=setting.last_message,error=str(exc),market_open=market_open,kiwoom_ok=kiwoom_ok,gbot_ok=gbot_ok,
                               candidate_count=candidate_count,owned_count=owned_count,**counts)
        except Exception:rollback_quietly(db)
        return {"ok":False,"message":str(exc) or "자동매매 판단 실패"}
    finally:
        db.close()
        async with _auto_trade_task_lock:_auto_trade_running_users.discard(user_id)


def _auto_diagnostics_payload(db:Session,user_id:int,setting:AutoTradingSetting):
    now=_auto_trade_now();start=_auto_history_start(now)
    rows=(db.query(AutoTradingCycle).filter(AutoTradingCycle.user_id==user_id,AutoTradingCycle.started_at>=start)
          .order_by(AutoTradingCycle.id.desc()).limit(200).all())
    recent=rows[:10]
    heartbeat_age=(now-_auto_watcher_heartbeat_at).total_seconds() if _auto_watcher_heartbeat_at else None
    watcher_running=bool(_auto_trade_watcher_task and not _auto_trade_watcher_task.done())
    errors=sum(1 for x in rows if x.status=="error" and not is_recoverable_gbot_response_error(x.error_message))
    safe_skips=sum(1 for x in rows if x.status=="skipped" or is_recoverable_gbot_response_error(x.error_message))
    effective_last_error=setting.last_error or _auto_watcher_last_error
    if is_recoverable_gbot_response_error(effective_last_error):
        effective_last_error=""
    health=diagnostic_health(
        watcher_running=watcher_running,heartbeat_age_seconds=heartbeat_age,enabled=bool(setting.enabled),
        market_open=_auto_market_open(setting,now),today_cycles=len(rows),error_cycles=errors,last_error=effective_last_error,
    )
    if health.get("level")=="ok":
        health={"level":"ok","label":"정상 운용","message":"자동 운용 서비스와 최근 실행 기록이 정상입니다."}
    elif re.search(r"watcher|heartbeat|감시 프로세스",f"{health.get('label','')} {health.get('message','')}",re.IGNORECASE):
        health={"level":health.get("level") or "error","label":"자동 운용 확인 필요","message":"자동 운용 서비스 상태를 확인해주세요."}
    else:
        health={**health,"message":_sanitize_public_ai_result(health.get("message") or "자동 운용 상태를 확인해주세요.")}
    successful=[x for x in rows if x.status=="success"]
    latest_cycle=rows[0] if rows else None
    latest_gbot_decision=(db.query(AutoTradingDecision)
        .filter(AutoTradingDecision.user_id==user_id,AutoTradingDecision.model_name!="StockLog Risk Guard")
        .order_by(AutoTradingDecision.id.desc()).first())
    gemini_creds=get_provider_credentials(PROVIDER_GEMINI,db)
    gbot_configured=bool((gemini_creds.get("api_key") or "").strip() and gemini_creds.get("source") not in {"none","disabled"})
    if not gbot_configured:
        integrity_level="error";integrity_label="Gbot 연결 필요";integrity_message="Gbot 연결 정보가 없어 자동 주문 판단을 실행할 수 없습니다."
    elif latest_cycle and (latest_cycle.status=="skipped" or is_recoverable_gbot_response_error(latest_cycle.error_message)):
        safe_wait_message=(
            latest_cycle.message
            if latest_cycle.status=="skipped"
            else "Gbot 응답이 주문 안전 기준을 충족하지 못해 주문 없이 다음 회차를 기다립니다."
        )
        integrity_level="idle";integrity_label="안전 대기";integrity_message=_sanitize_public_ai_result(safe_wait_message)
    elif latest_cycle and latest_cycle.status in {"error","rate_limited"}:
        integrity_level="warning";integrity_label="최근 Gbot 확인 필요";integrity_message=_sanitize_public_ai_result(latest_cycle.error_message or latest_cycle.message or "최근 Gbot 회차가 정상 완료되지 않았습니다.")
    elif latest_cycle and latest_cycle.gbot_ok:
        integrity_level="healthy";integrity_label="Gbot 정상";integrity_message="최근 자동 판단이 정상적으로 완료되었습니다. Gbot 판단을 완료하지 못한 회차에는 주문하지 않습니다."
    else:
        integrity_level="idle";integrity_label="Gbot 판단 대기";integrity_message="아직 오늘 완료된 Gbot 판단 회차가 없습니다. 1회 판단으로 연결과 응답 품질을 확인할 수 있습니다."
    gbot_integrity={
        "level":integrity_level,"label":integrity_label,"message":integrity_message,"configured":gbot_configured,
        "last_gbot_at":latest_gbot_decision.decided_at.isoformat() if latest_gbot_decision and latest_gbot_decision.decided_at else None,
        "last_decision":_auto_decision_json(latest_gbot_decision) if latest_gbot_decision else None,
        "latest_cycle":_auto_cycle_json(latest_cycle) if latest_cycle else None,
        "risk_rule_override":bool(float(setting.stop_loss_pct or 0)>0 or float(setting.take_profit_pct or 0)>0),
        "risk_rule_text":"설정한 손절/익절 가격 규칙은 Gbot 의견과 별개로 보유수량 매도를 우선 실행할 수 있습니다.",
        "min_confidence":float(setting.min_confidence or 0),
    }
    return {
        "health":health,"gbot_integrity":gbot_integrity,
        "today":{
            "cycles":len(rows),"success":len(successful),"errors":errors,
            "rate_limited":sum(1 for x in rows if x.status=="rate_limited"),"skipped":safe_skips,
            "candidate_total":sum(int(x.candidate_count or 0) for x in rows),
            "decision_total":sum(int(x.decision_count or 0) for x in rows),
            "buy_total":sum(int(x.buy_count or 0) for x in rows),"sell_total":sum(int(x.sell_count or 0) for x in rows),
            "hold_total":sum(int(x.hold_count or 0) for x in rows),"blocked_total":sum(int(x.blocked_count or 0) for x in rows),
            "order_total":sum(int(x.order_count or 0) for x in rows),
            "gbot_success_cycles":sum(1 for x in rows if x.gbot_ok),
        },
        "last_successful_cycle":_auto_cycle_json(successful[0]) if successful else None,
        "recent_cycles":[_auto_cycle_json(x) for x in recent],
    }


def _auto_status_payload(db:Session,user_id:int,portfolio_payload:dict|None=None):
    setting=_auto_setting(db,user_id)
    if portfolio_payload is None:
        snap=db.query(KiwoomAccountSnapshot).filter(KiwoomAccountSnapshot.user_id==user_id).first()
        portfolio=_snapshot_to_payload(snap) or {"summary":{},"orders":[]}
    else:
        portfolio=portfolio_payload
    _auto_reconcile_orders(db,user_id,portfolio)
    _auto_rebuild_positions_from_fills(db,user_id,portfolio)
    _auto_cap_positions_to_account(db,user_id,portfolio)
    _auto_refresh_learning_outcomes(db,user_id,portfolio)
    positions=db.query(AutoTradingPosition).filter(AutoTradingPosition.user_id==user_id,AutoTradingPosition.quantity>0).order_by(AutoTradingPosition.updated_at.desc()).all()
    codes=[p.stock_code for p in positions]
    visible_codes=_stocklog_public_code_set(db,codes)
    visible_positions=[p for p in positions if p.stock_code in visible_codes]
    hidden_legacy_position_count=max(0,len(positions)-len(visible_positions))
    # Keep raw stock rows internal for valuation/account-safety only. Excluded
    # legacy holdings are never returned by the public auto-trading status.
    valuation_stocks={x.code:x for x in db.query(Stock).filter(Stock.code.in_(codes)).all()} if codes else {}
    stocks={x.code:x for x in db.query(Stock).filter(Stock.code.in_(visible_codes),*_stocklog_public_clauses()).all()} if visible_codes else {}
    # Keep status lightweight. Full audit history is paginated by /history.
    decisions=db.query(AutoTradingDecision).filter(AutoTradingDecision.user_id==user_id).order_by(AutoTradingDecision.id.desc()).limit(40).all()
    recent_fills=(db.query(AutoTradingDecision).filter(
        AutoTradingDecision.user_id==user_id,
        AutoTradingDecision.filled_quantity>0,
        AutoTradingDecision.status.in_(["partial","filled"]),
    ).order_by(AutoTradingDecision.updated_at.desc(),AutoTradingDecision.id.desc()).limit(30).all())
    decision_codes=_stocklog_public_code_set(db,[x.stock_code for x in decisions]+[x.stock_code for x in recent_fills])
    decisions=[x for x in decisions if x.stock_code in decision_codes][:12]
    recent_fills=[x for x in recent_fills if x.stock_code in decision_codes][:8]
    pending_order_count=db.query(AutoTradingDecision).filter(
        AutoTradingDecision.user_id==user_id,
        AutoTradingDecision.status.in_(["accepted","partial"]),
    ).count()
    # Use the same broker holding/current-price basis as the portfolio page.
    # Stock.price can be stale/zero and the bot ledger may represent only part
    # of a mixed holding, so value only the Gbot-attributed quantity at the
    # broker holding's normalized current price.
    holding_map=_auto_account_holdings_map(portfolio)
    total_invested=0.0
    total_eval=0.0
    total_auto_pnl=0.0
    total_auto_fee=0.0
    auto_position_metrics={}
    market_phase=krx_market_phase(_auto_trade_now())
    for p in positions:
        h=holding_map.get(p.stock_code) or {}
        actual_qty=max(0,int(float(h.get("quantity") or 0)))
        bot_qty=min(actual_qty,max(0,int(p.quantity or 0))) if actual_qty>0 else max(0,int(p.quantity or 0))
        current=max(0.0,float(h.get("current_price") or h.get("price") or 0))
        if current<=0 and actual_qty>0:
            evaluation=max(0.0,float(h.get("evaluation_amount") or 0))
            if evaluation>0: current=evaluation/actual_qty
        if current<=0 and valuation_stocks.get(p.stock_code):
            current=max(0.0,float(valuation_stocks[p.stock_code].price or 0))
        if current<=0: current=max(0.0,float(p.avg_price or 0))
        ratio=(bot_qty/actual_qty) if actual_qty>0 else 1.0
        broker_purchase=max(0.0,float(h.get("purchase_amount") or 0))
        attributed_cost=(broker_purchase*ratio) if broker_purchase>0 and actual_qty>0 else float(p.invested_amount or 0)
        total_invested+=attributed_cost
        broker_eval=max(0.0,float(h.get("evaluation_amount") or 0))
        attributed_eval=(broker_eval*ratio) if broker_eval>0 and actual_qty>0 else current*bot_qty
        attributed_pnl=float(h.get("profit_loss") or 0)*ratio if actual_qty>0 else (attributed_eval-attributed_cost)
        gross_market_value=current*bot_qty
        explicit_fee=max(0.0,float(h.get("fee_amount") or 0))*ratio if actual_qty>0 else 0.0
        implied_fee=max(0.0,gross_market_value-attributed_cost-attributed_pnl) if gross_market_value>0 and attributed_cost>0 else 0.0
        attributed_fee=explicit_fee if explicit_fee>0 else implied_fee
        fee_estimated=bool(explicit_fee<=0 and attributed_fee>0)
        stock_row=valuation_stocks.get(p.stock_code)
        return_rates=auto_position_return_rates(
            current_price=current,
            average_price=float(p.avg_price or 0),
            portfolio_day_return_rate=float(h.get("day_return_rate") or 0),
            market_change_rate=float(stock_row.change_rate or 0) if stock_row else 0.0,
            day_profit_basis=str(h.get("day_profit_basis") or ""),
            market_phase=market_phase,
        )
        total_eval+=attributed_eval
        total_auto_pnl+=attributed_pnl
        total_auto_fee+=attributed_fee
        auto_position_metrics[p.stock_code]={
            "quantity":bot_qty,
            "avg_price":float(p.avg_price or 0),
            "current_price":current,
            "purchase_amount":attributed_cost,
            "evaluation_amount":attributed_eval,
            "market_value":gross_market_value,
            "fee_amount":attributed_fee,
            "fee_estimated":fee_estimated,
            "profit_loss":attributed_pnl,
            "profit_loss_after_fee":attributed_pnl,
            "return_rate":return_rates["return_rate"],
            "net_return_rate":((attributed_pnl/attributed_cost)*100.0) if attributed_cost>0 else 0.0,
            "day_return_rate":return_rates["day_return_rate"],
            "day_profit":float(h.get("day_profit") or 0)*ratio if actual_qty>0 else 0.0,
        }
    account_summary=(portfolio.get("summary") or {})
    effective_cash,effective_cash_source=_auto_order_cash(account_summary)
    account_value_reference=_auto_account_value_reference(account_summary,effective_cash)
    reserve_amount=account_value_reference*float(setting.min_cash_ratio or 0)/100.0
    capital_committed,capital_meta=_auto_committed_capital(portfolio,positions,0)
    # Display and enforcement share the same conservative principal basis.
    total_invested=max(total_invested,capital_committed)
    monitor_health=_auto_monitor_health_payload(user_id,setting,len(visible_positions))
    return {"settings":_auto_setting_json(setting),"running":user_id in _auto_trade_running_users,"market_open":_auto_market_open(setting),"market_phase":market_phase,
            "diagnostics":_auto_diagnostics_payload(db,user_id,setting),
            "learning":_auto_learning_summary(db,user_id),
            "monitoring":{**monitor_health,"items":_auto_monitor_public_state(user_id,visible_positions)},
            "summary":{"auto_invested":total_invested,"auto_evaluation":total_eval,"auto_profit_loss":total_auto_pnl,
                       "auto_fee_amount":total_auto_fee,"auto_profit_loss_after_fee":total_auto_pnl,
                       "capital_guard_committed":capital_committed,"capital_guard_breakdown":capital_meta,
                       "capital_limit_exceeded":bool(float(setting.max_capital or 0)>0 and capital_committed>float(setting.max_capital or 0)+1),
                       "capital_limit_over_amount":max(0.0,capital_committed-float(setting.max_capital or 0)),
                       "position_count":len(visible_positions),"hidden_legacy_position_count":hidden_legacy_position_count,"account_total_asset":float(account_summary.get("total_asset") or 0),
                       "account_cash":float(account_summary.get("cash") or 0),"buying_power":float(account_summary.get("buying_power") or 0),
                       "buying_power_available":bool(account_summary.get("buying_power_available")),
                       "effective_order_cash":effective_cash,"effective_order_cash_source":effective_cash_source,
                       "account_value_reference":account_value_reference,"cash_reserve_amount":reserve_amount},
            "positions":[{**_auto_position_json(p,stocks.get(p.stock_code)),**(auto_position_metrics.get(p.stock_code) or {})} for p in visible_positions],
            "decisions":[_auto_decision_json(x) for x in decisions],
            "recent_fills":[_auto_decision_json(x) for x in recent_fills],
            "pending_order_count":int(pending_order_count or 0)}


@app.get("/api/trading/auto/status")
async def auto_trading_status(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"mock_trading")
    # The browser may poll this endpoint every 5 seconds.  Never turn that into
    # a 5-second Kiwoom account poll: reuse the snapshot until the normal broker
    # refresh floor (20s by default) has elapsed, even when buying-power fields
    # are unavailable and StockLog is using the cash fallback.
    snap=db.query(KiwoomAccountSnapshot).filter(KiwoomAccountSnapshot.user_id==u.id).first()
    broker_floor=max(10.0,float(os.getenv("KIWOOM_ACCOUNT_SYNC_MIN_INTERVAL_SECONDS","20") or 20))
    snapshot_fresh=bool(
        snap and snap.last_success_at
        and (datetime.now()-snap.last_success_at).total_seconds()<broker_floor
    )
    if snapshot_fresh:
        portfolio=_snapshot_to_payload(snap) or {"summary":{},"orders":[]}
    else:
        try:
            portfolio=await _sync_kiwoom_account(u,db,force=False)
        except Exception:
            snap=db.query(KiwoomAccountSnapshot).filter(KiwoomAccountSnapshot.user_id==u.id).first()
            portfolio=_snapshot_to_payload(snap) or {"summary":{},"orders":[]}
    portfolio=_enrich_portfolio_holdings(portfolio,db)
    portfolio=_portfolio_apply_live_metrics(portfolio,db)
    return _auto_status_payload(db,u.id,portfolio)


@app.get("/api/trading/auto/history")
def auto_trading_history(
    mode:str=Query("orders",pattern=r"^(orders|all)$"),
    page:int=Query(1,ge=1),
    page_size:int=Query(12,ge=5,le=30),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    """Paginated Gbot audit. A broker fill updates the same order card row."""
    _require_feature(u,db,"mock_trading")
    snap=db.query(KiwoomAccountSnapshot).filter(KiwoomAccountSnapshot.user_id==u.id).first()
    portfolio=_snapshot_to_payload(snap) or {"summary":{},"orders":[]}
    _auto_reconcile_orders(db,u.id,portfolio)
    query=db.query(AutoTradingDecision).filter(AutoTradingDecision.user_id==u.id)
    if mode=="orders":
        query=_auto_order_history_filter(query)
    total=int(query.count() or 0)
    pages=max(1,math.ceil(total/page_size))
    page=min(page,pages)
    rows=(query.order_by(AutoTradingDecision.id.desc())
          .offset((page-1)*page_size).limit(page_size).all())
    return {
        "items":[_auto_decision_json(x) for x in rows],
        "page":page,"pages":pages,"page_size":page_size,"total":total,
    }


@app.get("/api/trading/auto/cycles")
def auto_trading_cycles(
    page:int=Query(1,ge=1),page_size:int=Query(15,ge=5,le=50),
    u:User=Depends(current_user),db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    query=db.query(AutoTradingCycle).filter(AutoTradingCycle.user_id==u.id)
    total=int(query.count() or 0);pages=max(1,math.ceil(total/page_size));page=min(page,pages)
    rows=(query.order_by(AutoTradingCycle.id.desc()).offset((page-1)*page_size).limit(page_size).all())
    return {"items":[_auto_cycle_json(x) for x in rows],"page":page,"pages":pages,"page_size":page_size,"total":total}


@app.get("/api/trading/auto/learning")
def auto_trading_learning(
    page:int=Query(1,ge=1),page_size:int=Query(12,ge=5,le=30),
    u:User=Depends(current_user),db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    snap=db.query(KiwoomAccountSnapshot).filter(KiwoomAccountSnapshot.user_id==u.id).first()
    portfolio=_snapshot_to_payload(snap) or {"summary":{},"holdings":[]}
    _auto_refresh_learning_outcomes(db,u.id,portfolio)
    query=db.query(AutoTradingOutcome).filter(AutoTradingOutcome.user_id==u.id)
    total=int(query.count() or 0);pages=max(1,math.ceil(total/page_size));page=min(page,pages)
    rows=(query.order_by(AutoTradingOutcome.id.desc()).offset((page-1)*page_size).limit(page_size).all())
    return {"summary":_auto_learning_summary(db,u.id),"items":[_auto_learning_case_json(x) for x in rows],"page":page,"pages":pages,"page_size":page_size,"total":total}


@app.post("/api/trading/auto/learning/review-ready")
async def auto_trading_learning_review_ready(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"mock_trading")
    ready=db.query(AutoTradingOutcome.id).filter(AutoTradingOutcome.user_id==u.id,AutoTradingOutcome.status=="review_ready",AutoTradingOutcome.reviewed_at.is_(None)).count()
    if ready<=0:return {"ok":True,"message":"현재 AI 사후분석 대기 건이 없습니다.","ready":0}
    if u.id in _auto_learning_running_users:return {"ok":True,"message":"이미 AI 사후분석이 진행 중입니다.","ready":ready}
    asyncio.create_task(_auto_review_learning_cases_once(u.id))
    return {"ok":True,"message":f"AI 사후분석을 시작했습니다. 대기 {ready}건을 순차적으로 분석합니다.","ready":ready}


@app.delete("/api/trading/auto/history/{decision_id}")
def auto_trading_history_delete(
    decision_id:int,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    row=db.query(AutoTradingDecision).filter(AutoTradingDecision.id==decision_id,AutoTradingDecision.user_id==u.id).first()
    if not row:
        raise HTTPException(404,"자동매매 이력을 찾을 수 없습니다.")
    if row.status in {"accepted","partial","submitting"}:
        raise HTTPException(409,"미체결 또는 진행 중인 주문 이력은 체결 상태 확인을 위해 삭제할 수 없습니다.")
    db.delete(row);commit_or_rollback(db)
    return {"ok":True,"message":"자동매매 이력을 삭제했습니다."}


@app.delete("/api/trading/auto/history")
def auto_trading_history_clear(
    mode:str=Query("orders",pattern=r"^(orders|all)$"),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"mock_trading")
    query=db.query(AutoTradingDecision).filter(
        AutoTradingDecision.user_id==u.id,
        ~AutoTradingDecision.status.in_(["accepted","partial","submitting"]),
    )
    if mode=="orders":
        query=_auto_order_history_filter(query)
    count=query.count()
    query.delete(synchronize_session=False);commit_or_rollback(db)
    return {"ok":True,"message":f"종료된 자동매매 이력 {count:,}건을 삭제했습니다.","deleted":count}


def _trade_fill_poll_lock(user_id:int):
    lock=_trade_fill_poll_locks.get(user_id)
    if lock is None:
        lock=asyncio.Lock()
        _trade_fill_poll_locks[user_id]=lock
    return lock


def _trade_fill_events_from_orders(db:Session,user_id:int,orders:list[dict]):
    execution_rows=[x for x in (orders or []) if isinstance(x,dict) and str(x.get("source_tr") or "")=="ka10076" and float(x.get("filled_qty") or 0)>0]
    if not execution_rows:return []
    order_nos={str(x.get("order_no") or "").strip() for x in execution_rows if str(x.get("order_no") or "").strip()}
    audits=(db.query(OrderAudit).filter(OrderAudit.user_id==user_id,OrderAudit.broker_order_no.in_(order_nos)).order_by(OrderAudit.id.desc()).all()) if order_nos else []
    audit_side={str(x.broker_order_no or "").strip():x.side for x in audits if str(x.broker_order_no or "").strip()}
    audit_qty={str(x.broker_order_no or "").strip():int(x.quantity or 0) for x in audits if str(x.broker_order_no or "").strip()}
    auto_rows=(db.query(AutoTradingDecision).filter(AutoTradingDecision.user_id==user_id,AutoTradingDecision.broker_order_no.in_(order_nos)).all()) if order_nos else []
    auto_order_nos={str(x.broker_order_no or "").strip() for x in auto_rows if str(x.broker_order_no or "").strip()}
    auto_qty={str(x.broker_order_no or "").strip():int(x.requested_quantity or 0) for x in auto_rows if str(x.broker_order_no or "").strip()}
    codes={str(x.get("code") or "").strip() for x in execution_rows if str(x.get("code") or "").strip()}
    stock_names={x.code:x.name for x in db.query(Stock).filter(Stock.code.in_(codes)).all()} if codes else {}

    grouped={}
    for row in execution_rows:
        order_no=str(row.get("order_no") or "").strip()
        code=str(row.get("code") or "").strip()
        raw_side=str(audit_side.get(order_no) or row.get("side") or "").strip().lower()
        side="sell" if raw_side in ("sell","매도") or "sell" in raw_side or "매도" in raw_side else "buy"
        price=max(0.0,float(row.get("price") or 0))
        qty=max(0,int(float(row.get("filled_qty") or 0)))
        raw_time=re.sub(r"[^0-9]","",str(row.get("time") or ""))[-6:]
        key=(order_no,code,side)
        item=grouped.setdefault(key,{
            "order_no":order_no,"code":code,"name":str(row.get("name") or stock_names.get(code) or code),"side":side,
            "quantity":0,"fill_value":0.0,"latest_time":"","requested_quantity":0,
        })
        item["quantity"]+=qty
        item["fill_value"]+=price*qty
        if raw_time>=item["latest_time"]:item["latest_time"]=raw_time
        item["requested_quantity"]=max(
            int(item["requested_quantity"] or 0),max(0,int(float(row.get("order_qty") or 0))),
            int(audit_qty.get(order_no,0)),int(auto_qty.get(order_no,0)),
        )

    events=[]
    for key,item in grouped.items():
        total_qty=int(item["quantity"] or 0)
        avg_price=(float(item["fill_value"] or 0)/total_qty) if total_qty else 0.0
        raw_key="|".join(map(str,key))
        event_id=hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
        when=_auto_broker_fill_time({"time":item.get("latest_time")})
        order_qty=int(item.get("requested_quantity") or 0)
        events.append({
            "id":event_id,"order_no":item["order_no"],"code":item["code"],"name":item["name"],"side":item["side"],
            "quantity":total_qty,"price":avg_price,"amount":float(item["fill_value"] or 0),
            "time":when.isoformat(),"partial":bool(order_qty and total_qty<order_qty),"order_quantity":order_qty,
            "order_filled_quantity":total_qty,"source":"auto" if item["order_no"] in auto_order_nos else "manual",
        })
    events.sort(key=lambda x:(x.get("time") or "",x.get("order_no") or "",x.get("id") or ""),reverse=True)
    return events[:40]


@app.get("/api/trading/fill-events")
async def trading_fill_events(u:User=Depends(current_user),db:Session=Depends(get_db)):
    """Lightweight account-wide execution feed used by the global UI notifier.

    It polls only Kiwoom's execution TR, not the full portfolio.  The endpoint is
    safe to call from every StockLog page and keeps a short per-user server cache
    so multiple browser renders cannot hammer the broker API.
    """
    _require_feature(u,db,"mock_trading")
    ttl=max(2.5,min(10.0,float(os.getenv("KIWOOM_FILL_POLL_MIN_INTERVAL_SECONDS","5") or 5)))
    now=time.monotonic()
    cached=_trade_fill_poll_cache.get(u.id)
    if cached and now-float(cached.get("at") or 0)<ttl:
        return {"items":cached.get("items") or [],"cached":True,"server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
    lock=_trade_fill_poll_lock(u.id)
    async with lock:
        now=time.monotonic();cached=_trade_fill_poll_cache.get(u.id)
        if cached and now-float(cached.get("at") or 0)<ttl:
            return {"items":cached.get("items") or [],"cached":True,"server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
        try:
            _,cli=client_for(u,db)
            # This endpoint is polled globally; release its DB checkout before Kiwoom.
            commit_or_rollback(db)
            await cli.issue_token()
            rows=await cli.recent_executions()
            # Keep the original automatic order card current even while the user
            # is browsing another page.
            _auto_reconcile_orders(db,u.id,{"orders":rows})
            items=_trade_fill_events_from_orders(db,u.id,rows)
            _trade_fill_poll_cache[u.id]={"at":time.monotonic(),"items":items}
            return {"items":items,"cached":False,"server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
        except HTTPException as exc:
            if int(exc.status_code or 0)==400:
                return {"items":[],"cached":False,"configured":False,"server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
            logger.warning("global trade fill poll http error user_id=%s error=%s",u.id,_sync_error_text(exc,500))
            if cached:return {"items":cached.get("items") or [],"cached":True,"stale":True,"server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
            return {"items":[],"cached":False,"error":"체결 알림 연결을 잠시 확인하지 못했습니다.","server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
        except Exception as exc:
            logger.warning("global trade fill poll failed user_id=%s error=%s",u.id,_sync_error_text(exc,500))
            if cached:return {"items":cached.get("items") or [],"cached":True,"stale":True,"server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}
            return {"items":[],"cached":False,"error":"체결 알림 연결을 잠시 확인하지 못했습니다.","server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}


@app.get("/api/trading/auto/options")
def auto_trading_options(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"mock_trading")
    categories=set()
    for column in (Stock.category,Stock.sector,Stock.industry_name,Stock.theme_group):
        for value, in db.query(column).filter(*_stocklog_public_clauses()).distinct().all():
            text_value=str(value or "").strip()
            if text_value and text_value not in {"기타","종합","기타 사업"}:categories.add(text_value)
    themes=sorted({str(x[0]).strip() for x in (db.query(StockTheme.theme_name).join(Stock,Stock.code==StockTheme.stock_code).filter(*_stocklog_public_clauses()).distinct().all()) if x[0] and str(x[0]).strip()})
    return {"markets":["KOSPI","KOSDAQ"],"categories":sorted(categories)[:220],"themes":themes[:700]}


@app.put("/api/trading/auto/settings")
def auto_trading_save_settings(body:AutoTradingSettingsIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"mock_trading");row=_auto_setting(db,u.id)
    if body.max_price and body.max_price<body.min_price:raise HTTPException(422,"최대 주가는 최소 주가보다 커야 합니다.")
    if body.max_market_cap and body.max_market_cap<body.min_market_cap:raise HTTPException(422,"최대 시가총액은 최소 시가총액보다 커야 합니다.")
    if body.max_position_amount>body.max_capital:raise HTTPException(422,"종목당 최대 투자금액은 자동운용 총한도보다 클 수 없습니다.")
    invalid_markets={str(x or "").upper() for x in body.markets}-set(STOCKLOG_PUBLIC_MARKETS)
    if invalid_markets:raise HTTPException(422,"자동매매 시장은 KOSPI와 KOSDAQ만 선택할 수 있습니다.")
    if not body.use_all_themes and not body.themes:raise HTTPException(422,"전체 테마를 끄면 거래할 테마를 1개 이상 선택해주세요.")
    try:
        start_clock=datetime.strptime(body.trading_start,"%H:%M")
        end_clock=datetime.strptime(body.trading_end,"%H:%M")
    except ValueError as exc:
        raise HTTPException(422,"자동 거래 시간을 확인해주세요.") from exc
    if start_clock>=end_clock:raise HTTPException(422,"자동 거래 종료 시간은 시작 시간보다 늦어야 합니다.")
    for key,value in body.model_dump().items():
        if key=="markets":row.markets_json=json.dumps(value,ensure_ascii=False)
        elif key=="categories":row.categories_json=json.dumps(value,ensure_ascii=False)
        elif key=="themes":row.themes_json=json.dumps(value,ensure_ascii=False)
        else:setattr(row,key,value)
    if row.enabled:row.next_cycle_at=_auto_trade_now()+timedelta(minutes=int(row.interval_minutes or 30))
    commit_or_rollback(db);db.refresh(row)
    return {"ok":True,"message":"자동매매 설정을 저장했습니다.","settings":_auto_setting_json(row)}


@app.post("/api/trading/auto/start")
def auto_trading_start(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"mock_trading")
    cred=db.query(KiwoomCredential).filter(KiwoomCredential.user_id==u.id).first()
    if not cred or not cred.use_mock:raise HTTPException(400,"자동매매는 키움 모의투자 연결에서만 시작할 수 있습니다.")
    if not (get_provider_credentials(PROVIDER_GEMINI,db).get("api_key") or "").strip():raise HTTPException(400,"StockLog Gbot 연결 정보를 먼저 설정해주세요.")
    row=_auto_setting(db,u.id);row.enabled=True;row.last_error="";row.last_message="자동매매가 시작되었습니다.";row.next_cycle_at=_auto_trade_now();commit_or_rollback(db)
    return {"ok":True,"message":"StockLog Gbot 자동 모의투자를 시작했습니다.","settings":_auto_setting_json(row)}


@app.post("/api/trading/auto/stop")
def auto_trading_stop(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"mock_trading");row=_auto_setting(db,u.id);row.enabled=False;row.next_cycle_at=None;row.last_message="자동매매가 중지되었습니다.";commit_or_rollback(db)
    return {"ok":True,"message":"자동 모의투자를 중지했습니다. 이미 전송된 모의주문은 취소되지 않습니다.","settings":_auto_setting_json(row)}


@app.post("/api/trading/auto/run-once")
async def auto_trading_run_once(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"mock_trading")
    cred=db.query(KiwoomCredential).filter(KiwoomCredential.user_id==u.id).first()
    if not cred or not cred.use_mock:raise HTTPException(400,"자동매매 판단은 키움 모의투자 연결에서만 사용할 수 있습니다.")
    if not (get_provider_credentials(PROVIDER_GEMINI,db).get("api_key") or "").strip():raise HTTPException(400,"StockLog Gbot 연결 정보를 먼저 설정해주세요.")
    if u.id in _auto_trade_running_users:raise HTTPException(409,"이미 Gbot 자동매매 판단이 진행 중입니다.")
    setting=_auto_setting(db,u.id)
    now=_auto_trade_now()
    last_error=str(setting.last_error or "")
    if ("한도" in last_error or "429" in last_error or "rate" in last_error.lower() or "quota" in last_error.lower()) and setting.next_cycle_at and setting.next_cycle_at>now:
        remain=max(1,math.ceil((setting.next_cycle_at-now).total_seconds()/60))
        raise HTTPException(429,f"StockLog Gbot 호출 한도 대기 중입니다. 약 {remain}분 뒤 다시 판단할 수 있습니다.")
    # Do not keep the request open for a long Gemini call. The status endpoint is polled by the page.
    asyncio.create_task(_run_auto_trade_cycle(u.id,manual=True))
    return {"ok":True,"message":"Gbot 1회 판단을 시작했습니다. 거래시간 밖이면 주문 없이 판단 기록만 남깁니다."}


async def _auto_reconcile_pending_fills(user_id:int):
    """Keep automatic order cards current even when no browser is open."""
    db=SessionLocal()
    try:
        user=db.query(User).filter(User.id==user_id,User.is_active==True).first()
        if not user:return
        _,cli=client_for(user,db)
        commit_or_rollback(db)
        await cli.issue_token()
        rows=await cli.recent_executions()
        _auto_reconcile_orders(db,user_id,{"orders":rows})
    except HTTPException:
        rollback_quietly(db)
    except Exception as exc:
        rollback_quietly(db)
        logger.debug("auto pending fill reconciliation skipped user_id=%s error=%s",user_id,_sync_error_text(exc,300))
    finally:
        db.close()


async def _auto_trading_watcher_loop():
    global _auto_watcher_heartbeat_at,_auto_watcher_last_error,_auto_watcher_last_scan
    while True:
        try:
            _auto_watcher_heartbeat_at=_auto_trade_now()
            db=SessionLocal()
            try:
                now=_auto_trade_now()
                rows=db.query(AutoTradingSetting).filter(AutoTradingSetting.enabled==True).all()
                due=[r.user_id for r in rows if (r.next_cycle_at is None or r.next_cycle_at<=now) and r.user_id not in _auto_trade_running_users and _auto_market_open(r,now)]
                monitor_due=[r.user_id for r in rows if _auto_market_open(r,now) and (time.monotonic()-float(_auto_monitor_last_check.get(r.user_id) or 0)>=_AUTO_MONITOR_SECONDS)]
                pending_ids={x[0] for x in db.query(AutoTradingDecision.user_id).filter(AutoTradingDecision.status.in_(["accepted","partial"])).distinct().all()}
                learning_ids={x[0] for x in db.query(AutoTradingOutcome.user_id).filter(AutoTradingOutcome.status=="review_ready",AutoTradingOutcome.reviewed_at.is_(None)).distinct().all()}
                _auto_watcher_last_scan={"enabled_users":len(rows),"due_users":len(due),"monitor_due_users":len(monitor_due),"pending_users":len(pending_ids),"learning_due_users":len(learning_ids)}
                _auto_watcher_last_error=""
            finally:db.close()
            for user_id in (pending_ids-set(due)):asyncio.create_task(_auto_reconcile_pending_fills(user_id))
            for user_id in monitor_due:
                if user_id not in _auto_trade_running_users:
                    _auto_monitor_last_check[user_id]=time.monotonic()
                    asyncio.create_task(_auto_monitor_positions_once(user_id))
            for user_id in learning_ids:
                last=float(_auto_learning_last_scan.get(user_id) or 0)
                if time.monotonic()-last>=_AUTO_LEARNING_SCAN_SECONDS and user_id not in _auto_learning_running_users:
                    _auto_learning_last_scan[user_id]=time.monotonic()
                    asyncio.create_task(_auto_review_learning_cases_once(user_id))
            for user_id in due:asyncio.create_task(_run_auto_trade_cycle(user_id))
            _auto_watcher_heartbeat_at=_auto_trade_now()
        except asyncio.CancelledError:raise
        except Exception as exc:
            _auto_watcher_last_error=_sync_error_text(exc,1000)
            logger.exception("auto trading watcher failed")
        await asyncio.sleep(30)


@app.on_event("startup")
async def start_auto_trading_watcher():
    global _auto_trade_watcher_task
    if _auto_trade_watcher_task is None or _auto_trade_watcher_task.done():_auto_trade_watcher_task=asyncio.create_task(_auto_trading_watcher_loop())


@app.on_event("shutdown")
async def stop_auto_trading_watcher():
    global _auto_trade_watcher_task
    if _auto_trade_watcher_task and not _auto_trade_watcher_task.done():
        _auto_trade_watcher_task.cancel()
        try:await _auto_trade_watcher_task
        except BaseException:pass


# ---------------------------------------------------------------------------
# Production auto trading. Storage, broker client, snapshots and audits are
# intentionally separate from paper trading. Every broker path fails closed.
# ---------------------------------------------------------------------------
def _live_auto_setting(db:Session,user_id:int,create:bool=True):
    row=db.query(LiveAutoTradingSetting).filter(LiveAutoTradingSetting.user_id==user_id).first()
    if not row and create:
        row=LiveAutoTradingSetting(user_id=user_id);db.add(row);commit_or_rollback(db);db.refresh(row)
    return row


def _live_auto_decision_json(row:LiveAutoTradingDecision):
    return _sanitize_public_ai_result({
        "id":row.id,"cycle_id":row.cycle_id,"code":row.stock_code,"name":row.stock_name,
        "action":row.action,"status":row.status,"confidence":float(row.confidence or 0),
        "requested_quantity":int(row.requested_quantity or 0),"requested_price":float(row.requested_price or 0),
        "requested_amount":float(row.requested_amount or 0),"filled_quantity":int(row.filled_quantity or 0),
        "filled_price":float(row.filled_price or 0),"filled_amount":float(row.filled_amount or 0),
        "reason":row.reason or "","evidence":_safe_json_list(row.evidence_json),"risks":_safe_json_list(row.risks_json),
        "exit_plan":row.exit_plan or "","guard_message":row.guard_message or "","broker_order_no":row.broker_order_no or "",
        "order_attempted":bool(row.order_submitted_at or row.broker_order_no),
        "decided_at":row.decided_at.isoformat() if row.decided_at else None,
        "order_submitted_at":row.order_submitted_at.isoformat() if row.order_submitted_at else None,
        "filled_at":row.filled_at.isoformat() if row.filled_at else None,
    })


def _live_auto_reconcile_positions(db:Session,user_id:int,orders:list[dict]):
    grouped={}
    for item in orders or []:
        if not isinstance(item,dict):continue
        no=str(item.get("order_no") or "").strip();qty=max(0,int(float(item.get("filled_qty") or 0)))
        if not no or qty<=0:continue
        price=max(0.0,float(item.get("price") or 0));entry=grouped.setdefault(no,{"qty":0,"value":0.0,"time":item.get("time")})
        entry["qty"]+=qty;entry["value"]+=price*qty;entry["time"]=item.get("time") or entry["time"]
    if not grouped:return 0
    decisions=(db.query(LiveAutoTradingDecision).filter(
        LiveAutoTradingDecision.user_id==user_id,LiveAutoTradingDecision.broker_order_no.in_(list(grouped))
    ).all())
    changed=0
    for decision in decisions:
        fill=grouped.get(str(decision.broker_order_no or "")) or {};total=int(fill.get("qty") or 0)
        previous=max(0,int(decision.filled_quantity or 0));delta=max(0,total-previous)
        price=(float(fill.get("value") or 0)/total) if total else 0.0
        if delta<=0:continue
        pos=db.query(LiveAutoTradingPosition).filter(LiveAutoTradingPosition.user_id==user_id,
            LiveAutoTradingPosition.stock_code==decision.stock_code).first()
        if not pos:
            pos=LiveAutoTradingPosition(user_id=user_id,stock_code=decision.stock_code,stock_name=decision.stock_name,
                quantity=0,avg_price=0,invested_amount=0);db.add(pos);flush_or_rollback(db)
        if decision.action=="buy":
            cost=float(pos.invested_amount or 0)+delta*price;pos.quantity=int(pos.quantity or 0)+delta
            pos.invested_amount=cost;pos.avg_price=(cost/pos.quantity) if pos.quantity else 0
        elif decision.action=="sell":
            sell=min(delta,int(pos.quantity or 0));old_qty=max(0,int(pos.quantity or 0));avg=float(pos.avg_price or 0)
            pos.quantity=max(0,old_qty-sell);pos.invested_amount=max(0.0,pos.quantity*avg)
            if pos.quantity==0:pos.avg_price=0
        decision.filled_quantity=total;decision.filled_price=price;decision.filled_amount=total*price
        decision.filled_at=_auto_broker_fill_time({"time":fill.get("time")})
        decision.status="filled" if total>=int(decision.requested_quantity or 0) else "partial";changed+=1
    if changed:commit_or_rollback(db)
    return changed


def _live_auto_status_payload(db:Session,user_id:int):
    setting=_live_auto_setting(db,user_id)
    cred=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==user_id).first()
    snap=db.query(KiwoomLiveAccountSnapshot).filter(KiwoomLiveAccountSnapshot.user_id==user_id).first()
    portfolio=_live_snapshot_to_payload(snap) or {"summary":{},"holdings":[]}
    holding_map=_auto_account_holdings_map(portfolio)
    positions=db.query(LiveAutoTradingPosition).filter(LiveAutoTradingPosition.user_id==user_id,LiveAutoTradingPosition.quantity>0).all()
    position_items=[];invested=0.0;evaluation=0.0
    for pos in positions:
        h=holding_map.get(pos.stock_code) or {};actual=max(0,int(float(h.get("quantity") or 0)))
        qty=min(actual,int(pos.quantity or 0)) if actual else 0
        current=float(h.get("current_price") or h.get("price") or pos.avg_price or 0)
        cost=float(pos.avg_price or 0)*qty;value=current*qty;pnl=value-cost
        invested+=cost;evaluation+=value
        position_items.append({"code":pos.stock_code,"name":pos.stock_name or h.get("name") or pos.stock_code,"quantity":qty,
            "avg_price":float(pos.avg_price or 0),"current_price":current,"evaluation_amount":value,"profit_loss":pnl,
            "return_rate":((pnl/cost)*100 if cost else 0)})
    decisions=(db.query(LiveAutoTradingDecision).filter(LiveAutoTradingDecision.user_id==user_id)
               .order_by(LiveAutoTradingDecision.id.desc()).limit(30).all())
    cycles=(db.query(LiveAutoTradingCycle).filter(LiveAutoTradingCycle.user_id==user_id)
            .order_by(LiveAutoTradingCycle.id.desc()).limit(8).all())
    return {"environment":"live","connection":_live_settings_json(cred),"settings":_auto_setting_json(setting),
        "running":user_id in _live_auto_trade_running_users,"market_open":_auto_market_open(setting),
        "market_phase":krx_market_phase(_auto_trade_now()),
        "summary":{"auto_invested":invested,"auto_evaluation":evaluation,"auto_profit_loss":evaluation-invested,
                   "position_count":len([x for x in position_items if x["quantity"]>0]),
                   "account_total_asset":float((portfolio.get("summary") or {}).get("total_asset") or 0),
                   "buying_power":float((portfolio.get("summary") or {}).get("buying_power") or 0)},
        "positions":position_items,"decisions":[_live_auto_decision_json(x) for x in decisions],
        "recent_fills":[_live_auto_decision_json(x) for x in decisions if int(x.filled_quantity or 0)>0][:8],
        "pending_order_count":sum(1 for x in decisions if x.status in {"accepted","partial"}),
        "diagnostics":{"health":{"level":"ok" if not setting.last_error else "warning",
            "label":"실전 자동운용 준비" if not setting.enabled else "실전 자동운용 중",
            "message":setting.last_error or setting.last_message or "실전 자동매매는 별도 승인과 한도 안에서만 주문합니다."},
            "recent_cycles":[{"id":x.id,"cycle_id":x.cycle_id,"status":x.status,"message":x.message or "","error":x.error_message or "",
                              "decision_count":x.decision_count,"order_count":x.order_count,
                              "started_at":x.started_at.isoformat() if x.started_at else None} for x in cycles]},
        "learning":{"total_cases":0,"recent_cases":[],"recurring_patterns":[],"guardrail":"실전 자동매매 학습 이력은 모의투자 이력과 분리됩니다."},
        "monitoring":{"items":[]}}


async def _run_live_auto_trade_cycle(user_id:int,*,manual:bool=False):
    async with _live_auto_trade_task_lock:
        if user_id in _live_auto_trade_running_users:return {"ok":False,"message":"이미 실전 자동 판단이 진행 중입니다."}
        _live_auto_trade_running_users.add(user_id)
    db=SessionLocal();cycle_id=f"live-{_auto_trade_now().strftime('%Y%m%d%H%M%S')}-{user_id}-{uuid.uuid4().hex[:6]}";cycle=None
    try:
        user=db.query(User).filter(User.id==user_id,User.is_active==True).first()
        if not user:return {"ok":False,"message":"사용자를 찾을 수 없습니다."}
        setting=_live_auto_setting(db,user_id)
        cycle=LiveAutoTradingCycle(user_id=user_id,cycle_id=cycle_id,status="running",started_at=_auto_trade_now());db.add(cycle);commit_or_rollback(db);db.refresh(cycle)
        if not manual and not setting.enabled:
            cycle.status="skipped";cycle.message="실전 자동매매가 중지 상태입니다.";cycle.finished_at=_auto_trade_now();commit_or_rollback(db)
            return {"ok":False,"message":cycle.message}
        cred=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==user_id).first()
        if not cred or not cred.account_no or not cred.trading_enabled:
            setting.enabled=False;setting.next_cycle_at=None;setting.last_error="실전 계좌 연결과 실전 주문 활성화가 필요합니다."
            cycle.status="error";cycle.error_message=setting.last_error;cycle.message=setting.last_error;cycle.finished_at=_auto_trade_now();commit_or_rollback(db)
            return {"ok":False,"message":setting.last_error}
        portfolio=await _sync_live_kiwoom_account(user,db,force=True);portfolio=_enrich_portfolio_holdings(portfolio,db)
        _,cli=live_client_for(user,db);commit_or_rollback(db)
        executions=await cli.recent_executions();_live_auto_reconcile_positions(db,user_id,executions)
        holding_map=_auto_account_holdings_map(portfolio)
        positions=db.query(LiveAutoTradingPosition).filter(LiveAutoTradingPosition.user_id==user_id,LiveAutoTradingPosition.quantity>0).all()
        for pos in positions:
            actual=max(0,int(float((holding_map.get(pos.stock_code) or {}).get("quantity") or 0)))
            if int(pos.quantity or 0)>actual:
                pos.quantity=actual;pos.invested_amount=float(pos.avg_price or 0)*actual
        commit_or_rollback(db)
        positions=[x for x in positions if int(x.quantity or 0)>0]
        owned_codes=[x.stock_code for x in positions]
        candidates,owned_context=_auto_candidate_rows(db,setting,owned_codes)
        decisions,meta=await _auto_gbot_decisions(db,user_id,setting,candidates,owned_context,positions,
            (portfolio.get("summary") or {}),learning_memory_override=build_learning_memory([]))
        now=_auto_trade_now();market_open=_auto_market_open(setting,now);submitted=0;recorded=0;new_buys=0
        if bool((meta or {}).get("safe_skip")):
            decisions=[];setting.last_message=str((meta or {}).get("safe_skip_reason") or "Gbot 응답 안전 기준 미충족으로 실전 주문 없이 건너뛰었습니다.")[:4000]
        stocks={x.code:x for x in db.query(Stock).filter(Stock.code.in_([str(d.get("code") or "") for d in decisions]),*_stocklog_public_clauses()).all()} if decisions else {}
        context={x.get("code"):x for x in [*candidates,*owned_context] if isinstance(x,dict)}
        summary=portfolio.get("summary") or {};order_cash,_=_auto_order_cash(summary)
        account_value=_auto_account_value_reference(summary,order_cash);reserve=account_value*float(setting.min_cash_ratio or 0)/100
        committed=sum(float(x.invested_amount or 0) for x in positions)
        today_count=db.query(LiveOrderAudit).filter(LiveOrderAudit.user_id==user_id,LiveOrderAudit.source=="auto",
            LiveOrderAudit.created_at>=_auto_history_start(now),LiveOrderAudit.status=="accepted").count()
        for raw in decisions:
            code=str(raw.get("code") or "");action=str(raw.get("action") or "hold").lower();stock=stocks.get(code)
            if not stock:continue
            row=LiveAutoTradingDecision(user_id=user_id,cycle_id=cycle_id,stock_code=code,stock_name=stock.name,action=action,
                status="decision",confidence=max(0,min(100,float(raw.get("confidence") or 0))),reason=str(raw.get("reason") or "")[:12000],
                evidence_json=json.dumps(raw.get("evidence") or [],ensure_ascii=False),risks_json=json.dumps(raw.get("risks") or [],ensure_ascii=False),
                exit_plan=str(raw.get("exit_plan") or "")[:6000],decided_at=now)
            db.add(row);flush_or_rollback(db);recorded+=1
            guard="";price=float((context.get(code) or {}).get("price") or stock.price or 0);qty=0
            if action not in {"buy","sell"}:row.status="hold";continue
            if not market_open:guard="정규 거래시간이 아니므로 실전 주문을 전송하지 않았습니다."
            elif float(row.confidence or 0)<float(setting.min_confidence or 0):guard="최소 확신도 기준을 충족하지 못했습니다."
            elif today_count+submitted>=int(setting.max_daily_orders or 1):guard="오늘 실전 자동 주문 최대 횟수에 도달했습니다."
            elif price<=0:guard="최신 가격이 없어 주문금액을 검증할 수 없습니다."
            elif db.query(LiveAutoTradingDecision.id).filter(LiveAutoTradingDecision.user_id==user_id,
                    LiveAutoTradingDecision.stock_code==code,LiveAutoTradingDecision.action==action,
                    LiveAutoTradingDecision.status.in_(["accepted","partial"]),LiveAutoTradingDecision.id!=row.id).first():
                guard="같은 종목의 기존 실전 자동주문 체결을 확인하는 중입니다."
            if not guard and action=="buy":
                if len(positions)>=int(setting.max_positions or 1):guard="실전 자동 보유 종목 수 한도에 도달했습니다."
                elif new_buys>=int(setting.max_new_buys_per_cycle or 1):guard="회차당 신규 매수 한도에 도달했습니다."
                else:
                    available=max(0.0,min(float(setting.max_position_amount or 0),float(setting.max_capital or 0)-committed,order_cash-reserve))
                    qty=int(available//price)
                    if qty<1:guard="현금 보유·총 운용·종목당 한도를 지키면 매수 가능한 수량이 없습니다."
            elif not guard and action=="sell":
                pos=next((x for x in positions if x.stock_code==code),None);qty=int(pos.quantity or 0) if pos else 0
                if qty<1:guard="Gbot이 실전 자동매수한 보유수량이 없어 매도를 차단했습니다."
            row.requested_quantity=max(0,qty);row.requested_price=price;row.requested_amount=price*max(0,qty)
            if guard:row.status="blocked";row.guard_message=guard;continue
            row.status="submitting";row.order_submitted_at=now;commit_or_rollback(db);row_id=row.id
            try:
                broker,order_no=await _submit_stocklog_live_order(db=db,user=user,side=action,stock_code=code,quantity=qty,
                    order_type="market",price=None,exchange="KRX",source="auto")
                row=db.query(LiveAutoTradingDecision).filter(LiveAutoTradingDecision.id==row_id).first()
                row.status="accepted";row.broker_order_no=order_no;row.broker_response_json=json.dumps(broker,ensure_ascii=False);commit_or_rollback(db)
                submitted+=1
                if action=="buy":new_buys+=1;committed+=price*qty;order_cash=max(0,order_cash-price*qty)
            except Exception as exc:
                rollback_quietly(db);row=db.query(LiveAutoTradingDecision).filter(LiveAutoTradingDecision.id==row_id).first()
                if row:row.status="order_failed";row.guard_message=f"키움 실전주문 전송 실패: {str(exc)[:1000]}";commit_or_rollback(db)
        setting=_live_auto_setting(db,user_id);setting.last_cycle_at=now
        setting.next_cycle_at=(now+timedelta(minutes=int(setting.interval_minutes or 30))) if setting.enabled else None
        setting.last_error="";setting.last_message=f"실전 Gbot 판단 {recorded}건 · 실전주문 {submitted}건"
        cycle=db.query(LiveAutoTradingCycle).filter(LiveAutoTradingCycle.id==cycle.id).first();cycle.status="success";cycle.message=setting.last_message
        cycle.decision_count=recorded;cycle.order_count=submitted;cycle.finished_at=_auto_trade_now();commit_or_rollback(db)
        return {"ok":True,"message":setting.last_message,"cycle_id":cycle_id,"decisions":recorded,"orders":submitted,"market_open":market_open}
    except Exception as exc:
        logger.exception("live auto trading cycle failed user_id=%s",user_id);rollback_quietly(db)
        try:
            setting=_live_auto_setting(db,user_id);setting.last_cycle_at=_auto_trade_now()
            setting.next_cycle_at=_auto_trade_now()+timedelta(minutes=int(setting.interval_minutes or 30)) if setting.enabled else None
            setting.last_error=str(exc)[:3000];setting.last_message="실전 자동매매 판단 중 오류가 발생해 주문을 중단했습니다."
            if cycle:
                cycle=db.query(LiveAutoTradingCycle).filter(LiveAutoTradingCycle.id==cycle.id).first()
                if cycle:cycle.status="error";cycle.message=setting.last_message;cycle.error_message=str(exc)[:8000];cycle.finished_at=_auto_trade_now()
            commit_or_rollback(db)
        except Exception:rollback_quietly(db)
        return {"ok":False,"message":"실전 자동매매 판단을 완료하지 못해 주문하지 않았습니다."}
    finally:
        db.close()
        async with _live_auto_trade_task_lock:_live_auto_trade_running_users.discard(user_id)


@app.get("/api/live-trading/auto/status")
def live_auto_trading_status(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading");return _live_auto_status_payload(db,u.id)


@app.get("/api/live-trading/auto/options")
def live_auto_trading_options(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    categories=set()
    for column in (Stock.category,Stock.sector,Stock.industry_name,Stock.theme_group):
        for value, in db.query(column).filter(*_stocklog_public_clauses()).distinct().all():
            if str(value or "").strip() not in {"","기타","종합","기타 사업"}:categories.add(str(value).strip())
    themes=sorted({str(x[0]).strip() for x in db.query(StockTheme.theme_name).join(Stock,Stock.code==StockTheme.stock_code)
                   .filter(*_stocklog_public_clauses()).distinct().all() if x[0] and str(x[0]).strip()})
    return {"markets":["KOSPI","KOSDAQ"],"categories":sorted(categories)[:220],"themes":themes[:700]}


@app.put("/api/live-trading/auto/settings")
def save_live_auto_trading_settings(body:AutoTradingSettingsIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading");row=_live_auto_setting(db,u.id)
    if body.max_price and body.max_price<body.min_price:raise HTTPException(422,"최대 주가는 최소 주가보다 커야 합니다.")
    if body.max_market_cap and body.max_market_cap<body.min_market_cap:raise HTTPException(422,"최대 시가총액은 최소 시가총액보다 커야 합니다.")
    if body.max_position_amount>body.max_capital:raise HTTPException(422,"종목당 최대 투자금액은 실전 자동운용 총한도보다 클 수 없습니다.")
    if not body.use_all_themes and not body.themes:raise HTTPException(422,"전체 테마를 끄면 거래할 테마를 1개 이상 선택해주세요.")
    if datetime.strptime(body.trading_start,"%H:%M")>=datetime.strptime(body.trading_end,"%H:%M"):
        raise HTTPException(422,"자동 거래 종료 시간은 시작 시간보다 늦어야 합니다.")
    for key,value in body.model_dump().items():
        if key=="markets":row.markets_json=json.dumps(value,ensure_ascii=False)
        elif key=="categories":row.categories_json=json.dumps(value,ensure_ascii=False)
        elif key=="themes":row.themes_json=json.dumps(value,ensure_ascii=False)
        else:setattr(row,key,value)
    if row.enabled:row.next_cycle_at=_auto_trade_now()+timedelta(minutes=int(row.interval_minutes or 30))
    commit_or_rollback(db);db.refresh(row)
    return {"ok":True,"message":"실전 자동매매 안전 설정을 저장했습니다.","settings":_auto_setting_json(row)}


@app.get("/api/live-trading/auto/history")
def live_auto_trading_history(page:int=Query(1,ge=1),page_size:int=Query(12,ge=5,le=50),mode:str=Query("orders"),
                              u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    query=db.query(LiveAutoTradingDecision).filter(LiveAutoTradingDecision.user_id==u.id)
    if mode=="orders":query=query.filter(LiveAutoTradingDecision.action.in_(["buy","sell"]))
    total=query.count();pages=max(1,math.ceil(total/page_size));page=min(page,pages)
    rows=query.order_by(LiveAutoTradingDecision.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items":[_live_auto_decision_json(x) for x in rows],"page":page,"pages":pages,"page_size":page_size,"total":total}


@app.delete("/api/live-trading/auto/history/{decision_id}")
def delete_live_auto_trading_history(decision_id:int,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    row=db.query(LiveAutoTradingDecision).filter(LiveAutoTradingDecision.id==decision_id,LiveAutoTradingDecision.user_id==u.id).first()
    if not row:raise HTTPException(404,"실전 자동매매 이력을 찾을 수 없습니다.")
    if row.status in {"accepted","partial","submitting"}:raise HTTPException(409,"진행 중인 실전 주문 이력은 삭제할 수 없습니다.")
    db.delete(row);commit_or_rollback(db);return {"ok":True,"message":"실전 자동매매 이력을 삭제했습니다."}


@app.delete("/api/live-trading/auto/history")
def clear_live_auto_trading_history(mode:str=Query("orders"),u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    query=db.query(LiveAutoTradingDecision).filter(LiveAutoTradingDecision.user_id==u.id,
        ~LiveAutoTradingDecision.status.in_(["accepted","partial","submitting"]))
    if mode=="orders":query=query.filter(LiveAutoTradingDecision.action.in_(["buy","sell"]))
    count=query.count();query.delete(synchronize_session=False);commit_or_rollback(db)
    return {"ok":True,"message":f"종료된 실전 자동매매 이력 {count:,}건을 삭제했습니다.","deleted":count}


@app.post("/api/live-trading/auto/start")
def start_live_auto_trading(body:LiveAutoTradingStartIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    try:require_confirmation(body.confirmation_text,LIVE_AUTO_START_TEXT)
    except LiveTradingSafetyError as exc:raise HTTPException(400,str(exc)) from exc
    cred=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==u.id).first()
    if not cred or not cred.account_no or not cred.trading_enabled:raise HTTPException(400,"실계좌 연결 테스트와 실전 주문 활성화를 먼저 완료해주세요.")
    if not (get_provider_credentials(PROVIDER_GEMINI,db).get("api_key") or "").strip():raise HTTPException(400,"StockLog Gbot 연결 정보를 먼저 설정해주세요.")
    row=_live_auto_setting(db,u.id);row.enabled=True;row.last_error="";row.last_message="실전 자동매매가 시작되었습니다.";row.next_cycle_at=_auto_trade_now();commit_or_rollback(db)
    return {"ok":True,"message":"실전 자동매매를 시작했습니다. 설정 한도와 안전 검증을 통과한 주문만 전송됩니다.","settings":_auto_setting_json(row)}


@app.post("/api/live-trading/auto/stop")
def stop_live_auto_trading(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading");row=_live_auto_setting(db,u.id);row.enabled=False;row.next_cycle_at=None
    row.last_message="실전 자동매매가 중지되었습니다.";commit_or_rollback(db)
    return {"ok":True,"message":"실전 자동매매를 중지했습니다. 이미 전송된 주문은 키움에서 확인해주세요.","settings":_auto_setting_json(row)}


@app.post("/api/live-trading/auto/run-once")
async def run_live_auto_trading_once(body:LiveAutoTradingStartIn,u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"live_trading")
    try:require_confirmation(body.confirmation_text,LIVE_AUTO_START_TEXT)
    except LiveTradingSafetyError as exc:raise HTTPException(400,str(exc)) from exc
    cred=db.query(KiwoomLiveCredential).filter(KiwoomLiveCredential.user_id==u.id).first()
    if not cred or not cred.trading_enabled:raise HTTPException(400,"실전 주문 기능을 먼저 활성화해주세요.")
    if u.id in _live_auto_trade_running_users:raise HTTPException(409,"이미 실전 자동 판단이 진행 중입니다.")
    asyncio.create_task(_run_live_auto_trade_cycle(u.id,manual=True))
    return {"ok":True,"message":"실전 Gbot 1회 판단을 시작했습니다. 거래시간 밖이거나 안전 기준 미충족이면 주문하지 않습니다."}


async def _live_auto_trading_watcher_loop():
    while True:
        try:
            db=SessionLocal()
            try:
                now=_auto_trade_now();rows=db.query(LiveAutoTradingSetting).filter(LiveAutoTradingSetting.enabled==True).all()
                due=[x.user_id for x in rows if (x.next_cycle_at is None or x.next_cycle_at<=now) and _auto_market_open(x,now)
                     and x.user_id not in _live_auto_trade_running_users]
            finally:db.close()
            for user_id in due:asyncio.create_task(_run_live_auto_trade_cycle(user_id))
        except asyncio.CancelledError:raise
        except Exception:logger.exception("live auto trading watcher failed")
        await asyncio.sleep(30)


@app.on_event("startup")
async def start_live_auto_trading_watcher():
    global _live_auto_trade_watcher_task
    if _live_auto_trade_watcher_task is None or _live_auto_trade_watcher_task.done():
        _live_auto_trade_watcher_task=asyncio.create_task(_live_auto_trading_watcher_loop())


@app.on_event("shutdown")
async def stop_live_auto_trading_watcher():
    global _live_auto_trade_watcher_task
    if _live_auto_trade_watcher_task and not _live_auto_trade_watcher_task.done():
        _live_auto_trade_watcher_task.cancel()
        try:await _live_auto_trade_watcher_task
        except BaseException:pass

KOSPI_CACHE_CODE = "INDEX:KOSPI"

def _chart_lock(user_id: int, code: str):
    key = (user_id, code)
    lock = _chart_sync_locks.get(key)
    if not lock:
        lock = asyncio.Lock()
        _chart_sync_locks[key] = lock
    return lock


def _update_real_market_metrics(stock: Stock, rows: list[dict]):
    """Update price-derived Stock metrics from normalized Kiwoom daily bars.

    ``daily_stock_chart`` returns normalized OHLCV rows.  Keep this helper
    deliberately provider-agnostic so both on-demand chart refresh and full
    Kiwoom synchronization use the same deterministic calculations.
    """
    if not stock or not rows:
        return False

    clean=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        try:
            close=float(row.get("close") or 0)
        except (TypeError,ValueError):
            continue
        if close <= 0:
            continue
        clean.append({"date":str(row.get("date") or ""),"close":close})
    if not clean:
        return False

    # Be defensive about provider ordering.  Kiwoom normalization normally
    # returns oldest -> newest, but sorting by YYYYMMDD keeps calculations safe.
    clean.sort(key=lambda x:x["date"])
    closes=[x["close"] for x in clean]
    latest=closes[-1]
    stock.price=latest

    if len(closes) >= 2 and closes[-2] > 0:
        stock.change_rate=round((latest-closes[-2])/closes[-2]*100.0,4)

    # 20-trading-day momentum needs 21 closing prices (today + 20 sessions ago).
    if len(closes) >= 21 and closes[-21] > 0:
        stock.momentum_20d=round((latest/closes[-21]-1.0)*100.0,4)

    # StockLog volatility is the standard deviation of the latest 20 daily
    # percentage returns (percentage points, not annualized).
    returns=[]
    recent=closes[-21:] if len(closes) >= 21 else closes
    for prev,cur in zip(recent,recent[1:]):
        if prev > 0:
            returns.append((cur/prev-1.0)*100.0)
    if len(returns) >= 2:
        stock.volatility=round(float(statistics.stdev(returns)),4)

    # DART stores shares outstanding; combine it with the Kiwoom real price to
    # keep market cap in StockLog's documented unit (억원).
    try:
        shares=float(stock.shares_outstanding or 0)
    except (TypeError,ValueError):
        shares=0.0
    if shares > 0 and latest > 0:
        stock.market_cap=round(latest*shares/100_000_000.0,4)

    stock.updated_at=datetime.now()
    return True


def _sync_programming_error(exc: BaseException) -> bool:
    """Return True for defects that must abort a bulk loop immediately.

    Data/provider errors can be isolated per symbol.  A missing symbol or broken
    object contract is a deployment/code defect and retrying it for thousands of
    stocks only floods APIs and diagnostic logs.
    """
    return isinstance(exc,(NameError,AttributeError,NotImplementedError))


def _validate_kiwoom_sync_runtime():
    required={
        "_update_real_market_metrics":globals().get("_update_real_market_metrics"),
        "_upsert_price_rows":globals().get("_upsert_price_rows"),
        "_apply_kiwoom_stock_metrics":globals().get("_apply_kiwoom_stock_metrics"),
        "recalculate_price_multiples":globals().get("recalculate_price_multiples"),
    }
    missing=[name for name,value in required.items() if not callable(value)]
    if missing:
        raise RuntimeError("Kiwoom sync runtime incomplete: missing " + ", ".join(missing))


def _upsert_price_rows(db: Session, stock_code: str, rows: list[dict]):
    if not rows:
        return 0
    dates = [x["date"] for x in rows]
    existing = {
        x.trade_date: x
        for x in db.query(PriceBar).filter(
            PriceBar.stock_code == stock_code,
            PriceBar.trade_date.in_(dates),
        ).all()
    }
    for row in rows:
        bar = existing.get(row["date"])
        if not bar:
            bar = PriceBar(stock_code=stock_code, trade_date=row["date"])
            db.add(bar)
        bar.open = float(row["open"])
        bar.high = float(row["high"])
        bar.low = float(row["low"])
        bar.close = float(row["close"])
        bar.volume = float(row.get("volume") or 0)
    commit_or_rollback(db)
    return len(rows)


async def _ensure_real_chart(u: User, s: Stock, db: Session, force: bool = False):
    key = (u.id, s.code)
    ttl = int(os.getenv("KIWOOM_CHART_CACHE_SECONDS", "300"))
    cached_at = _chart_sync_cache.get(key, 0)
    now = time.time()

    if not force and cached_at and now - cached_at < ttl:
        return {"stock_source": "mysql-real-cache", "kospi_source": "mysql-real-cache", "warnings": []}

    async with _chart_lock(u.id, s.code):
        cached_at = _chart_sync_cache.get(key, 0)
        if not force and cached_at and time.time() - cached_at < ttl:
            return {"stock_source": "mysql-real-cache", "kospi_source": "mysql-real-cache", "warnings": []}

        _, cli = client_for(u, db)
        warnings = []
        # The chart lock protects duplicate work; it must not also pin a MySQL
        # connection during Kiwoom HTTP waits.
        commit_or_rollback(db)

        try:
            stock_rows, stock_meta = await cli.daily_stock_chart(s.code, max_rows=500)
        except Exception as e:
            real_count = db.query(PriceBar).filter(PriceBar.stock_code == s.code).count()
            if real_count == 0:
                raise HTTPException(502, f"키움 실제 일봉 조회 실패(ka10081): {e}")
            warnings.append(f"최신 종목 일봉 갱신 실패: {e}")
            stock_meta = {"api_id": "ka10081", "cached": True}
        else:
            _upsert_price_rows(db, s.code, stock_rows)
            if stock_rows:
                latest = stock_rows[-1]
                previous = stock_rows[-2] if len(stock_rows) >= 2 else None
                s.price = float(latest["close"])
                if previous and previous["close"]:
                    s.change_rate = round((latest["close"] - previous["close"]) / previous["close"] * 100, 4)
                commit_or_rollback(db)

        kospi_key = (u.id, KOSPI_CACHE_CODE)
        kospi_cached_at = _chart_sync_cache.get(kospi_key, 0)
        if not force and kospi_cached_at and time.time() - kospi_cached_at < ttl:
            kospi_meta = {"api_id": "ka20006", "available": True, "cached": True}
        else:
            try:
                kospi_rows, kospi_meta = await cli.daily_kospi_chart(max_rows=500)
            except Exception as e:
                warnings.append(f"KOSPI 실제 일봉 조회 실패(ka20006): {e}")
                kospi_meta = {"api_id": "ka20006", "available": False}
            else:
                _upsert_price_rows(db, KOSPI_CACHE_CODE, kospi_rows)
                kospi_meta["available"] = True
                _chart_sync_cache[kospi_key] = time.time()

        _chart_sync_cache[key] = time.time()
        return {
            "stock_source": stock_meta,
            "kospi_source": kospi_meta,
            "warnings": warnings,
        }


def _build_real_chart(code: str, db: Session, limit: int = 500):
    bars = db.query(PriceBar).filter(
        PriceBar.stock_code == code
    ).order_by(PriceBar.trade_date.desc()).limit(limit).all()
    bars = list(reversed(bars))

    kospi_rows = db.query(PriceBar).filter(
        PriceBar.stock_code == KOSPI_CACHE_CODE
    ).all()
    kospi_map = {x.trade_date: x.close for x in kospi_rows}

    return [{
        "date": x.trade_date,
        "open": x.open,
        "high": x.high,
        "low": x.low,
        "close": x.close,
        "volume": x.volume,
        "kospi": kospi_map.get(x.trade_date),
    } for x in bars]

@app.get("/api/stocks/search")
def stock_search(
    q:str=Query("", min_length=1),
    limit:int=Query(12, ge=1, le=30),
    _:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    q = q.strip()
    rows = (
        db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .filter(_name_search_clause(q))
        .order_by(
            case(
                (Stock.code == q, 0),
                (Stock.name == q, 1),
                (Stock.code.startswith(q), 2),
                (Stock.name.startswith(q), 3),
                else_=4,
            ),
            Stock.market_cap.desc(),
        )
        .limit(limit)
        .all()
    )
    theme_map = _theme_map_for_codes(
        db,
        [s.code for s in rows],
        limit=2,
    )

    return [{
        "code":s.code,
        "name":s.name,
        **_stock_name_payload(s),
        "market":s.market,
        "sector":s.sector,
        "price":s.price,
        "change_rate":s.change_rate,
        "category":s.category,
        "sector":s.sector,
        "industry_name":s.industry_name,
        "industry_source":s.industry_source,
        "themes":theme_map.get(s.code, []),
        "theme_fallback":_stock_theme_fallback(s),
    } for s in rows]

@app.get("/api/stocks/{code}/chart/cached")
def stock_cached_chart(
    code:str,
    _:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    stock=_stocklog_public_stock(db,code)
    if not stock:
        raise HTTPException(404,"종목을 찾을 수 없습니다.")
    chart=_build_real_chart(code,db,limit=160)
    return {
        "stock":{
            "code":stock.code,
            "name":stock.name,
            "price":stock.price,
            "change_rate":stock.change_rate,
        },
        "chart":chart,
        "available":bool(chart),
        "_meta":{
            "source":"stocklog-last-real-chart",
            "demo":False,
            "cached":True,
        },
    }



FLOW_CATEGORY_FIELDS={
    "individual":"individual_net",
    "foreign":"foreign_net",
    "institution":"institution_net",
    "financial_investment":"financial_investment_net",
    "insurance":"insurance_net",
    "investment_trust":"investment_trust_net",
    "other_finance":"other_finance_net",
    "bank":"bank_net",
    "pension":"pension_net",
    "private_equity":"private_equity_net",
    "national":"national_net",
    "other_corp":"other_corp_net",
    "foreign_other":"foreign_other_net",
}
FLOW_INVESTOR_LABELS={
    "all":"종합","foreign":"외국인","institution":"기관",
    "individual":"개인","financial_investment":"금융투자",
    "investment_trust":"투신","pension":"연기금",
    "insurance":"보험","bank":"은행","private_equity":"사모펀드",
}
FLOW_PERIODS={1,3,5,7,20}


def _flow_state(db:Session):
    row=db.query(FullMarketSyncState).filter(FullMarketSyncState.key=="investor_flow").first()
    if not row:
        row=FullMarketSyncState(
            key="investor_flow",running=False,phase="idle",job_type="flow",
            stage_label="수급 데이터",message="수급 동기화 전입니다.",
        )
        db.add(row);commit_or_rollback(db);db.refresh(row)
    return row


def _flow_provider_status(row:FullMarketSyncState):
    try:
        value=json.loads(row.provider_status_json or "{}")
        return value if isinstance(value,dict) else {}
    except Exception:
        return {}


def _flow_status_json(row:FullMarketSyncState):
    total=int(row.item_total or row.total or 0)
    done=int(row.item_completed or row.completed or 0)
    progress=round(done/max(1,total)*100,1) if total else 0.0
    elapsed=0.0
    if row.started_at:
        elapsed=max(0.0,(datetime.now()-row.started_at).total_seconds())
    eta=(elapsed/done*(total-done)) if done and total>done else 0.0
    return {
        "running":bool(row.running),"phase":row.phase or "idle",
        "stage_label":row.stage_label or "수급 데이터","total":total,"completed":done,
        "success":int(row.success or 0),"failed":int(row.failed or 0),
        "progress":progress,"current_code":row.current_code or "","current_name":row.current_name or "",
        "message":row.message or "","last_error":row.last_error or "",
        "started_at":row.started_at.isoformat() if row.started_at else None,
        "finished_at":row.finished_at.isoformat() if row.finished_at else None,
        "eta_seconds":round(eta,1),
        "provider_status":_flow_provider_status(row),
        "updated_at":row.updated_at.isoformat() if row.updated_at else None,
    }


@app.get("/api/admin/sync-error-logs")
async def admin_sync_error_logs(
    limit:int=Query(80,ge=1,le=250),
    _:User=Depends(admin_monitor_user),
):
    # Filesystem-only metadata listing. Authentication uses the isolated monitor
    # executor/pool so a busy main DB or telemetry queue cannot make this page hang.
    return {"items":list_sync_diagnostics(limit),"directory":"runtime/sync-error-logs"}


@app.post("/api/admin/sync-error-logs/client-event")
async def admin_sync_error_log_client_event(
    body:AdminClientDiagnosticIn,
    admin:User=Depends(admin_monitor_user),
):
    filename=begin_sync_diagnostic(
        "frontend",
        run_id=body.request_id or f"admin-{admin.id}",
        metadata={"source":"frontend","admin_user_id":admin.id,"url":body.url,"method":body.method,"status":body.status},
    )
    append_sync_diagnostic(
        filename,
        "ERROR",
        body.event,
        details={
            "message":body.message,
            "stack":body.stack,
            "url":body.url,
            "method":body.method,
            "status":body.status,
            "request_id":body.request_id,
            "context":body.context,
        },
    )
    return {"ok":True,"filename":filename}


@app.get("/api/admin/sync-error-logs/download-all")
async def admin_sync_error_logs_download_all(
    limit:int=Query(250,ge=1,le=250),
    _:User=Depends(admin_monitor_user),
):
    def _build_zip():
        items=list_sync_diagnostics(limit)
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            manifest=[
                "StockLog synchronization diagnostics bundle",
                f"created_at_kst={datetime.now(ZoneInfo('Asia/Seoul')).isoformat()}",
                f"file_count={len(items)}",
                "NOTE=Individual TXT files are already secret-masked by StockLog.",
                "",
            ]
            archive.writestr("README.txt","\n".join(manifest).encode("utf-8"))
            for item in items:
                try:
                    path=diagnostic_path(item.get("filename") or "")
                    archive.write(path,arcname=path.name)
                except (ValueError,FileNotFoundError,OSError):
                    continue
        buffer.seek(0)
        return buffer

    buffer=await run_monitor_blocking(_build_zip)
    stamp=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    headers={"Content-Disposition":f'attachment; filename="StockLog_sync_diagnostics_{stamp}.zip"'}
    return StreamingResponse(buffer,media_type="application/zip",headers=headers)


@app.get("/api/admin/sync-error-logs/{filename}")
async def admin_sync_error_log_download(
    filename:str,
    _:User=Depends(admin_monitor_user),
):
    try:
        path=diagnostic_path(filename)
    except (ValueError,FileNotFoundError):
        raise HTTPException(404,"오류 로그 파일을 찾을 수 없습니다.")
    return FileResponse(
        path=str(path),
        media_type="text/plain; charset=utf-8",
        filename=path.name,
    )


def _upsert_flow_rows(db:Session,stock_code:str,payload:dict):
    saved=0
    now=datetime.now()
    for item in payload.get("rows") or []:
        try:
            trade_date=datetime.strptime(str(item.get("date") or ""),"%Y%m%d").date()
        except Exception:
            continue
        row=(db.query(StockInvestorFlowDaily).filter(
            StockInvestorFlowDaily.stock_code==stock_code,
            StockInvestorFlowDaily.trade_date==trade_date,
        ).first())
        if not row:
            row=StockInvestorFlowDaily(stock_code=stock_code,trade_date=trade_date)
            db.add(row)
        row.close_price=float(item.get("close_price") or 0)
        row.price_change=float(item.get("price_change") or 0)
        row.trading_value=float(item.get("trading_value") or 0)
        for key,column in FLOW_CATEGORY_FIELDS.items():
            setattr(row,column,float(item.get(key) or 0))
        row.source=str(payload.get("source") or "kiwoom-ka10060")
        row.observed_at=now;row.updated_at=now
        saved+=1
    return saved


def _flow_error_kind(exc:Exception):
    return classify_flow_error(exc)


async def _fetch_flow_with_retry(
    cli,
    stock_code:str,
    today:str,
    history_days:int,
    max_attempts:int=3,
    fallback_previous_dates:bool=False,
):
    """Fetch investor-flow history with transient retry and optional date fallback.

    A normal bulk sync makes one date request per stock to keep API traffic bounded.
    A targeted detail/AI backfill may additionally retry the most recent prior
    weekdays when Kiwoom reports no rows for the requested date (holiday, delayed
    daily table, or an intraday provider edge case).
    """
    retries=0
    last_exc=None
    candidate_dates=[str(today)]
    if fallback_previous_dates:
        try:
            base=datetime.strptime(str(today),"%Y%m%d")
            cursor=base
            while len(candidate_dates)<6:
                cursor-=timedelta(days=1)
                if cursor.weekday()<5:
                    candidate_dates.append(cursor.strftime("%Y%m%d"))
        except Exception:
            pass

    for date_index,request_date in enumerate(candidate_dates):
        last_no_data=None
        for attempt in range(1,max_attempts+1):
            try:
                payload=await cli.stock_investor_history(stock_code,request_date,history_days)
                rows=(payload or {}).get("rows") or []
                if not rows:
                    last_no_data=RuntimeError(f"Kiwoom investor-flow rows empty date={request_date}")
                    break
                if date_index:
                    payload=dict(payload or {})
                    payload["requested_date"]=request_date
                    payload["fallback_from_date"]=str(today)
                return payload,retries,"ok",None
            except Exception as exc:
                last_exc=exc
                kind=_flow_error_kind(exc)
                if kind=="no_data":
                    last_no_data=exc
                    break
                if kind!="transient" or attempt>=max_attempts:
                    return None,retries,kind,exc
                retries+=1
                await asyncio.sleep(retry_delay_seconds(attempt))
        if last_no_data is not None:
            last_exc=last_no_data
            if not fallback_previous_dates:
                return None,retries,"no_data",last_no_data
            continue
    return None,retries,"no_data",last_exc


async def _run_flow_sync(requested_by_user_id:int,universe_limit:int,history_days:int):
    global _flow_sync_task
    diagnostic_file=begin_sync_diagnostic(
        "investor-flow",
        run_id=f"flow-{requested_by_user_id}-{time.time_ns()}",
        metadata={
            "requested_by_user_id":requested_by_user_id,
            "universe_limit":int(universe_limit),
            "history_days":int(history_days),
        },
    )
    diagnostic_token=activate_sync_diagnostic(diagnostic_file)
    append_sync_diagnostic(
        diagnostic_file,"INFO","FLOW_SYNC_START",
        details={"universe_limit":int(universe_limit),"history_days":int(history_days)},
    )
    with SessionLocal() as db:
        state=_flow_state(db)
        try:
            requester=db.query(User).filter(User.id==requested_by_user_id).first()
            if not requester or not requester.is_admin:
                raise RuntimeError("수급 동기화 관리자 계정을 확인하지 못했습니다.")
            _,cli=client_for(requester,db)
            base_q=(db.query(Stock).filter(
                Stock.is_active==True,
                Stock.is_analysis_eligible==True,
                Stock.market.in_(["KOSPI","KOSDAQ"]),
            ))
            eligible_total=int(base_q.count())
            q=base_q.order_by(Stock.market_cap.desc(),Stock.code.asc())
            if universe_limit>0:
                q=q.limit(universe_limit)
            stocks=q.with_entities(Stock.code,Stock.name).all()
            state.running=True;state.phase="collecting";state.job_type="flow"
            state.item_total=len(stocks);state.total=len(stocks);state.item_completed=0;state.completed=0
            state.success=0;state.failed=0;state.current_code="";state.current_name=""
            state.message=f"최근 {history_days}거래일 수급 데이터를 수집하고 있습니다."
            state.last_error="";state.failures_json="[]";state.started_at=datetime.now();state.finished_at=None
            provider={
                "requested_limit":int(universe_limit),
                "history_days":int(history_days),
                "eligible_total":eligible_total,
                "selected_total":len(stocks),
                "outside_selection":max(0,eligible_total-len(stocks)),
                "skipped":0,
                "missing_data":0,
                "cached_when_provider_empty":0,
                "retried":0,
                "transient_recovered":0,
                "deferred":0,
                "provider_circuit_open":False,
                "provider_circuit_reason":"",
                "failure_reasons":{},
                "diagnostic_log":diagnostic_file,
                "missing_samples":[],
            }
            state.provider_status_json=_bounded_provider_json(provider)
            commit_or_rollback(db)
            append_sync_diagnostic(
                diagnostic_file,"INFO","FLOW_SYNC_SCOPE_RESOLVED",
                details={
                    "eligible_total":eligible_total,
                    "selected_total":len(stocks),
                    "outside_selection":provider["outside_selection"],
                },
            )
            failures=[]
            consecutive_transient=0
            today=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
            for idx,stock in enumerate(stocks,1):
                db.refresh(state)
                if not state.running:
                    state.phase="stopped";state.message="관리자가 수급 동기화를 중지했습니다.";break
                state.current_code=stock.code;state.current_name=stock.name
                state.stage_label=f"수급 {idx:,}/{len(stocks):,}"
                # Return the DB checkout before waiting on Kiwoom HTTP.
                commit_or_rollback(db)
                payload,retries,outcome,exc=await _fetch_flow_with_retry(cli,stock.code,today,history_days)
                provider["retried"]+=int(retries)
                if outcome=="ok":
                    consecutive_transient=0
                    saved=_upsert_flow_rows(db,stock.code,payload)
                    if saved>0:
                        state.success=int(state.success or 0)+1
                        if retries:
                            provider["transient_recovered"]+=1
                    else:
                        provider["skipped"]+=1
                        provider["missing_data"]+=1
                        sample={"code":stock.code,"name":stock.name,"kind":"parse_empty","rows_received":len((payload or {}).get("rows") or [])}
                        if len(provider["missing_samples"])<25:
                            provider["missing_samples"].append(sample)
                        append_sync_diagnostic(diagnostic_file,"WARNING","FLOW_ROWS_NOT_SAVED",details=sample)
                elif outcome=="no_data":
                    consecutive_transient=0
                    # Provider-empty is never silently treated as successful coverage.
                    # Existing cached rows can still keep the stock analyzable; otherwise
                    # it is explicitly counted and logged as missing data.
                    existing_rows=(db.query(StockInvestorFlowDaily.id).filter(
                        StockInvestorFlowDaily.stock_code==stock.code
                    ).limit(1).count())
                    provider["skipped"]+=1
                    if existing_rows:
                        provider["cached_when_provider_empty"]+=1
                    else:
                        provider["missing_data"]+=1
                        sample={
                            "code":stock.code,"name":stock.name,"kind":"provider_no_data",
                            "date":today,"retries":int(retries),"error":_sync_error_text(exc or RuntimeError("no_data"),800),
                        }
                        if len(provider["missing_samples"])<25:
                            provider["missing_samples"].append(sample)
                        append_sync_diagnostic(diagnostic_file,"WARNING","FLOW_PROVIDER_NO_DATA",details=sample,exc=exc)
                elif outcome=="transient":
                    consecutive_transient+=1
                    provider["deferred"]+=1
                    provider["failure_reasons"]["transient_deferred"]=int(provider["failure_reasons"].get("transient_deferred",0))+1
                    sample={
                        "code":stock.code,"name":stock.name,"kind":"transient_deferred",
                        "date":today,"retries":int(retries),"error":_sync_error_text(exc or RuntimeError("transient"),800),
                    }
                    if len(provider["missing_samples"])<25:
                        provider["missing_samples"].append(sample)
                    append_sync_diagnostic(diagnostic_file,"WARNING","FLOW_PROVIDER_TRANSIENT_DEFERRED",details=sample,exc=exc)
                    if provider_circuit_should_open(consecutive_transient,threshold=BULK_PROVIDER_CIRCUIT_THRESHOLD):
                        remaining=max(0,len(stocks)-idx)
                        provider["deferred"]+=remaining
                        provider["provider_circuit_open"]=True
                        provider["provider_circuit_reason"]=(
                            f"키움 수급 API가 {consecutive_transient}개 종목 연속 일시 실패하여 "
                            f"남은 {remaining:,}종목을 다음 동기화로 보류했습니다."
                        )
                        state.message=provider["provider_circuit_reason"]
                else:
                    consecutive_transient=0
                    state.failed=int(state.failed or 0)+1
                    reason=outcome or "hard"
                    provider["failure_reasons"][reason]=int(provider["failure_reasons"].get(reason,0))+1
                    failure={
                        "code":stock.code,"name":stock.name,
                        "kind":reason,"error":_sync_error_text(exc or RuntimeError(reason),1200),
                        "date":today,"retries":int(retries),"index":idx,"total":len(stocks),
                    }
                    if len(failures)<32:
                        failures.append(failure)
                    append_sync_diagnostic(diagnostic_file,"ERROR","FLOW_STOCK_FAILED",details=failure,exc=exc)
                state.item_completed=idx;state.completed=idx
                state.progress_value=round(idx/max(1,len(stocks))*100,2)
                if idx%5==0 or idx==len(stocks):
                    warning_count=int(state.failed or 0)+int(provider.get("missing_data") or 0)
                    provider["warning_count"]=warning_count
                    provider["selected_coverage_percent"]=round(
                        (int(state.success or 0)+int(provider.get("cached_when_provider_empty") or 0))
                        /max(1,len(stocks))*100,2
                    )
                    state.failures_json=_bounded_failures_json(failures)
                    state.provider_status_json=_bounded_provider_json(provider)
                    state.updated_at=datetime.now()
                # IMPORTANT: never carry an investor-flow INSERT/UPDATE transaction
                # into the next Kiwoom HTTP await.  The old every-5-items commit left
                # one main-pool connection checked out while the network was idle,
                # which amplified pool contention and made /sync-overview time out.
                commit_or_rollback(db)
                if provider.get("provider_circuit_open"):
                    append_sync_diagnostic(
                        diagnostic_file,"WARNING","FLOW_PROVIDER_CIRCUIT_OPEN",
                        details={
                            "completed":idx,"total":len(stocks),"deferred":int(provider.get("deferred") or 0),
                            "reason":provider.get("provider_circuit_reason") or "",
                        },
                    )
                    break
                await asyncio.sleep(0)
            warning_count=(
                int(state.failed or 0)
                +int(provider.get("missing_data") or 0)
                +int(provider.get("deferred") or 0)
            )
            provider["warning_count"]=warning_count
            provider["selected_coverage_percent"]=round(
                (int(state.success or 0)+int(provider.get("cached_when_provider_empty") or 0))
                /max(1,len(stocks))*100,2
            ) if stocks else 100.0
            if state.running:
                state.phase="partial" if warning_count else "done"
                scope_label="전체 분석종목" if int(universe_limit)==0 else f"상위 {len(stocks):,}종목"
                state.message=(
                    f"수급 동기화 완료 · 범위 {scope_label} · 저장 성공 {int(state.success or 0):,} / "
                    f"데이터 없음 {int(provider['missing_data']):,} / 기존 캐시 사용 {int(provider['cached_when_provider_empty']):,} / "
                    f"다음 실행 보류 {int(provider.get('deferred') or 0):,} / "
                    f"최종 실패 {int(state.failed or 0):,}"
                )
            state.running=False;state.current_code="";state.current_name="";state.stage_label="수급 데이터"
            state.finished_at=datetime.now();state.failures_json=_bounded_failures_json(failures)
            try:
                provider["smart_score_cache"]=_rebuild_smart_score_cache(db)
                if state.phase in {"done","completed","partial"}:
                    state.message += " · 스마트 분석 점수 갱신"
            except Exception as cache_exc:
                rollback_quietly(db)
                state=_flow_state(db)
                provider=_flow_status_json(state).get("provider_status") or provider
                provider["smart_score_cache_warning"]=_sync_error_text(cache_exc,500)
                provider["diagnostic_log"]=diagnostic_file
                append_sync_diagnostic(diagnostic_file,"ERROR","FLOW_SMART_SCORE_CACHE_FAILED",exc=cache_exc)
                logger.exception("smart score cache rebuild after flow sync failed")
            state.provider_status_json=_bounded_provider_json(provider)
            commit_or_rollback(db)
            append_sync_diagnostic(
                diagnostic_file,"INFO","FLOW_SYNC_FINISH",
                details={
                    "phase":state.phase,"success":int(state.success or 0),"failed":int(state.failed or 0),
                    "missing_data":int(provider.get("missing_data") or 0),
                    "deferred":int(provider.get("deferred") or 0),
                    "cached_when_provider_empty":int(provider.get("cached_when_provider_empty") or 0),
                    "selected_total":len(stocks),"eligible_total":eligible_total,
                    "selected_coverage_percent":provider.get("selected_coverage_percent"),
                },
            )
        except asyncio.CancelledError:
            append_sync_diagnostic(diagnostic_file,"WARNING","FLOW_SYNC_CANCELLED")
            rollback_quietly(db)
            state=_flow_state(db)
            state.running=False;state.phase="stopped";state.message="수급 동기화가 중단되었습니다.";state.finished_at=datetime.now()
            provider=_flow_provider_status(state);provider["diagnostic_log"]=diagnostic_file;state.provider_status_json=_bounded_provider_json(provider)
            commit_or_rollback(db);raise
        except Exception as exc:
            append_sync_diagnostic(diagnostic_file,"ERROR","FLOW_SYNC_FATAL",details={"requested_by_user_id":requested_by_user_id},exc=exc)
            logger.exception("investor flow sync failed")
            rollback_quietly(db)
            state=_flow_state(db)
            state.running=False;state.phase="failed";state.last_error=_sync_error_text(exc,1000)
            state.message="수급 동기화 중 오류가 발생했습니다.";state.finished_at=datetime.now()
            provider=_flow_provider_status(state);provider["diagnostic_log"]=diagnostic_file;state.provider_status_json=_bounded_provider_json(provider)
            commit_or_rollback(db)
        finally:
            _flow_sync_task=None
            deactivate_sync_diagnostic(diagnostic_token)


@app.get("/api/admin/flow-sync/status")
def admin_flow_sync_status(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    state=_flow_state(db)
    if state.running and not _sync_task_alive(_flow_sync_task):
        state.running=False;state.phase="cancelled";state.stage_label="중지됨"
        state.current_code="";state.current_name="";state.eta_seconds=0
        state.message="백엔드 재시작 또는 작업 종료로 이전 수급 동기화를 종료 처리했습니다."
        state.finished_at=datetime.now();commit_or_rollback(db)
    return _flow_status_json(state)


@app.post("/api/admin/flow-sync/start")
async def admin_flow_sync_start(body:FlowSyncStartIn,admin:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _flow_sync_task
    async with _flow_sync_lock:
        state=_flow_state(db)
        if state.running or (_flow_sync_task and not _flow_sync_task.done()):
            raise HTTPException(409,"수급 동기화가 이미 진행 중입니다.")
        state.running=True;state.phase="queued";state.message="수급 동기화를 준비하고 있습니다."
        state.requested_by_user_id=admin.id;state.started_at=datetime.now();state.finished_at=None;commit_or_rollback(db)
        _flow_sync_task=asyncio.create_task(_run_flow_sync(admin.id,int(body.universe_limit),int(body.history_days)))
    return {"ok":True,"message":"수급 동기화를 시작했습니다.","status":_flow_status_json(state)}


@app.post("/api/admin/flow-sync/stop")
def admin_flow_sync_stop(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    state=_flow_state(db)
    if not state.running:
        return {"ok":True,"message":"진행 중인 수급 동기화가 없습니다.","status":_flow_status_json(state)}
    state.running=False;state.message="현재 종목 처리 후 수급 동기화를 중지합니다.";commit_or_rollback(db)
    return {"ok":True,"message":state.message,"status":_flow_status_json(state)}


def _percentile_scores(values:list[float]):
    if not values:
        return []
    positive=sorted(v for v in values if float(v)>0)
    if not positive:
        return [0.0 for _ in values]
    import bisect
    return [0.0 if float(v)<=0 else bisect.bisect_right(positive,float(v))/len(positive) for v in values]


def _positive_streak(rows:list[StockInvestorFlowDaily],field:str):
    streak=0
    for row in sorted(rows,key=lambda x:x.trade_date,reverse=True):
        if float(getattr(row,field) or 0)>0: streak+=1
        else: break
    return streak


def _flow_insight(item:dict):
    if item.get("joint_buy") and item.get("individual_net",0)<0:
        return "개인 순매도 속 외국인/기관 동반 순매수"
    if item.get("joint_buy"):
        return "외국인/기관 동반 순매수"
    if item.get("foreign_streak",0)>=3:
        return f"외국인 {item['foreign_streak']}거래일 연속 순매수"
    if item.get("institution_streak",0)>=3:
        return f"기관 {item['institution_streak']}거래일 연속 순매수"
    if item.get("reversal"):
        return "최근 매도세에서 순매수로 수급 반전"
    if item.get("foreign_net",0)>0:
        return "외국인 누적 순매수 강세"
    if item.get("institution_net",0)>0:
        return "기관 누적 순매수 강세"
    return "최근 수급 흐름을 관찰할 필요가 있습니다."


@app.get("/api/flow-analysis/rankings")
def flow_analysis_rankings(
    period:int=Query(7),
    investor:str=Query("all",max_length=40),
    market:str=Query("ALL",max_length=20),
    signal:str=Query("all",max_length=30),
    sort:str=Query("score",max_length=30),
    q:str=Query("",max_length=80),
    page:int=Query(1,ge=1),
    page_size:int=Query(30,ge=10,le=100),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"flow_analysis")
    period=int(period)
    if period not in FLOW_PERIODS:
        raise HTTPException(422,"수급 기간은 1·3·5·7·20 거래일만 지원합니다.")
    investor=str(investor or "all").lower()
    if investor not in FLOW_INVESTOR_LABELS:
        raise HTTPException(422,"지원하지 않는 투자자 필터입니다.")
    signal=str(signal or "all").lower()
    advanced_requested=(period!=1 or investor not in {"all","foreign","institution","individual"} or signal!="all")
    advanced=_feature_access(u,db,"flow_advanced").get("enabled",False)
    if advanced_requested and not advanced:
        raise HTTPException(403,"현재 회원 등급에서는 당일 기본 수급 분석만 사용할 수 있습니다.")

    date_rows=(db.query(StockInvestorFlowDaily.trade_date).distinct().order_by(StockInvestorFlowDaily.trade_date.desc()).limit(period).all())
    dates=[r[0] for r in date_rows]
    if not dates:
        return {"items":[],"page":1,"pages":1,"total":0,"period":period,"latest_date":None,"message":"수급 데이터 동기화 전입니다.","advanced_enabled":bool(advanced),"unit":"shares"}
    flow_rows=db.query(StockInvestorFlowDaily).filter(StockInvestorFlowDaily.trade_date.in_(dates)).all()
    codes=list({r.stock_code for r in flow_rows})
    # Compute the 0-100 score against the same full synchronized universe first.
    # Search/market/signal filters are presentation filters and must not change a
    # stock's score merely because the user changed the UI selection.
    stocks={s.code:s for s in db.query(Stock).filter(Stock.code.in_(codes),*_stocklog_public_clauses()).all()}
    market=str(market or "ALL").upper()
    keyword=str(q or "").strip()
    grouped={}
    for row in flow_rows:
        if row.stock_code in stocks:
            grouped.setdefault(row.stock_code,[]).append(row)
    items=[]
    detail_fields=["financial_investment_net","investment_trust_net","pension_net","insurance_net","bank_net","private_equity_net"]
    for code,rows in grouped.items():
        rows=sorted(rows,key=lambda x:x.trade_date,reverse=True)
        stock=stocks[code]
        sums={field:sum(float(getattr(r,field) or 0) for r in rows) for field in FLOW_CATEGORY_FIELDS.values()}
        foreign=sums["foreign_net"];institution=sums["institution_net"];individual=sums["individual_net"]
        foreign_days=sum(1 for r in rows if float(r.foreign_net or 0)>0)
        institution_days=sum(1 for r in rows if float(r.institution_net or 0)>0)
        breadth=sum(1 for f in detail_fields if sums[f]>0)/len(detail_fields)
        shares=float(stock.shares_outstanding or 0)
        if shares<=0 and stock.market_cap and stock.price:
            shares=(float(stock.market_cap)*100_000_000)/max(1,float(stock.price))
        flow_ratio=(max(0,foreign)+max(0,institution))/max(1,shares)*100 if shares>0 else 0.0
        foreign_ratio=max(0,foreign)/max(1,shares)*100 if shares>0 else max(0,foreign)
        institution_ratio=max(0,institution)/max(1,shares)*100 if shares>0 else max(0,institution)
        latest=rows[0]
        oldest=rows[-1]
        latest_close=float(latest.close_price or stock.price or 0)
        oldest_close=float(oldest.close_price or latest_close or 0)
        period_change=(
            ((latest_close-oldest_close)/oldest_close*100)
            if len(rows)>1 and oldest_close>0
            else float(stock.change_rate or 0)
        )
        prior=rows[1:]
        reversal=(
            (float(latest.foreign_net or 0)>0 and sum(float(r.foreign_net or 0) for r in prior)<0)
            or (float(latest.institution_net or 0)>0 and sum(float(r.institution_net or 0) for r in prior)<0)
        ) if prior else False
        # Prefer the latest intraday/universe price for the card.  If a stock
        # quote has not been refreshed yet, the newest ka10060 close still gives
        # the user a useful broker-confirmed fallback without another API call.
        current_price=float(stock.price or latest_close or 0)
        daily_change_rate=float(stock.change_rate or 0)
        if (not stock.price or stock.change_rate is None) and len(rows)>1:
            prev_close=float(rows[1].close_price or 0)
            if prev_close>0 and latest_close>0:
                daily_change_rate=(latest_close-prev_close)/prev_close*100
        item={
            "code":code,"name":stock.name,"market":stock.market,
            "price":round(current_price,2),"change_rate":round(daily_change_rate,4),
            "period_change_rate":round(period_change,4),
            "latest_date":latest.trade_date.isoformat(),"days":len(rows),
            "foreign_net":foreign,"institution_net":institution,"individual_net":individual,
            "financial_investment_net":sums["financial_investment_net"],"investment_trust_net":sums["investment_trust_net"],
            "pension_net":sums["pension_net"],"insurance_net":sums["insurance_net"],"bank_net":sums["bank_net"],
            "private_equity_net":sums["private_equity_net"],
            "foreign_buy_days":foreign_days,"institution_buy_days":institution_days,
            "foreign_streak":_positive_streak(rows,"foreign_net"),"institution_streak":_positive_streak(rows,"institution_net"),
            "joint_buy":foreign>0 and institution>0,"reversal":bool(reversal),"breadth":breadth,
            "persistence":((foreign_days+institution_days)/(2*max(1,len(rows)))),
            "flow_ratio":flow_ratio,"_foreign_ratio":foreign_ratio,"_institution_ratio":institution_ratio,
            "series":[{
                "date":r.trade_date.isoformat(),"foreign":r.foreign_net,"institution":r.institution_net,
                "individual":r.individual_net,"financial_investment":r.financial_investment_net,
                "investment_trust":r.investment_trust_net,"pension":r.pension_net,
            } for r in sorted(rows,key=lambda x:x.trade_date)],
        }
        items.append(item)
    foreign_p=_percentile_scores([x["_foreign_ratio"] for x in items])
    inst_p=_percentile_scores([x["_institution_ratio"] for x in items])
    strength_p=_percentile_scores([x["flow_ratio"] for x in items])
    for idx,item in enumerate(items):
        # Price confirmation follows the selected flow period, not only today's
        # tick, so a 7-day flow score reflects the same 7-day context.
        price=float(item.get("period_change_rate") or 0)
        price_confirm=max(0.0,min(1.0,(price+2.0)/6.0))
        score=(foreign_p[idx]*25+inst_p[idx]*25+item["breadth"]*15+item["persistence"]*15+strength_p[idx]*10+price_confirm*10)
        item["score"]=round(max(0,min(100,score)),1)
        item["insight"]=_flow_insight(item)
        selected={
            "all":item["foreign_net"]+item["institution_net"],"foreign":item["foreign_net"],
            "institution":item["institution_net"],"individual":item["individual_net"],
            "financial_investment":item["financial_investment_net"],"investment_trust":item["investment_trust_net"],
            "pension":item["pension_net"],"insurance":item["insurance_net"],"bank":item["bank_net"],
            "private_equity":item["private_equity_net"],
        }[investor]
        item["selected_net"]=selected
        item.pop("_foreign_ratio",None);item.pop("_institution_ratio",None)

    # Presentation filters are intentionally applied only after scoring.
    if market in {"KOSPI","KOSDAQ"}:
        items=[x for x in items if x.get("market")==market]
    if keyword:
        key_lower=keyword.lower()
        items=[x for x in items if key_lower in str(x.get("name") or "").lower() or key_lower in str(x.get("code") or "").lower()]

    if signal=="joint": items=[x for x in items if x["joint_buy"]]
    elif signal=="streak": items=[x for x in items if max(x["foreign_streak"],x["institution_streak"])>=3]
    elif signal=="reversal": items=[x for x in items if x["reversal"]]
    elif signal=="foreign": items=[x for x in items if x["foreign_net"]>0]
    elif signal=="institution": items=[x for x in items if x["institution_net"]>0]
    elif signal!="all": raise HTTPException(422,"지원하지 않는 수급 신호 필터입니다.")
    sort=str(sort or "score").lower()
    if sort=="net": items.sort(key=lambda x:(x["selected_net"],x["score"]),reverse=True)
    elif sort=="strength": items.sort(key=lambda x:(x["flow_ratio"],x["score"]),reverse=True)
    elif sort=="persistence": items.sort(key=lambda x:(x["persistence"],x["score"]),reverse=True)
    else: items.sort(key=lambda x:(x["score"],x["selected_net"]),reverse=True)
    total=len(items);pages=max(1,math.ceil(total/page_size));safe_page=min(page,pages)
    page_items=items[(safe_page-1)*page_size:safe_page*page_size]
    return {
        "items":page_items,"page":safe_page,"pages":pages,"total":total,"page_size":page_size,
        "period":period,"investor":investor,"investor_label":FLOW_INVESTOR_LABELS[investor],"market":market,
        "signal":signal,"sort":sort,"latest_date":dates[0].isoformat(),"oldest_date":dates[-1].isoformat(),
        "advanced_enabled":bool(advanced),"unit":"shares",
        "summary":{
            "joint_buy":sum(1 for x in items if x["joint_buy"]),
            "foreign_positive":sum(1 for x in items if x["foreign_net"]>0),
            "institution_positive":sum(1 for x in items if x["institution_net"]>0),
            "reversal":sum(1 for x in items if x["reversal"]),
        },
    }


def _stock_detail_flow_payload(db:Session,stock:Stock,period:int=7):
    rows=(
        db.query(StockInvestorFlowDaily)
        .filter(StockInvestorFlowDaily.stock_code==stock.code)
        .order_by(StockInvestorFlowDaily.trade_date.desc())
        .limit(max(1,min(int(period or 7),20)))
        .all()
    )
    if not rows:
        return {
            "available":False,
            "code":stock.code,
            "name":stock.name,
            "days":0,
            "series":[],
            "message":"관리자 수급 동기화 후 이 종목의 수급 데이터가 표시됩니다.",
        }
    ordered=sorted(rows,key=lambda x:x.trade_date)
    foreign=sum(float(r.foreign_net or 0) for r in rows)
    institution=sum(float(r.institution_net or 0) for r in rows)
    individual=sum(float(r.individual_net or 0) for r in rows)
    item={
        "foreign_net":foreign,
        "institution_net":institution,
        "individual_net":individual,
        "joint_buy":foreign>0 and institution>0,
        "foreign_streak":_positive_streak(rows,"foreign_net"),
        "institution_streak":_positive_streak(rows,"institution_net"),
        "reversal":False,
    }
    if len(rows)>1:
        latest=rows[0]
        prior=rows[1:]
        item["reversal"]=(
            (float(latest.foreign_net or 0)>0 and sum(float(r.foreign_net or 0) for r in prior)<0)
            or (float(latest.institution_net or 0)>0 and sum(float(r.institution_net or 0) for r in prior)<0)
        )
    return {
        "available":True,
        "code":stock.code,
        "name":stock.name,
        "days":len(rows),
        "latest_date":rows[0].trade_date.isoformat(),
        "foreign_net":foreign,
        "institution_net":institution,
        "individual_net":individual,
        "foreign_buy_days":sum(1 for r in rows if float(r.foreign_net or 0)>0),
        "institution_buy_days":sum(1 for r in rows if float(r.institution_net or 0)>0),
        "insight":_flow_insight(item),
        "series":[{
            "date":r.trade_date.isoformat(),
            "foreign":float(r.foreign_net or 0),
            "institution":float(r.institution_net or 0),
            "individual":float(r.individual_net or 0),
        } for r in ordered],
        "source":"mysql-investor-flow-cache",
    }


@app.get("/api/stocks/{code}/investor-flow")
async def stock_investor_flow(
    code:str,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    stock=_stocklog_public_stock(db,code)
    if not stock:
        raise HTTPException(404,"종목을 찾을 수 없습니다.")

    today=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    cache_key=(u.id,code,today)
    cached=_investor_flow_cache.get(cache_key)
    now_mono=time.monotonic()
    if cached and now_mono-float(cached.get("cached_at",0))<90:
        return {**cached["payload"],"cached":True,"stale":False}

    try:
        _,cli=client_for(u,db)
        commit_or_rollback(db)
        result=await cli.stock_investor_trades(code,today)
        payload={
            "available":True,
            "code":stock.code,
            "name":stock.name,
            "date":result.get("date") or today,
            "unit":result.get("unit") or "shares",
            "categories":result.get("categories") or {},
            "source":result.get("source") or "kiwoom-ka10060",
            "cached":False,
            "stale":False,
            "observed_at":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        }
        _investor_flow_cache[cache_key]={"cached_at":now_mono,"payload":payload}
        return payload
    except Exception as exc:
        if cached:
            return {**cached["payload"],"cached":True,"stale":True}
        msg=str(exc)
        if "429" in msg:
            raise HTTPException(429,"투자자별 매매동향 조회가 일시적으로 제한되었습니다.") from exc
        raise HTTPException(502,"키움 투자자별 매매동향을 불러오지 못했습니다.") from exc


@app.get("/api/stocks/{code}/chart")
async def stock_chart(
    code: str,
    force: bool = Query(False),
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    s = _stocklog_public_stock(db,code)
    if not s:
        raise HTTPException(404, "종목을 찾을 수 없습니다.")

    sync_meta = await _ensure_real_chart(u, s, db, force=force)
    chart = _build_real_chart(code, db, limit=500)
    if not chart:
        raise HTTPException(502, "실제 일봉 데이터가 없습니다. 데모 데이터는 사용하지 않습니다.")

    return {
        "stock": {
            "code": s.code,
            "name": s.name,
            "price": s.price,
            "change_rate": s.change_rate,
        },
        "chart": chart,
        "_meta": {
            "source": "kiwoom-real",
            "demo": False,
            **sync_meta,
        },
    }

@app.get("/api/stocks/{code}/quote")
async def stock_quote(
    code: str,
    force: bool = Query(False),
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """
    실제 키움 일봉 기준 최신 시세 요약.
    데모 fallback은 사용하지 않습니다.
    """
    s = _stocklog_public_stock(db,code)
    if not s:
        raise HTTPException(404, "종목을 찾을 수 없습니다.")

    sync_meta = await _ensure_real_chart(u, s, db, force=force)
    chart = _build_real_chart(code, db, limit=5)
    if not chart:
        raise HTTPException(502, "실제 시세 데이터가 없습니다.")

    latest = chart[-1]
    prev = chart[-2] if len(chart) >= 2 else None

    close = float(latest.get("close") or 0)
    prev_close = float(prev.get("close") or 0) if prev else 0
    change = close - prev_close if prev_close else 0
    change_rate = (change / prev_close * 100) if prev_close else 0

    return {
        "code": s.code,
        "name": s.name,
        "market": s.market,
        "sector": s.sector,
        "date": latest.get("date"),
        "current_price": close,
        "previous_close": prev_close,
        "change": change,
        "change_rate": change_rate,
        "open": latest.get("open"),
        "high": latest.get("high"),
        "low": latest.get("low"),
        "volume": latest.get("volume"),
        "holding_quantity": 0,
        "_meta": {
            "source": "kiwoom-real-daily",
            "demo": False,
            **sync_meta,
        },
    }

@app.get("/api/stocks/{code}/orderbook")
async def stock_orderbook(
    code:str,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    stock=_stocklog_public_stock(db,code)

    if not stock:
        raise HTTPException(
            404,
            "종목을 찾을 수 없습니다.",
        )

    try:
        _,cli=client_for(
            u,
            db,
        )
        commit_or_rollback(db)

        data=await cli.stock_orderbook(
            code
        )

        return {
            **data,
            "name":
                stock.name,
            "market":
                stock.market,
        }

    except KiwoomError as exc:
        raise HTTPException(
            502,
            "실제 호가 정보를 불러오지 못했습니다.",
        ) from exc


@app.get("/api/smart/categories")
def smart_categories(u:User=Depends(current_user),db:Session=Depends(get_db)):
    _require_feature(u,db,"smart_analysis")
    return ["전체","가치주","성장주","모멘텀","배당","저변동","종합"]

def _safe_float(value):
    try:
        return float(value) if value is not None else None
    except Exception:
        return None



def _safe_theme_db_stats(
    db: Session,
):
    """
    Admin/dashboard status must never fail because optional theme
    metadata tables are missing or temporarily unavailable.
    """
    result = {
        "themes": 0,
        "stock_theme_links": 0,
        "kiwoom_themes": 0,
        "market_themes": 0,
        "kiwoom_theme_links": 0,
        "market_theme_links": 0,
        "themes_table": False,
        "stock_themes_table": False,
        "theme_db_error": None,
    }

    try:
        inspector = inspect(engine)
        tables = set(
            inspector.get_table_names()
        )

        result["themes_table"] = (
            "themes" in tables
        )
        result["stock_themes_table"] = (
            "stock_themes" in tables
        )

    except Exception as exc:
        result["theme_db_error"] = (
            "스키마 확인 실패: "
            f"{type(exc).__name__}: {exc}"
        )
        return result

    try:
        if result["themes_table"]:
            result["themes"] = (
                db.query(Theme)
                .filter(
                    Theme.is_active == True
                )
                .count()
            )

        if result["stock_themes_table"]:
            result["stock_theme_links"] = db.query(StockTheme).count()
            result["kiwoom_theme_links"] = (
                db.query(StockTheme)
                .filter(StockTheme.source=="kiwoom")
                .count()
            )
            result["market_theme_links"] = (
                db.query(StockTheme)
                .filter(StockTheme.source=="infostock")
                .count()
            )
            result["kiwoom_themes"] = (
                db.query(StockTheme.theme_code)
                .filter(StockTheme.source=="kiwoom")
                .distinct()
                .count()
            )
            result["market_themes"] = (
                db.query(StockTheme.theme_code)
                .filter(StockTheme.source=="infostock")
                .distinct()
                .count()
            )

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass

        result["theme_db_error"] = (
            f"{type(exc).__name__}: {exc}"
        )
        result["themes"] = 0
        result["stock_theme_links"] = 0
        result["kiwoom_themes"] = 0
        result["market_themes"] = 0
        result["kiwoom_theme_links"] = 0
        result["market_theme_links"] = 0

    return result


NAME_BUSINESS_HINTS=(
    ("반도체","반도체"),
    ("바이오","바이오"),
    ("제약","제약"),
    ("화학","화학"),
    ("건설","건설"),
    ("제강","철강·금속"),
    ("철강","철강·금속"),
    ("제지","제지"),
    ("식품","식품"),
    ("푸드","식품"),
    ("증권","증권"),
    ("보험","보험"),
    ("금융","금융"),
    ("은행","은행"),
    ("에너지","에너지"),
    ("전력","전력·전기"),
    ("미디어","미디어·콘텐츠"),
    ("교육","교육"),
    ("게임","게임"),
    ("엔터","엔터테인먼트"),
    ("해운","해운"),
    ("항공","항공"),
    ("모터스","자동차·부품"),
    ("자동차","자동차·부품"),
    ("로봇","로봇"),
    ("로보","로봇"),
)


def _meaningful_sector(stock: Stock):
    sector=str(stock.sector or "").strip()
    if sector and sector not in ("기타","-","미분류","제조","제조업"):
        return sector
    return ""


def _stock_name_business_hint(stock: Stock):
    name=str(stock.name or "").strip()
    for token,label in NAME_BUSINESS_HINTS:
        if token in name:
            return label
    return ""


def _stock_theme_fallback(stock: Stock):
    """
    Theme membership is non-exhaustive.

    Real theme relations remain first-class. If no theme exists, return
    an actual business classification instead of the misleading
    `키움 테마 미분류` label.
    """
    industry=str(
        getattr(stock,"industry_name","")
        or ""
    ).strip()

    if industry:
        return {
            "name":industry,
            "source":"industry",
            "label":f"사업 · {industry}",
            "source_label":"OpenDART 공식 업종코드 기반",
        }

    sector=_meaningful_sector(stock)
    if sector:
        return {
            "name":sector,
            "source":"sector",
            "label":f"업종 · {sector}",
            "source_label":"저장된 실제 업종",
        }

    hint=_stock_name_business_hint(stock)
    if hint:
        return {
            "name":hint,
            "source":"name_hint",
            "label":f"사업 · {hint}",
            "source_label":"회사명 기반 보조분류",
        }

    return {
        "name":"기타 사업",
        "source":"business_other",
        "label":"사업 · 기타",
        "source_label":"사업분류 보강 대기",
    }


def _apply_dart_industry_profile(stock: Stock, profile):
    if not profile:
        return False

    code=str(profile.get("industry_code") or "").strip()
    name=str(profile.get("industry_name") or "").strip()

    if not code or not name:
        return False

    stock.industry_code=code
    stock.industry_name=name
    stock.industry_source="opendart"
    stock.industry_updated_at=datetime.now()

    # Never overwrite a meaningful existing sector.
    if not _meaningful_sector(stock):
        stock.sector=name

    stock.updated_at=datetime.now()
    return True


def _classification_coverage_stats(
    db: Session,
    *,
    sample_limit: int=30,
    analysis_eligible_only: bool=False,
):
    query=db.query(Stock).filter(Stock.is_active==True)
    if analysis_eligible_only:
        query=query.filter(Stock.is_analysis_eligible==True,Stock.market.in_(STOCKLOG_PUBLIC_MARKETS))
    stocks=(
        query
        .order_by(Stock.market.asc(),Stock.code.asc())
        .all()
    )

    active_codes={str(s.code) for s in stocks}

    theme_codes={
        str(code)
        for (code,) in (
            db.query(StockTheme.stock_code)
            .join(Theme,Theme.theme_code==StockTheme.theme_code)
            .filter(
                Theme.is_active==True,
                StockTheme.source.in_(["infostock","kiwoom"]),
            )
            .distinct()
            .all()
        )
    }

    actual_theme_codes=active_codes & theme_codes

    source_counts={
        "theme":0,
        "opendart":0,
        "sector":0,
        "name_hint":0,
        "other":0,
    }
    weak=[]
    dart_industry=0
    effective=0

    for stock in stocks:
        code=str(stock.code)

        if code in actual_theme_codes:
            source_counts["theme"]+=1
            effective+=1
            continue

        industry=str(getattr(stock,"industry_name","") or "").strip()
        if industry:
            source_counts["opendart"]+=1
            dart_industry+=1
            effective+=1
            continue

        if _meaningful_sector(stock):
            source_counts["sector"]+=1
            effective+=1
            continue

        if _stock_name_business_hint(stock):
            source_counts["name_hint"]+=1
            effective+=1
            continue

        source_counts["other"]+=1
        if len(weak)<sample_limit:
            weak.append({
                "code":stock.code,
                "name":stock.name,
                "market":stock.market,
                "fallback":_stock_theme_fallback(stock),
            })

    total=len(stocks)

    return {
        "active_stocks":total,
        "actual_theme_stocks":len(actual_theme_codes),
        "dart_industry_stocks":dart_industry,
        "effective_classified_stocks":effective,
        "weak_fallback_stocks":max(0,total-effective),
        "coverage_percent":round(effective/total*100 if total else 0,2),
        "source_counts":source_counts,
        "weak_sample":weak,
    }



def _theme_coverage_stats(
    db: Session,
    *,
    sample_limit: int = 30,
):
    try:
        active_stocks = (
            db.query(Stock)
            .filter(*_stocklog_public_clauses())
            .order_by(Stock.market.asc(), Stock.code.asc())
            .all()
        )

        themed_codes = {
            str(code)
            for (code,) in (
                db.query(StockTheme.stock_code)
                .join(
                    Theme,
                    Theme.theme_code == StockTheme.theme_code,
                )
                .filter(Theme.is_active == True, StockTheme.source == "kiwoom")
                .distinct()
                .all()
            )
        }

        active_codes = {str(stock.code) for stock in active_stocks}
        official_codes = active_codes & themed_codes

        missing = [
            stock
            for stock in active_stocks
            if str(stock.code) not in official_codes
        ]

        total = len(active_stocks)
        official = len(official_codes)

        return {
            "active_stocks": total,
            "official_theme_stocks": official,
            "missing_official_theme_stocks": len(missing),
            "coverage_percent": round(
                official / total * 100 if total else 0,
                2,
            ),
            "missing_sample": [
                {
                    "code": stock.code,
                    "name": stock.name,
                    "market": stock.market,
                    "sector": stock.sector,
                    "fallback": _stock_theme_fallback(stock),
                }
                for stock in missing[:sample_limit]
            ],
        }

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass

        return {
            "active_stocks": 0,
            "official_theme_stocks": 0,
            "missing_official_theme_stocks": 0,
            "coverage_percent": 0,
            "missing_sample": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _theme_source_label(source: str):
    return {
        "infostock": "시장 테마 · 인포스탁",
        "kiwoom": "키움 REST 테마",
    }.get(str(source or ""), str(source or "기타"))


def _theme_map_for_codes(
    db: Session,
    codes,
    limit: int | None = None,
    sources=None,
):
    codes = [str(x) for x in (codes or []) if x]
    if not codes:
        return {}
    public_codes=_stocklog_public_code_set(db,codes)
    codes=[code for code in codes if code in public_codes]
    if not codes:
        return {}

    try:
        q = (
            db.query(StockTheme, Theme)
            .join(Theme, Theme.theme_code == StockTheme.theme_code)
            .filter(
                StockTheme.stock_code.in_(codes),
                Theme.is_active == True,
            )
        )

        if sources:
            values = [str(x) for x in sources if x]
            if values:
                q = q.filter(StockTheme.source.in_(values))

        rows = (
            q.order_by(
                StockTheme.stock_code.asc(),
                case(
                    (StockTheme.source == "infostock", 0),
                    (StockTheme.source == "kiwoom", 1),
                    else_=9,
                ),
                Theme.change_rate.desc(),
                Theme.name.asc(),
            )
            .all()
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print("[WARN] multi-source theme query failed:", repr(exc))
        return {}

    result = {}
    canonical_map = _theme_canonical_map(db)
    classified={}
    for stock in db.query(Stock).filter(Stock.code.in_(codes)).all():
        tax=_stock_taxonomy_payload(stock)
        if not tax.get("primary") or not _classification_is_verified(stock):
            continue
        classified[stock.code]={
            # Smart list badges show stable parent groups. Detailed child themes
            # are returned separately and never split Samsung/Jeju Semiconductor.
            "names":tax.get("groups") or [tax.get("primary")],
            "subthemes":tax.get("subthemes") or [],
            "business":str(stock.primary_business or "").strip(),
            "confidence":stock.classification_confidence,
        }
    for code,item in classified.items():
        bucket=result.setdefault(code,[])
        for idx,name in enumerate(item["names"]):
            if limit is not None and len(bucket)>=limit:
                break
            bucket.append({
                "theme_code":f"CLASSIFIED:{code}:{idx}",
                "name":name,
                "display_name":name,
                "source":"classification",
                "sources":["classification"],
                "source_labels":["StockLog 사업기반 분류"],
                "confidence":item.get("confidence"),
                "primary_business":item.get("business"),
                "subthemes":item.get("subthemes") or [],
                "_normalized":re.sub(r"\s+","",name.lower()),
            })

    for relation, theme in rows:
        # Provider themes remain stored as evidence, but do not leak back into
        # Smart badges once a stock has a verified business classification.
        if relation.stock_code in classified:
            continue
        bucket = result.setdefault(relation.stock_code, [])
        source = str(relation.source or "kiwoom")
        raw_theme_name=str(theme.name or "").strip()
        display_name = canonical_map.get(str(theme.theme_code or "")) or canonical_group_for_theme(raw_theme_name) or raw_theme_name
        normalized = re.sub(r"\s+", "", display_name.lower())

        same = next(
            (x for x in bucket if x.get("_normalized") == normalized),
            None,
        )

        if same:
            if source not in same["sources"]:
                same["sources"].append(source)
                same["source_labels"].append(_theme_source_label(source))
            continue

        if limit is not None and len(bucket) >= limit:
            continue

        bucket.append({
            "theme_code": theme.theme_code,
            "name": display_name,
            "raw_name": str(theme.name or "").strip(),
            "change_rate": theme.change_rate,
            "source": source,
            "source_label": _theme_source_label(source),
            "sources": [source],
            "source_labels": [_theme_source_label(source)],
            "_normalized": normalized,
        })

    for bucket in result.values():
        for item in bucket:
            item.pop("_normalized", None)

    return result


def _provider_taxonomy_for_codes(db: Session, codes=None):
    """Build parent/sub themes from raw provider relations without losing rows."""
    q=(db.query(StockTheme,Theme)
       .join(Theme,Theme.theme_code==StockTheme.theme_code)
       .filter(Theme.is_active==True))
    if codes is not None:
        values=[str(x) for x in codes if x]
        if not values:
            return {}
        q=q.filter(StockTheme.stock_code.in_(values))
    result={}
    try:
        rows=q.all()
    except Exception:
        rollback_quietly(db)
        return {}
    canonical=_theme_canonical_map(db)
    for relation,theme in rows:
        code=str(relation.stock_code or "")
        raw=str(theme.name or relation.theme_name or "").strip()
        if not code or not raw:
            continue
        bucket=result.setdefault(code,{"groups":set(),"subthemes":set()})
        matches=map_theme_name(raw)
        if matches:
            for item in matches:
                group=str(item.get("group") or "").strip()
                sub=str(item.get("subtheme") or "").strip()
                if group: bucket["groups"].add(group)
                if sub and sub!=group: bucket["subthemes"].add(sub)
        else:
            display=canonical.get(str(theme.theme_code or "")) or raw
            display=_clean_canonical_theme_name(display)
            if display: bucket["groups"].add(display)
    return result


def _effective_stock_theme_sets(stock: Stock, provider_map=None):
    """Verified engine result first; provider taxonomy only for unresolved rows."""
    tax=_stock_taxonomy_payload(stock)
    if tax.get("primary") and _classification_is_verified(stock):
        return set(tax.get("groups") or []),set(tax.get("subthemes") or []),"engine"
    fallback=(provider_map or {}).get(str(stock.code),{})
    return set(fallback.get("groups") or []),set(fallback.get("subthemes") or []),"provider_fallback"


def _stock_theme_items(
    db: Session,
    stock_code: str,
    limit: int | None = None,
    sources=None,
):
    return _theme_map_for_codes(
        db,
        [stock_code],
        limit=limit,
        sources=sources,
    ).get(stock_code, [])


def _theme_source_coverage_stats(
    db: Session,
    source: str,
    sample_limit: int = 30,
):
    stocks = (
        db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .order_by(Stock.market.asc(), Stock.code.asc())
        .all()
    )

    linked_codes = {
        str(code)
        for (code,) in (
            db.query(StockTheme.stock_code)
            .join(Theme, Theme.theme_code == StockTheme.theme_code)
            .filter(
                Theme.is_active == True,
                StockTheme.source == source,
            )
            .distinct()
            .all()
        )
    }

    active_codes = {str(x.code) for x in stocks}
    linked = active_codes & linked_codes
    missing = [x for x in stocks if str(x.code) not in linked]
    total = len(stocks)

    return {
        "source": source,
        "active_stocks": total,
        "linked_stocks": len(linked),
        "missing_stocks": len(missing),
        "coverage_percent": round(len(linked) / total * 100 if total else 0, 2),
        "missing_sample": [
            {
                "code": x.code,
                "name": x.name,
                "market": x.market,
                "sector": x.sector,
            }
            for x in missing[:sample_limit]
        ],
    }


def _combined_theme_coverage_stats(
    db: Session,
    sample_limit: int = 30,
):
    stocks = (
        db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .order_by(Stock.market.asc(), Stock.code.asc())
        .all()
    )

    linked_codes = {
        str(code)
        for (code,) in (
            db.query(StockTheme.stock_code)
            .join(Theme, Theme.theme_code == StockTheme.theme_code)
            .filter(
                Theme.is_active == True,
                StockTheme.source.in_(["infostock", "kiwoom"]),
            )
            .distinct()
            .all()
        )
    }

    active_codes = {str(x.code) for x in stocks}
    linked = active_codes & linked_codes
    missing = [x for x in stocks if str(x.code) not in linked]
    total = len(stocks)

    return {
        "active_stocks": total,
        "linked_stocks": len(linked),
        "missing_stocks": len(missing),
        "coverage_percent": round(len(linked) / total * 100 if total else 0, 2),
        "missing_sample": [
            {
                "code": x.code,
                "name": x.name,
                "market": x.market,
                "sector": x.sector,
                "fallback": _stock_theme_fallback(x),
            }
            for x in missing[:sample_limit]
        ],
    }



def _theme_keywords(theme_name: str):
    """
    Output theme names are always actual Kiwoom Theme rows.
    Keywords are only used to find mentions in real news/report text.
    """
    name = str(theme_name or "").strip()
    lowered = name.lower()

    parts = {
        x.strip()
        for x in re.split(
            r"[\s/·,()_\-+&]+",
            lowered,
        )
        if len(x.strip()) >= 2
    }

    keywords = {
        lowered,
        *parts,
    }

    alias_groups = {
        "hbm": {
            "hbm",
            "고대역폭메모리",
            "hbm3",
            "hbm3e",
            "hbm4",
        },
        "반도체": {
            "반도체",
            "메모리",
            "dram",
            "d램",
            "낸드",
            "nand",
            "파운드리",
        },
        "ai": {
            "인공지능",
            "ai",
            "생성형 ai",
            "온디바이스 ai",
        },
        "로봇": {
            "로봇",
            "휴머노이드",
            "협동로봇",
        },
        "원전": {
            "원전",
            "원자력",
            "smr",
            "소형모듈원자로",
        },
        "2차전지": {
            "2차전지",
            "이차전지",
            "배터리",
            "양극재",
            "음극재",
            "전고체",
            "전해질",
        },
        "자동차": {
            "자동차",
            "전기차",
            "자율주행",
            "완성차",
        },
        "조선": {
            "조선",
            "선박",
            "lng선",
            "수주",
        },
        "바이오": {
            "바이오",
            "신약",
            "임상",
            "의약품",
        },
        "방산": {
            "방산",
            "방위산업",
            "무기체계",
        },
    }

    for key, aliases in alias_groups.items():
        if (
            key in lowered
            or any(
                alias in lowered
                for alias in aliases
            )
        ):
            keywords.update(aliases)

    return {
        x
        for x in keywords
        if x and len(x) >= 2
    }


def _infer_related_themes(
    db: Session,
    news,
    reports,
    official_theme_codes=None,
    limit: int = 5,
):
    """
    Real-data-only inference:
    - Candidate names come only from synchronized real market/kiwoom themes.
    - Evidence comes only from actual Google News items and broker report titles.
    - No new/synthetic theme name is generated.
    """
    try:
        themes = (
            db.query(Theme)
            .filter(
                Theme.is_active == True
            )
            .all()
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass

        print(
            "[WARN] related-theme inference skipped:",
            repr(exc),
        )
        return []

    if not themes:
        return []

    official_theme_codes = set(
        official_theme_codes or []
    )

    news_docs = []

    for item in (news or []):
        if not isinstance(item, dict):
            continue

        news_docs.append(
            {
                "title": str(
                    item.get("title") or ""
                ).lower(),
                "description": str(
                    item.get("description") or ""
                ).lower(),
            }
        )

    report_titles = [
        str(
            item.get("title") or ""
        ).lower()
        for item in (reports or [])
        if isinstance(item, dict)
    ]

    result = []

    for theme in themes:
        keywords = _theme_keywords(
            theme.name
        )

        score = 0.0
        evidence = 0

        for doc in news_docs:
            title = doc["title"]
            description = doc["description"]

            matched = False

            for keyword in keywords:
                if keyword in title:
                    score += (
                        6.0
                        if keyword
                        == theme.name.lower()
                        else 2.5
                    )
                    matched = True

                if keyword in description:
                    score += 1.0
                    matched = True

            if matched:
                evidence += 1

        for report_title in report_titles:
            matched = False

            for keyword in keywords:
                if keyword in report_title:
                    score += (
                        7.0
                        if keyword
                        == theme.name.lower()
                        else 3.0
                    )
                    matched = True

            if matched:
                evidence += 1

        if score < 3:
            continue

        # Existing official association is shown separately, but a real
        # news/report mention can still receive an evidence score.
        result.append(
            {
                "theme_code": theme.theme_code,
                "name": theme.name,
                "score": round(
                    min(100.0, score * 5.0),
                    0,
                ),
                "evidence_count": evidence,
                "already_official": (
                    theme.theme_code
                    in official_theme_codes
                ),
                "source": "news+reports",
            }
        )

    result.sort(
        key=lambda x: (
            x["score"],
            x["evidence_count"],
        ),
        reverse=True,
    )

    return result[:limit]


def _smart_stock_payload(stock: Stock) -> dict:
    return {
        "code": stock.code,
        "name": stock.name,
        **_stock_name_payload(stock),
        "market": stock.market,
        "price": stock.price,
        "change_rate": stock.change_rate,
        "market_cap": stock.market_cap,
        "per": stock.per,
        "pbr": stock.pbr,
        "eps": stock.eps,
        "bps": stock.bps,
        "roe": stock.roe,
        "revenue_growth": stock.revenue_growth,
        "operating_margin": stock.operating_margin,
        "dividend_yield": stock.dividend_yield,
        "momentum_20d": stock.momentum_20d,
        "volatility": stock.volatility,
    }


def _smart_signal_maps(db: Session, codes: list[str]):
    """Read already-synchronized flow/news/report signals in bulk.

    Smart recommendation must stay read-only and must never trigger external API
    calls.  This helper therefore only uses local synchronized cache tables.
    """
    unique_codes=list(dict.fromkeys(str(code or "").strip() for code in codes if code))
    if not unique_codes:
        return {},{}

    flow_cutoff=datetime.now().date()-timedelta(days=45)
    flow_rows=(
        db.query(StockInvestorFlowDaily)
        .filter(
            StockInvestorFlowDaily.stock_code.in_(unique_codes),
            StockInvestorFlowDaily.trade_date>=flow_cutoff,
        )
        .order_by(
            StockInvestorFlowDaily.stock_code.asc(),
            StockInvestorFlowDaily.trade_date.desc(),
        )
        .all()
    )
    flow_grouped={}
    for row in flow_rows:
        bucket=flow_grouped.setdefault(row.stock_code,[])
        if len(bucket)<10:
            bucket.append(row)

    flow_map={}
    for code,items in flow_grouped.items():
        foreign=sum(float(item.foreign_net or 0) for item in items)
        institution=sum(float(item.institution_net or 0) for item in items)
        combined=[float(item.foreign_net or 0)+float(item.institution_net or 0) for item in items]
        positive_days=sum(1 for value in combined if value>0)
        gross=sum(abs(float(item.foreign_net or 0))+abs(float(item.institution_net or 0)) for item in items)
        net=foreign+institution
        direction_ratio=(net/gross*100.0) if gross>0 else 0.0
        flow_map[code]={
            "days":len(items),
            "foreign_net":foreign,
            "institution_net":institution,
            "positive_days":positive_days,
            "net_ratio":direction_ratio,
        }

    six_months_ago=datetime.now()-timedelta(days=183)
    sentiment_map={code:{"positive":0,"neutral":0,"negative":0,"news":0,"reports":0} for code in unique_codes}

    news_rows=(
        db.query(NewsCache.stock_code,NewsCache.sentiment)
        .filter(
            NewsCache.stock_code.in_(unique_codes),
            or_(
                NewsCache.published_dt>=six_months_ago,
                and_(NewsCache.published_dt.is_(None),NewsCache.fetched_at>=six_months_ago),
            ),
        )
        .all()
    )
    for code,sentiment in news_rows:
        item=sentiment_map.setdefault(code,{"positive":0,"neutral":0,"negative":0,"news":0,"reports":0})
        label=str(sentiment or "neutral").lower()
        if label not in {"positive","neutral","negative"}: label="neutral"
        item[label]+=1
        item["news"]+=1

    report_rows=(
        db.query(BrokerReportCache.stock_code,BrokerReportCache.sentiment)
        .filter(
            BrokerReportCache.stock_code.in_(unique_codes),
            or_(
                BrokerReportCache.report_dt>=six_months_ago,
                and_(BrokerReportCache.report_dt.is_(None),BrokerReportCache.fetched_at>=six_months_ago),
            ),
        )
        .all()
    )
    for code,sentiment in report_rows:
        item=sentiment_map.setdefault(code,{"positive":0,"neutral":0,"negative":0,"news":0,"reports":0})
        label=str(sentiment or "neutral").lower()
        if label not in {"positive","neutral","negative"}: label="neutral"
        item[label]+=1
        item["reports"]+=1

    return flow_map,sentiment_map


_smart_score_cache_lock=threading.Lock()


def _smart_cached_components(stock: Stock) -> list[dict]:
    try:
        raw=json.loads(stock.smart_score_components_json or "[]")
        if not isinstance(raw,list):
            return []
        # Ignore malformed legacy entries instead of allowing a single stale
        # cache row to make the full Smart list return HTTP 500.
        return [item for item in raw if isinstance(item,dict)]
    except Exception:
        return []


def _smart_cached_profile(stock: Stock, profile_scores=None, profile_code=""):
    return profile_score_from_components(
        _smart_cached_components(stock),
        stock=_smart_stock_payload(stock),
        profile_scores=profile_scores,
        profile_code=profile_code,
        aggregate_score=stock.smart_ai_score,
    )


def _smart_score_cache_stats(db: Session):
    total=(db.query(Stock).filter(*_stocklog_public_clauses()).count())
    cached=(db.query(Stock).filter(
        *_stocklog_public_clauses(),
        Stock.smart_ai_score.isnot(None),
        Stock.smart_score_updated_at.isnot(None),
    ).count())
    latest=(db.query(Stock.smart_score_updated_at)
        .filter(Stock.smart_score_updated_at.isnot(None))
        .order_by(Stock.smart_score_updated_at.desc())
        .first())
    latest_at=latest[0] if latest else None
    return {
        "total":int(total or 0),
        "cached":int(cached or 0),
        "coverage":round((cached/max(1,total))*100,1) if total else 0.0,
        "updated_at":latest_at.isoformat() if latest_at else None,
    }


def _rebuild_smart_score_cache(db: Session, *, batch_size:int=220, progress_callback=None):
    """Refresh stock-side Smart scores using only already synchronized DB data.

    This never calls an external API. It is intentionally cheap enough to run
    as the final step of full synchronization and stores only stock-side scores;
    per-member profile fit is calculated from cached component scores.
    """
    stocks=(db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .order_by(Stock.id.asc())
        .all())
    total=len(stocks)
    now=datetime.now()
    updated=0
    for start in range(0,total,max(20,int(batch_size or 220))):
        chunk=stocks[start:start+max(20,int(batch_size or 220))]
        codes=[stock.code for stock in chunk]
        flow_map,sentiment_map=_smart_signal_maps(db,codes)
        for stock in chunk:
            scorecard=_smart_scorecard(stock,flow_map=flow_map,sentiment_map=sentiment_map)
            stock.smart_ai_score=float(scorecard.get("ai_score") or 0)
            stock.smart_ai_label=str(scorecard.get("ai_label") or "")[:40]
            stock.smart_score_coverage=float(scorecard.get("coverage") or 0)
            stock.smart_score_components_json=json.dumps(scorecard.get("components") or [],ensure_ascii=False,separators=(",",":"))
            stock.smart_score_updated_at=now
            updated+=1
        commit_or_rollback(db)
        if progress_callback:
            try:
                progress_callback(updated,total)
            except Exception:
                logger.exception("smart score cache progress callback failed")
    return {**_smart_score_cache_stats(db),"updated":updated}


def _ensure_smart_score_cache(db: Session):
    stats=_smart_score_cache_stats(db)
    # A newly upgraded database has no cached values yet. Build once from local
    # synchronized data so the Smart page works immediately without waiting for
    # another nightly sync. Partial caches are left for the next sync to finish.
    if stats["total"] and stats["cached"]==0:
        with _smart_score_cache_lock:
            stats=_smart_score_cache_stats(db)
            if stats["total"] and stats["cached"]==0:
                return _rebuild_smart_score_cache(db)
    return stats


def _smart_scorecard(
    stock: Stock,
    *,
    flow_map=None,
    sentiment_map=None,
    profile_scores=None,
    profile_code="",
):
    return build_scorecard(
        _smart_stock_payload(stock),
        flow=(flow_map or {}).get(stock.code),
        sentiment=(sentiment_map or {}).get(stock.code),
        profile_scores=profile_scores,
        profile_code=profile_code,
    )


def _smart_row(stock: Stock, theme_map=None):
    tax=_stock_taxonomy_payload(stock)
    verified_theme = tax.get("primary") if _classification_is_verified(stock) else None
    provider_items=(theme_map or {}).get(stock.code, [])
    provider_fallback=(provider_items[0].get("display_name") or provider_items[0].get("name")) if provider_items else None
    # The Smart list should expose when the underlying recommendation inputs
    # were actually refreshed.  Pick the newest meaningful stock-data timestamp
    # rather than the API response time, because the recommendation endpoint
    # itself is polled frequently even when the database inputs are unchanged.
    updated_candidates = [
        stock.smart_score_updated_at,
        stock.kiwoom_metrics_updated_at,
        stock.dart_financials_updated_at,
        stock.valuation_calculated_at,
        stock.updated_at,
    ]
    recommendation_updated_at = max(
        (value for value in updated_candidates if value is not None),
        default=None,
    )

    return {
        "code": stock.code,
        "name": stock.name,
        **_stock_name_payload(stock),
        "market": stock.market,
        "sector": stock.sector,
        "industry_name": stock.industry_name,
        "industry_source": stock.industry_source,
        "primary_theme": verified_theme or provider_fallback or stock.primary_theme,
        "primary_business": stock.primary_business if verified_theme else None,
        "investment_theme": verified_theme,
        "theme_group": verified_theme,
        "theme_groups": tax.get("groups") if verified_theme else [],
        "theme_subthemes": tax.get("subthemes") if verified_theme else [],
        "theme_engine_version": tax.get("engine_version") if verified_theme else None,
        "classification_confidence": stock.classification_confidence,
        "classification_reason": stock.classification_reason,
        "themes": (theme_map or {}).get(stock.code, []),
        "theme_fallback": verified_theme or provider_fallback or _stock_theme_fallback(stock),
        "display_category": verified_theme or provider_fallback or stock.primary_theme or (stock.sector if stock.sector and stock.sector != "기타" else stock.category),
        "category": stock.category,
        "price": stock.price,
        "change_rate": stock.change_rate,
        "market_cap": stock.market_cap,
        "per": stock.per,
        "pbr": stock.pbr,
        "eps": stock.eps,
        "bps": stock.bps,
        "roe": stock.roe,
        "revenue_growth": stock.revenue_growth,
        "operating_margin": stock.operating_margin,
        "dividend_yield": stock.dividend_yield,
        "momentum_20d": stock.momentum_20d,
        "volatility": stock.volatility,
        "score": stock.score,
        "recommendation_updated_at": (
            recommendation_updated_at.isoformat()
            if recommendation_updated_at
            else None
        ),
        "kiwoom_metrics_updated_at": (
            stock.kiwoom_metrics_updated_at.isoformat()
            if stock.kiwoom_metrics_updated_at
            else None
        ),
        "dart_financials_updated_at": (
            stock.dart_financials_updated_at.isoformat()
            if stock.dart_financials_updated_at
            else None
        ),
    }


def _ai_recommendation_score(stock: Stock):
    """
    StockLog 종합 알고리즘 점수.

    Financial quality remains the core of the recommendation, while a modest
    part of the score now reacts to 20-day momentum and today's price move.
    This avoids a visually frozen top-20 list for several days without turning
    the Smart page into a short-term momentum screener.
    """
    score = 0.0
    reasons = []

    roe = _safe_float(stock.roe)
    growth = _safe_float(stock.revenue_growth)
    margin = _safe_float(stock.operating_margin)
    per = _safe_float(stock.per)
    pbr = _safe_float(stock.pbr)
    momentum = _safe_float(stock.momentum_20d)
    day_change = _safe_float(stock.change_rate)
    dividend = _safe_float(stock.dividend_yield)

    # 76 points: relatively slow-moving quality / valuation inputs.
    if roe is not None:
        score += max(0, min(24, roe * 1.2))
        if roe >= 12:
            reasons.append("ROE 우수")

    if growth is not None:
        score += max(0, min(19, 9 + growth * 0.5))
        if growth >= 8:
            reasons.append("매출 성장")

    if margin is not None:
        score += max(0, min(14, margin * 0.7))
        if margin >= 10:
            reasons.append("영업이익률 양호")

    if per is not None and per > 0:
        if per <= 12:
            score += 17
            reasons.append("PER 저평가")
        elif per <= 20:
            score += 11
        elif per <= 30:
            score += 5

    if pbr is not None and pbr > 0:
        if pbr <= 1.2:
            score += 9
            reasons.append("PBR 저평가")
        elif pbr <= 2:
            score += 5

    # 17 points: market-sensitive inputs.  They are intentionally capped so
    # one strong trading day cannot overwhelm business fundamentals.
    if momentum is not None:
        score += max(0, min(12, 5 + momentum * 0.3))
        if momentum >= 10:
            reasons.append("20일 모멘텀 양호")

    if day_change is not None and day_change > 0:
        score += max(0, min(5, day_change * 0.8))
        if day_change >= 2:
            reasons.append("당일 주가 흐름 양호")

    # Up to 2 points for meaningful cash return.
    if dividend is not None and dividend >= 2:
        score += min(2, max(0, dividend - 1))
        reasons.append("배당")

    return round(min(100, score), 1), reasons[:4]


def _smart_hidden_summary_reasons(stock: Stock, theme_items=None):
    """List-card reasons should add context that is not already visible in PER/PBR/ROE/growth columns."""
    out=[]
    momentum=_safe_float(stock.momentum_20d)
    day_change=_safe_float(stock.change_rate)
    dividend=_safe_float(stock.dividend_yield)
    volatility=_safe_float(stock.volatility)
    market_cap=_safe_float(stock.market_cap)
    if theme_items:
        names=[str(x.get("name") or "").strip() for x in theme_items if isinstance(x,dict) and x.get("name")]
        if names: out.append(f"{names[0]} 테마에 속한 종목")
    if momentum is not None:
        if momentum>=10: out.append("최근 20거래일 동안 주가 흐름이 강한 편")
        elif momentum<=-10: out.append("최근 20거래일 주가 흐름은 약해 진입 시점 확인 필요")
    if volatility is not None:
        if volatility<=2.5: out.append("최근 가격 흔들림이 비교적 작은 편")
        elif volatility>=6: out.append("가격 변동이 큰 종목이라 분할 접근이 유리")
    if dividend is not None and dividend>=2.5: out.append(f"배당수익률 {dividend:.1f}% 수준의 현금환원 요소 보유")
    if market_cap is not None and market_cap>=100000: out.append("시가총액이 큰 편이라 상대적으로 거래 기반이 안정적")
    if day_change is not None and abs(day_change)>=4: out.append("오늘 주가 변동폭이 커 단기 추격 여부를 확인할 필요")
    return out[:4]


def _buffett_score(stock: Stock):
    """버핏 스타일: 수익성/가격/성장/안정성 중심의 규칙 기반 점수."""
    score = 0.0
    reasons = []

    roe = _safe_float(stock.roe)
    margin = _safe_float(stock.operating_margin)
    growth = _safe_float(stock.revenue_growth)
    per = _safe_float(stock.per)
    pbr = _safe_float(stock.pbr)
    dividend = _safe_float(stock.dividend_yield)

    if roe is not None:
        if roe >= 15:
            score += 30
            reasons.append("ROE 15% 이상")
        elif roe >= 10:
            score += 20
        elif roe >= 7:
            score += 10

    if margin is not None:
        if margin >= 15:
            score += 20
            reasons.append("높은 영업이익률")
        elif margin >= 10:
            score += 14
        elif margin >= 5:
            score += 7

    if growth is not None:
        if growth >= 10:
            score += 15
            reasons.append("매출 성장")
        elif growth >= 3:
            score += 9
        elif growth >= 0:
            score += 4

    if per is not None and per > 0:
        if per <= 12:
            score += 20
            reasons.append("합리적 PER")
        elif per <= 18:
            score += 14
        elif per <= 25:
            score += 7

    if pbr is not None and pbr > 0:
        if pbr <= 1.5:
            score += 10
            reasons.append("낮은 PBR")
        elif pbr <= 2.5:
            score += 5

    if dividend is not None and dividend >= 2:
        score += min(5, dividend)

    return round(min(100, score), 1), reasons[:4]


def _custom_formula_dict(formula: SmartFormula | None):
    defaults = {
        "per_max": 15.0,
        "pbr_max": 2.0,
        "roe_min": 10.0,
        "revenue_growth_min": 5.0,
        "operating_margin_min": 7.0,
        "dividend_yield_min": None,
        "momentum_20d_min": None,
        "market_cap_min": None,
    }

    if not formula:
        return defaults

    for key in list(defaults):
        defaults[key] = getattr(formula, key)
    return defaults


def _matches_custom(stock: Stock, formula: dict):
    checks = [
        ("per_max", stock.per, lambda v, x: v <= x),
        ("pbr_max", stock.pbr, lambda v, x: v <= x),
        ("roe_min", stock.roe, lambda v, x: v >= x),
        ("revenue_growth_min", stock.revenue_growth, lambda v, x: v >= x),
        ("operating_margin_min", stock.operating_margin, lambda v, x: v >= x),
        ("dividend_yield_min", stock.dividend_yield, lambda v, x: v >= x),
        ("momentum_20d_min", stock.momentum_20d, lambda v, x: v >= x),
        ("market_cap_min", stock.market_cap, lambda v, x: v >= x),
    ]

    matched = 0
    active = 0
    reasons = []

    labels = {
        "per_max": "PER",
        "pbr_max": "PBR",
        "roe_min": "ROE",
        "revenue_growth_min": "매출성장",
        "operating_margin_min": "영업이익률",
        "dividend_yield_min": "배당",
        "momentum_20d_min": "모멘텀",
        "market_cap_min": "시가총액",
    }

    for key, raw, predicate in checks:
        target = formula.get(key)
        if target is None:
            continue
        active += 1
        value = _safe_float(raw)
        if value is not None and predicate(value, float(target)):
            matched += 1
            reasons.append(labels[key])
        else:
            return False, 0, reasons

    score = round(matched / active * 100, 1) if active else 0
    return True, score, reasons



def _investment_profile_payload(row: InvestmentProfile | None):
    if not row:
        return None
    try:
        scores=json.loads(row.scores_json or "{}")
    except Exception:
        scores={}
    if not isinstance(scores, dict):
        # Older/partially-written profile rows must not take the whole Smart
        # recommendation endpoint down. Treat invalid payloads as empty.
        scores={}
    return {
        "result_code":row.result_code,
        "scores":scores,
        "completed_at":row.completed_at.isoformat() if row.completed_at else None,
    }


def _profile_recommendation_score(
    stock: Stock,
    profile_scores: dict | None,
    profile_code: str = "",
):
    """Match stock characteristics to the user's continuous investment-DNA scores."""
    percentages=(profile_scores or {}).get("percentages") or {}
    code=str(profile_code or "")

    defaults={
        "horizon":{"L":34.0,"N":33.0,"S":33.0},
        "risk":{"A":50.0,"D":50.0},
        "value":{"G":50.0,"V":50.0},
        "profit":{"P":50.0,"H":50.0},
        "spread":{"F":50.0,"M":50.0},
    }
    code_axes=[("horizon",0),("risk",1),("value",2),("profit",3),("spread",4)]
    for axis,idx in code_axes:
        if idx < len(code) and code[idx] in defaults[axis]:
            if not percentages.get(axis):
                percentages[axis]={k:(100.0 if k==code[idx] else 0.0) for k in defaults[axis]}

    def pct(axis,letter):
        try:
            return float((percentages.get(axis) or {}).get(letter,defaults[axis][letter]))
        except Exception:
            return defaults[axis][letter]

    def norm(value, low, high, neutral=50.0):
        value=_safe_float(value)
        if value is None:
            return neutral
        if high<=low:
            return neutral
        return round(max(0.0,min(100.0,(value-low)/(high-low)*100.0)),2)

    roe=norm(stock.roe,0,25)
    growth=norm(stock.revenue_growth,-5,30)
    margin=norm(stock.operating_margin,0,25)
    momentum=norm(stock.momentum_20d,-15,25)
    change=norm(stock.change_rate,-8,12)
    dividend=norm(stock.dividend_yield,0,6,35)

    per=_safe_float(stock.per)
    if per is None or per<=0:
        per_score=45.0
    elif per<=8:
        per_score=100.0
    elif per<=15:
        per_score=85.0
    elif per<=25:
        per_score=65.0
    elif per<=40:
        per_score=40.0
    else:
        per_score=15.0

    pbr=_safe_float(stock.pbr)
    if pbr is None or pbr<=0:
        pbr_score=45.0
    elif pbr<=0.8:
        pbr_score=100.0
    elif pbr<=1.5:
        pbr_score=85.0
    elif pbr<=2.5:
        pbr_score=65.0
    elif pbr<=5:
        pbr_score=40.0
    else:
        pbr_score=15.0

    volatility=_safe_float(stock.volatility)
    stability_vol=50.0 if volatility is None else max(0.0,min(100.0,100.0-(volatility*7.0)))
    market_cap=_safe_float(stock.market_cap)
    if market_cap is None or market_cap<=0:
        cap_stability=45.0
    else:
        import math
        cap_stability=max(0.0,min(100.0,(math.log10(max(market_cap,100.0))-2.0)/4.7*100.0))

    quality=(roe+margin)/2.0
    growth_score=(growth*0.55+roe*0.25+margin*0.20)
    valuation=(per_score*0.55+pbr_score*0.35+dividend*0.10)
    momentum_score=(momentum*0.75+change*0.25)
    stability=(stability_vol*0.45+cap_stability*0.35+quality*0.10+dividend*0.10)
    long_quality=(quality*0.35+growth_score*0.35+stability*0.30)
    balanced=(growth_score+valuation+momentum_score+stability)/4.0
    short_opportunity=(momentum_score*0.65+growth_score*0.20+quality*0.15)
    aggressive_opportunity=(growth_score*0.40+momentum_score*0.40+quality*0.20)
    early_profit=(momentum_score*0.45+valuation*0.30+stability*0.25)
    big_upside=(growth_score*0.50+quality*0.25+momentum_score*0.25)
    conviction=(growth_score*0.35+quality*0.30+momentum_score*0.20+valuation*0.15)

    horizon_fit=(pct("horizon","L")*long_quality+pct("horizon","N")*balanced+pct("horizon","S")*short_opportunity)/100.0
    risk_fit=(pct("risk","A")*aggressive_opportunity+pct("risk","D")*stability)/100.0
    value_fit=(pct("value","G")*growth_score+pct("value","V")*valuation)/100.0
    profit_fit=(pct("profit","P")*early_profit+pct("profit","H")*big_upside)/100.0
    spread_fit=(pct("spread","F")*conviction+pct("spread","M")*stability)/100.0

    profile_fit=(horizon_fit+risk_fit+value_fit+profit_fit+spread_fit)/5.0
    base_score,_=_ai_recommendation_score(stock)
    final=max(0.0,min(100.0,profile_fit*0.78+base_score*0.22))

    reasons=[]
    if pct("value","G")>=60 and growth_score>=65:
        reasons.append("성장 선호와 높은 적합도")
    if pct("value","V")>=60 and valuation>=65:
        reasons.append("가치 선호와 가격 매력")
    if pct("risk","D")>=60 and stability>=62:
        reasons.append("방어 성향에 안정적")
    if pct("risk","A")>=60 and aggressive_opportunity>=65:
        reasons.append("공격 성향에 기회 점수 우수")
    if pct("horizon","L")>=45 and long_quality>=65:
        reasons.append("장기 보유 성향과 적합")
    if pct("horizon","S")>=45 and momentum_score>=65:
        reasons.append("단기 모멘텀 성향과 적합")
    if pct("spread","M")>=60 and stability>=60:
        reasons.append("분산형 포트폴리오에 적합")
    if pct("spread","F")>=60 and conviction>=68:
        reasons.append("집중형 후보로 높은 확신도")
    if not reasons:
        best=max(
            [(growth_score,"성장성"),(valuation,"밸류"),(quality,"수익성"),(momentum_score,"모멘텀"),(stability,"안정성")],
            key=lambda x:x[0],
        )
        reasons.append(f"{best[1]} 강점")

    return round(final,1),reasons[:4],{
        "profile_fit":round(profile_fit,1),
        "growth":round(growth_score,1),
        "value":round(valuation,1),
        "momentum":round(momentum_score,1),
        "stability":round(stability,1),
        "quality":round(quality,1),
    }

def _smart_score_context(
    stock: Stock,
    mode: str,
    formula: dict | None = None,
    profile_scores: dict | None = None,
    profile_code: str = "",
):
    """Single source of truth for Smart recommendation scores."""
    mode=str(mode or "ai").lower().strip()

    if mode == "buffett":
        score,reasons=_buffett_score(stock)
        return {
            "mode":"buffett",
            "score":score,
            "reasons":reasons,
            "matched":score >= 40,
            "type":"버핏 스타일 기준",
        }

    if mode == "custom":
        matched,score,reasons=_matches_custom(
            stock,
            formula or _custom_formula_dict(None),
        )
        return {
            "mode":"custom",
            "score":score,
            "reasons":reasons,
            "matched":matched,
            "type":"나만의 공식",
        }

    if mode == "profile":
        score,reasons,components=_profile_recommendation_score(
            stock,
            profile_scores,
            profile_code,
        )
        return {
            "mode":"profile",
            "score":score,
            "reasons":reasons,
            "matched":score >= 35,
            "type":"내 투자성향 맞춤",
            "profile_components":components,
        }

    score,reasons=_ai_recommendation_score(stock)
    return {
        "mode":"ai",
        "score":score,
        "reasons":reasons,
        "matched":score >= 35,
        "type":"StockLog 종합 알고리즘",
    }


def _smart_score_summary(score_ctx):
    score=float(score_ctx.get("score") or 0)
    label=_recommendation_label_from_score(score)
    score_type=score_ctx.get("type") or "StockLog 점수"
    if label=="추천": body="추천 구간입니다. 현재 선택한 스마트 분석 기준에서 긍정 조건 충족도가 높은 편입니다."
    elif label=="비추천": body="비추천 구간입니다. 현재 선택한 스마트 분석 기준에서 충족도가 낮거나 위험 요인이 상대적으로 큽니다."
    else: body="관망 구간입니다. 긍정 조건과 주의 요인이 혼재해 추가 확인이 필요한 상태입니다."
    return f"현재 {score_type} 점수는 {score:.1f}점으로 {body} 상단 추천 점수와 아래 자동 분석 점수는 동일한 산식·동일한 최신 데이터 기준입니다."

def _recommendation_label_from_score(score):
    score=float(score or 0)
    return (
        "추천"
        if score >= 68
        else "관망"
        if score >= 48
        else "비추천"
    )

@app.get("/api/stocks/autocomplete")
def stock_autocomplete(q:str=Query("",min_length=1),limit:int=Query(8,ge=1,le=20),_:User=Depends(current_user),db:Session=Depends(get_db)):
    term=q.strip(); like=f"%{term}%"; prefix=f"{term}%"
    query=(db.query(Stock).filter(*_stocklog_public_clauses(),or_(Stock.name.like(like),Stock.code.like(like),Stock.name_aliases_json.like(like)))
          .order_by(case((Stock.code.like(prefix),0),(Stock.name.like(prefix),1),else_=2),Stock.market_cap.desc()).limit(limit))
    rows=query.all()
    if not rows:
        _upsert_kind_search_matches(db,term)
        rows=query.all()
    theme_map = _theme_map_for_codes(
        db,
        [s.code for s in rows],
        limit=2,
    )

    return [{
        "code":s.code,
        "name":s.name,
        **_stock_name_payload(s),
        "market":s.market,
        "price":s.price,
        "category":s.category,
        "industry_name":s.industry_name,
        "industry_source":s.industry_source,
        "themes":theme_map.get(s.code, []),
        "theme_fallback":_stock_theme_fallback(s),
    } for s in rows]


_THEME_GBOT_CACHE: dict[str, tuple[float, dict]] = {}
_THEME_GBOT_CACHE_TTL = 300.0


def _theme_gbot_cache_key(payload: dict) -> str:
    compact = {
        "theme_code": str(payload.get("theme_code") or "").strip(),
        "theme_name": str(payload.get("theme_name") or "").strip(),
        "change_rate": round(float(payload.get("change_rate") or 0), 2),
        "stocks": [
            {
                "code": str(x.get("code") or ""),
                "change_rate": round(float(x.get("change_rate") or 0), 2),
                "price": int(float(x.get("price") or 0)),
            }
            for x in (payload.get("stocks") or [])[:12]
            if isinstance(x, dict)
        ],
    }
    return hashlib.sha1(json.dumps(compact, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


@app.post("/api/themes/gbot-summary")
async def theme_gbot_summary(
    body: dict,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Compact Gbot explanation for the currently selected strong theme.

    The constituent list is already fetched by the browser. Reusing that
    snapshot avoids a second Kiwoom request and keeps this feature read-only.
    Successful summaries are cached briefly so repeatedly opening the same
    theme does not consume Gemini quota every time.
    """
    _require_feature(u, db, "theme_analysis")
    theme_name = str(body.get("theme_name") or "").strip()
    theme_code = str(body.get("theme_code") or "").strip()
    stocks = [x for x in (body.get("stocks") or []) if isinstance(x, dict)][:12]
    allowed_theme_codes=_stocklog_public_code_set(db,[str(x.get("code") or "").strip() for x in stocks])
    stocks=[x for x in stocks if str(x.get("code") or "").strip() in allowed_theme_codes]
    if not theme_name:
        raise HTTPException(422, "테마 이름이 필요합니다.")
    if not stocks:
        return {"available": False, "message": "구성종목 데이터가 없어 Gbot 요약을 만들지 않았습니다."}

    cache_key = _theme_gbot_cache_key(body)
    cached = _THEME_GBOT_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _THEME_GBOT_CACHE_TTL:
        return {**cached[1], "cached": True}

    api_key = str(get_provider_credentials(PROVIDER_GEMINI, db).get("api_key") or "").strip()
    if not api_key:
        return {"available": False, "message": "관리자에서 StockLog Gbot API 연결을 먼저 설정해주세요."}

    analyst = GeminiAnalyst(api_key)
    rising = sum(1 for x in stocks if float(x.get("change_rate") or 0) > 0)
    falling = sum(1 for x in stocks if float(x.get("change_rate") or 0) < 0)
    top = sorted(stocks, key=lambda x: float(x.get("change_rate") or -999), reverse=True)[:6]
    top_codes = [str(x.get("code") or "").strip() for x in top if str(x.get("code") or "").strip()]
    recent_news = []
    if top_codes:
        try:
            news_rows = (
                db.query(NewsCache)
                .filter(NewsCache.stock_code.in_(top_codes))
                .order_by(NewsCache.published_dt.desc(), NewsCache.fetched_at.desc(), NewsCache.id.desc())
                .limit(18)
                .all()
            )
            seen_titles = set()
            for row in news_rows:
                title = str(row.title or "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                recent_news.append({
                    "stock_code": row.stock_code,
                    "title": title[:180],
                    "published_at": row.published_dt.isoformat() if row.published_dt else str(row.published_at or ""),
                    "sentiment": str(row.sentiment or "neutral"),
                    "importance": round(float(row.importance_score or 0), 2),
                })
                if len(recent_news) >= 10:
                    break
        except Exception:
            rollback_quietly(db)
            recent_news = []
    prompt = {
        "theme": {
            "code": theme_code,
            "name": theme_name,
            "change_rate_percent": round(float(body.get("change_rate") or 0), 2),
            "rising_count": rising,
            "falling_count": falling,
            "constituent_count": len(stocks),
        },
        "top_constituents": [
            {
                "code": str(x.get("code") or ""),
                "name": str(x.get("name") or ""),
                "market": str(x.get("market") or ""),
                "price": float(x.get("price") or 0),
                "change_rate_percent": round(float(x.get("change_rate") or 0), 2),
                "per": x.get("per"),
                "pbr": x.get("pbr"),
                "roe": x.get("roe"),
            }
            for x in top
        ],
        "recent_stocklog_news": recent_news,
    }
    system = (
        "너는 StockLog Gbot의 시장 테마 분석 엔진이다. 사용자는 단순한 한두 문장 요약이 아니라 '왜 하필 지금 이 테마가 강한지'를 이해하고 싶어한다. "
        "반드시 제공된 현재 테마 등락률, 구성종목 상승/하락 분포, 상위 주도 종목, StockLog에 저장된 최근 뉴스만 근거로 한국어로 구체적으로 설명한다. "
        "summary는 4~6문장으로 작성한다. 첫 문장은 현재 강세의 가장 직접적인 촉매 또는 관찰 가능한 이유를 제시하고, 이어서 어떤 주도 종목이 테마를 끌고 있는지, "
        "상승이 테마 전반으로 확산되는지 일부 종목에 편중되는지, 최근 뉴스·실적·수주·정책 등 실제 확인된 재료가 가격 움직임과 어떻게 연결되는지를 설명한다. "
        "마지막에는 현재 강세가 단기 수급성인지 지속 가능성이 있는 흐름인지 근거 범위 안에서 평가한다. 명확한 단일 촉매가 확인되지 않으면 억지로 만들지 말고, "
        "'뚜렷한 단일 뉴스보다 구성종목 동반 상승/주도주 급등/수급 확산이 강세를 만들고 있다'처럼 데이터 기반으로 솔직하게 설명한다. "
        "없는 정책·수주·실적을 추측하지 않는다. 상승이 소수 종목에 편중되었거나 급등 과열이면 반드시 risks에 명시한다. JSON 객체만 반환한다. "
        "가독성을 위해 summary_lines에는 문장별로 나눠 4~6개 객체를 넣고, 그중 핵심 결론·촉매에 해당하는 1~2개만 important=true로 표시한다. "
        "형식: headline 문자열, summary 4~6문장 문자열, summary_lines=[{text:문장, important:boolean}], drivers 핵심 근거 3~4개 문자열, risks 주의점 1~3개 문자열, "
        "tone은 '강한 확산','선별적 강세','초기 강세','과열 주의','혼조' 중 하나."
    )
    # Recent-news/cache reads are complete; Gemini may take tens of seconds.
    # Do not keep a request-scoped DB transaction while waiting for it.
    commit_or_rollback(db)
    try:
        parsed, meta = await analyst._generate_json(
            system=system,
            prompt=prompt,
            model=analyst.background_model,
            request_kind="theme-gbot-summary",
            stock_code=theme_code,
            max_output_tokens=1400,
        )
        raw_summary=str(parsed.get("summary") or "").strip()[:1800]
        raw_lines=parsed.get("summary_lines") or []
        summary_lines=[]
        if isinstance(raw_lines,list):
            for item in raw_lines[:6]:
                if isinstance(item,dict):
                    text=str(item.get("text") or "").strip()[:420]
                    if text:
                        summary_lines.append({"text":text,"important":bool(item.get("important"))})
                elif str(item).strip():
                    summary_lines.append({"text":str(item).strip()[:420],"important":False})
        if not summary_lines and raw_summary:
            fallback_lines=[x.strip() for x in re.split(r"(?<=[.!?])\s+",raw_summary) if x.strip()][:6]
            summary_lines=[{"text":text,"important":index==0} for index,text in enumerate(fallback_lines)]
        if summary_lines and not any(x.get("important") for x in summary_lines):
            summary_lines[0]["important"]=True
        result = {
            "available": True,
            "headline": str(parsed.get("headline") or f"{theme_name} 강세 흐름").strip()[:120],
            "summary": raw_summary,
            "summary_lines":summary_lines,
            "drivers": [str(x).strip()[:180] for x in (parsed.get("drivers") or []) if str(x).strip()][:4],
            "risks": [str(x).strip()[:220] for x in (parsed.get("risks") or []) if str(x).strip()][:3],
            "tone": str(parsed.get("tone") or "시장 강도 분석").strip()[:40],
            "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
            "cached": False,
        }
        if not result["summary"]:
            result["summary"] = f"{theme_name} 구성종목의 현재 등락 분포를 기준으로 강세 흐름을 확인했습니다."
        if not result["summary_lines"]:
            result["summary_lines"]=[{"text":result["summary"],"important":True}]
        _THEME_GBOT_CACHE[cache_key] = (time.time(), result)
        if len(_THEME_GBOT_CACHE) > 300:
            cutoff = time.time() - _THEME_GBOT_CACHE_TTL
            for key, (created, _) in list(_THEME_GBOT_CACHE.items()):
                if created < cutoff:
                    _THEME_GBOT_CACHE.pop(key, None)
        return result
    except GeminiRateLimitError as exc:
        return {
            "available": False,
            "message": f"Gbot 호출 한도에 잠시 도달했습니다. 약 {max(1, int(math.ceil(exc.retry_after_seconds / 60)))}분 뒤 다시 선택하면 자동으로 재시도합니다.",
        }
    except Exception as exc:
        logger.warning("theme Gbot summary failed theme=%s error=%s", theme_name, _sync_error_text(exc, 500))
        return {"available": False, "message": "Gbot 테마 요약을 잠시 불러오지 못했습니다. 구성종목은 정상적으로 확인할 수 있습니다."}


@app.get("/api/themes")
async def strong_themes(
    limit:int=Query(80,ge=1,le=200),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"theme_analysis")
    """Live Kiwoom themes with cache/DB fallback.

    Theme browsing is intentionally low priority. A temporary broker throttle
    must never blank a page that already has synchronized real theme data.
    """
    try:
        _,cli=client_for(u,db)
        commit_or_rollback(db)
        await cli.issue_token()
        rows=await cli.theme_groups()
        rows.sort(key=lambda x: x.get("change_rate") if x.get("change_rate") is not None else -999999, reverse=True)
        return {
            "source":"kiwoom-theme-cache" if cli.last_theme_cache_stale else "kiwoom-theme",
            "stale":bool(cli.last_theme_cache_stale),
            "warning":"키움 호출 제한으로 마지막 정상 테마 데이터를 표시합니다." if cli.last_theme_cache_stale else "",
            "items":rows[:limit],
        }
    except HTTPException:
        raise
    except Exception as exc:
        print("[WARN] Kiwoom theme live request failed; using stored themes:", repr(exc))
        try:
            rows=(
                db.query(Theme)
                .filter(Theme.is_active==True)
                .order_by(Theme.change_rate.desc(),Theme.name.asc())
                .limit(limit)
                .all()
            )
            if rows:
                return {
                    "source":"stored-theme-fallback",
                    "stale":True,
                    "warning":"키움 실시간 조회가 잠시 제한되어 마지막 동기화 테마를 표시합니다.",
                    "items":[{
                        "theme_code":x.theme_code,
                        "theme_name":x.name,
                        "change_rate":x.change_rate,
                        "stock_count":x.stock_count,
                    } for x in rows],
                }
        except Exception as db_exc:
            print("[WARN] stored theme fallback failed:", repr(db_exc))
        raise HTTPException(502,"키움 테마 조회가 일시적으로 제한되었습니다. 잠시 후 자동으로 다시 시도됩니다.") from exc


def _theme_detail_stock_enrichment(
    db: Session,
    codes: list[str],
):
    """
    Read only the columns needed by the strong-theme page.

    Explicit columns keep theme browsing independent from unrelated Stock
    model/schema additions. If enrichment fails, caller can still render the
    actual Kiwoom theme constituents.
    """
    clean_codes=[
        str(code)
        for code in dict.fromkeys(
            codes or []
        )
        if re.fullmatch(
            r"\d{6}",
            str(code),
        )
    ]

    if not clean_codes:
        return {}

    rows=(
        db.query(
            Stock.code,
            Stock.name,
            Stock.price,
            Stock.change_rate,
            Stock.market,
            Stock.primary_theme,
            Stock.per,
            Stock.pbr,
            Stock.roe,
        )
        .filter(
            Stock.code.in_(clean_codes),
            *_stocklog_public_clauses(),
        )
        .all()
    )

    result={}

    for row in rows:
        mapping=row._mapping

        result[
            str(
                mapping["code"]
            )
        ]={
            "code":
                mapping["code"],
            "name":
                mapping["name"],
            "price":
                mapping["price"],
            "change_rate":
                mapping["change_rate"],
            "market":
                mapping["market"],
            "primary_theme":
                mapping["primary_theme"],
            "per":
                mapping["per"],
            "pbr":
                mapping["pbr"],
            "roe":
                mapping["roe"],
        }

    return result


def _stored_theme_detail_items(
    db: Session,
    theme_code: str,
):
    """
    Fallback only to previously synchronized REAL theme relations.

    No synthetic constituents are generated. This is used only when a live
    Kiwoom detail request temporarily fails.
    """
    relations=(
        db.query(
            StockTheme.stock_code,
            StockTheme.theme_name,
            StockTheme.source,
        )
        .filter(
            StockTheme.theme_code
            == theme_code
        )
        .order_by(
            StockTheme.stock_code.asc()
        )
        .all()
    )

    if not relations:
        return [],""

    codes=[
        str(
            row._mapping[
                "stock_code"
            ]
        )
        for row in relations
    ]

    enrichment=(
        _theme_detail_stock_enrichment(
            db,
            codes,
        )
    )

    theme_name=""

    items=[]

    for relation in relations:
        rm=relation._mapping

        code=str(
            rm["stock_code"]
        )

        if not theme_name:
            theme_name=str(
                rm["theme_name"]
                or ""
            )

        stock=enrichment.get(
            code,
            {}
        )

        items.append(
            {
                "code":
                    code,
                "name":
                    stock.get(
                        "name"
                    )
                    or code,
                "price":
                    stock.get(
                        "price"
                    ),
                "change_rate":
                    stock.get(
                        "change_rate"
                    ),
                "market":
                    stock.get(
                        "market"
                    ),
                "category":
                    theme_name
                    or stock.get(
                        "primary_theme"
                    ),
                "per":
                    stock.get(
                        "per"
                    ),
                "pbr":
                    stock.get(
                        "pbr"
                    ),
                "roe":
                    stock.get(
                        "roe"
                    ),
            }
        )

    items.sort(
        key=lambda x:(
            x.get(
                "change_rate"
            )
            if x.get(
                "change_rate"
            ) is not None
            else -999999
        ),
        reverse=True,
    )

    return items,theme_name


@app.get("/api/themes/{theme_code}")
async def theme_detail(
    theme_code:str,
    theme_name:str=Query(""),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"theme_analysis")
    """
    Strong-theme browsing must be READ ONLY.

    Previous versions persisted Theme/StockTheme rows inside this GET endpoint.
    That meant a successful Kiwoom ka90002 response could still become a 500
    merely because MySQL had a lock/schema/constraint issue.

    Persistence belongs to Admin -> full theme synchronization.
    This endpoint now:
      1) reads live Kiwoom constituents,
      2) optionally enriches them from StockLog's stock cache,
      3) never writes/commits theme DB state,
      4) falls back to previously synchronized real relations if Kiwoom is
         temporarily unavailable.
    """
    code_value=str(
        theme_code
        or ""
    ).strip()

    requested_name=str(
        theme_name
        or ""
    ).strip()

    if not code_value:
        raise HTTPException(
            status_code=400,
            detail="테마 코드가 올바르지 않습니다.",
        )

    live_error=None

    try:
        _,cli=client_for(
            u,
            db,
        )
        commit_or_rollback(db)

        await cli.issue_token()

        members=await cli.theme_stocks(
            code_value
        )

    except HTTPException:
        raise

    except Exception as exc:
        live_error=exc
        members=None

        print(
            "[WARN] live theme detail request failed:",
            f"theme_code={code_value}",
            f"theme_name={requested_name!r}",
            repr(exc),
        )

    # Live provider failed -> previously synchronized REAL relations.
    if members is None:
        try:
            cached_items,cached_name=(
                _stored_theme_detail_items(
                    db,
                    code_value,
                )
            )

        except Exception as cache_exc:
            cached_items=[]
            cached_name=""

            print(
                "[WARN] stored theme detail fallback failed:",
                f"theme_code={code_value}",
                repr(cache_exc),
            )

            try:
                db.rollback()
            except Exception:
                pass

        if cached_items:
            return {
                "theme_code":
                    code_value,
                "theme_name":
                    requested_name
                    or cached_name,
                "source":
                    "stored-real-theme",
                "live":
                    False,
                "fallback":
                    True,
                "message":
                    (
                        "실시간 테마 조회가 일시적으로 불안정해 "
                        "최근 정상 동기화된 실제 구성종목을 표시합니다."
                    ),
                "items":
                    cached_items,
            }

        # Neither live nor stored real data exists.
        if isinstance(
            live_error,
            KiwoomError,
        ):
            raise HTTPException(
                status_code=502,
                detail=(
                    "키움에서 현재 테마 구성종목을 가져오지 못했습니다. "
                    "잠시 후 다시 시도해주세요."
                ),
            )

        raise HTTPException(
            status_code=500,
            detail=(
                "테마 구성종목을 불러오지 못했습니다. "
                "잠시 후 다시 시도해주세요."
            ),
        )

    # A legitimate theme can theoretically return no current members.
    if not members:
        return {
            "theme_code":
                code_value,
            "theme_name":
                requested_name,
            "source":
                "kiwoom-live",
            "live":
                True,
            "fallback":
                False,
            "message":
                "현재 확인되는 구성종목이 없습니다.",
            "items":[],
        }

    codes=[
        str(
            item.get(
                "code"
            )
            or ""
        )
        for item in members
    ]

    # StockLog enrichment must never make a successful live theme response fail.
    try:
        saved=(
            _theme_detail_stock_enrichment(
                db,
                codes,
            )
        )

    except Exception as enrich_exc:
        saved={}

        print(
            "[WARN] theme detail local enrichment failed:",
            f"theme_code={code_value}",
            repr(enrich_exc),
        )

        try:
            db.rollback()
        except Exception:
            pass

    result=[]

    for item in members:
        code=str(
            item.get(
                "code"
            )
            or ""
        )

        stock=saved.get(
            code,
            {}
        )
        if not stock:
            continue

        result.append(
            {
                "code":
                    code,
                "name":
                    item.get(
                        "name"
                    )
                    or stock.get(
                        "name"
                    )
                    or code,
                "price":
                    (
                        item.get(
                            "price"
                        )
                        if item.get(
                            "price"
                        ) is not None
                        else stock.get(
                            "price"
                        )
                    ),
                "change_rate":
                    (
                        item.get(
                            "change_rate"
                        )
                        if item.get(
                            "change_rate"
                        ) is not None
                        else stock.get(
                            "change_rate"
                        )
                    ),
                "market":
                    stock.get(
                        "market"
                    ),
                "category":
                    requested_name
                    or stock.get(
                        "primary_theme"
                    ),
                "per":
                    stock.get(
                        "per"
                    ),
                "pbr":
                    stock.get(
                        "pbr"
                    ),
                "roe":
                    stock.get(
                        "roe"
                    ),
            }
        )

    result.sort(
        key=lambda x:(
            x.get(
                "change_rate"
            )
            if x.get(
                "change_rate"
            ) is not None
            else -999999
        ),
        reverse=True,
    )

    return {
        "theme_code":
            code_value,
        "theme_name":
            requested_name,
        "source":
            "kiwoom-live",
        "live":
            True,
        "fallback":
            False,
        "message":
            "",
        "items":
            result,
    }


# ----------------------------------------------------------------------
# v3.30.2 Smart-page market overview
# ----------------------------------------------------------------------

_MARKET_OVERVIEW_TTL_SECONDS=30
_MARKET_OVERVIEW_CACHE_FILE=(
    Path(__file__)
    .resolve()
    .parents[2]
    / "runtime"
    / "market_overview_last_actual.json"
)

_market_overview_cache={
    "fetched_at":0.0,
    "items":{},
}
_market_overview_lock=asyncio.Lock()

_MARKET_OVERVIEW_SYMBOLS=(
    {
        "key":"nasdaq",
        "label":"NASDAQ",
        "sub_label":"Nasdaq Composite",
        "symbol":"^IXIC",
        "encoded_symbol":"%5EIXIC",
        "value_suffix":"",
        "decimals":2,
        "kind":"index",
    },
    {
        "key":"vix",
        "label":"VIX",
        "sub_label":"CBOE Volatility Index",
        "symbol":"^VIX",
        "encoded_symbol":"%5EVIX",
        "value_suffix":"",
        "decimals":2,
        "kind":"index",
    },
    {
        "key":"kospi",
        "label":"KOSPI",
        "sub_label":"코스피",
        "symbol":"^KS11",
        "encoded_symbol":"%5EKS11",
        "value_suffix":"",
        "decimals":2,
        "kind":"index",
    },
    {
        "key":"kosdaq",
        "label":"KOSDAQ",
        "sub_label":"코스닥",
        "symbol":"^KQ11",
        "encoded_symbol":"%5EKQ11",
        "value_suffix":"",
        "decimals":2,
        "kind":"index",
    },
    {
        "key":"usdkrw",
        "label":"달러 / 원화",
        "sub_label":"USD/KRW · 1달러 기준",
        "symbol":"KRW=X",
        "encoded_symbol":"KRW%3DX",
        "value_suffix":"원",
        "decimals":2,
        "kind":"fx",
    },
    {
        "key":"usdjpy",
        "label":"원화 / 엔",
        "sub_label":"KRW/JPY · 100엔 기준",
        "symbol":"JPY=X",
        "encoded_symbol":"JPY%3DX",
        "value_suffix":"원",
        "decimals":0,
        "kind":"fx",
    },
)


def _market_number(value):
    if value in (None,"","-","--"):
        return None

    try:
        number=float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except Exception:
        return None


def _load_market_overview_disk_cache():
    try:
        if not _MARKET_OVERVIEW_CACHE_FILE.exists():
            return {}

        data=json.loads(
            _MARKET_OVERVIEW_CACHE_FILE.read_text(
                encoding="utf-8"
            )
        )

        items=data.get("items") or {}
        if not isinstance(items,dict):
            return {}

        clean={}

        for key,item in items.items():
            if not isinstance(item,dict):
                continue

            if _market_number(item.get("value")) is None:
                continue

            clean[str(key)]=dict(item)

        return clean

    except Exception as exc:
        print(
            "[WARN] market disk cache read failed:",
            repr(exc),
        )
        return {}


def _save_market_overview_disk_cache(items):
    """
    Persist only actual successful market values.

    This survives backend restarts. Closed markets therefore continue to
    display the last actual close/rate rather than changing to '조회 대기'.
    """
    try:
        actual={}

        for key,item in (items or {}).items():
            if not isinstance(item,dict):
                continue
            if not item.get("available"):
                continue
            if _market_number(item.get("value")) is None:
                continue

            actual[str(key)]=dict(item)

        if not actual:
            return

        _MARKET_OVERVIEW_CACHE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        tmp=_MARKET_OVERVIEW_CACHE_FILE.with_suffix(
            ".tmp"
        )

        tmp.write_text(
            json.dumps(
                {
                    "saved_at":datetime.now(timezone.utc).isoformat(),
                    "items":actual,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        tmp.replace(
            _MARKET_OVERVIEW_CACHE_FILE
        )

    except Exception as exc:
        print(
            "[WARN] market disk cache write failed:",
            repr(exc),
        )


def _market_state_label(state,kind):
    value=str(state or "").upper()

    if value in ("REGULAR","OPEN"):
        return "거래 중" if kind=="index" else "환율 시장"

    if value in ("PRE","PREPRE"):
        return "장 시작 전"

    if value in ("POST","POSTPOST","CLOSED","CLOSE"):
        return "장 마감"

    return ""


def _yahoo_chart_quote(
    payload,
    config,
    *,
    interval="1d",
):
    if not isinstance(payload,dict):
        raise RuntimeError("시장 데이터 응답 형식 오류")

    chart=payload.get("chart") or {}
    error=chart.get("error")

    if error:
        raise RuntimeError(
            str(
                error.get("description")
                or error.get("code")
                or "시장 데이터 조회 오류"
            )
        )

    results=chart.get("result") or []
    if not results:
        raise RuntimeError("시장 데이터 결과 없음")

    result=results[0] or {}
    meta=result.get("meta") or {}

    quote_blocks=(
        (result.get("indicators") or {})
        .get("quote")
        or [{}]
    )
    quote=quote_blocks[0] if quote_blocks else {}

    closes=quote.get("close") or []
    timestamps=result.get("timestamp") or []

    actual_points=[]

    for idx,raw in enumerate(closes):
        value=_market_number(raw)
        if value is None:
            continue

        ts=timestamps[idx] if idx<len(timestamps) else None
        actual_points.append((ts,value))

    latest_chart_value=actual_points[-1][1] if actual_points else None
    latest_chart_ts=actual_points[-1][0] if actual_points else None

    current=_market_number(
        meta.get("regularMarketPrice")
    )

    # Closed market: Yahoo may omit regularMarketPrice in some responses.
    # Latest actual chart close is then the correct last observed market value.
    if current is None:
        current=latest_chart_value

    if current is None:
        raise RuntimeError("현재/마감 시장값 없음")

    previous=_market_number(
        meta.get("chartPreviousClose")
    )

    if previous is None:
        previous=_market_number(
            meta.get("previousClose")
        )

    if previous is None and len(actual_points)>=2:
        previous=actual_points[-2][1]

    change=(
        current-previous
        if previous is not None
        else None
    )

    change_rate=(
        change/previous*100
        if change is not None and previous not in (None,0)
        else None
    )

    market_time=(
        meta.get("regularMarketTime")
        or latest_chart_ts
    )

    updated_at=None
    if market_time:
        try:
            updated_at=datetime.fromtimestamp(
                int(market_time),
                tz=timezone.utc,
            ).isoformat()
        except Exception:
            updated_at=None

    market_state=str(
        meta.get("marketState") or ""
    ).upper()

    closed=(
        market_state
        in ("CLOSED","CLOSE","POST","POSTPOST")
    )

    return {
        "key":config["key"],
        "label":config["label"],
        "sub_label":config["sub_label"],
        "symbol":config["symbol"],
        "value":current,
        "previous":previous,
        "change":change,
        "change_rate":change_rate,
        "value_suffix":config["value_suffix"],
        "decimals":config["decimals"],
        "kind":config.get("kind"),
        "currency":meta.get("currency"),
        "market_state":market_state,
        "state_label":_market_state_label(
            market_state,
            config.get("kind"),
        ),
        "closed":closed,
        "updated_at":updated_at,
        "available":True,
        "stale":False,
        "last_actual":True,
        "interval_source":interval,
    }


async def _fetch_yahoo_chart(
    client,
    config,
    *,
    range_value,
    interval,
):
    last_error=None

    for host in (
        "query1.finance.yahoo.com",
        "query2.finance.yahoo.com",
    ):
        url=(
            f"https://{host}/v8/finance/chart/"
            f"{config['encoded_symbol']}"
        )

        try:
            response=await client.get(
                url,
                params={
                    "range":range_value,
                    "interval":interval,
                    "includePrePost":"true",
                    "events":"div,splits",
                },
                headers={
                    "User-Agent":"Mozilla/5.0 StockLog/3.30.3",
                    "Accept":"application/json,text/plain,*/*",
                },
            )
            response.raise_for_status()

            return _yahoo_chart_quote(
                response.json(),
                config,
                interval=interval,
            )

        except Exception as exc:
            last_error=exc

    raise RuntimeError(
        str(last_error)
        if last_error
        else "시장 데이터 조회 실패"
    )


async def _fetch_yahoo_market_item(
    client:httpx.AsyncClient,
    config,
):
    """
    Market close is not an error.

    1) 5d / 5m actual chart -> latest observed value, including after close.
    2) 1mo / 1d actual history -> last official daily close.
    """
    errors=[]

    for range_value,interval in (
        ("5d","5m"),
        ("1mo","1d"),
    ):
        try:
            item=await _fetch_yahoo_chart(
                client,
                config,
                range_value=range_value,
                interval=interval,
            )

            if item.get("available"):
                return item

        except Exception as exc:
            errors.append(
                f"{interval}: {exc}"
            )

    raise RuntimeError(
        " / ".join(errors)
        or "시장 데이터 조회 실패"
    )


def _apply_krw_jpy_cross_rate(items):
    """Convert Yahoo USD/KRW + USD/JPY quotes to KRW per 100 JPY."""
    try:
        usdkrw=items.get("usdkrw") or {}
        usdjpy=items.get("usdjpy") or {}
        krw_now=_market_number(usdkrw.get("value"))
        jpy_now=_market_number(usdjpy.get("value"))
        krw_prev=_market_number(usdkrw.get("previous"))
        jpy_prev=_market_number(usdjpy.get("previous"))
        if krw_now is None or jpy_now in (None,0):
            return items
        current=krw_now/jpy_now*100.0
        previous=(krw_prev/jpy_prev*100.0) if krw_prev is not None and jpy_prev not in (None,0) else None
        converted=dict(usdjpy)
        converted.update({
            "label":"원화 / 엔",
            "sub_label":"KRW/JPY · 100엔 기준",
            "value":current,
            "previous":previous,
            "change":current-previous if previous is not None else None,
            "change_rate":((current-previous)/previous*100.0) if previous not in (None,0) else None,
            "value_suffix":"원",
            "decimals":0,
            "source_pair":"USD/KRW ÷ USD/JPY × 100",
        })
        items=dict(items)
        items["usdjpy"]=converted
        return items
    except Exception:
        return items


def _ordered_market_items(items):
    items=_apply_krw_jpy_cross_rate(dict(items or {}))
    return [
        dict(
            items.get(
                config["key"],
                {
                    "key":config["key"],
                    "label":config["label"],
                    "sub_label":config["sub_label"],
                    "symbol":config["symbol"],
                    "kind":config.get("kind"),
                    "value_suffix":config["value_suffix"],
                    "decimals":config["decimals"],
                    "available":False,
                    "stale":False,
                    "warning":"외부 시장 데이터 연결 대기",
                },
            )
        )
        for config in _MARKET_OVERVIEW_SYMBOLS
    ]


async def _market_overview_actual():
    now=time.time()

    # Server restart recovery.
    if not _market_overview_cache["items"]:
        disk_items=_load_market_overview_disk_cache()

        if disk_items:
            for item in disk_items.values():
                item["stale"]=True
                item["from_persistent_cache"]=True
                item["warning"]="최신값 확인 중 · 마지막 실제값"

            _market_overview_cache["items"]=disk_items

    if (
        _market_overview_cache["items"]
        and now-_market_overview_cache["fetched_at"]
        < _MARKET_OVERVIEW_TTL_SECONDS
    ):
        return {
            "items":_ordered_market_items(
                _market_overview_cache["items"]
            ),
            "cached":True,
        }

    async with _market_overview_lock:
        now=time.time()

        if (
            _market_overview_cache["items"]
            and now-_market_overview_cache["fetched_at"]
            < _MARKET_OVERVIEW_TTL_SECONDS
        ):
            return {
                "items":_ordered_market_items(
                    _market_overview_cache["items"]
                ),
                "cached":True,
            }

        async with httpx.AsyncClient(
            timeout=8,
            follow_redirects=True,
        ) as client:
            results=await asyncio.gather(
                *[
                    _fetch_yahoo_market_item(
                        client,
                        config,
                    )
                    for config in _MARKET_OVERVIEW_SYMBOLS
                ],
                return_exceptions=True,
            )

        previous_items=dict(
            _market_overview_cache["items"]
        )
        disk_items=_load_market_overview_disk_cache()

        current_items={}
        successful_actual={}

        for config,result in zip(
            _MARKET_OVERVIEW_SYMBOLS,
            results,
        ):
            key=config["key"]

            if isinstance(result,Exception):
                fallback=(
                    previous_items.get(key)
                    or disk_items.get(key)
                )

                if (
                    fallback
                    and fallback.get("available")
                    and _market_number(
                        fallback.get("value")
                    ) is not None
                ):
                    fallback=dict(fallback)
                    fallback["stale"]=True
                    fallback["from_persistent_cache"]=True
                    fallback["warning"]="최신값 갱신 대기 · 마지막 실제값"
                    current_items[key]=fallback
                else:
                    current_items[key]={
                        "key":key,
                        "label":config["label"],
                        "sub_label":config["sub_label"],
                        "symbol":config["symbol"],
                        "kind":config.get("kind"),
                        "value_suffix":config["value_suffix"],
                        "decimals":config["decimals"],
                        "available":False,
                        "stale":False,
                        "warning":"외부 시장 데이터 연결 대기",
                    }

                print(
                    "[WARN] market overview item failed:",
                    key,
                    repr(result),
                )
            else:
                fresh=dict(result)
                fresh["from_persistent_cache"]=False
                current_items[key]=fresh
                successful_actual[key]=fresh

        _market_overview_cache["items"]=current_items
        _market_overview_cache["fetched_at"]=time.time()

        # Merge only successful ACTUAL results into durable cache.
        durable=dict(disk_items)
        durable.update(successful_actual)
        _save_market_overview_disk_cache(durable)

        return {
            "items":_ordered_market_items(current_items),
            "cached":False,
        }


@app.get("/api/market-overview")
async def market_overview(
    _:User=Depends(current_user),
):
    data=await _market_overview_actual()

    return {
        **data,
        "refresh_seconds":_MARKET_OVERVIEW_TTL_SECONDS,
        "source":"actual-market-data",
        "generated_at":datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/smart/filter-options")
def smart_filter_options(
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_feature(u,db,"smart_analysis")

    stocks=(db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .all())
    provider_map=_provider_taxonomy_for_codes(db,[stock.code for stock in stocks])
    groups=set()
    tree={}
    classified_count=0
    fallback_count=0
    for stock in stocks:
        stock_groups,stock_subs,source=_effective_stock_theme_sets(stock,provider_map)
        if source=="engine" and stock_groups:
            classified_count+=1
        elif stock_groups:
            fallback_count+=1
        groups.update(stock_groups)
        for sub in stock_subs:
            matches=map_theme_name(sub)
            parent=str(matches[0].get("group") or "").strip() if matches else ""
            if parent:
                tree.setdefault(parent,set()).add(sub)

    # Every returned label is sorted and no arbitrary 160-row truncation is
    # applied. This fixes the old selector that silently hid valid themes.
    ordered=sorted(groups,key=theme_alpha_key)
    theme_tree={
        group:sorted(tree.get(group,set()),key=theme_alpha_key)
        for group in ordered
        if tree.get(group)
    }

    tier=user_tier(u)
    full_market=bool(_feature_access(u,db,"smart_full_market").get("enabled",False))
    markets=[str(value or "").strip() for (value,) in (
        db.query(Stock.market)
        .filter(*_stocklog_public_clauses())
        .distinct().all()
    ) if str(value or "").strip()]
    market_order={"KOSPI":0,"KOSDAQ":1}
    markets=sorted(set(markets),key=lambda x:(market_order.get(x.upper(),99),x))
    return {
        "strategies":["전체","가치","성장","모멘텀","배당","안정"],
        "themes":ordered,
        "theme_tree":theme_tree,
        "markets":markets,
        "theme_count":len(ordered),
        "taxonomy_group_count":len(taxonomy_groups()),
        "classified_stock_count":classified_count,
        "provider_fallback_stock_count":fallback_count,
        "theme_engine_version":THEME_ENGINE_VERSION,
        "canonical_enabled":_theme_canonical_column_available(),
        "access":{
            "tier":tier,
            "tier_label":TIER_LABELS.get(tier,tier),
            "full_market_enabled":full_market,
            "advanced_filters":full_market,
            "max_accessible":None if full_market else 20,
        },
        "filter_presets":{
            "ai_score":[0,50,60,70,80],
            "profile_score":[0,50,60,70,80],
            "coverage":[0,50,70,85,100],
            "market_cap":[0,1000,5000,10000,50000],
            "per_max":[0,10,15,20,30],
            "pbr_max":[0,1,1.5,2,3],
            "roe_min":[-999,5,10,15,20],
            "dividend_min":[-1,1,2,3,5],
            "page_sizes":[10,20,50],
        },
    }


def _stock_name_aliases(stock: Stock) -> list[str]:
    try:
        values=json.loads(stock.name_aliases_json or "[]")
    except Exception:
        values=[]
    out=[]
    for value in values if isinstance(values,list) else []:
        name=str(value or "").strip()
        if name and name != str(stock.name or "").strip() and name not in out:
            out.append(name)
    return out[:20]


def _stock_name_matches(stock: Stock, query: str) -> bool:
    term=str(query or "").strip().casefold()
    if not term:
        return True
    if term in str(stock.code or "").casefold() or term in str(stock.name or "").casefold():
        return True
    return any(term in alias.casefold() for alias in _stock_name_aliases(stock))


def _stock_name_payload(stock: Stock) -> dict:
    return {
        "former_names":_stock_name_aliases(stock),
        "name_source":stock.name_source or None,
        "name_verified_at":stock.name_verified_at.isoformat() if stock.name_verified_at else None,
        "name_changed_at":stock.name_changed_at.isoformat() if stock.name_changed_at else None,
    }


def _name_search_clause(q: str):
    return or_(
        Stock.name.contains(q),
        Stock.code.contains(q),
        Stock.name_aliases_json.contains(q),
    )


def _upsert_kind_search_matches(db: Session, query: str) -> int:
    """Recover a listed company that is absent/inactive in the local master.

    This runs only when an explicit Smart search has no exact local hit, so a
    transient provider omission cannot make a valid KOSPI/KOSDAQ company
    undiscoverable until the next full synchronization.
    """
    term=str(query or "").strip()
    if not term:
        return 0
    try:
        matches=find_kind_company(term)
    except Exception as exc:
        logger.warning("KRX KIND 검색 보강 실패 query=%s error=%s", term, exc)
        return 0
    if not matches:
        return 0
    # Keep partial-result expansion bounded. Exact name/code is first.
    selected=matches[:30]
    codes=[str(x.get("code") or "") for x in selected]
    existing={x.code:x for x in db.query(Stock).filter(Stock.code.in_(codes)).all()}
    now=datetime.now()
    changed=0
    for item in selected:
        code=str(item.get("code") or "")
        if not re.fullmatch(r"\d{6}",code):
            continue
        st=existing.get(code)
        if not st:
            st=Stock(
                code=code,
                name=str(item.get("name") or code),
                market=str(item.get("market") or ""),
                sector="기타",category="종합",is_active=True,
                is_analysis_eligible=True,analysis_exclusion_reason=None,
                name_source=str(item.get("source") or "KRX_KIND"),
                name_verified_at=now if bool(item.get("name_verified",True)) else None,
            )
            db.add(st); existing[code]=st; changed+=1
        else:
            before=(st.name,st.market,bool(st.is_active),bool(st.is_analysis_eligible))
            incoming_name=str(item.get("name") or "").strip()
            if incoming_name and bool(item.get("name_verified",True)) and incoming_name != str(st.name or "").strip():
                aliases=_stock_name_aliases(st)
                old_name=str(st.name or "").strip()
                if old_name and old_name not in aliases:
                    aliases.append(old_name)
                st.name_aliases_json=json.dumps(aliases,ensure_ascii=False)
                st.name=incoming_name
                st.name_source=str(item.get("source") or "KRX_KIND")
                st.name_verified_at=now
                st.name_changed_at=now
            st.market=str(item.get("market") or st.market)
            st.is_active=True
            # KIND corpList contains listed corporations, so it is safe to
            # restore company-analysis eligibility here unless another explicit
            # product exclusion applies.
            reason=_analysis_exclusion_reason({"name":st.name,"market":st.market})
            st.is_analysis_eligible=not bool(reason)
            st.analysis_exclusion_reason=reason or None
            after=(st.name,st.market,bool(st.is_active),bool(st.is_analysis_eligible))
            if before!=after: changed+=1
        st.universe_last_seen_at=now
        st.universe_missing_count=0
        st.updated_at=now
    if changed:
        commit_or_rollback(db)
    return changed


def _has_exact_local_stock(db: Session, query: str) -> bool:
    term=str(query or "").strip()
    if not term:
        return False
    return db.query(Stock.id).filter(
        or_(Stock.code==term, Stock.name==term, Stock.name_aliases_json.contains(term)),
        Stock.market.in_(STOCKLOG_PUBLIC_MARKETS),
        Stock.is_active==True,
        Stock.is_analysis_eligible==True,
    ).first() is not None


@app.get("/api/smart/recommend/{mode}")
def smart_recommendations(
    mode: str,
    category: str = Query("전체"),
    strategy: str = Query("전체"),
    theme: str = Query("전체"),
    subtheme: str = Query("전체"),
    q: str = Query("", max_length=80),
    market: str = Query("전체", max_length=20),
    ai_score_min: float = Query(0, ge=0, le=100),
    profile_score_min: float = Query(0, ge=0, le=100),
    coverage_min: float = Query(0, ge=0, le=100),
    market_cap_min: float = Query(0, ge=0),
    per_max: float = Query(0, ge=0),
    pbr_max: float = Query(0, ge=0),
    roe_min: float = Query(-999, ge=-999, le=999),
    dividend_min: float = Query(-1, ge=-1, le=100),
    flow_signal: str = Query("전체", max_length=20),
    sentiment_signal: str = Query("전체", max_length=20),
    sort_by: str = Query("ai_score", max_length=30),
    sort_order: str = Query("desc", max_length=8),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=10, le=50),
    limit: int | None = Query(None, ge=1, le=1000),
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Explainable Smart Analysis list with membership-scoped market access.

    NORMAL users receive only the top 20 recommendation universe. PREMIUM,
    EVENT and ADMIN (or any tier with ``smart_full_market`` enabled) can browse
    every analysis-eligible listed company with server-side pagination and
    advanced filters. Stock-side scores are read from the synchronized cache;
    only the lightweight per-user fit score is calculated at request time.
    """
    _require_feature(u,db,"smart_analysis")
    mode=str(mode).lower().strip()
    if mode not in {"ai","profile"}:
        raise HTTPException(400,"지원하지 않는 스마트 추천 모드입니다.")
    if str(flow_signal or "전체") not in {"전체","긍정","부정"}:
        raise HTTPException(422,"수급 필터는 전체·긍정·부정만 지원합니다.")
    if str(sentiment_signal or "전체") not in {"전체","긍정","부정"}:
        raise HTTPException(422,"뉴스·리포트 필터는 전체·긍정·부정만 지원합니다.")
    sort_by=str(sort_by or "ai_score").strip().lower()
    sort_order=str(sort_order or "desc").strip().lower()
    if sort_by not in {"ai_score","profile_score"}:
        raise HTTPException(422,"점수 정렬 기준은 종합점수 또는 투자성향만 지원합니다.")
    if sort_order not in {"asc","desc"}:
        raise HTTPException(422,"점수 정렬 방향은 오름차순 또는 내림차순만 지원합니다.")

    tier=user_tier(u)
    full_market=bool(_feature_access(u,db,"smart_full_market").get("enabled",False))
    advanced_requested=(
        str(market or "전체")!="전체"
        or float(ai_score_min or 0)>0
        or float(profile_score_min or 0)>0
        or float(coverage_min or 0)>0
        or float(market_cap_min or 0)>0
        or float(per_max or 0)>0
        or float(pbr_max or 0)>0
        or float(roe_min)>-999
        or float(dividend_min)>-1
        or str(flow_signal or "전체")!="전체"
        or str(sentiment_signal or "전체")!="전체"
        or int(page_size or 10)>10
    )
    if advanced_requested and not full_market:
        raise HTTPException(403,"전체 시장 탐색과 고급 필터는 프리미엄 이상 회원에게 제공됩니다.")

    # Keep backward compatibility with old clients that sent only `limit`.
    if limit is not None:
        page_size=max(10,min(50 if full_market else 20,int(limit)))
    elif not full_market:
        page_size=10

    cache_stats=_ensure_smart_score_cache(db)
    profile_row=(
        db.query(InvestmentProfile)
        .filter(InvestmentProfile.user_id==u.id)
        .first()
    )
    profile_payload=_investment_profile_payload(profile_row)
    profile_scores=(profile_payload or {}).get("scores") or {}
    profile_code=(profile_payload or {}).get("result_code") or ""

    if mode=="profile" and not profile_row:
        return {
            "mode":"profile","count":0,"total":0,"pages":1,"page":1,"page_size":page_size,
            "items":[],"profile_required":True,"profile":None,
            "access":{
                "tier":tier,"tier_label":TIER_LABELS.get(tier,tier),
                "full_market_enabled":full_market,"scope":"full_market" if full_market else ("full_market_search" if str(q or "").strip() else "daily_random20"),
                "max_accessible":None if full_market else 20,"advanced_filters":full_market,
            },
            "cache":cache_stats,
            "disclaimer":"내 성향 추천을 사용하려면 먼저 투자 성향 분석을 완료해주세요.",
            "score_guide":{
                "ai":"StockLog 알고리즘으로 재무·가격·수급·뉴스 등 동기화 데이터를 같은 기준으로 분석한 종합점수입니다. 더 깊고 정확한 해석은 종목 상세의 프리미엄 AI 분석에서 확인할 수 있습니다.",
                "profile":"내 투자성향 점수는 StockLog 종합점수와 별개입니다. 종목의 성장성·가치성·안정성·변동성·보유기간 성격이 내 투자방식과 얼마나 비슷한지 독립적으로 계산합니다.",
            },
        }

    raw_search=str(q or "").strip()
    keyword=raw_search.casefold()
    explicit_search=bool(keyword)
    if explicit_search and not _has_exact_local_stock(db,raw_search):
        _upsert_kind_search_matches(db,raw_search)
    # Search and ranking use the exact same public universe. Excluded listed
    # products are intentionally not discoverable anywhere in StockLog.
    stock_query=db.query(Stock).filter(*_stocklog_public_clauses())
    stocks=stock_query.all()

    scored=[]
    for stock in stocks:
        ai_score=float(stock.smart_ai_score if stock.smart_ai_score is not None else 0.0)
        coverage=float(stock.smart_score_coverage if stock.smart_score_coverage is not None else 0.0)
        profile_info=(
            _smart_cached_profile(stock,profile_scores,profile_code)
            if profile_row else {"score":None,"label":"성향 미검사","components":[]}
        )
        profile_score=profile_info.get("score")
        selected_score=profile_score if mode=="profile" else ai_score
        if selected_score is None:
            selected_score=0.0
        scored.append((stock,ai_score,coverage,profile_score,profile_info,float(selected_score)))

    # Membership browsing scope and explicit-search scope are intentionally
    # different. PREMIUM+ accounts always browse the full analysis universe.
    # NORMAL accounts see a stable daily random 20-stock discovery list when
    # no search term is supplied, but an explicit name/code search MUST search
    # the complete active KOSPI/KOSDAQ analysis universe. Restricting search to
    # the random 20 made valid stocks such as 한글과컴퓨터(030520) appear to be
    # missing even though they were present in stock_universe. Premium score
    # fields remain server-side locked for NORMAL users, so widening the search
    # scope does not leak ranking information.
    if full_market:
        scored.sort(key=lambda item:(item[5],item[1],float(item[0].market_cap or 0)),reverse=True)
        accessible=scored
    elif explicit_search:
        accessible=scored
    else:
        shuffle_day=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        def _normal_shuffle_key(item):
            stock=item[0]
            raw=f"{shuffle_day}|{u.id}|{stock.code}".encode("utf-8")
            return hashlib.sha256(raw).hexdigest()
        accessible=sorted(scored,key=_normal_shuffle_key)[:20]

    if category and category!="전체" and strategy=="전체":
        strategy=category.replace("주","") if category in {"가치주","성장주"} else category

    needs_theme_filter = bool((theme and theme != "전체") or (subtheme and subtheme != "전체"))
    provider_taxonomy = (
        _provider_taxonomy_for_codes(db,[item[0].code for item in accessible])
        if needs_theme_filter else {}
    )

    selected_market=str(market or "전체").strip().upper()
    filtered=[]
    for item in accessible:
        stock,ai_score,coverage,profile_score,profile_info,selected_score=item
        if keyword and not _stock_name_matches(stock, keyword):
            continue
        if not strategy_match(stock,strategy):
            continue
        if (theme and theme!="전체") or (subtheme and subtheme!="전체"):
            stock_groups,stock_subthemes,_theme_source=_effective_stock_theme_sets(stock,provider_taxonomy)
            if theme and theme!="전체" and theme not in stock_groups:
                continue
            if subtheme and subtheme!="전체" and subtheme not in stock_subthemes:
                continue
        if full_market:
            if selected_market!="전체" and str(stock.market or "").upper()!=selected_market:
                continue
            if ai_score<float(ai_score_min or 0):
                continue
            if coverage<float(coverage_min or 0):
                continue
            if float(stock.market_cap or 0)<float(market_cap_min or 0):
                continue
            if float(profile_score or 0)<float(profile_score_min or 0):
                continue
            if float(per_max or 0)>0 and (stock.per is None or float(stock.per)<=0 or float(stock.per)>float(per_max)):
                continue
            if float(pbr_max or 0)>0 and (stock.pbr is None or float(stock.pbr)<=0 or float(stock.pbr)>float(pbr_max)):
                continue
            if float(roe_min)>-999 and (stock.roe is None or float(stock.roe)<float(roe_min)):
                continue
            if float(dividend_min)>-1 and (stock.dividend_yield is None or float(stock.dividend_yield)<float(dividend_min)):
                continue
            component_map={str(x.get("key") or ""):x for x in _smart_cached_components(stock)}
            if str(flow_signal or "전체")!="전체":
                flow_item=component_map.get("flow") or {}
                flow_score=float(flow_item.get("score") or 50)
                if not flow_item.get("available"):
                    continue
                if flow_signal=="긍정" and flow_score<60: continue
                if flow_signal=="부정" and flow_score>40: continue
            if str(sentiment_signal or "전체")!="전체":
                sentiment_item=component_map.get("sentiment") or {}
                sentiment_score=float(sentiment_item.get("score") or 50)
                if not sentiment_item.get("available"):
                    continue
                if sentiment_signal=="긍정" and sentiment_score<60: continue
                if sentiment_signal=="부정" and sentiment_score>40: continue
        filtered.append(item)

    # PREMIUM+ sorts the complete filtered universe before pagination.  The
    # previous browser-only sort happened after pagination, so it could only
    # rearrange the current 10/20/50 rows and made the score arrows appear
    # broken.  Keep missing profile scores at the bottom in both directions.
    if full_market:
        def _requested_score(item):
            return item[3] if sort_by=="profile_score" else item[1]

        def _requested_sort_key(item):
            value=_requested_score(item)
            missing=value is None
            numeric=float(value or 0.0)
            primary=numeric if sort_order=="asc" else -numeric
            return (
                missing,
                primary,
                -float(item[1] or 0.0),
                -float(item[0].market_cap or 0.0),
            )

        filtered.sort(key=_requested_sort_key)
    total=len(filtered)
    pages=max(1,math.ceil(total/max(1,page_size)))
    current_page=min(int(page),pages)
    start=(current_page-1)*page_size
    page_scored=filtered[start:start+page_size]

    page_stocks=[item[0] for item in page_scored]
    theme_map=_theme_map_for_codes(db,[stock.code for stock in page_stocks],limit=2)
    rows=[]
    for stock,ai_score,coverage,profile_score,profile_info,selected_score in page_scored:
        row=_smart_row(stock,theme_map)
        if full_market:
            row["ai_recommend_score"]=round(ai_score,1)
            row["ai_recommend_label"]=stock.smart_ai_label or ("강한 추천" if ai_score>=75 else "추천" if ai_score>=60 else "관심" if ai_score>=45 else "보수적")
            row["profile_recommend_score"]=profile_score
            row["profile_recommend_label"]=profile_info.get("label")
            row["score_coverage"]=round(coverage,1)
            row["recommend_score"]=selected_score
            row["recommend_type"]=("내 투자성향 적합도" if mode=="profile" else "StockLog 종합점수")
            row["score_preview"]=[
                {"key":x.get("key"),"label":x.get("label"),"score":x.get("score"),"profile_score":x.get("profile_score"),"available":x.get("available")}
                for x in (profile_info.get("components") or _smart_cached_components(stock))
            ]
        else:
            # Do not serialize premium score values/labels/components to NORMAL
            # clients. Hiding only in React would still expose them in DevTools.
            row.pop("score",None)
            row["premium_score_locked"]=True
        row["analysis_available"]=bool(stock.is_analysis_eligible)
        row["analysis_ready"]=bool(stock.is_analysis_eligible and stock.smart_score_updated_at is not None)
        row["analysis_exclusion_reason"]=stock.analysis_exclusion_reason if not stock.is_analysis_eligible else None
        rows.append(row)

    return {
        "mode":mode,
        "count":len(rows),
        "total":total,
        "pages":pages,
        "page":current_page,
        "page_size":page_size,
        "sort_by":sort_by if full_market else None,
        "sort_order":sort_order if full_market else None,
        "universe_total":len(scored),
        "profile":profile_payload,
        "profile_required":False,
        "items":rows,
        "access":{
            "tier":tier,
            "tier_label":TIER_LABELS.get(tier,tier),
            "full_market_enabled":full_market,
            "scope":"full_market" if full_market else ("full_market_search" if explicit_search else "daily_random20"),
            "max_accessible":None if full_market else 20,
            "advanced_filters":full_market,
        },
        "cache":cache_stats,
        "disclaimer":(
            "프리미엄 전체 시장 탐색은 동기화된 분석 가능 종목을 페이지 단위로 제공합니다. 점수는 투자 지시가 아닙니다."
            if full_market else
            "일반 회원은 종합점수 순위를 노출하지 않는 일일 랜덤 20종목을 탐색할 수 있습니다. StockLog 종합점수·성향 적합도·전체 시장 순위는 프리미엄 이상에서 제공됩니다."
        ),
        "score_guide":{
            "ai":"StockLog 알고리즘으로 재무·가격·수급·뉴스 등 동기화 데이터를 같은 기준으로 분석한 종합점수입니다. 더 깊고 정확한 해석은 종목 상세의 프리미엄 AI 분석에서 확인할 수 있습니다.",
            "profile":"내 투자성향 점수는 종합점수와 별개로 종목의 성장성·가치성·안정성·변동성·보유기간 성격 등이 내 투자방식과 얼마나 비슷한지 계산합니다.",
        },
    }


@app.get("/api/smart/stocks/{code}/score-detail")
def smart_stock_score_detail(
    code:str,
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"smart_analysis")
    if not bool(_feature_access(u,db,"smart_full_market").get("enabled",False)):
        raise HTTPException(403,"추천 점수 상세는 프리미엄 이상 회원에게 제공됩니다.")
    stock=(
        db.query(Stock)
        .filter(Stock.code==code,*_stocklog_public_clauses())
        .first()
    )
    if not stock:
        raise HTTPException(404,"종목을 찾을 수 없습니다.")

    profile_row=(
        db.query(InvestmentProfile)
        .filter(InvestmentProfile.user_id==u.id)
        .first()
    )
    profile_payload=_investment_profile_payload(profile_row)
    profile_scores=(profile_payload or {}).get("scores") or {}
    profile_code=(profile_payload or {}).get("result_code") or ""
    flow_map,sentiment_map=_smart_signal_maps(db,[stock.code])
    scorecard=_smart_scorecard(
        stock,
        flow_map=flow_map,
        sentiment_map=sentiment_map,
        profile_scores=profile_scores if profile_row else None,
        profile_code=profile_code,
    )
    scorecard["stock"]={
        "code":stock.code,
        "name":stock.name,
        **_stock_name_payload(stock),
        "market":stock.market,
        "price":stock.price,
        "change_rate":stock.change_rate,
        "themes":_theme_map_for_codes(db,[stock.code],limit=3).get(stock.code,[]),
        "theme_fallback":_stock_theme_fallback(stock),
    }
    scorecard["profile"] = profile_payload
    scorecard["updated_at"] = (
        max(
            [value for value in [stock.smart_score_updated_at,stock.kiwoom_metrics_updated_at,stock.dart_financials_updated_at,stock.updated_at] if value is not None],
            default=None,
        ).isoformat()
        if any([stock.smart_score_updated_at,stock.kiwoom_metrics_updated_at,stock.dart_financials_updated_at,stock.updated_at])
        else None
    )
    return scorecard


@app.get("/api/smart/formula")
def get_smart_formula(
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_feature(u,db,"smart_analysis")
    formula = (
        db.query(SmartFormula)
        .filter(SmartFormula.user_id == u.id)
        .first()
    )
    return _custom_formula_dict(formula)


@app.put("/api/smart/formula")
def save_smart_formula(
    payload: dict,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    allowed = {
        "per_max",
        "pbr_max",
        "roe_min",
        "revenue_growth_min",
        "operating_margin_min",
        "dividend_yield_min",
        "momentum_20d_min",
        "market_cap_min",
    }

    formula = (
        db.query(SmartFormula)
        .filter(SmartFormula.user_id == u.id)
        .first()
    )

    if not formula:
        formula = SmartFormula(user_id=u.id)
        db.add(formula)

    for key in allowed:
        if key not in payload:
            continue

        value = payload.get(key)
        if value in (None, ""):
            setattr(formula, key, None)
        else:
            try:
                setattr(formula, key, float(value))
            except Exception:
                raise HTTPException(400, f"{key} 값이 올바르지 않습니다.")

    formula.updated_at = datetime.now()
    commit_or_rollback(db)
    db.refresh(formula)

    return {
        "ok": True,
        "message": "나만의 공식이 저장되었습니다.",
        "formula": _custom_formula_dict(formula),
    }


@app.get("/api/smart/value")
def smart_value(
    per_max:float=Query(999),pbr_max:float=Query(999),market_cap_min:float=Query(0),
    sort:str=Query("score"),limit:int=Query(100,ge=1,le=1000),
    category:str=Query("전체"),market:str=Query("전체"),q:str=Query(""),
    u:User=Depends(current_user),db:Session=Depends(get_db)
):
    _require_feature(u,db,"smart_analysis")
    qry=db.query(Stock).filter(*_stocklog_public_clauses(),Stock.market_cap>=market_cap_min)
    if per_max<999: qry=qry.filter(or_(Stock.per==None,Stock.per<=per_max))
    if pbr_max<999: qry=qry.filter(or_(Stock.pbr==None,Stock.pbr<=pbr_max))
    if category!="전체": qry=qry.filter(Stock.category==category)
    if market!="전체": qry=qry.filter(Stock.market==market)
    if q: qry=qry.filter(_name_search_clause(q))
    if sort=="score": qry=qry.order_by(Stock.score.desc())
    elif sort=="market_cap": qry=qry.order_by(Stock.market_cap.desc())
    elif sort=="change": qry=qry.order_by(Stock.change_rate.desc())
    elif sort=="per": qry=qry.order_by(Stock.per.asc())
    rows=qry.limit(limit).all()
    return [{
        "code":s.code,"name":s.name,"market":s.market,"sector":s.sector,"category":s.category,
        "price":s.price,"change_rate":s.change_rate,"market_cap":s.market_cap,
        "per":s.per,"pbr":s.pbr,"eps":s.eps,"bps":s.bps,"roe":s.roe,"revenue_growth":s.revenue_growth,
        "operating_margin":s.operating_margin,"dividend_yield":s.dividend_yield,
        "momentum_20d":s.momentum_20d,"volatility":s.volatility,"score":s.score
    } for s in rows]

def _apply_kiwoom_stock_metrics(
    stock: Stock,
    metrics: dict,
):
    """
    Kiwoom은 시세 원천.
    PER/PBR/EPS/BPS/ROE는 DART 계산값을 유지합니다.
    """
    if metrics.get("price") not in (
        None,
        0,
    ):
        stock.price = float(
            metrics["price"]
        )

    if metrics.get(
        "dividend_yield"
    ) is not None:
        stock.dividend_yield = float(
            metrics["dividend_yield"]
        )

    recalculate_price_multiples(
        stock
    )

    stock.kiwoom_metrics_updated_at = (
        datetime.now()
    )
    stock.updated_at = datetime.now()


_AI_CACHE_HOURS=max(
    1,
    int(
        os.getenv(
            "AI_ANALYSIS_CACHE_HOURS",
            "3",
        )
    ),
)

_AI_BATCH_LIMIT=max(
    1,
    min(
        20,
        int(
            os.getenv(
                "AI_BATCH_MAX_STOCKS",
                "10",
            )
        ),
    ),
)

_ai_batch_lock=asyncio.Lock()

# CPU-only Ollama: only one actual generation may run at once.
_ai_generation_lock=asyncio.Lock()
_ai_detail_tasks={}

# Live detail-AI progress is intentionally separate from the durable analysis cache.
# It is only operational/ephemeral state used to show members that Obot is really
# loading/evaluating/generating instead of looking frozen.  Durable stage state still
# lives in AiStockAnalysis.status so a process restart remains safe.
_ai_live_progress={}

def _ai_progress_update(key:str, stage:str, detail=None):
    now=datetime.now()
    detail=detail if isinstance(detail,dict) else {}
    current=_ai_live_progress.get(key) or {}
    previous_stage=str(current.get("stage") or "")
    stage=str(stage or "running")
    stage_changed=previous_stage!=stage
    if stage_changed or not current.get("started_at"):
        stage_started_at=now
    else:
        stage_started_at=current.get("stage_started_at") or now
    started_at=current.get("started_at") or now
    default_messages={
        "queued":"프리미엄 AI 분석을 시작할 준비를 하고 있습니다.",
        "context":"종목의 재무·가격·수급·뉴스 데이터를 정리하고 있습니다.",
        "running":"프리미엄 AI 분석을 준비하고 있습니다.",
        "obot_running":"이전 분석 상태를 정리하고 있습니다.",
        "obot_completed":"이전 분석 상태를 정리했습니다.",
        "gbot_running":"StockLog Gbot이 전체 정량 데이터와 공개 정보를 분석하고 있습니다.",
        "gbot_completed":"StockLog Gbot 최종 분석을 완료했습니다.",
        "verifying":"StockLog가 AI 의견과 실제 정량 데이터의 일치 여부를 검증하고 있습니다.",
        "ready":"프리미엄 AI 분석을 완료했습니다.",
        "failed":"프리미엄 AI 분석을 완료하지 못했습니다.",
    }
    next_message=detail.get("message")
    if not next_message:
        next_message=default_messages.get(stage) if stage_changed else current.get("message")
    next_phase=detail.get("phase")
    if not next_phase:
        next_phase=stage if stage_changed else current.get("phase")
    item={
        **current,
        "stage":stage,
        "started_at":started_at,
        "stage_started_at":stage_started_at,
        "last_activity_at":now,
        "phase":str(next_phase or ""),
        "message":str(next_message or ""),
        "received_chars":int(detail.get("received_chars") or current.get("received_chars") or 0),
        "chunks":int(detail.get("chunks") or current.get("chunks") or 0),
        "attempt":int(detail.get("attempt") or current.get("attempt") or 1),
        "done":bool(detail.get("done",False)),
    }
    _ai_live_progress[key]=item
    return item

def _ai_progress_public(key:str):
    item=_ai_live_progress.get(key)
    if not item:
        return None
    now=datetime.now()
    started=item.get("started_at") or now
    internal_stage=str(item.get("stage") or "")
    if internal_stage in {"queued","context"}:
        public_stage="preparing"
        public_message="Gbot 분석을 준비하고 있습니다."
    elif internal_stage in {"ready","stale","failed"}:
        public_stage=internal_stage
        public_message={
            "ready":"Gbot 분석이 완료되었습니다.",
            "stale":"새로운 데이터가 반영되어 다시 분석할 수 있습니다.",
            "failed":"Gbot 분석을 완료하지 못했습니다.",
        }[internal_stage]
    else:
        public_stage="analyzing"
        public_message="Gbot이 투자 데이터를 분석하고 있습니다."
    return {
        "stage":public_stage,
        "message":public_message,
        "elapsed_seconds":max(0,int((now-started).total_seconds())),
        "started_at":started.isoformat(),
    }

_ai_batch_state={
    "running":False,
    "total":0,
    "completed":0,
    "current_code":"",
    "failed":0,
    "started_at":None,
    "finished_at":None,
    "message":"",
}

_PORTFOLIO_MOMENTUM_CACHE_HOURS=max(1,int(os.getenv("PORTFOLIO_AI_MOMENTUM_CACHE_HOURS","4")))
_portfolio_momentum_jobs={}


def _clean_ai_number(value):
    try:
        number=float(value)
        if not math.isfinite(number):
            return None
        return round(number,4)
    except Exception:
        return None


def _return_pct(current, previous):
    current=_clean_ai_number(current)
    previous=_clean_ai_number(previous)

    if (
        current is None
        or previous in (
            None,
            0,
        )
    ):
        return None

    return round(
        (
            current
            - previous
        )
        / previous
        * 100,
        2,
    )


def _moving_average_value(
    closes,
    period,
):
    values=[
        float(value)
        for value in closes[-period:]
        if value not in (
            None,
            0,
        )
    ]

    if len(values)<period:
        return None

    return round(
        sum(values)
        / len(values),
        2,
    )


def _price_action_context(
    chart,
):
    if not chart:
        return {
            "available":False,
        }

    closes=[
        _clean_ai_number(
            row.get("close")
        )
        for row in chart
    ]

    valid_closes=[
        value
        for value in closes
        if value is not None
    ]

    if not valid_closes:
        return {
            "available":False,
        }

    latest=valid_closes[-1]

    def prior_close(days):
        if len(valid_closes)<=days:
            return None
        return valid_closes[-1-days]

    ma20=_moving_average_value(
        valid_closes,
        20,
    )
    ma60=_moving_average_value(
        valid_closes,
        60,
    )
    ma240=_moving_average_value(
        valid_closes,
        240,
    )

    volumes=[
        _clean_ai_number(
            row.get("volume")
        )
        for row in chart
        if _clean_ai_number(
            row.get("volume")
        ) is not None
    ]

    latest_volume=(
        volumes[-1]
        if volumes
        else None
    )

    volume20=(
        sum(volumes[-20:])
        / 20
        if len(volumes)>=20
        else None
    )

    year_slice=valid_closes[-250:]
    high52=max(
        year_slice
    ) if year_slice else None
    low52=min(
        year_slice
    ) if year_slice else None

    return {
        "available":True,
        "latest_date":
            chart[-1].get("date"),
        "current_price":
            latest,
        "return_1d_pct":
            _return_pct(
                latest,
                prior_close(1),
            ),
        "return_5d_pct":
            _return_pct(
                latest,
                prior_close(5),
            ),
        "return_20d_pct":
            _return_pct(
                latest,
                prior_close(20),
            ),
        "return_60d_pct":
            _return_pct(
                latest,
                prior_close(60),
            ),
        "ma20":ma20,
        "ma60":ma60,
        "ma240":ma240,
        "price_vs_ma20":
            (
                "above"
                if ma20 is not None
                and latest>ma20
                else "below"
                if ma20 is not None
                and latest<ma20
                else "equal_or_unknown"
            ),
        "price_vs_ma60":
            (
                "above"
                if ma60 is not None
                and latest>ma60
                else "below"
                if ma60 is not None
                and latest<ma60
                else "equal_or_unknown"
            ),
        "price_vs_ma240":
            (
                "above"
                if ma240 is not None
                and latest>ma240
                else "below"
                if ma240 is not None
                and latest<ma240
                else "equal_or_unknown"
            ),
        "volume_vs_20d_avg":
            (
                round(
                    latest_volume
                    / volume20,
                    2,
                )
                if latest_volume is not None
                and volume20
                else None
            ),
        "high_52w":high52,
        "distance_from_52w_high_pct":
            (
                round(
                    (
                        latest
                        / high52
                        - 1
                    )
                    * 100,
                    2,
                )
                if high52
                else None
            ),
        "low_52w":low52,
    }


def _median_numeric(
    values,
):
    cleaned=[
        float(value)
        for value in values
        if value is not None
        and math.isfinite(
            float(value)
        )
    ]

    if not cleaned:
        return None

    return round(
        statistics.median(
            cleaned
        ),
        2,
    )


def _peer_context(
    stock,
    db,
):
    filters=[
        *_stocklog_public_clauses(),
        Stock.code!=stock.code,
    ]

    basis="sector"

    if (
        stock.industry_name
        and stock.industry_name!="기타"
    ):
        filters.append(
            Stock.industry_name
            == stock.industry_name
        )
        basis="industry_name"

    elif (
        stock.sector
        and stock.sector!="기타"
    ):
        filters.append(
            Stock.sector
            == stock.sector
        )
    else:
        return {
            "available":False,
            "basis":"none",
            "peer_count":0,
        }

    peers=(
        db.query(Stock)
        .filter(*filters)
        .order_by(
            Stock.market_cap.desc()
        )
        .limit(30)
        .all()
    )

    if not peers:
        return {
            "available":False,
            "basis":basis,
            "peer_count":0,
        }

    return {
        "available":True,
        "basis":basis,
        "peer_count":len(peers),
        "median":{
            "per":_median_numeric(
                [
                    p.per
                    for p in peers
                    if p.per is not None
                    and p.per>0
                ]
            ),
            "pbr":_median_numeric(
                [
                    p.pbr
                    for p in peers
                    if p.pbr is not None
                    and p.pbr>0
                ]
            ),
            "roe":_median_numeric(
                [
                    p.roe
                    for p in peers
                ]
            ),
            "revenue_growth":_median_numeric(
                [
                    p.revenue_growth
                    for p in peers
                ]
            ),
            "operating_margin":_median_numeric(
                [
                    p.operating_margin
                    for p in peers
                ]
            ),
        },
        "largest_peers":[
            {
                "name":p.name,
                "code":p.code,
                "market_cap":
                    _clean_ai_number(
                        p.market_cap
                    ),
                "per":
                    _clean_ai_number(
                        p.per
                    ),
                "pbr":
                    _clean_ai_number(
                        p.pbr
                    ),
                "roe":
                    _clean_ai_number(
                        p.roe
                    ),
            }
            for p in peers[:5]
        ],
    }


def _compact_financial_context(
    financials,
):
    rows=[]

    for row in (
        financials
        or []
    )[:4]:
        rows.append(
            {
                "period":
                    row.get("period"),
                "revenue":
                    _clean_ai_number(
                        row.get("revenue")
                    ),
                "operating_profit":
                    _clean_ai_number(
                        row.get(
                            "operating_profit"
                        )
                    ),
                "net_income":
                    _clean_ai_number(
                        row.get("net_income")
                    ),
                "assets":
                    _clean_ai_number(
                        row.get("assets")
                    ),
                "liabilities":
                    _clean_ai_number(
                        row.get(
                            "liabilities"
                        )
                    ),
                "equity":
                    _clean_ai_number(
                        row.get("equity")
                    ),
                "comparison_period":
                    row.get(
                        "comparison_period"
                    ),
                "change":
                    row.get("change")
                    or {},
            }
        )

    return rows


def _compact_news_context(
    items,
):
    result=[]

    for item in (
        items
        or []
    )[:8]:
        result.append(
            {
                "title":
                    str(
                        item.get("title")
                        or ""
                    )[:180],
                "publisher":
                    str(
                        item.get(
                            "publisher"
                        )
                        or ""
                    )[:60],
                "published_at":
                    item.get(
                        "published_at"
                    ),
                "sentiment":
                    item.get(
                        "sentiment"
                    ),
                "sentiment_score":
                    _clean_ai_number(
                        item.get(
                            "sentiment_score"
                        )
                    ),
                "summary":
                    str(
                        item.get(
                            "brief_summary"
                        )
                        or item.get(
                            "description"
                        )
                        or ""
                    )[:240],
            }
        )

    return result


def _compact_report_context(
    reports,
):
    result=[]

    for item in (
        reports
        or []
    )[:4]:
        result.append(
            {
                "date":
                    item.get("date"),
                "broker":
                    str(
                        item.get("broker")
                        or ""
                    )[:60],
                "title":
                    str(
                        item.get("title")
                        or ""
                    )[:180],
                "sentiment":
                    item.get(
                        "sentiment"
                    ),
                "investment_opinion":
                    item.get(
                        "investment_opinion"
                    ),
                "target_price":
                    _clean_ai_number(
                        item.get(
                            "target_price"
                        )
                    ),
                "summary":
                    str(
                        item.get(
                            "brief_summary"
                        )
                        or ""
                    )[:260],
            }
        )

    return result


def _compact_market_context(
    overview,
):
    result=[]

    for item in (
        overview.get("items")
        or []
    ):
        if not item.get(
            "available",
            False,
        ):
            continue

        result.append(
            {
                "key":
                    item.get("key"),
                "label":
                    item.get("label"),
                "value":
                    _clean_ai_number(
                        item.get("value")
                    ),
                "change_rate":
                    _clean_ai_number(
                        item.get(
                            "change_rate"
                        )
                    ),
                "state":
                    item.get(
                        "state_label"
                    ),
                "closed":
                    bool(
                        item.get("closed")
                    ),
                "stale":
                    bool(
                        item.get("stale")
                    ),
            }
        )

    return result


def _ai_context_fingerprint(
    context,
):
    # Market snapshot changes too frequently and would invalidate the expensive
    # local-CPU analysis every few seconds. Exclude it from the fingerprint.
    stable=dict(
        context
    )
    stable.pop(
        "market_context",
        None,
    )
    stable.pop(
        "generated_at",
        None,
    )

    payload=json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",",":"),
    )

    return hashlib.sha256(
        payload.encode(
            "utf-8"
        )
    ).hexdigest()


def _cached_news_for_ai(db, stock_code, limit=6):
    """Use both newest and highest-impact real articles; never wait on the web here."""
    pool=(db.query(NewsCache).filter(NewsCache.stock_code==stock_code).order_by(NewsCache.published_dt.desc(),NewsCache.id.desc()).limit(80).all())
    latest=pool[:3]
    important=sorted(pool,key=lambda x:(float(getattr(x,"importance_score",0) or 0),getattr(x,"published_dt",None) or datetime.min),reverse=True)[:3]
    selected=[];seen=set()
    for row in latest+important:
        key=row.id
        if key in seen:continue
        seen.add(key);selected.append(row)
        if len(selected)>=max(1,min(int(limit),8)):break
    selected=sorted(selected,key=lambda x:getattr(x,"published_dt",None) or datetime.min,reverse=True)
    items=[];counts={"positive":0,"neutral":0,"negative":0}
    for row in selected:
        sentiment=str(row.sentiment or "neutral").lower()
        if sentiment not in counts:sentiment="neutral"
        counts[sentiment]+=1
        items.append({"title":str(row.title or "")[:120],"published_at":row.published_dt.strftime("%Y-%m-%d %H:%M") if row.published_dt else str(row.published_at or "")[:20],"publisher":str(row.publisher or "")[:40],"sentiment":sentiment,"score":_clean_ai_number(row.sentiment_score),"importance":_clean_ai_number(getattr(row,"importance_score",0))})
    dominant=max(counts,key=counts.get) if items else "neutral"
    return {"count":len(items),"sentiment_counts":counts,"dominant":dominant,"items":items}


def _cached_reports_for_ai(db,stock_code,limit=3):
    rows=(db.query(BrokerReportCache).filter(BrokerReportCache.stock_code==stock_code).order_by(BrokerReportCache.report_dt.desc(),BrokerReportCache.id.desc()).limit(max(1,min(int(limit),5))).all())
    return {"count":len(rows),"items":[{"date":r.report_date,"broker":str(r.broker or "")[:30],"title":str(r.title or "")[:100],"sentiment":r.sentiment,"opinion":r.investment_opinion,"target_price":_clean_ai_number(r.target_price)} for r in rows]}


def _cached_disclosures_for_ai(db,stock_code,limit=4):
    pool=(db.query(DisclosureCache).filter(DisclosureCache.stock_code==stock_code).order_by(DisclosureCache.receipt_dt.desc(),DisclosureCache.id.desc()).limit(40).all())
    latest=pool[:2];important=sorted(pool,key=lambda r:(float(r.importance_score or 0),r.receipt_dt or datetime.min),reverse=True)[:2]
    selected=[];seen=set()
    for r in latest+important:
        if r.id in seen:continue
        seen.add(r.id);selected.append(r)
        if len(selected)>=max(1,min(int(limit),6)):break
    return {"count":len(selected),"items":[{"date":r.receipt_date,"name":str(r.report_name or "")[:110],"importance":_clean_ai_number(r.importance_score)} for r in selected]}

def _compact_financials_for_ai(financials):
    """Keep three disclosed periods and the balance-sheet facts needed for real interpretation."""
    result=[]
    for row in (financials or [])[:3]:
        change=row.get("change") or {}
        assets=_clean_ai_number(row.get("assets"))
        liabilities=_clean_ai_number(row.get("liabilities"))
        equity=_clean_ai_number(row.get("equity"))
        revenue=_clean_ai_number(row.get("revenue"))
        operating_profit=_clean_ai_number(row.get("operating_profit"))
        result.append({
            "period":row.get("period"),
            "comparison_period":row.get("comparison_period"),
            "revenue":revenue,
            "operating_profit":operating_profit,
            "net_income":_clean_ai_number(row.get("net_income")),
            "assets":assets,
            "liabilities":liabilities,
            "equity":equity,
            "revenue_change_pct":_clean_ai_number(change.get("revenue")),
            "operating_profit_change_pct":_clean_ai_number(change.get("operating_profit")),
            "net_income_change_pct":_clean_ai_number(change.get("net_income")),
            "assets_change_pct":_clean_ai_number(change.get("assets")),
            "liabilities_change_pct":_clean_ai_number(change.get("liabilities")),
            "equity_change_pct":_clean_ai_number(change.get("equity")),
            "debt_ratio_pct":round(liabilities/equity*100,2) if liabilities is not None and equity not in (None,0) else None,
            "operating_margin_calc_pct":round(operating_profit/revenue*100,2) if operating_profit is not None and revenue not in (None,0) else None,
        })
    return result


def _investor_flow_context_for_ai(db:Session,stock:Stock):
    """Summarize stored Kiwoom ka10060 data without making another broker request."""
    rows=(
        db.query(StockInvestorFlowDaily)
        .filter(StockInvestorFlowDaily.stock_code==stock.code)
        .order_by(StockInvestorFlowDaily.trade_date.desc())
        .limit(20)
        .all()
    )
    if not rows:
        return {"available":False,"periods":{},"latest_period":{},"latest_date":None}

    detail_fields=(
        "financial_investment_net","investment_trust_net","pension_net",
        "insurance_net","bank_net","private_equity_net",
    )
    shares=float(stock.shares_outstanding or 0)
    if shares<=0 and stock.market_cap and stock.price:
        shares=(float(stock.market_cap)*100_000_000)/max(1,float(stock.price))

    def summarize(period:int):
        selected=rows[:min(period,len(rows))]
        if not selected:return {}
        sums={
            key:sum(float(getattr(r,key) or 0) for r in selected)
            for key in (
                "individual_net","foreign_net","institution_net",
                "financial_investment_net","investment_trust_net","pension_net",
                "insurance_net","bank_net","private_equity_net",
            )
        }
        latest=selected[0];oldest=selected[-1]
        latest_close=float(latest.close_price or stock.price or 0)
        oldest_close=float(oldest.close_price or latest_close or 0)
        price_change=((latest_close-oldest_close)/oldest_close*100) if len(selected)>1 and oldest_close>0 else float(stock.change_rate or 0)
        foreign_days=sum(1 for r in selected if float(r.foreign_net or 0)>0)
        institution_days=sum(1 for r in selected if float(r.institution_net or 0)>0)
        foreign=float(sums["foreign_net"]);institution=float(sums["institution_net"])
        combined=foreign+institution
        detail_breadth=sum(1 for field in detail_fields if float(sums[field])>0)/len(detail_fields)
        return {
            "days":len(selected),
            "foreign_net":round(foreign,2),
            "institution_net":round(institution,2),
            "individual_net":round(float(sums["individual_net"]),2),
            "foreign_institution_net":round(combined,2),
            "financial_investment_net":round(float(sums["financial_investment_net"]),2),
            "investment_trust_net":round(float(sums["investment_trust_net"]),2),
            "pension_net":round(float(sums["pension_net"]),2),
            "insurance_net":round(float(sums["insurance_net"]),2),
            "bank_net":round(float(sums["bank_net"]),2),
            "private_equity_net":round(float(sums["private_equity_net"]),2),
            "foreign_buy_days":foreign_days,
            "institution_buy_days":institution_days,
            "foreign_streak":_positive_streak(selected,"foreign_net"),
            "institution_streak":_positive_streak(selected,"institution_net"),
            "joint_buy":bool(foreign>0 and institution>0),
            "institution_breadth_ratio":round(detail_breadth,3),
            "combined_vs_shares_pct":round(combined/max(1,shares)*100,5) if shares>0 else None,
            "period_price_change_pct":round(price_change,3),
        }

    periods={str(period):summarize(period) for period in (1,5,20)}
    return {
        "available":True,
        "unit":"shares",
        "latest_date":rows[0].trade_date.isoformat(),
        "periods":periods,
        "latest_period":periods.get("5") or periods.get("1") or {},
    }


async def _ensure_stock_flow_for_ai(db:Session,stock:Stock) -> dict:
    """Backfill missing investor flow for an analyzed stock using the admin broker connection.

    Bulk flow sync can intentionally be limited to the top N names. Premium analysis,
    however, must not silently lose its supply/demand evidence merely because a stock
    sat outside that batch. Only completely missing DB coverage triggers this fetch.
    """
    existing=(
        db.query(StockInvestorFlowDaily.id)
        .filter(StockInvestorFlowDaily.stock_code==stock.code)
        .first()
    )
    if existing:
        return {"attempted":False,"status":"cached"}

    lock=_ai_flow_backfill_locks.setdefault(stock.code,asyncio.Lock())
    async with lock:
        existing=(
            db.query(StockInvestorFlowDaily.id)
            .filter(StockInvestorFlowDaily.stock_code==stock.code)
            .first()
        )
        if existing:
            return {"attempted":False,"status":"cached_after_wait"}

        admin=_find_sync_admin(db,require_kiwoom=True)
        if not admin:
            filename=begin_sync_diagnostic(
                "analysis-flow-backfill",
                run_id=f"{stock.code}-{time.time_ns()}",
                metadata={"stock_code":stock.code,"stock_name":stock.name},
            )
            append_sync_diagnostic(
                filename,"ERROR","FLOW_BACKFILL_NO_ADMIN_CREDENTIAL",
                details={"stock_code":stock.code,"stock_name":stock.name,"reason":"active admin Kiwoom credential not found"},
            )
            return {"attempted":True,"status":"no_admin_credential","diagnostic_log":filename}

        try:
            _,cli=client_for(admin,db)
            # Credential lookup checked out the DB. Release it before Kiwoom I/O.
            commit_or_rollback(db)
            today=datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
            payload,retries,outcome,exc=await _fetch_flow_with_retry(cli,stock.code,today,20,max_attempts=3,fallback_previous_dates=True)
            if outcome=="ok":
                saved=_upsert_flow_rows(db,stock.code,payload or {})
                if saved>0:
                    commit_or_rollback(db)
                    logger.info("AI flow backfill completed stock=%s rows=%s retries=%s",stock.code,saved,retries)
                    return {"attempted":True,"status":"saved","rows":saved,"retries":retries}
                outcome="parse_empty"
                exc=RuntimeError("키움 수급 응답은 있었지만 저장 가능한 날짜 행이 없습니다.")

            rollback_quietly(db)
            filename=begin_sync_diagnostic(
                "analysis-flow-backfill",
                run_id=f"{stock.code}-{time.time_ns()}",
                metadata={"stock_code":stock.code,"stock_name":stock.name,"date":today},
            )
            append_sync_diagnostic(
                filename,
                "WARNING" if outcome=="no_data" else "ERROR",
                "FLOW_BACKFILL_FAILED",
                details={
                    "stock_code":stock.code,"stock_name":stock.name,"date":today,
                    "outcome":outcome,"retries":int(retries),
                    "error":_sync_error_text(exc or RuntimeError(outcome),2000),
                },
                exc=exc,
            )
            return {"attempted":True,"status":outcome,"retries":retries,"diagnostic_log":filename}
        except Exception as exc:
            rollback_quietly(db)
            filename=begin_sync_diagnostic(
                "analysis-flow-backfill",
                run_id=f"{stock.code}-{time.time_ns()}",
                metadata={"stock_code":stock.code,"stock_name":stock.name},
            )
            append_sync_diagnostic(
                filename,"ERROR","FLOW_BACKFILL_FATAL",
                details={"stock_code":stock.code,"stock_name":stock.name},
                exc=exc,
            )
            logger.exception("AI flow backfill failed stock=%s",stock.code)
            return {"attempted":True,"status":"failed","diagnostic_log":filename}


def _theme_context_for_ai(db:Session,stock:Stock):
    links=(
        db.query(StockTheme)
        .filter(StockTheme.stock_code==stock.code)
        .order_by(StockTheme.updated_at.desc())
        .limit(12)
        .all()
    )
    if not links and not stock.primary_theme:
        return {"available":False,"primary":None,"items":[]}
    codes=[x.theme_code for x in links]
    themes={}
    if codes:
        themes={x.theme_code:x for x in db.query(Theme).filter(Theme.theme_code.in_(codes)).all()}
    items=[]
    for link in links:
        theme=themes.get(link.theme_code)
        rate=_clean_ai_number(theme.change_rate if theme else None)
        rank=None
        if rate is not None:
            try:
                rank=(db.query(Theme).filter(Theme.is_active==True,Theme.change_rate>rate).count()+1)
            except Exception:
                rank=None
        items.append({
            "theme_code":link.theme_code,
            "theme_name":link.theme_name,
            "change_rate_pct":rate,
            "market_rank":rank,
            "updated_at":link.updated_at.isoformat() if link.updated_at else None,
        })
    items.sort(key=lambda x:(x.get("change_rate_pct") is not None,x.get("change_rate_pct") or -999),reverse=True)
    return {
        "available":bool(items or stock.primary_theme),
        "primary":stock.primary_theme,
        "items":items[:6],
    }


def _fast_quant_preanalysis(stock, peer, price_action, financials, news, score_ctx):
    """Deterministic interpretation hints. The LLM explains these; it does not recalculate them."""
    def view_from_points(points):
        if points >= 2:
            return "positive"
        if points <= -2:
            return "negative"
        return "neutral"

    valuation_points=0
    median=(peer or {}).get("median") or {}
    per=_clean_ai_number(stock.per)
    pbr=_clean_ai_number(stock.pbr)
    roe=_clean_ai_number(stock.roe)
    peer_per=_clean_ai_number(median.get("per"))
    peer_pbr=_clean_ai_number(median.get("pbr"))
    peer_roe=_clean_ai_number(median.get("roe"))
    if per and per>0 and peer_per and peer_per>0:
        valuation_points += 1 if per <= peer_per else -1
    if pbr and pbr>0 and peer_pbr and peer_pbr>0:
        valuation_points += 1 if pbr <= peer_pbr else -1
    if roe is not None and peer_roe is not None:
        valuation_points += 1 if roe >= peer_roe else -1

    momentum_points=0
    if price_action.get("price_vs_ma20")=="above": momentum_points+=1
    elif price_action.get("price_vs_ma20")=="below": momentum_points-=1
    if price_action.get("price_vs_ma60")=="above": momentum_points+=1
    elif price_action.get("price_vs_ma60")=="below": momentum_points-=1
    r20=_clean_ai_number(price_action.get("return_20d_pct"))
    if r20 is not None:
        momentum_points += 1 if r20>2 else -1 if r20<-2 else 0

    financial_points=0
    latest=(financials or [{}])[0] if financials else {}
    change=latest.get("change") or {}
    for key in ("revenue","operating_profit","net_income"):
        value=_clean_ai_number(change.get(key))
        if value is not None:
            financial_points += 1 if value>0 else -1 if value<0 else 0
    growth=_clean_ai_number(stock.revenue_growth)
    margin=_clean_ai_number(stock.operating_margin)
    if growth is not None:
        financial_points += 1 if growth>0 else -1 if growth<0 else 0
    if margin is not None:
        financial_points += 1 if margin>0 else -1 if margin<0 else 0

    news_counts=(news or {}).get("sentiment_counts") or {}
    news_points=int(news_counts.get("positive",0))-int(news_counts.get("negative",0))

    return {
        "overall_score":score_ctx.get("score"),
        "overall_recommendation":_recommendation_label_from_score(score_ctx.get("score")),
        "valuation_view":view_from_points(valuation_points),
        "financial_view":view_from_points(financial_points),
        "momentum_view":view_from_points(momentum_points),
        "news_view":view_from_points(news_points),
        "evidence":{
            "valuation_points":valuation_points,
            "financial_points":financial_points,
            "momentum_points":momentum_points,
            "news_points":news_points,
        },
    }


async def _build_stock_ai_context(
    stock,
    user,
    db,
    mode="ai",
):
    """Build a CPU-friendly context: calculations first, LLM explanation second."""
    mode=str(mode or "ai").lower().strip()
    if mode not in {"ai","profile","buffett","custom"}:
        mode="ai"

    # A top-N administrator flow sync may legitimately omit a smaller-cap stock.
    # Premium analysis repairs only completely missing flow rows on demand, so an
    # analyzed stock never loses the supply/demand section merely because of batch scope.
    await _ensure_stock_flow_for_ai(db,stock)

    # 260 bars are enough for 20/60/240-day indicators and much cheaper than 500.
    chart=_build_real_chart(stock.code, db, limit=260)
    price_action=_price_action_context(chart)

    raw_financials=financials_from_db(stock.code, db, limit=4)
    financials=enrich_financial_growth(raw_financials)

    # AI must not block on external sites. News collection remains a separate StockLog job.
    news=_cached_news_for_ai(db, stock.code, limit=6)

    formula=None
    if mode=="custom":
        formula_obj=(
            db.query(SmartFormula)
            .filter(SmartFormula.user_id==user.id)
            .first()
        )
        formula=_custom_formula_dict(formula_obj)

    profile_scores=None
    profile_code=""
    if mode=="profile":
        profile_row=(db.query(InvestmentProfile).filter(InvestmentProfile.user_id==user.id).first())
        payload=_investment_profile_payload(profile_row)
        profile_scores=(payload or {}).get("scores") or {}
        profile_code=(payload or {}).get("result_code") or ""

    score_ctx=_smart_score_context(stock, mode, formula, profile_scores, profile_code)
    peer=_peer_context(stock, db)
    peer_compact={
        "available":bool(peer.get("available")),
        "basis":peer.get("basis"),
        "peer_count":peer.get("peer_count",0),
        "median":peer.get("median") or {},
    }

    # AI never crawls external sites. It consumes the latest data already collected by StockLog.
    reports=_cached_reports_for_ai(db,stock.code,limit=3)
    disclosures=_cached_disclosures_for_ai(db,stock.code,limit=4)

    market=[]
    if str(os.getenv("AI_INCLUDE_MARKET_CONTEXT","true")).lower() in {"1","true","yes","on"}:
        # All context DB reads above are complete. Market overview is external
        # network I/O and can wait several seconds, so return the checkout first.
        commit_or_rollback(db)
        try:
            overview=await asyncio.wait_for(_market_overview_actual(), timeout=3)
            market=_compact_market_context(overview)[:4]
        except Exception:
            market=[]

    preanalysis=_fast_quant_preanalysis(
        stock, peer_compact, price_action, financials, news, score_ctx
    )

    context={
        "company":{
            "name":stock.name,
            "code":stock.code,
            "market":stock.market,
            "sector":stock.sector,
            "industry":stock.industry_name,
            "theme":stock.primary_theme,
        },
        "metrics":{
            "price":_clean_ai_number(stock.price),
            "change_pct":_clean_ai_number(stock.change_rate),
            "market_cap_억원":_clean_ai_number(stock.market_cap),
            "per":_clean_ai_number(stock.per),
            "pbr":_clean_ai_number(stock.pbr),
            "eps":_clean_ai_number(stock.eps),
            "bps":_clean_ai_number(stock.bps),
            "roe_pct":_clean_ai_number(stock.roe),
            "revenue_growth_pct":_clean_ai_number(stock.revenue_growth),
            "operating_margin_pct":_clean_ai_number(stock.operating_margin),
            "dividend_yield_pct":_clean_ai_number(stock.dividend_yield),
            "momentum_20d_pct":_clean_ai_number(stock.momentum_20d),
            "volatility":_clean_ai_number(stock.volatility),
        },
        "peer":peer_compact,
        "financials":_compact_financials_for_ai(financials),
        "supply_demand":_investor_flow_context_for_ai(db,stock),
        "themes":_theme_context_for_ai(db,stock),
        "momentum":{
            key:price_action.get(key)
            for key in (
                "available","return_1d_pct","return_5d_pct","return_20d_pct","return_60d_pct",
                "price_vs_ma20","price_vs_ma60","price_vs_ma240","volume_vs_20d_avg",
                "distance_from_52w_high_pct",
            )
        },
        "news":news,
        "reports":reports,
        "disclosures":disclosures,
        "market":market,
        "quant":{
            "mode":score_ctx.get("mode"),
            "type":score_ctx.get("type"),
            "score":score_ctx.get("score"),
            "recommendation":_recommendation_label_from_score(score_ctx.get("score")),
            "reasons":[str(x)[:100] for x in (score_ctx.get("reasons") or [])[:4]],
        },
        "preanalysis":preanalysis,
        "data_freshness":{
            "kiwoom_metrics_updated_at":stock.kiwoom_metrics_updated_at.isoformat() if stock.kiwoom_metrics_updated_at else None,
            "dart_financials_updated_at":stock.dart_financials_updated_at.isoformat() if stock.dart_financials_updated_at else None,
            "stock_updated_at":stock.updated_at.isoformat() if stock.updated_at else None,
        },
        "rules":"입력 사실만 사용. 밸류·실적·수급·모멘텀·테마·뉴스·공시·리포트를 서로 연결해 신규 진입과 기존 보유 관점을 분리해서 판단.",
        "generated_at":datetime.now(timezone.utc).isoformat(),
    }

    return context, _ai_context_fingerprint(context)



def _sanitize_public_ai_result(value):
    """Hide implementation-provider names from every public AI payload.

    Internal provider/model metadata remains in the DB and server logs for operations,
    while customers only see the StockLog Gbot product name.
    """
    if isinstance(value, list):
        return [_sanitize_public_ai_result(item) for item in value]
    if isinstance(value, dict):
        cleaned={}
        for key,item in value.items():
            public_key=str(key)
            lowered=public_key.lower()
            if lowered in {
                "_meta","provider","providers","model","models","model_name",
                "requested_model","manual_model","background_model","dual_analysis",
                "bot_views","model_consensus","gemini_verdict","ollama_verdict",
                "gbot_verdict","obot_verdict",
            } or "provider" in lowered or "model" in lowered:
                continue
            cleaned[public_key]=_sanitize_public_ai_result(item)
        return cleaned
    if isinstance(value, str):
        text=re.sub(
            r"\b(?:gemini|ollama)(?:[-_.][A-Za-z0-9]+)*\b",
            "StockLog Gbot",
            value,
            flags=re.IGNORECASE,
        )
        replacements=(
            ("Google AI Studio", "StockLog Gbot"),
            ("StockLog Obot", "StockLog Gbot"),
            ("Obot", "Gbot"),
            ("obot", "Gbot"),
        )
        for old,new in replacements:
            text=text.replace(old,new)
        return text
    return value


def _premium_dual_ai_required(user: User) -> bool:
    """Deprecated compatibility flag: premium detail now uses Gbot only."""
    return False

def _premium_gbot_required(user: User) -> bool:
    return user_tier(user) in {"PREMIUM","EVENT","ADMIN"}


def _ai_cache_payload(
    row,
    *,
    current_hash=None,
):
    if not row:
        return None

    try:
        result=json.loads(
            row.result_json
            or "{}"
        )
    except Exception:
        result={}

    now=datetime.now()

    # v3.58.3 deep-consensus results include verdict/model_consensus.  Older
    # short-form caches are still readable but should be marked stale so the
    # next explicit analysis upgrades them to the richer schema.
    legacy_schema=bool(
        row.mode!="portfolio_momentum"
        and result
        and (
            not result.get("verdict")
            or not result.get("model_consensus")
        )
    )
    stale=bool(
        legacy_schema
        or (
            row.expires_at
            and row.expires_at<=now
        )
        or (
            current_hash
            and row.context_hash
            != current_hash
        )
    )

    # Backfill older completed premium analyses from the stored factual context.
    # This improves the explanation without consuming another AI use or making a new inference call.
    if isinstance(result,dict) and row.mode!="portfolio_momentum" and result:
        try:
            stored_context=json.loads(row.context_json or "{}")
        except Exception:
            stored_context={}
        if isinstance(stored_context,dict) and stored_context:
            try:
                result=finalize_deep_result(result,stored_context)
            except Exception as exc:
                logger.warning("AI cache evidence backfill failed code=%s error=%s",row.stock_code,type(exc).__name__)

    # Public analysis responses intentionally hide provider/model implementation details.
    if isinstance(result,dict):
        result=_sanitize_public_ai_result(result)

    return {
        "stock_code":
            row.stock_code,
        "mode":
            row.mode,
        "status":
            row.status,
        "stale":
            stale,
        "result":
            result,
        "error_message":
            _sanitize_public_ai_result(row.error_message),
        "generated_at":
            (
                row.generated_at.isoformat()
                if row.generated_at
                else None
            ),
        "expires_at":
            (
                row.expires_at.isoformat()
                if row.expires_at
                else None
            ),
    }



def _ai_analyst_for(db: Session) -> HybridAnalyst:
    """Build the internal analyst ensemble. Public payloads expose only Gbot branding."""
    creds=get_provider_credentials(PROVIDER_GEMINI,db)
    api_key=creds.get("api_key","") if creds.get("source") not in {"none","disabled"} else ""
    return HybridAnalyst(api_key)


async def _run_ai_analysis(
    *,
    stock,
    user,
    db,
    mode="ai",
    force=False,
):
    progress_key=f"{stock.code}:{mode}"
    if (_ai_live_progress.get(progress_key) or {}).get("stage")!="queued":
        _ai_live_progress.pop(progress_key,None)
    _ai_progress_update(progress_key,"context",{
        "phase":"context",
        "message":"종목의 재무·가격·수급·뉴스 데이터를 정리하고 있습니다.",
    })
    row=(
        db.query(AiStockAnalysis)
        .filter(
            AiStockAnalysis.stock_code==stock.code,
            AiStockAnalysis.mode==mode,
        )
        .first()
    )

    if not row:
        row=AiStockAnalysis(
            stock_code=stock.code,
            mode=mode,
        )
        db.add(row)

    analyst=_ai_analyst_for(db)
    require_dual=False
    require_gbot=_premium_gbot_required(user) and mode!="portfolio_momentum"

    # Preserve the provider/model attached to an existing cache row until a
    # fresh generation really completes. Otherwise an old Ollama cache could
    # be mislabeled as Gemini merely because Gemini was configured later.
    row.status="context"
    row.error_message=""
    row.updated_at=datetime.now()
    commit_or_rollback(db)

    try:
        context,context_hash=await _build_stock_ai_context(
            stock,
            user,
            db,
            mode,
        )

        cached=_ai_cache_payload(
            row,
            current_hash=context_hash,
        )

        if (
            not force
            and row.generated_at
            and row.result_json not in {"", "{}"}
            and cached
            and not cached["stale"]
            and (not require_gbot or bool((cached.get("result") or {}).get("gbot_analysis")))
        ):
            row.status="ready"
            _ai_progress_update(progress_key,"ready",{"phase":"cached","message":"최근 완료된 프리미엄 AI 분석을 불러왔습니다.","done":True})
            commit_or_rollback(db)

            return {
                **cached,
                "status":"ready",
                "cached":True,
            }

        row.status="running"
        row.context_hash=context_hash
        row.context_json=json.dumps(
            context,
            ensure_ascii=False,
        )
        row.error_message=""
        row.updated_at=datetime.now()
        commit_or_rollback(db)

        stage_persist={"stage":"","at":0.0}
        def _set_ai_stage(stage, detail=None):
            stage=str(stage or "running")[:20]
            _ai_progress_update(progress_key,stage,detail)
            now_mono=time.monotonic()
            # Persist stage immediately on a transition, then only touch the DB at
            # most every five seconds while streaming tokens. Live details are served
            # from the in-process progress state.
            if stage!=stage_persist["stage"] or now_mono-stage_persist["at"]>=5.0:
                row.status=stage
                row.updated_at=datetime.now()
                commit_or_rollback(db)
                stage_persist["stage"]=stage
                stage_persist["at"]=now_mono

        async with _ai_generation_lock:
            result,meta=await analyst.analyze(
                context,
                require_dual=False,
                require_gbot=require_gbot,
                progress_callback=_set_ai_stage if require_gbot else None,
            )

        now=datetime.now()

        row.provider=str(meta.get("provider") or analyst.provider)
        row.model_name=str(meta.get("model") or analyst.model)
        row.status="ready"
        _ai_progress_update(progress_key,"ready",{"phase":"done","message":"프리미엄 AI 분석을 완료했습니다.","done":True})
        row.context_hash=context_hash
        row.result_json=json.dumps(
            {
                **result,
                "_meta":meta,
            },
            ensure_ascii=False,
        )
        row.error_message=""
        row.generated_at=now
        row.expires_at=now+timedelta(hours=_AI_CACHE_HOURS)
        row.updated_at=now
        commit_or_rollback(db)
        db.refresh(row)

        payload=_ai_cache_payload(
            row,
            current_hash=context_hash,
        )

        return {
            **payload,
            "status":"ready",
            "cached":False,
        }

    except DualAnalysisUnavailable as exc:
        # Premium stock detail requires Gbot. Obot is no longer part of this path.
        row.status="failed"
        row.error_message=str(exc) or "StockLog Gbot 분석을 완료하지 못했습니다."
        _ai_progress_update(progress_key,"failed",{"phase":"failed","message":row.error_message,"done":True})
        row.updated_at=datetime.now()
        commit_or_rollback(db)
        logger.warning("premium Gbot AI incomplete code=%s error=%s",stock.code,row.error_message)
        raise

    except httpx.ConnectError as exc:
        row.status="failed"
        row.error_message=(
            "AI 분석 서비스 연결에 실패했습니다. 잠시 후 다시 시도해주세요."
        )
        _ai_progress_update(progress_key,"failed",{"phase":"failed","message":row.error_message,"done":True})
        row.updated_at=datetime.now()
        commit_or_rollback(db)
        print("[ERROR] AI connect:", stock.code, repr(exc))
        raise

    except httpx.TimeoutException as exc:
        # Premium Gbot analysis must never be silently downgraded to a local model.
        if require_gbot:
            row.status="failed"
            row.error_message="StockLog Gbot 분석 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            _ai_progress_update(progress_key,"failed",{"phase":"failed","message":row.error_message,"done":True})
            row.updated_at=datetime.now()
            commit_or_rollback(db)
            raise DualAnalysisUnavailable(row.error_message) from exc
        # Non-premium compatibility path may still use a deterministic result.
        if "context" in locals() and context:
            now=datetime.now()
            result=_deterministic_fallback(context, "pipeline_timeout")
            row.status="ready"
            row.result_json=json.dumps(
                {
                    **result,
                    "_meta":{
                        "model":getattr(analyst,"model",None),
                        "fallback":True,
                        "fallback_reason":"pipeline_timeout",
                    },
                },
                ensure_ascii=False,
            )
            row.error_message=""
            row.generated_at=now
            row.expires_at=now+timedelta(hours=_AI_CACHE_HOURS)
            row.updated_at=now
            commit_or_rollback(db)
            db.refresh(row)
            print("[WARN] AI timeout fallback:", stock.code, repr(exc))
            payload=_ai_cache_payload(row, current_hash=row.context_hash)
            return {**payload, "status":"ready", "cached":False, "fallback":True}

        row.status="failed"
        row.error_message=(
            "AI 코멘트 생성 전 데이터 준비 시간이 초과되었습니다."
        )
        row.updated_at=datetime.now()
        commit_or_rollback(db)
        print("[ERROR] AI context timeout:", stock.code, repr(exc))
        raise

    except httpx.HTTPStatusError as exc:
        row.status="failed"
        status_code=exc.response.status_code if exc.response else 0
        row.error_message=(
            f"AI 분석 서비스 요청 오류({status_code}). 잠시 후 다시 시도해주세요."
        )
        _ai_progress_update(progress_key,"failed",{"phase":"failed","message":row.error_message,"done":True})
        row.updated_at=datetime.now()
        commit_or_rollback(db)
        print("[ERROR] AI HTTP:", stock.code, repr(exc))
        raise

    except Exception as exc:
        row.status="failed"

        if "JSON" in str(exc):
            user_error="AI 응답을 JSON 분석 결과로 변환하지 못했습니다."
        else:
            user_error=(
                "AI 분석 컨텍스트 구성 또는 결과 처리 중 오류가 발생했습니다."
            )

        row.error_message=user_error
        _ai_progress_update(progress_key,"failed",{"phase":"failed","message":row.error_message,"done":True})
        row.updated_at=datetime.now()
        commit_or_rollback(db)

        print(
            "[ERROR] AI pipeline:",
            stock.code,
            type(exc).__name__,
            repr(exc),
        )
        raise


def _portfolio_momentum_context(stock, db):
    chart=_build_real_chart(stock.code,db,limit=120)
    price_action=_price_action_context(chart)
    momentum={
        key:price_action.get(key)
        for key in (
            "available","return_1d_pct","return_5d_pct","return_20d_pct","return_60d_pct",
            "price_vs_ma20","price_vs_ma60","volume_vs_20d_avg","distance_from_52w_high_pct",
        )
    }
    context={
        "company":{"name":stock.name,"code":stock.code,"market":stock.market,"sector":stock.sector},
        "momentum":momentum,
        "generated_at":datetime.now(timezone.utc).date().isoformat(),
    }
    stable={"company":context["company"],"momentum":momentum,"date":context["generated_at"]}
    fingerprint=hashlib.sha256(json.dumps(stable,ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")).hexdigest()
    return context,fingerprint


async def _run_portfolio_momentum_analysis(stock, db):
    mode="portfolio_momentum"
    row=(db.query(AiStockAnalysis).filter(AiStockAnalysis.stock_code==stock.code,AiStockAnalysis.mode==mode).first())
    if not row:
        row=AiStockAnalysis(stock_code=stock.code,mode=mode)
        db.add(row)
        flush_or_rollback(db)
    context,context_hash=_portfolio_momentum_context(stock,db)
    now=datetime.now()
    if (
        row.status=="ready"
        and row.result_json not in {"","{}"}
        and row.generated_at
        and row.expires_at
        and row.expires_at>now
        and row.context_hash==context_hash
    ):
        return _ai_cache_payload(row,current_hash=context_hash)

    analyst=_ai_analyst_for(db)
    row.provider=analyst.provider;row.model_name=analyst.model;row.status="running";row.context_hash=context_hash
    row.context_json=json.dumps(context,ensure_ascii=False);row.error_message="";row.updated_at=now
    commit_or_rollback(db)
    try:
        async with _ai_generation_lock:
            # Another premium member may hold the same stock. Re-check the shared
            # stock-level cache after waiting for the single CPU AI slot so the
            # same momentum analysis is never generated twice unnecessarily.
            db.refresh(row)
            lock_now=datetime.now()
            if (
                row.status=="ready"
                and row.result_json not in {"","{}"}
                and row.expires_at
                and row.expires_at>lock_now
                and row.context_hash==context_hash
            ):
                return _ai_cache_payload(row,current_hash=context_hash)
            row.status="running";row.context_hash=context_hash;row.context_json=json.dumps(context,ensure_ascii=False)
            row.updated_at=lock_now;commit_or_rollback(db)
            result,meta=await analyst.analyze_momentum(context)
        now=datetime.now()
        row.provider=str(meta.get("provider") or analyst.provider);row.model_name=str(meta.get("model") or analyst.model)
        row.status="ready"
        row.result_json=json.dumps({**result,"_meta":meta},ensure_ascii=False)
        row.error_message="";row.generated_at=now
        row.expires_at=now+timedelta(hours=_PORTFOLIO_MOMENTUM_CACHE_HOURS);row.updated_at=now
        commit_or_rollback(db);db.refresh(row)
        return _ai_cache_payload(row,current_hash=context_hash)
    except Exception as exc:
        row.status="failed";row.error_message="AI 모멘텀 분석을 잠시 완료하지 못했습니다.";row.updated_at=datetime.now()
        commit_or_rollback(db)
        logger.warning("portfolio momentum failed code=%s error=%s",stock.code,type(exc).__name__)
        return _ai_cache_payload(row,current_hash=context_hash)


def _portfolio_snapshot_codes(db,user_id:int):
    snap=(db.query(KiwoomAccountSnapshot).filter(KiwoomAccountSnapshot.user_id==user_id).first())
    if not snap:
        return []
    try: holdings=json.loads(snap.holdings_json or "[]")
    except Exception: holdings=[]
    result=[]
    for item in holdings if isinstance(holdings,list) else []:
        code=str((item or {}).get("code") or (item or {}).get("stock_code") or "").strip()
        if re.fullmatch(r"\d{6}",code) and code not in result: result.append(code)
    eligible=_stocklog_public_code_set(db,result)
    return [code for code in result if code in eligible][:30]


async def _portfolio_momentum_worker(user_id:int,codes:list[str]):
    state={"running":True,"total":len(codes),"completed":0,"failed":0,"current_code":"","started_at":datetime.now().isoformat(),"finished_at":None,"message":"보유종목 AI 모멘텀을 자동 분석하고 있습니다."}
    _portfolio_momentum_jobs[user_id]=state
    try:
        for code in codes:
            state["current_code"]=code
            db=SessionLocal()
            try:
                user=db.query(User).filter(User.id==user_id,User.is_active==True).first()
                if not user or user_tier(user) not in {"PREMIUM","EVENT","ADMIN"} or not feature_policy(db,user_tier(user),"portfolio_ai_momentum").get("enabled"):
                    state["failed"]+=1;continue
                stock=_stocklog_public_stock(db,code)
                if not stock:
                    state["failed"]+=1;continue
                payload=await _run_portfolio_momentum_analysis(stock,db)
                if not payload or payload.get("status")!="ready": state["failed"]+=1
            except Exception as exc:
                state["failed"]+=1
                logger.warning("portfolio momentum worker item failed code=%s error=%s",code,type(exc).__name__)
            finally:
                db.close()
            state["completed"]+=1
            await asyncio.sleep(0.05)
    finally:
        state["running"]=False;state["current_code"]="";state["finished_at"]=datetime.now().isoformat()
        state["message"]="보유종목 AI 모멘텀 분석이 완료되었습니다."


@app.get("/api/trading/portfolio/outlook")
@app.get("/api/kiwoom/portfolio/ai-momentum")
def portfolio_ai_momentum(u:User=Depends(current_user),db:Session=Depends(get_db)):
    if user_tier(u) not in {"PREMIUM","EVENT","ADMIN"}:
        raise HTTPException(403,"보유종목 AI 모멘텀은 프리미엄 이상 회원 기능입니다.")
    _require_feature(u,db,"portfolio_ai_momentum")
    codes=_portfolio_snapshot_codes(db,u.id)
    rows=[]
    if codes:
        rows=(db.query(AiStockAnalysis).filter(AiStockAnalysis.stock_code.in_(codes),AiStockAnalysis.mode=="portfolio_momentum").all())
    by_code={row.stock_code:row for row in rows}
    items=[]
    now=datetime.now()
    for code in codes:
        stock=_stocklog_public_stock(db,code)
        row=by_code.get(code)
        result={}
        if row:
            try: result=json.loads(row.result_json or "{}")
            except Exception: result={}
        items.append({
            "code":code,"name":stock.name if stock else code,
            "status":row.status if row else "pending",
            "ready":bool(row and row.status=="ready" and result),
            "stale":bool(row and row.expires_at and row.expires_at<=now),
            "analysis":_sanitize_public_ai_result(result),
            "generated_at":row.generated_at.isoformat() if row and row.generated_at else None,
        })
    return {"enabled":True,"tier":user_tier(u),"items":items,"job":dict(_portfolio_momentum_jobs.get(u.id) or {"running":False,"total":len(codes),"completed":0,"failed":0})}


@app.post("/api/trading/portfolio/outlook/start")
@app.post("/api/kiwoom/portfolio/ai-momentum/start")
async def portfolio_ai_momentum_start(u:User=Depends(current_user),db:Session=Depends(get_db)):
    if user_tier(u) not in {"PREMIUM","EVENT","ADMIN"}:
        raise HTTPException(403,"보유종목 AI 모멘텀은 프리미엄 이상 회원 기능입니다.")
    _require_feature(u,db,"portfolio_ai_momentum")
    codes=_portfolio_snapshot_codes(db,u.id)
    if not codes:
        return {"ok":True,"count":0,"message":"AI 모멘텀을 분석할 보유종목이 없습니다."}
    current=_portfolio_momentum_jobs.get(u.id) or {}
    if current.get("running"):
        return {"ok":True,"count":len(codes),"message":"보유종목 AI 모멘텀 분석이 이미 진행 중입니다.","job":dict(current)}
    _portfolio_momentum_jobs[u.id]={
        "running":True,"total":len(codes),"completed":0,"failed":0,"current_code":"",
        "started_at":datetime.now().isoformat(),"finished_at":None,"message":"보유종목 AI 모멘텀 분석을 준비하고 있습니다.",
    }
    asyncio.create_task(_portfolio_momentum_worker(u.id,codes))
    return {"ok":True,"count":len(codes),"message":f"보유종목 {len(codes)}개의 AI 모멘텀을 자동 확인합니다.","job":dict(_portfolio_momentum_jobs[u.id])}


@app.get("/api/ai/status")
async def ai_status(
    _:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    """Public AI readiness using StockLog product branding only."""
    enabled=str(os.getenv("AI_ANALYST_ENABLED","true")).lower() not in {"0","false","no","off"}
    if not enabled:
        return {"enabled":False,"ok":False,"message":"StockLog AI 분석이 현재 비활성화되어 있습니다."}

    g_public=provider_public_status(PROVIDER_GEMINI,db)
    g_ready=bool(g_public.get("configured") and g_public.get("enabled",True))
    return {
        "enabled":True,
        "ok":g_ready,
        "engine":{"label":"StockLog Gbot","ready":g_ready},
        "message":(
            "StockLog Gbot 프리미엄 분석을 사용할 수 있습니다."
            if g_ready else
            "StockLog Gbot 연결 설정을 확인해주세요."
        ),
    }


@app.get("/api/ai/cache")
def ai_cache_list(
    codes:str=Query(""),
    mode:str=Query("ai"),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    requested=[
        code.strip()
        for code in codes.split(",")
        if re.fullmatch(r"\d{6}",code.strip())
    ][:100]

    if not requested:
        return {"items":{}}

    public_codes=_stocklog_public_code_set(db,requested)
    requested=[code for code in requested if code in public_codes]
    if not requested:
        return {"items":{}}

    allowed=_granted_ai_codes(u,db,requested,mode)
    if not allowed:
        return {"items":{}}

    rows=(
        db.query(AiStockAnalysis)
        .filter(
            AiStockAnalysis.stock_code.in_(allowed),
            AiStockAnalysis.mode==mode,
        )
        .all()
    )

    return {
        "items":{
            row.stock_code:_ai_cache_payload(row)
            for row in rows
        },
    }


def _ai_row_for(db, code, mode):
    return (
        db.query(AiStockAnalysis)
        .filter(
            AiStockAnalysis.stock_code==code,
            AiStockAnalysis.mode==mode,
        )
        .first()
    )


@app.get("/api/stocks/{code}/ai-analysis/status")
def stock_ai_analysis_status(
    code:str,
    smart_mode:str=Query("ai"),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"ai_analysis")
    if not _stocklog_public_stock(db,code):
        raise HTTPException(404,"StockLog 분석 대상 종목이 아닙니다.")
    mode=str(smart_mode or "ai").lower().strip()
    if mode not in {"ai","profile","buffett","custom"}:
        mode="ai"

    if not _has_ai_analysis_access(u,db,code,mode):
        return {
            "exists":False,
            "status":"missing",
            "stale":True,
            "result":None,
            "message":"이 계정에서는 아직 AI 분석을 열지 않았습니다.",
        }

    row=_ai_row_for(db, code, mode)
    if not row:
        return {
            "exists":False,
            "status":"missing",
            "stale":True,
            "result":None,
            "message":"아직 AI 분석 결과가 없습니다.",
        }

    payload=_ai_cache_payload(row) or {}
    stale=bool(payload.get("stale"))
    status=row.status
    # A failed refresh must never hide the last successfully completed analysis.
    # Keep serving the previous result as stale/ready and expose the refresh error separately.
    refresh_error=""
    if status=="failed" and payload.get("result") and row.generated_at:
        refresh_error=_sanitize_public_ai_result(row.error_message) or "최근 재분석은 완료하지 못했습니다."
        status="stale" if stale else "ready"
    elif status=="ready" and stale:
        status="stale"

    message={
        "queued":"AI 분석 대기열에 등록되었습니다.",
        "context":"Gbot 분석을 준비하고 있습니다.",
        "running":"Gbot이 투자 데이터를 분석하고 있습니다.",
        "obot_running":"Gbot이 투자 데이터를 분석하고 있습니다.",
        "obot_completed":"Gbot이 투자 데이터를 분석하고 있습니다.",
        "gbot_running":"Gbot이 투자 데이터를 분석하고 있습니다.",
        "gbot_completed":"Gbot 분석을 마무리하고 있습니다.",
        "verifying":"Gbot 분석을 마무리하고 있습니다.",
        "ready":"AI 분석이 완료되었습니다.",
        "stale":"기존 AI 분석이 만료되었거나 데이터가 갱신되어 재분석이 필요합니다.",
        "failed":_sanitize_public_ai_result(row.error_message) or "AI 분석에 실패했습니다.",
    }.get(status,"AI 분석 상태를 확인하고 있습니다.")

    progress=_ai_progress_public(f"{code}:{mode}")
    # If the durable row is already terminal, never let an old in-memory stage make
    # the browser believe generation is still running.
    if progress and status in {"ready","stale","failed"}:
        progress={**progress,"stage":status,"message":message}

    return {
        "exists":True,
        **payload,
        "status":status,
        "stale":stale,
        "message":message,
        "refresh_error":refresh_error or None,
        "progress":progress,
    }


async def _detail_ai_background_worker(
    user_id,
    code,
    mode,
    force,
):
    key=f"{code}:{mode}"
    db=SessionLocal()

    try:
        user=(
            db.query(User)
            .filter(
                User.id==user_id,
                User.is_active==True,
            )
            .first()
        )
        stock=(
            db.query(Stock)
            .filter(Stock.code==code,*_stocklog_public_clauses())
            .first()
        )

        if not user or not stock:
            row=_ai_row_for(db, code, mode)

            if row:
                row.status="failed"
                row.error_message=(
                    "사용자 또는 종목 정보를 찾지 못했습니다."
                )
                commit_or_rollback(db)

            return

        await _run_ai_analysis(
            stock=stock,
            user=user,
            db=db,
            mode=mode,
            force=force,
        )

    except Exception as exc:
        print(
            "[ERROR] detail AI background:",
            code,
            repr(exc),
        )

    finally:
        db.close()
        _ai_detail_tasks.pop(key, None)


@app.post("/api/stocks/{code}/ai-analysis/start")
async def stock_ai_analysis_start(
    code:str,
    smart_mode:str=Query("ai"),
    force:bool=Query(False),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"ai_analysis")
    enabled=str(os.getenv("AI_ANALYST_ENABLED","true")).lower() not in {"0","false","no","off"}
    if not enabled:
        raise HTTPException(503,"StockLog AI 분석이 현재 비활성화되어 있습니다.")

    stock=_stocklog_public_stock(db,code)
    if not stock:
        raise HTTPException(404,"종목을 찾을 수 없습니다.")

    mode=str(smart_mode or "ai").lower().strip()
    if mode not in {"ai","profile","buffett","custom"}:
        mode="ai"

    key=f"{code}:{mode}"
    had_access=_has_ai_analysis_access(u,db,code,mode)
    # A member spends a daily use only when unlocking a new stock/mode, or when
    # explicitly requesting a fresh re-analysis. Reopening an unlocked cache is free.
    usage_state=_ai_usage_status(u,db)
    if (not had_access) or force:
        usage_state=_consume_ai_usage(u,db,1)
    if not had_access:
        _grant_ai_analysis_access(u,db,code,mode)

    # Inference is shared by stock/mode, not user. If another account already
    # started the same analysis, just subscribe this account to that shared job.
    existing=_ai_detail_tasks.get(key)
    if existing and not existing.done():
        return {
            "ok":True,
            "already_running":True,
            "status":"running",
            "message":(
                f"진행 중인 공용 AI 분석에 연결했습니다. 오늘 {usage_state.get('used',0)}/{usage_state.get('daily_limit',0)}회 사용했습니다."
                if not usage_state.get("unlimited") and not had_access
                else "진행 중인 공용 AI 분석에 연결했습니다."
            ),
            "ai_usage":usage_state,
        }

    row=_ai_row_for(db, code, mode)
    if not row:
        row=AiStockAnalysis(stock_code=code,mode=mode)
        db.add(row)
        commit_or_rollback(db)
        db.refresh(row)

    # Batch jobs and detail jobs share the same cache row. Avoid starting a
    # second inference when any healthy worker is already processing it.
    recently_active=bool(
        row.updated_at
        and row.updated_at>datetime.now()-timedelta(minutes=10)
    )
    if (
        not force
        and row.status in {"queued","context","running","obot_running","obot_completed","gbot_running","gbot_completed","verifying"}
        and recently_active
    ):
        return {
            "ok":True,
            "already_running":True,
            "status":row.status,
            "message":"진행 중인 공용 AI 분석에 연결했습니다.",
            "ai_usage":usage_state,
        }

    cached_payload=_ai_cache_payload(row) if row.result_json not in {"", "{}"} else None
    if (
        not force
        and row.status=="ready"
        and row.expires_at
        and row.expires_at>datetime.now()
        and row.result_json not in {"", "{}"}
        and bool(cached_payload and cached_payload.get("result"))
    ):
        return {
            "ok":True,
            "cached":True,
            "status":"ready",
            "message":(
                "최근 StockLog 분석 결과를 즉시 열었습니다."
                if had_access
                else (
                    f"AI 분석 1회를 사용해 최근 결과를 열었습니다. 오늘 {usage_state.get('used',0)}/{usage_state.get('daily_limit',0)}회 사용했습니다."
                    if not usage_state.get("unlimited")
                    else "최근 StockLog 분석 결과를 즉시 열었습니다."
                )
            ),
            "ai_usage":usage_state,
        }

    row.status="queued"
    row.error_message=""
    row.updated_at=datetime.now()
    commit_or_rollback(db)
    _ai_live_progress.pop(key,None)
    _ai_progress_update(key,"queued",{
        "phase":"queued",
        "message":"프리미엄 AI 분석을 시작할 준비를 하고 있습니다.",
    })

    task=asyncio.create_task(_detail_ai_background_worker(u.id,code,mode,force))
    _ai_detail_tasks[key]=task

    return {
        "ok":True,
        "cached":False,
        "status":"queued",
        "message":(
            f"AI 분석을 시작했습니다. 오늘 {usage_state.get('used',0)}/{usage_state.get('daily_limit',0)}회 사용했습니다."
            if not usage_state.get("unlimited") and ((not had_access) or force)
            else "AI 분석을 시작했습니다."
        ),
        "ai_usage":usage_state,
    }


@app.get("/api/stocks/{code}/ai-analysis")
async def stock_ai_analysis(
    code:str,
    smart_mode:str=Query("ai"),
    force:bool=Query(False),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"ai_analysis")
    enabled=str(os.getenv("AI_ANALYST_ENABLED","true")).lower() not in {"0","false","no","off"}
    if not enabled:
        raise HTTPException(503,"StockLog AI 분석이 현재 비활성화되어 있습니다.")

    stock=_stocklog_public_stock(db,code)
    if not stock:
        raise HTTPException(404,"종목을 찾을 수 없습니다.")

    mode=str(smart_mode or "ai").lower().strip()
    if mode not in {"ai","profile","buffett","custom"}:
        mode="ai"

    had_access=_has_ai_analysis_access(u,db,code,mode)
    if (not had_access) or force:
        _consume_ai_usage(u,db,1)
    if not had_access:
        _grant_ai_analysis_access(u,db,code,mode)

    try:
        return await _run_ai_analysis(stock=stock,user=u,db=db,mode=mode,force=force)
    except DualAnalysisUnavailable as exc:
        raise HTTPException(503,str(exc) or "StockLog Gbot 분석을 완료하지 못했습니다.") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(504,"AI 분석 제한시간을 초과했습니다. 잠시 후 다시 시도해주세요.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502,"AI 분석 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.") from exc
    except Exception as exc:
        raise HTTPException(500,"AI 분석을 완료하지 못했습니다. 서버 로그를 확인해주세요.") from exc


async def _ai_batch_worker(
    user_id,
    codes,
    mode,
):
    global _ai_batch_state

    async with _ai_batch_lock:
        _ai_batch_state={
            "running":True,
            "total":len(codes),
            "completed":0,
            "current_code":"",
            "failed":0,
            "started_at":
                datetime.now().isoformat(),
            "finished_at":None,
            "message":"AI 분석을 순차 처리하고 있습니다.",
        }

        try:
            for code in codes:
                _ai_batch_state[
                    "current_code"
                ]=code

                db=SessionLocal()

                try:
                    user=(
                        db.query(User)
                        .filter(
                            User.id==user_id,
                            User.is_active==True,
                        )
                        .first()
                    )

                    stock=(
                        db.query(Stock)
                        .filter(Stock.code==code,*_stocklog_public_clauses())
                        .first()
                    )

                    if not user or not stock:
                        _ai_batch_state[
                            "failed"
                        ]+=1
                        continue

                    try:
                        await _run_ai_analysis(
                            stock=stock,
                            user=user,
                            db=db,
                            mode=mode,
                            force=False,
                        )
                    except Exception as exc:
                        _ai_batch_state[
                            "failed"
                        ]+=1
                        print(
                            "[WARN] AI batch item:",
                            code,
                            repr(exc),
                        )

                finally:
                    db.close()

                _ai_batch_state[
                    "completed"
                ]+=1

        finally:
            _ai_batch_state[
                "running"
            ]=False
            _ai_batch_state[
                "current_code"
            ]=""
            _ai_batch_state[
                "finished_at"
            ]=datetime.now().isoformat()
            _ai_batch_state[
                "message"
            ]="AI 분석 큐 처리가 완료되었습니다."


@app.post("/api/ai/batch")
async def ai_batch_start(
    codes:str=Query(""),
    mode:str=Query("ai"),
    u:User=Depends(current_user),
    db:Session=Depends(get_db),
):
    _require_feature(u,db,"ai_analysis")
    if _ai_batch_state.get("running"):
        raise HTTPException(409,"이미 AI 분석 큐가 실행 중입니다.")

    clean_codes=[
        code.strip()
        for code in codes.split(",")
        if re.fullmatch(r"\d{6}",code.strip())
    ]
    clean_codes=list(dict.fromkeys(clean_codes))[:_AI_BATCH_LIMIT]
    eligible_codes=_stocklog_public_code_set(db,clean_codes)
    clean_codes=[code for code in clean_codes if code in eligible_codes]
    if not clean_codes:
        raise HTTPException(400,"StockLog 분석 대상 종목이 없습니다.")

    clean_mode=str(mode or "ai").lower().strip()
    if clean_mode not in {"ai","buffett","custom"}:
        clean_mode="ai"

    if _ai_usage_unlimited(u,db):
        process_codes=clean_codes
        usage_state=_ai_usage_status(u,db)
    else:
        already=_granted_ai_codes(u,db,clean_codes,clean_mode)
        new_codes=[code for code in clean_codes if code not in already]
        usage_state=_ai_usage_status(u,db)
        remaining=max(0,int(usage_state.get("remaining") or 0))
        if not new_codes:
            return {
                "ok":True,
                "count":0,
                "message":"선택된 추천 종목은 이미 이 계정에서 AI 열람 권한을 가지고 있습니다.",
                "ai_usage":usage_state,
            }
        if remaining<1:
            raise HTTPException(429,f"오늘 AI 분석 {usage_state.get('daily_limit',0)}회를 모두 사용했습니다. 내일 00:00에 다시 이용할 수 있습니다.")
        process_codes=new_codes[:remaining]
        usage_state=_consume_ai_usage(u,db,len(process_codes))
        for code in process_codes:
            _grant_ai_analysis_access(u,db,code,clean_mode)

    asyncio.create_task(_ai_batch_worker(u.id,process_codes,clean_mode))
    return {
        "ok":True,
        "count":len(process_codes),
        "message":(
            f"{len(process_codes)}개 종목의 AI 분석/캐시 열람을 순차 처리합니다."
            + (f" (오늘 {usage_state.get('used',0)}/{usage_state.get('daily_limit',0)}회 사용)" if not usage_state.get("unlimited") else "")
        ),
        "ai_usage":usage_state,
    }


@app.get("/api/ai/batch/status")
def ai_batch_status(
    _:User=Depends(current_user),
):
    return dict(
        _ai_batch_state
    )


@app.get("/api/stocks/{code}/detail")
async def stock_detail(
    code: str,
    refresh_news: bool = Query(False),
    smart_mode: str = Query("ai"),
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    st = _stocklog_public_stock(db,code)
    if not st:
        raise HTTPException(404, "종목을 찾을 수 없습니다.")

    # Detail pages must not silently show an empty supply/demand card merely
    # because a prior administrator bulk sync used a top-N universe.  Repair
    # completely missing DB coverage for this exact stock before rendering.
    flow_backfill_meta=await _ensure_stock_flow_for_ai(db,st)

    warnings = []
    data_status = {
        "price": {"ok": False, "message": ""},
        "valuation": {"ok": False, "message": ""},
        "financials": {"ok": False, "message": ""},
        "reports": {"ok": False, "message": ""},
    }

    # ------------------------------------------------------
    # 1) 실제 일봉
    # ------------------------------------------------------
    chart = _build_real_chart(code, db, limit=500)
    sync_meta = {
        "stock_source": "mysql-real-market-data",
        "kospi_source": "mysql-real-market-data",
        "warnings": warnings,
    }

    if not chart:
        try:
            sync_meta = await _ensure_real_chart(
                u,
                st,
                db,
                force=False,
            )
            chart = _build_real_chart(code, db, limit=500)
        except Exception as exc:
            warnings.append(f"실제 일봉 보강 실패: {exc}")

    if chart:
        data_status["price"] = {
            "ok": True,
            "message": f"실제 일봉 {len(chart)}개",
        }
    else:
        data_status["price"] = {
            "ok": False,
            "message": "실제 일봉 데이터가 아직 없습니다.",
        }

    # ------------------------------------------------------
    # 2) OpenDART 재무 + 주식수 + 밸류에이션
    # ------------------------------------------------------
    raw_fins = financials_from_db(
        st.code,
        db,
        limit=4,
    )

    dart_key = (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip()

    needs_comparison_refresh = bool(raw_fins) and any(
        row.get("comparison_income_period") is None
        for row in raw_fins[:1]
    )

    if (
        not raw_fins
        or st.valuation_calculated_at is None
        or needs_comparison_refresh
    ) and dart_key:
        try:
            if not st.corp_code:
                await sync_dart_corp_codes(
                    db
                )
                db.refresh(st)

            if st.corp_code:
                # financials_from_db/db.refresh above opened a read transaction.
                # Release it and let provider credential lookup use a short-lived
                # isolated session before OpenDART network I/O.
                commit_or_rollback(db)
                fin_rows = await fetch_dart_financials(
                    st,
                    None,
                )

                if fin_rows:
                    upsert_financials(
                        st.code,
                        fin_rows,
                        db,
                    )

                    share_info = await fetch_dart_share_count(
                        st,
                        fin_rows,
                        db=None,
                    )

                    valuation = calculate_dart_valuation(
                        st,
                        fin_rows,
                        share_info,
                    )

                    if not apply_dart_valuation(
                        st,
                        valuation,
                    ):
                        warnings.append(
                            valuation.get(
                                "reason",
                                "밸류에이션 계산 실패",
                            )
                        )

                    dividend = await fetch_dart_dividend_yield(
                        st,
                        fin_rows,
                        db=None,
                    )
                    if dividend and dividend.get("yield") is not None:
                        st.dividend_yield = dividend["yield"]

                    st.dart_financials_updated_at = (
                        datetime.now()
                    )
                    st.category = classify_stock(
                        st
                    )
                    st.score = compute_score(
                        st
                    )[0]
                    st.updated_at = datetime.now()
                    commit_or_rollback(db)
                    db.refresh(st)

                    raw_fins = financials_from_db(
                        st.code,
                        db,
                        limit=4,
                    )

        except Exception as exc:
            db.rollback()
            warnings.append(
                "OpenDART 재무/밸류에이션 "
                f"보강 실패: {exc}"
            )

    valuation_available = any(
        value is not None
        for value in (
            st.per,
            st.pbr,
            st.eps,
            st.bps,
            st.roe,
        )
    )

    if valuation_available:
        data_status["valuation"] = {
            "ok": True,
            "message": (
                "OpenDART 재무·주식수·배당 + "
                "키움 현재가 계산값"
            ),
        }
    elif not dart_key:
        data_status["valuation"] = {
            "ok": False,
            "message": (
                "OpenDART API 키가 없어 "
                "EPS/BPS/ROE/PER/PBR을 계산할 수 없습니다."
            ),
        }
    else:
        data_status["valuation"] = {
            "ok": False,
            "message": (
                "OpenDART 재무 또는 주식수 부족으로 "
                "밸류에이션을 계산하지 못했습니다."
            ),
        }

    if raw_fins:
        data_status["financials"] = {
            "ok": True,
            "message": f"OpenDART 실제 재무 {len(raw_fins)}개 기간",
        }
    elif not dart_key:
        data_status["financials"] = {
            "ok": False,
            "message": "OpenDART API 키가 없어 사업성과/재무 데이터를 가져올 수 없습니다.",
        }
    elif not st.corp_code:
        data_status["financials"] = {
            "ok": False,
            "message": "해당 종목의 OpenDART corp_code를 찾지 못했습니다.",
        }
    else:
        data_status["financials"] = {
            "ok": False,
            "message": "OpenDART에서 최근 재무제표 결과가 없습니다.",
        }

    fins = enrich_financial_growth(raw_fins)

    # ------------------------------------------------------
    # 4) News
    # ------------------------------------------------------
    try:
        news_result = await get_stock_news(
            st,
            db,
            force=refresh_news,
            ttl_seconds=int(
                os.getenv(
                    "NEWS_CACHE_SECONDS",
                    "3600",
                )
            ),
            display=int(
                os.getenv(
                    "NEWS_DISPLAY_COUNT",
                    "20",
                )
            ),
        )
    except Exception as exc:
        try:
            news_result = await get_stock_news(
                st,
                db,
                force=False,
                ttl_seconds=10**9,
            )
        except Exception:
            news_result = {
                "items": [],
                "summary": {},
                "source": "unavailable",
            }
        news_result["warning"] = (
            f"최신 뉴스 조회 실패: {exc}"
        )

    news = news_result.get("items", [])

    # ------------------------------------------------------
    # 5) Broker reports: recent links only
    # ------------------------------------------------------
    try:
        report_result = await get_broker_reports(
            st,
            db=db,
            force=refresh_news,
            limit=int(
                os.getenv(
                    "BROKER_REPORT_COUNT",
                    "5",
                )
            ),
        )
    except Exception as exc:
        report_result = {
            "items": [],
            "summary": {"overall":"neutral","average_score":0,"total":0,"positive":0,"neutral":0,"negative":0,"positive_points":[],"negative_points":[]},
            "source": "naver-finance-research",
            "warning": f"증권사 리포트 조회 실패: {exc}",
        }

    reports = report_result.get("items", [])
    data_status["reports"] = {
        "ok": bool(reports),
        "message": (
            f"최근 증권사 리포트 {len(reports)}건"
            if reports
            else report_result.get(
                "warning",
                "최근 리포트가 없습니다.",
            )
        ),
    }

    # ------------------------------------------------------
    # 6) Official OpenDART disclosures
    # ------------------------------------------------------
    try:
        disclosure_result = await get_stock_disclosures(
            st, db, force=False,
            days=int(os.getenv("DISCLOSURE_LOOKBACK_DAYS", "180")),
            limit=int(os.getenv("DISCLOSURE_DISPLAY_COUNT", "20")),
        )
    except Exception as exc:
        disclosure_result={"items":[],"important_items":[],"source":"unavailable","warning":f"공시 조회 실패: {exc}"}
    disclosures=disclosure_result.get("items") or []
    data_status["disclosures"]={
        "ok":bool(disclosures),
        "message":f"최근 공식 공시 {len(disclosures)}건" if disclosures else (disclosure_result.get("warning") or "최근 공시가 없습니다."),
    }

    analysis = build_deep_analysis(
        st,
        raw_fins,
        news,
    )

    detail_mode=str(
        smart_mode or "ai"
    ).lower().strip()
    if detail_mode not in {
        "ai",
        "profile",
        "buffett",
        "custom",
    }:
        detail_mode="ai"

    detail_formula=None
    if detail_mode == "custom":
        formula_obj=(
            db.query(SmartFormula)
            .filter(
                SmartFormula.user_id
                == u.id
            )
            .first()
        )
        detail_formula=_custom_formula_dict(
            formula_obj
        )

    detail_profile_scores=None
    detail_profile_code=""
    if detail_mode=="profile":
        detail_profile_row=(db.query(InvestmentProfile).filter(InvestmentProfile.user_id==u.id).first())
        detail_profile_payload=_investment_profile_payload(detail_profile_row)
        detail_profile_scores=(detail_profile_payload or {}).get("scores") or {}
        detail_profile_code=(detail_profile_payload or {}).get("result_code") or ""

    score_ctx=_smart_score_context(
        st,
        detail_mode,
        detail_formula,
        detail_profile_scores,
        detail_profile_code,
    )
    analysis["score"]=score_ctx["score"]
    analysis["recommendation"]=(
        _recommendation_label_from_score(
            score_ctx["score"]
        )
    )
    analysis["reasons"]=(
        score_ctx["reasons"]
        or analysis.get("reasons",[])
    )
    analysis["score_mode"]=score_ctx["mode"]
    analysis["score_type"]=score_ctx["type"]
    analysis["summary"]=_smart_score_summary(score_ctx)
    analysis["score_consistency"]={"single_source":True,"mode":score_ctx["mode"],"type":score_ctx["type"],"score":score_ctx["score"]}

    news=sorted(
        news or [],
        key=lambda x:(
            x.get("published_at") or ""
            if isinstance(x,dict)
            else ""
        ),
        reverse=True,
    )

    combined_themes = _stock_theme_items(
        db,
        st.code,
    )

    market_themes = _stock_theme_items(
        db,
        st.code,
        sources=["infostock"],
    )

    kiwoom_themes = _stock_theme_items(
        db,
        st.code,
        sources=["kiwoom"],
    )

    related_themes = _infer_related_themes(
        db,
        news,
        reports,
        official_theme_codes=[
            x["theme_code"]
            for x in combined_themes
        ],
        limit=5,
    )

    investor_flow=_stock_detail_flow_payload(db,st,period=7)
    flow_backfill_status=str((flow_backfill_meta or {}).get("status") or "")
    data_status["investor_flow"]={
        "ok":bool(investor_flow.get("available")),
        "message": (
            f"최근 수급 {int(investor_flow.get('days') or 0)}거래일"
            if investor_flow.get("available")
            else "저장된 수급 데이터가 없습니다. 관리자 동기화/보충수집 진단 TXT를 확인하세요."
        ),
        "backfill_status":flow_backfill_status,
        "diagnostic_log":(flow_backfill_meta or {}).get("diagnostic_log"),
    }

    return {
        "stock": {
            "code": st.code,
            "name": st.name,
            "market": st.market,
            "sector": st.sector,
            "industry_name": st.industry_name,
            "industry_source": st.industry_source,
            "primary_theme": (_stock_taxonomy_payload(st).get("primary") or st.investment_theme or st.primary_theme),
            "primary_business": st.primary_business,
            "investment_theme": (_stock_taxonomy_payload(st).get("primary") or st.investment_theme),
            "investment_themes_json": st.investment_themes_json,
            "theme_group": _stock_taxonomy_payload(st).get("primary"),
            "theme_groups": _stock_taxonomy_payload(st).get("groups"),
            "theme_subthemes": _stock_taxonomy_payload(st).get("subthemes"),
            "theme_engine_version": _stock_taxonomy_payload(st).get("engine_version"),
            "classification_confidence": st.classification_confidence,
            "classification_reason": st.classification_reason,
            "classification_source_summary": st.classification_source_summary,
            "themes": combined_themes,
            "market_themes": market_themes,
            "kiwoom_themes": kiwoom_themes,
            "theme_fallback": _stock_theme_fallback(st),
            "display_category": (
                _stock_taxonomy_payload(st).get("primary")
                or st.investment_theme
                or st.primary_theme
                or st.industry_name
                or (
                    st.sector
                    if st.sector
                    and st.sector != "기타"
                    else st.category
                )
            ),
            "category": st.category,
            "price": st.price,
            "change_rate": st.change_rate,
            "market_cap": st.market_cap,
            "per": st.per,
            "pbr": st.pbr,
            "eps": st.eps,
            "bps": st.bps,
            "shares_outstanding": st.shares_outstanding,
            "roe": st.roe,
            "revenue_growth": st.revenue_growth,
            "operating_margin": st.operating_margin,
            "dividend_yield": st.dividend_yield,
            "momentum_20d": st.momentum_20d,
            "volatility": st.volatility,
        },
        "chart": chart or [],
        "investor_flow": investor_flow,
        "reports": reports,
        "report_summary": report_result.get("summary", {}),
        "disclosures": disclosures,
        "important_disclosures": disclosure_result.get("important_items", []),
        "themes": combined_themes,
        "market_themes": market_themes,
        "kiwoom_themes": kiwoom_themes,
        "related_themes": related_themes,
        "data_status": data_status,
        "_meta": {
            "source": "real-data-only",
            "demo": False,
            **sync_meta,
            "news": {
                "source": news_result.get("source"),
                "fetched": news_result.get(
                    "fetched",
                    False,
                ),
                "last_fetched_at": news_result.get(
                    "last_fetched_at"
                ),
                "warning": news_result.get(
                    "warning"
                ),
                "summary": news_result.get(
                    "summary",
                    {},
                ),
                "important_count": len(news_result.get("important_items") or []),
            },
            "reports": {
                "source": report_result.get("source"),
                "warning": report_result.get("warning"),
                "last_fetched_at": report_result.get("last_fetched_at"),
            },
            "disclosures": {
                "source": disclosure_result.get("source"),
                "warning": disclosure_result.get("warning"),
                "last_fetched_at": disclosure_result.get("last_fetched_at"),
            },
            "valuation_source": "opendart-financials+shares+kiwoom-price",
            "financial_source": "mysql-opendart-cache",
        },
        "news": news,
        "important_news": news_result.get("important_items", []),
        "news_summary": news_result.get(
            "summary",
            {},
        ),
        "financials": fins,
        "analysis": analysis,
    }

@app.post("/api/stocks/{code}/news/refresh")
async def refresh_stock_news(code:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
    st=_stocklog_public_stock(db,code)
    if not st:raise HTTPException(404,"종목을 찾을 수 없습니다.")
    try:r=await get_stock_news(st,db,force=True,display=int(os.getenv("NEWS_DISPLAY_COUNT","20")))
    except Exception as ex:raise HTTPException(502,f"뉴스 새로고침 실패: {ex}")
    st.score=compute_score(st,r.get("items",[]))[0];st.category=classify_stock(st);st.updated_at=datetime.now();commit_or_rollback(db);return r

THEME_SYNC_KEY="theme_sync"


def _theme_sync_job(db: Session):
    job=(
        db.query(FullMarketSyncState)
        .filter(
            FullMarketSyncState.key
            == THEME_SYNC_KEY
        )
        .first()
    )

    if not job:
        job=FullMarketSyncState(
            key=THEME_SYNC_KEY,
            job_type="themes",
        )
        db.add(job)
        commit_or_rollback(db)
        db.refresh(job)

    return job


def _theme_sync_json(job):
    try:
        failures=json.loads(
            job.failures_json
            or "[]"
        )
    except Exception:
        failures=[]

    try:
        provider_status=json.loads(
            job.provider_status_json
            or "{}"
        )
    except Exception:
        provider_status={}

    return {
        "running":bool(job.running),
        "phase":job.phase,
        "stage_label":job.stage_label or "",
        "item_total":job.item_total,
        "item_completed":job.item_completed,
        "success":job.success,
        "failed":job.failed,
        "progress":round(
            float(
                job.progress_value
                or 0
            ),
            2,
        ),
        "current_code":job.current_code,
        "current_name":job.current_name,
        "eta_seconds":round(
            float(
                job.eta_seconds
                or 0
            ),
            1,
        ),
        "message":job.message,
        "last_error":job.last_error,
        "failures":failures[-30:],
        "provider_status":provider_status,
        "run_id":str(
            provider_status.get("run_id")
            or ""
        ),
        "started_at":(
            job.started_at.isoformat()
            if job.started_at
            else None
        ),
        "updated_at":(
            job.updated_at.isoformat()
            if job.updated_at
            else None
        ),
        "finished_at":(
            job.finished_at.isoformat()
            if job.finished_at
            else None
        ),
    }


def _refresh_primary_themes(db: Session):
    all_active=db.query(Stock).filter(Stock.is_active == True).all()
    for stock in all_active:
        stock.primary_theme=None
    flush_or_rollback(db)

    stocks=(
        db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .all()
    )

    rows=(
        db.query(
            StockTheme,
            Theme,
        )
        .join(
            Theme,
            Theme.theme_code
            == StockTheme.theme_code,
        )
        .filter(
            Theme.is_active == True
        )
        .order_by(
            StockTheme.stock_code.asc(),
            case(
                (StockTheme.source == "infostock", 0),
                (StockTheme.source == "kiwoom", 1),
                else_=9,
            ),
            Theme.change_rate.desc(),
            Theme.name.asc(),
        )
        .all()
    )

    stock_map={
        stock.code:stock
        for stock in stocks
    }

    selected=set()

    for relation, theme in rows:
        if relation.stock_code in selected:
            continue

        stock=stock_map.get(
            relation.stock_code
        )

        if not stock:
            continue

        stock.primary_theme=theme.name
        selected.add(
            relation.stock_code
        )

    commit_or_rollback(db)


def _theme_sync_provider_from_row(row):
    try:
        return json.loads(
            row.provider_status_json
            or "{}"
        )
    except Exception:
        return {}


def _theme_sync_stop_state(
    expected_run_id: str | None = None,
):
    """
    DB-backed cancellation state.

    A worker is cancelled when either:
    - its run_id is no longer the DB's active run_id, or
    - DB provider stop_requested is true.

    This means cancellation does NOT depend on the worker being able to
    persist a final `phase=cancelled` acknowledgement.
    """
    db=SessionLocal()

    try:
        row=(
            db.query(
                FullMarketSyncState.running,
                FullMarketSyncState.phase,
                FullMarketSyncState.provider_status_json,
            )
            .filter(
                FullMarketSyncState.key
                == THEME_SYNC_KEY
            )
            .first()
        )

        if not row:
            return {
                "requested":False,
                "running":False,
                "phase":"idle",
                "run_id":"",
                "run_mismatch":False,
                "restart_after_epoch":0.0,
            }

        provider=_theme_sync_provider_from_row(
            row
        )

        current_run_id=str(
            provider.get("run_id")
            or ""
        )

        run_mismatch=(
            bool(expected_run_id)
            and bool(current_run_id)
            and current_run_id
            != str(expected_run_id)
        )

        requested=(
            run_mismatch
            or bool(
                provider.get(
                    "stop_requested"
                )
            )
            or str(row.phase or "")
            == "stop_requested"
        )

        try:
            restart_after_epoch=float(
                provider.get(
                    "restart_after_epoch"
                )
                or 0
            )
        except Exception:
            restart_after_epoch=0.0

        return {
            "requested":
                requested,
            "running":
                bool(row.running),
            "phase":
                str(row.phase or ""),
            "run_id":
                current_run_id,
            "run_mismatch":
                run_mismatch,
            "restart_after_epoch":
                restart_after_epoch,
        }

    finally:
        db.close()


def _raise_if_theme_sync_stop_requested(
    expected_run_id: str | None = None,
):
    state=_theme_sync_stop_state(
        expected_run_id
    )

    if state["requested"]:
        raise asyncio.CancelledError()


def _write_theme_sync_stop_request():
    """
    Hard logical cancel.

    Invalidate the active run_id immediately. Any old worker that wakes
    later sees a run-id mismatch and loses permission to write progress or
    replace theme relations.

    UI status is immediately `cancelled`; it no longer waits forever for a
    worker acknowledgement. A short cooldown prevents a new Kiwoom sync
    from overlapping the old in-flight request.
    """
    db=SessionLocal()

    try:
        job=(
            db.query(
                FullMarketSyncState
            )
            .filter(
                FullMarketSyncState.key
                == THEME_SYNC_KEY
            )
            .first()
        )

        if not job:
            return {
                "was_running":False,
                "already_cancelled":True,
                "cancelled_run_id":"",
                "restart_after_epoch":0.0,
            }

        provider=_theme_sync_provider_from_row(
            job
        )

        old_run_id=str(
            provider.get("run_id")
            or ""
        )

        already_cancelled=(
            str(job.phase or "")
            == "cancelled"
            and not bool(job.running)
        )

        was_running=(
            bool(job.running)
            or str(job.phase or "")
            in (
                "themes",
                "theme-first",
                "theme-retry",
                "starting",
                "stop_requested",
            )
        )

        now_epoch=time.time()
        restart_after=(
            now_epoch + 12.0
            if was_running
            else now_epoch
        )

        # Critical: invalidate the old worker generation immediately.
        cancelled_token=(
            "cancel-"
            + str(
                time.time_ns()
            )
        )

        provider.update(
            {
                "run_id":
                    cancelled_token,
                "cancelled_run_id":
                    old_run_id,
                "stop_requested":
                    False,
                "current_status":
                    "cancelled",
                "current_status_message":
                    "관리자 요청으로 테마 동기화를 종료했습니다.",
                "restart_after_epoch":
                    restart_after,
            }
        )

        job.provider_status_json=json.dumps(
            provider,
            ensure_ascii=False,
        )
        job.running=False
        job.phase="cancelled"
        job.stage_label="중지됨"
        job.eta_seconds=0
        job.current_code=""
        job.current_name=""
        job.message=(
            "테마 동기화를 중지했습니다. "
            "완료된 테마 데이터는 유지됩니다."
        )
        job.finished_at=datetime.now()
        commit_or_rollback(db)

        return {
            "was_running":
                was_running,
            "already_cancelled":
                already_cancelled,
            "cancelled_run_id":
                old_run_id,
            "restart_after_epoch":
                restart_after,
        }

    finally:
        db.close()


def _reconcile_theme_sync_state_on_boot():
    """
    A backend restart guarantees all prior in-process asyncio theme tasks
    are gone. Convert legacy/stale stop_requested records to cancelled so
    the Admin page never remains permanently locked after a restart.
    """
    db=SessionLocal()

    try:
        job=(
            db.query(
                FullMarketSyncState
            )
            .filter(
                FullMarketSyncState.key
                == THEME_SYNC_KEY
            )
            .first()
        )

        if not job:
            return

        provider=_theme_sync_provider_from_row(
            job
        )

        stale=(
            str(job.phase or "")
            == "stop_requested"
            or bool(
                provider.get(
                    "stop_requested"
                )
            )
            or (
                bool(job.running)
                and str(job.phase or "")
                in (
                    "themes",
                    "theme-first",
                    "theme-retry",
                    "starting",
                )
            )
        )

        if not stale:
            return

        provider.update(
            {
                "run_id":
                    "boot-cancel-"
                    + str(
                        time.time_ns()
                    ),
                "stop_requested":
                    False,
                "current_status":
                    "cancelled",
                "current_status_message":
                    "백엔드 재시작으로 이전 테마 작업 종료를 확인했습니다.",
                "restart_after_epoch":
                    0,
            }
        )

        job.provider_status_json=json.dumps(
            provider,
            ensure_ascii=False,
        )
        job.running=False
        job.phase="cancelled"
        job.stage_label="중지됨"
        job.eta_seconds=0
        job.current_code=""
        job.current_name=""
        job.message=(
            "이전 테마 동기화 작업은 "
            "백엔드 재시작과 함께 종료되었습니다."
        )
        job.finished_at=datetime.now()
        commit_or_rollback(db)

    except Exception as exc:
        db.rollback()
        print(
            "[WARN] theme sync boot reconcile failed:",
            repr(exc),
        )

    finally:
        db.close()


_reconcile_theme_sync_state_on_boot()


def _legacy_theme_insert_columns():
    """Return legacy required theme columns that current ORM does not own.

    Some installations predate the current Theme model and still have
    NOT NULL columns such as rising_count/falling_count without defaults.
    The startup migration normally fixes them; this runtime fallback keeps
    theme synchronization working even when ALTER TABLE permission is absent.
    """
    supported={
        "theme_name":"text",
        "rising_count":"int",
        "falling_count":"int",
        "flat_count":"int",
        "unchanged_count":"int",
    }
    try:
        info=_mysql_table_column_info("themes")
    except Exception:
        return {}
    result={}
    for name,kind in supported.items():
        row=info.get(name)
        if not row:
            continue
        required=(
            str(row.get("null") or "").upper()!="YES"
            and row.get("default") is None
            and "auto_increment" not in str(row.get("extra") or "").lower()
        )
        if required:
            result[name]=kind
    return result


def _insert_theme_legacy_safe(db, theme_code, theme_name, change_rate):
    """Insert/update one Theme while satisfying surviving legacy columns."""
    legacy=_legacy_theme_insert_columns()
    columns=["theme_code","name","change_rate","stock_count","is_active","updated_at"]
    params={
        "theme_code":theme_code,
        "name":theme_name,
        "change_rate":change_rate,
        "stock_count":0,
        "is_active":1,
        "updated_at":datetime.now(),
    }
    if "theme_name" in legacy:
        columns.append("theme_name")
        params["theme_name"]=theme_name
    for name in ("rising_count","falling_count","flat_count","unchanged_count"):
        if name in legacy:
            columns.append(name)
            params[name]=0
    quoted=",".join(f"`{name}`" for name in columns)
    values=",".join(f":{name}" for name in columns)
    updates=[
        "`name`=VALUES(`name`)",
        "`change_rate`=VALUES(`change_rate`)",
        "`is_active`=1",
        "`updated_at`=VALUES(`updated_at`)",
    ]
    if "theme_name" in columns:
        updates.append("`theme_name`=VALUES(`theme_name`)")
    db.execute(
        text(
            f"INSERT INTO `themes` ({quoted}) VALUES ({values}) "
            "ON DUPLICATE KEY UPDATE "+",".join(updates)
        ),
        params,
    )


def _persist_theme_members_sync(
    item: dict,
    members: list[dict],
    source: str = "kiwoom",
):
    db=SessionLocal()

    theme_code=str(
        item.get("theme_code")
        or ""
    )
    theme_name=str(
        item.get("theme_name")
        or ""
    )

    started=time.monotonic()

    try:
        db.execute(
            text(
                "SET SESSION innodb_lock_wait_timeout = 4"
            )
        )

        try:
            db.execute(
                text(
                    "SET SESSION lock_wait_timeout = 4"
                )
            )
        except Exception:
            db.rollback()
            db.execute(
                text(
                    "SET SESSION innodb_lock_wait_timeout = 4"
                )
            )

        theme=(
            db.query(Theme)
            .filter(
                Theme.theme_code
                == theme_code
            )
            .first()
        )
        preserve_fallback_canonical=False
        if theme and not _theme_canonical_column_available():
            previous_relation=(
                db.query(StockTheme.theme_name)
                .filter(StockTheme.theme_code==theme_code)
                .first()
            )
            previous_raw=str(previous_relation[0] or "").strip() if previous_relation else ""
            current_display=str(theme.name or "").strip()
            preserve_fallback_canonical=bool(previous_raw and current_display and previous_raw!=current_display)

        if not theme:
            legacy_required=_legacy_theme_insert_columns()
            if legacy_required:
                # Runtime fallback for upgraded databases whose legacy NOT NULL
                # columns could not be ALTERed at startup.  This covers both
                # theme_name and old breadth counters such as rising_count.
                _insert_theme_legacy_safe(
                    db,
                    theme_code,
                    theme_name,
                    item.get("change_rate"),
                )
                theme=(
                    db.query(Theme)
                    .filter(Theme.theme_code==theme_code)
                    .first()
                )
            else:
                theme=Theme(
                    theme_code=theme_code,
                    name=theme_name,
                )
                db.add(theme)

        if not preserve_fallback_canonical:
            theme.name=theme_name
        theme.change_rate=item.get(
            "change_rate"
        )
        theme.is_active=True
        theme.updated_at=datetime.now()

        (
            db.query(StockTheme)
            .filter(
                StockTheme.theme_code
                == theme_code
            )
            .delete(
                synchronize_session=False
            )
        )

        unique={}

        for member in members or []:
            code=str(
                member.get("code")
                or ""
            )

            if not re.fullmatch(
                r"\d{6}",
                code,
            ):
                continue

            unique[code]=member

        eligible_codes=_stocklog_public_code_set(db,list(unique.keys()))
        unique={code:member for code,member in unique.items() if code in eligible_codes}

        rows=[
            StockTheme(
                stock_code=code,
                theme_code=theme_code,
                theme_name=theme_name,
                source=source,
            )
            for code in unique
        ]

        if rows:
            db.add_all(
                rows
            )

        theme.stock_count=len(
            unique
        )

        commit_or_rollback(db)

        return {
            "ok":True,
            "theme_code":
                theme_code,
            "member_codes":
                list(unique.keys()),
            "member_count":
                len(unique),
            "elapsed_seconds":
                round(
                    time.monotonic()
                    - started,
                    3,
                ),
        }

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass

        return {
            "ok":False,
            "theme_code":
                theme_code,
            "member_codes":[],
            "member_count":0,
            "elapsed_seconds":
                round(
                    time.monotonic()
                    - started,
                    3,
                ),
            "error":
                _sync_error_text(exc),
        }

    finally:
        db.close()


async def _persist_theme_members(
    item: dict,
    members: list[dict],
    source: str = "kiwoom",
):
    return await asyncio.to_thread(
        _persist_theme_members_sync,
        item,
        members,
        source,
    )


def _classify_theme_sync_error(error: str | None) -> str:
    """Classify per-theme failures for retry / operator UX.

    deterministic: a theme is likely empty/deprecated and can eventually be
    skipped for a while. transient: network/rate/provider issues worth retrying.
    unknown: keep as warning without blocking the unified sync.
    """
    msg=str(error or "").strip().lower()
    deterministic_tokens=(
        "구성종목 없음","조회 결과가 없습니다","조회 결과 없음",
        "데이터 없음","no data","not found","존재하지",
        "invalid theme","deprecated","empty theme","ignorable:",
    )
    transient_tokens=(
        "429","rate limit","too many","timeout","timed out",
        "temporar","connection","502","503","504","5xx",
    )
    if any(x in msg for x in deterministic_tokens):
        return "ignorable"
    if any(x in msg for x in transient_tokens):
        return "transient"
    return "unknown"


def _theme_ignore_registry(provider: dict | None) -> dict:
    raw=(provider or {}).get("ignored_themes") or {}
    return raw if isinstance(raw,dict) else {}


def _theme_is_temporarily_ignored(registry: dict, code: str) -> bool:
    entry=registry.get(str(code)) or {}
    until=str(entry.get("ignore_until") or "")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.now()
    except Exception:
        return False


async def _run_theme_sync(
    admin_id: int,
    run_id: str,
):
    async with _theme_sync_lock:
        db=SessionLocal()
        job=None
        started=time.monotonic()

        try:
            _require_theme_schema_ready()
            _raise_if_theme_sync_stop_requested(run_id)
            job=_theme_sync_job(db)
            previous_provider=_theme_sync_provider_from_row(job)
            ignore_registry=_theme_ignore_registry(previous_provider)

            job.running=True
            job.job_type="themes"
            job.phase="themes"
            job.stage_label="테마 목록 조회"
            job.item_total=0
            job.item_completed=0
            job.progress_value=0
            job.success=0
            job.failed=0
            job.current_code=""
            job.current_name=""
            job.current_market=""
            job.eta_seconds=0
            job.message="키움 ka90001 전체 테마 조회 중"
            job.failures_json="[]"
            job.provider_status_json=json.dumps(
                {
                    "theme_group_pages":0,
                    "theme_member_pages":0,
                    "theme_count":0,
                    "theme_links":0,
                    "unique_member_stocks":0,
                    "current_page":0,
                    "current_status":"starting",
                    "current_attempt":1,
                    "current_pass":"theme-list",
                    "current_started_at":datetime.now().isoformat(),
                    "retry_queue":0,
                    "retry_completed":0,
                    "stop_requested":False,
                    "run_id":run_id,
                    "restart_after_epoch":0,
                },
                ensure_ascii=False,
            )
            job.last_error=""
            job.requested_by_user_id=admin_id
            job.started_at=datetime.now()
            job.finished_at=None
            commit_or_rollback(db)

            admin=(
                db.query(User)
                .filter(User.id==admin_id)
                .first()
            )
            if not admin:
                raise RuntimeError("관리자 계정을 찾지 못했습니다.")

            _,cli=client_for(admin,db)
            # Credential SELECT must not stay checked out while Kiwoom waits.
            commit_or_rollback(db)
            await cli.issue_token()

            async def group_progress(event):
                _raise_if_theme_sync_stop_requested(run_id)

                if event.get("silent"):
                    return

                try:
                    provider=json.loads(job.provider_status_json or "{}")
                except Exception:
                    provider={}
                provider.update({
                    "current_page":int(event.get("page") or 0),
                    "current_status":event.get("status") or "requesting",
                    "current_status_message":event.get("message") or "",
                    "current_pass":"theme-list",
                    "current_attempt":1,
                })
                job.provider_status_json=json.dumps(provider,ensure_ascii=False)
                job.message=event.get("message") or job.message
                _raise_if_theme_sync_stop_requested(run_id)
                commit_or_rollback(db)

            groups=await cli.theme_groups(progress_cb=group_progress)
            _raise_if_theme_sync_stop_requested(run_id)

            if not groups:
                raise RuntimeError("키움 테마 전체 연속조회 결과가 없습니다.")

            group_pages=int(getattr(cli,"last_theme_group_pages",1) or 1)
            seen_theme_codes={str(x["theme_code"]) for x in groups if x.get("theme_code")}

            provider={
                "theme_group_pages":group_pages,
                "theme_member_pages":0,
                "theme_count":len(groups),
                "theme_links":0,
                "unique_member_stocks":0,
                "current_page":0,
                "current_status":"ready",
                "current_status_message":"1차 테마 수집 시작",
                "current_attempt":1,
                "current_pass":"first",
                "current_started_at":datetime.now().isoformat(),
                "retry_queue":0,
                "retry_completed":0,
                "ignored_themes":ignore_registry,
                "ignored_skipped":0,
                "warning_count":0,
                "stop_requested":False,
                "run_id":run_id,
                "restart_after_epoch":0,
            }

            job.item_total=len(groups)
            job.stage_label="1차 전체 수집"

            # Never allow a provider dict refresh to lose generation identity.
            provider["run_id"]=run_id
            provider["restart_after_epoch"]=0
            job.provider_status_json=json.dumps(provider,ensure_ascii=False)
            job.message=(
                f"ka90001 {group_pages:,}페이지 · 테마 {len(groups):,}개 확인 · "
                "느린 테마는 후순위 재수집합니다."
            )
            commit_or_rollback(db)

            failures=[]
            retry_queue=[]
            unique_member_codes=set()
            total_links=0
            total_member_pages=0

            async def fetch_and_store(item, index, pass_name, attempt):
                nonlocal total_links,total_member_pages,provider

                _raise_if_theme_sync_stop_requested(run_id)

                theme_code=str(item["theme_code"])
                theme_name=str(item["theme_name"])
                current_started_at=datetime.now().isoformat()

                job.current_code=theme_code
                job.current_name=theme_name
                job.stage_label=(
                    "1차 전체 수집"
                    if pass_name=="first"
                    else "실패 테마 재수집"
                )

                provider.update({
                    "current_page":0,
                    "current_status":"starting",
                    "current_status_message":"ka90002 요청 준비",
                    "current_attempt":attempt,
                    "current_pass":pass_name,
                    "current_started_at":current_started_at,
                })
                job.provider_status_json=json.dumps(provider,ensure_ascii=False)
                job.message=(
                    f"[{index:,}/{len(groups):,}] {theme_name} · "
                    + ("1차 조회" if pass_name=="first" else f"후순위 재시도 {attempt}/2")
                )
                commit_or_rollback(db)

                async def progress(event):
                    _raise_if_theme_sync_stop_requested(run_id)

                    if event.get("silent"):
                        return

                    provider.update({
                        "current_page":int(event.get("page") or 0),
                        "current_status":event.get("status") or "requesting",
                        "current_status_message":event.get("message") or "",
                        "current_attempt":attempt,
                        "current_pass":pass_name,
                        "current_started_at":current_started_at,
                    })

                    if event.get("raw_count") is not None:
                        provider["current_raw_count"]=int(
                            event.get("raw_count")
                            or 0
                        )

                    if event.get("member_count") is not None:
                        provider["current_member_count"]=int(
                            event.get("member_count")
                            or 0
                        )

                    job.provider_status_json=json.dumps(provider,ensure_ascii=False)
                    job.message=(
                        f"[{index:,}/{len(groups):,}] {theme_name} · "
                        f"{event.get('message') or '키움 응답 대기 중'}"
                    )
                    _raise_if_theme_sync_stop_requested(run_id)
                    commit_or_rollback(db)

                try:
                    members=await cli.theme_stocks(
                        theme_code,
                        progress_cb=progress,
                    )
                    _raise_if_theme_sync_stop_requested(run_id)

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    return False,str(exc)

                # Empty/deprecated themes must not wipe a previously valid
                # relationship set. Treat them as a non-fatal deterministic
                # issue and preserve the existing DB rows.
                if not members:
                    return False,"IGNORABLE: 구성종목 없음"

                member_pages=int(
                    getattr(
                        cli,
                        "last_theme_stock_pages",
                        {},
                    ).get(
                        theme_code,
                        1,
                    )
                    or 1
                )
                total_member_pages+=member_pages

                provider.update({
                    "current_page":
                        member_pages,
                    "current_status":
                        "parsed",
                    "current_status_message":
                        f"ka90002 파싱 완료 · 구성종목 {len(members):,}개",
                    "current_member_count":
                        len(members),
                })
                job.provider_status_json=json.dumps(
                    provider,
                    ensure_ascii=False,
                )
                job.message=(
                    f"[{index:,}/{len(groups):,}] {theme_name} · "
                    f"API 파싱 완료 ({len(members):,}개)"
                )
                commit_or_rollback(db)

                _raise_if_theme_sync_stop_requested(
                    run_id
                )

                provider.update({
                    "current_status":
                        "db_saving",
                    "current_status_message":
                        f"MySQL 저장 중 · {len(members):,}개 구성종목",
                    "current_db_elapsed":
                        0,
                })
                job.provider_status_json=json.dumps(
                    provider,
                    ensure_ascii=False,
                )
                job.message=(
                    f"[{index:,}/{len(groups):,}] {theme_name} · "
                    "MySQL 테마 관계 저장 중"
                )
                commit_or_rollback(db)

                save_result=await _persist_theme_members(
                    item,
                    members,
                    "kiwoom",
                )

                _raise_if_theme_sync_stop_requested(
                    run_id
                )

                if not save_result.get("ok"):
                    error=(
                        "DB 저장 실패 · "
                        + str(
                            save_result.get("error")
                            or "unknown"
                        )
                    )

                    provider.update({
                        "current_status":
                            "db_error",
                        "current_status_message":
                            error,
                        "current_db_elapsed":
                            save_result.get(
                                "elapsed_seconds",
                                0,
                            ),
                    })
                    job.provider_status_json=json.dumps(
                        provider,
                        ensure_ascii=False,
                    )
                    job.message=(
                        f"[{index:,}/{len(groups):,}] {theme_name} · "
                        f"{error} · 후순위 재수집"
                    )
                    commit_or_rollback(db)

                    return False,error

                member_codes=(
                    save_result.get(
                        "member_codes"
                    )
                    or []
                )

                for code in member_codes:
                    unique_member_codes.add(
                        code
                    )

                total_links+=len(
                    member_codes
                )

                provider.update({
                    "theme_member_pages":
                        total_member_pages,
                    "theme_links":
                        total_links,
                    "unique_member_stocks":
                        len(unique_member_codes),
                    "current_page":
                        member_pages,
                    "current_status":
                        "done",
                    "current_status_message":(
                        f"ka90002 {member_pages}페이지 · "
                        f"DB 저장 완료 {len(member_codes):,}개 · "
                        f"{save_result.get('elapsed_seconds',0):.2f}초"
                    ),
                    "current_member_count":
                        len(member_codes),
                    "current_db_elapsed":
                        save_result.get(
                            "elapsed_seconds",
                            0,
                        ),
                })
                job.provider_status_json=json.dumps(
                    provider,
                    ensure_ascii=False,
                )
                job.message=(
                    f"[{index:,}/{len(groups):,}] {theme_name} · "
                    f"DB 저장 완료 ({len(member_codes):,}개)"
                )
                commit_or_rollback(db)

                return True,None

            # -------- first pass: only one attempt, never block the whole run --------
            # v3.27.4 could reach this point with provider.run_id missing.
            provider["run_id"]=run_id
            provider["restart_after_epoch"]=0
            job.provider_status_json=json.dumps(
                provider,
                ensure_ascii=False,
            )
            commit_or_rollback(db)

            skipped_ignored=[]
            for index,item in enumerate(groups,1):
                _raise_if_theme_sync_stop_requested(run_id)
                theme_code=str(item.get("theme_code") or "")
                if _theme_is_temporarily_ignored(ignore_registry,theme_code):
                    entry=ignore_registry.get(theme_code) or {}
                    skipped_ignored.append({
                        "theme_code":theme_code,
                        "theme_name":str(item.get("theme_name") or ""),
                        "reason":str(entry.get("reason") or "반복적으로 비어 있거나 종료된 테마"),
                    })
                    provider["ignored_skipped"]=len(skipped_ignored)
                    job.item_completed=index
                    job.progress_value=index/max(len(groups),1)*90
                    job.provider_status_json=json.dumps(provider,ensure_ascii=False)
                    commit_or_rollback(db)
                    continue

                ok,error=await fetch_and_store(item,index,"first",1)
                _raise_if_theme_sync_stop_requested(run_id)
                if ok:
                    job.success+=1
                    ignore_registry.pop(theme_code,None)
                else:
                    retry_queue.append({
                        "index":index,
                        "item":item,
                        "first_error":error,
                    })

                provider["ignored_themes"]=ignore_registry
                provider["retry_queue"]=len(retry_queue)
                job.provider_status_json=json.dumps(provider,ensure_ascii=False)
                job.item_completed=index
                pct=index/max(len(groups),1)*90
                job.progress_value=pct
                elapsed=max(time.monotonic()-started,.1)
                job.eta_seconds=(elapsed*(90-pct)/pct if 0<pct<90 else 0)
                commit_or_rollback(db)

            # -------- deferred retry pass: failed themes only, max 2 attempts --------
            _raise_if_theme_sync_stop_requested(run_id)

            job.phase="theme-retry"
            job.stage_label="실패 테마 재수집"
            provider["current_pass"]="retry"
            provider["retry_queue"]=len(retry_queue)
            provider["retry_completed"]=0
            job.provider_status_json=json.dumps(provider,ensure_ascii=False)
            job.message=f"1차 수집 완료 · 실패 {len(retry_queue):,}개 테마만 후순위 재수집"
            commit_or_rollback(db)

            final_failures=[]

            for retry_pos,queued in enumerate(retry_queue,1):
                _raise_if_theme_sync_stop_requested(run_id)

                item=queued["item"]
                index=queued["index"]
                last_error=queued["first_error"]
                recovered=False

                for attempt in (1,2):
                    _raise_if_theme_sync_stop_requested(run_id)

                    ok,error=await fetch_and_store(item,index,"retry",attempt)
                    _raise_if_theme_sync_stop_requested(run_id)
                    if ok:
                        recovered=True
                        job.success+=1
                        break
                    last_error=error
                    if attempt < 2:
                        failure_kind=_classify_theme_sync_error(last_error)
                        wait_seconds=3.0 if failure_kind=="transient" else 1.25
                        provider.update({
                            "current_status":"retry_wait",
                            "current_status_message":f"{wait_seconds:g}초 후 마지막 재시도",
                            "current_attempt":attempt,
                        })
                        job.provider_status_json=json.dumps(provider,ensure_ascii=False)
                        job.message=f"{item['theme_name']} · {wait_seconds:g}초 후 마지막 재시도"
                        commit_or_rollback(db)
                        _raise_if_theme_sync_stop_requested(run_id)
                        await asyncio.sleep(wait_seconds)
                        _raise_if_theme_sync_stop_requested(run_id)

                theme_code=str(item["theme_code"])
                if recovered:
                    ignore_registry.pop(theme_code,None)
                else:
                    job.failed+=1
                    failure_kind=_classify_theme_sync_error(last_error)
                    final_failures.append({
                        "theme_code":theme_code,
                        "theme_name":str(item["theme_name"]),
                        "error":last_error,
                        "kind":failure_kind,
                    })
                    if failure_kind=="ignorable":
                        prev=ignore_registry.get(theme_code) or {}
                        count=int(prev.get("consecutive_failures") or 0)+1
                        entry={
                            "consecutive_failures":count,
                            "reason":str(last_error or "구성종목 없음"),
                            "last_failed_at":datetime.now().isoformat(),
                        }
                        if count>=3:
                            entry["ignore_until"]=(datetime.now()+timedelta(days=30)).isoformat()
                        ignore_registry[theme_code]=entry
                    else:
                        # Do not permanently suppress transient/unknown failures.
                        ignore_registry.pop(theme_code,None)
                provider["ignored_themes"]=ignore_registry

                provider["retry_completed"]=retry_pos
                job.failures_json=json.dumps(final_failures[-300:],ensure_ascii=False)
                job.provider_status_json=json.dumps(provider,ensure_ascii=False)
                # retry phase occupies final 10% of progress
                job.progress_value=90 + (retry_pos/max(len(retry_queue),1)*10)
                commit_or_rollback(db)

            _raise_if_theme_sync_stop_requested(run_id)
            _require_theme_schema_ready()
            _raise_if_theme_sync_stop_requested(run_id)

            (
                db.query(Theme)
                .filter(~Theme.theme_code.in_(seen_theme_codes))
                .update({Theme.is_active:False},synchronize_session=False)
            )

            stale_codes=[
                row.theme_code
                for row in db.query(Theme).filter(Theme.is_active==False).all()
            ]
            if stale_codes:
                (
                    db.query(StockTheme)
                    .filter(StockTheme.theme_code.in_(stale_codes))
                    .delete(synchronize_session=False)
                )

            commit_or_rollback(db)
            _refresh_primary_themes(db)
            coverage=_theme_coverage_stats(db,sample_limit=50)

            ignorable_count=sum(1 for x in final_failures if x.get("kind")=="ignorable")
            transient_count=sum(1 for x in final_failures if x.get("kind")=="transient")
            unknown_count=max(0,len(final_failures)-ignorable_count-transient_count)
            warning_count=len(final_failures)+len(skipped_ignored)
            provider.update({
                "theme_group_pages":group_pages,
                "theme_member_pages":total_member_pages,
                "theme_count":len(groups),
                "theme_links":db.query(StockTheme).count(),
                "unique_member_stocks":len(unique_member_codes),
                "coverage":coverage,
                "current_status":"finished",
                "current_status_message":"동기화 완료",
                "current_page":0,
                "warning_count":warning_count,
                "ignorable_failures":ignorable_count,
                "transient_failures":transient_count,
                "unknown_failures":unknown_count,
                "ignored_skipped":len(skipped_ignored),
                "warning_sample":final_failures[-20:],
                "ignored_sample":skipped_ignored[-20:],
                "ignored_themes":ignore_registry,
            })

            job.provider_status_json=json.dumps(provider,ensure_ascii=False)
            job.running=False
            job.phase="completed" if job.failed==0 else "partial"
            job.stage_label="완료" if job.failed==0 else "일부 실패"
            job.progress_value=100
            job.eta_seconds=0
            job.current_code=""
            job.current_name=""
            job.finished_at=datetime.now()

            if job.failed==0:
                job.last_error=""
                job.message=(
                    "키움 테마 동기화 완료 · "
                    f"테마 {len(groups):,}개 · ka90002 누적 {total_member_pages:,}p · "
                    f"공식 테마 연결 {coverage.get('official_theme_stocks',0):,}/"
                    f"{coverage.get('active_stocks',0):,} "
                    f"({coverage.get('coverage_percent',0):.1f}%)"
                )
            else:
                # Partial theme misses are operational warnings, not a system
                # error. Existing valid theme relationships were preserved.
                job.last_error=""
                job.message=(
                    f"키움 테마 동기화 완료 · {job.failed:,}개는 자동 보류/재시도 대상"
                )

            commit_or_rollback(db)

        except asyncio.CancelledError:
            if job:
                # Only the still-current generation may write final state.
                # If Stop API already invalidated this run_id, the DB is
                # already logically cancelled and this old worker must not
                # overwrite anything.
                state=_theme_sync_stop_state(
                    run_id
                )

                if not state["run_mismatch"]:
                    try:
                        provider=json.loads(
                            job.provider_status_json
                            or "{}"
                        )
                    except Exception:
                        provider={}

                    provider.update(
                        {
                            "stop_requested":False,
                            "current_status":"cancelled",
                            "current_status_message":
                                "관리자 요청으로 테마 동기화를 중지했습니다.",
                        }
                    )

                    job.provider_status_json=json.dumps(
                        provider,
                        ensure_ascii=False,
                    )
                    job.running=False
                    job.phase="cancelled"
                    job.stage_label="중지됨"
                    job.current_code=""
                    job.current_name=""
                    job.eta_seconds=0
                    job.message=(
                        "테마 동기화를 중지했습니다. "
                        "완전히 수집·저장된 테마 관계는 그대로 유지됩니다."
                    )
                    job.finished_at=datetime.now()
                    commit_or_rollback(db)

            raise

        except Exception as exc:
            if job:
                state=_theme_sync_stop_state(
                    run_id
                )

                if not state["run_mismatch"]:
                    job.running=False
                    job.phase="failed"
                    job.stage_label="실패"
                    job.last_error=f"{type(exc).__name__}: {exc}"
                    job.message="키움 테마 동기화 중단"
                    job.finished_at=datetime.now()
                    commit_or_rollback(db)

        finally:
            db.close()


def _finalize_market_theme_sync_sync(
    seen_theme_codes,
):
    """
    Finalize InfoStock theme synchronization outside the asyncio event loop.
    """
    db=SessionLocal()

    try:
        db.execute(
            text(
                "SET SESSION innodb_lock_wait_timeout = 5"
            )
        )

        seen_theme_codes=set(
            str(x)
            for x in (
                seen_theme_codes
                or []
            )
        )

        stale_query=(
            db.query(Theme)
            .filter(
                Theme.theme_code.like(
                    "INFO:%"
                )
            )
        )

        if seen_theme_codes:
            stale_query=(
                stale_query.filter(
                    ~Theme.theme_code.in_(
                        seen_theme_codes
                    )
                )
            )

        stale=stale_query.all()

        stale_codes=[
            row.theme_code
            for row in stale
        ]

        for row in stale:
            row.is_active=False

        if stale_codes:
            (
                db.query(StockTheme)
                .filter(
                    StockTheme.source
                    == "infostock",
                    StockTheme.theme_code.in_(
                        stale_codes
                    ),
                )
                .delete(
                    synchronize_session=False
                )
            )

        commit_or_rollback(db)

        _refresh_primary_themes(
            db
        )

        market_cov=(
            _theme_source_coverage_stats(
                db,
                "infostock",
                50,
            )
        )

        combined_cov=(
            _combined_theme_coverage_stats(
                db,
                50,
            )
        )

        link_count=(
            db.query(StockTheme)
            .filter(
                StockTheme.source
                == "infostock"
            )
            .count()
        )

        theme_count=(
            db.query(
                StockTheme.theme_code
            )
            .filter(
                StockTheme.source
                == "infostock"
            )
            .distinct()
            .count()
        )

        return {
            "ok":
                True,
            "market_coverage":
                market_cov,
            "combined_coverage":
                combined_cov,
            "link_count":
                link_count,
            "theme_count":
                theme_count,
        }

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass

        return {
            "ok":
                False,
            "error":
                f"{type(exc).__name__}: {exc}",
        }

    finally:
        db.close()


async def _finalize_market_theme_sync(
    seen_theme_codes,
):
    return await asyncio.to_thread(
        _finalize_market_theme_sync_sync,
        list(
            seen_theme_codes
            or []
        ),
    )


def _market_theme_running_fresh():
    """
    Fresh DB read for stop/cross-process state.
    """
    db=SessionLocal()

    try:
        job=(
            db.query(
                FullMarketSyncState
            )
            .filter(
                FullMarketSyncState.key
                == MARKET_THEME_SYNC_KEY
            )
            .first()
        )

        return bool(
            job
            and job.running
        )

    finally:
        db.close()


MARKET_THEME_SYNC_KEY="market_theme_sync"
_market_theme_sync_task=None
_market_theme_sync_lock=asyncio.Lock()


def _market_theme_job(db: Session):
    job=(
        db.query(FullMarketSyncState)
        .filter(FullMarketSyncState.key == MARKET_THEME_SYNC_KEY)
        .first()
    )
    if not job:
        job=FullMarketSyncState(
            key=MARKET_THEME_SYNC_KEY,
            running=False,
            phase="idle",
            job_type="market_themes",
        )
        db.add(job)
        commit_or_rollback(db)
        db.refresh(job)
    return job


def _market_theme_json(job):
    try:
        provider=json.loads(job.provider_status_json or "{}")
    except Exception:
        provider={}

    return {
        "running": bool(job.running),
        "phase": job.phase,
        "stage_label": job.stage_label,
        "item_total": job.item_total,
        "item_completed": job.item_completed,
        "progress": job.progress_value,
        "success": job.success,
        "failed": job.failed,
        "current_code": job.current_code,
        "current_name": job.current_name,
        "eta_seconds": job.eta_seconds,
        "message": job.message,
        "last_error": job.last_error,
        "provider_status": provider,
        "failures": _safe_json_list(job.failures_json),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


async def _run_market_theme_sync(
    admin_id: int,
):
    async with _market_theme_sync_lock:
        db=SessionLocal()
        job=None
        started=time.monotonic()

        try:
            _require_theme_schema_ready()

            job=_market_theme_job(
                db
            )

            job.running=True
            job.phase="catalog"
            job.job_type="market_themes"
            job.stage_label="시장 테마 목록"
            job.item_total=0
            job.item_completed=0
            job.progress_value=0
            job.success=0
            job.failed=0
            job.current_code=""
            job.current_name=""
            job.eta_seconds=0
            job.last_error=""
            job.message=(
                "Npay 증권의 인포스탁 국내 테마 목록을 조회합니다."
            )
            job.failures_json="[]"
            job.provider_status_json=json.dumps(
                {
                    "source":
                        "Npay Finance / InfoStock",
                    "catalog_pages":
                        0,
                    "theme_count":
                        0,
                    "theme_links":
                        0,
                    "unique_member_stocks":
                        0,
                    "current_status":
                        "catalog",
                },
                ensure_ascii=False,
            )
            job.requested_by_user_id=admin_id
            job.started_at=datetime.now()
            job.finished_at=None
            commit_or_rollback(db)

            async with NaverInfoStockThemeClient(
                timeout_seconds=12.0,
                request_gap_seconds=0.18,
            ) as client:

                async def catalog_progress(
                    event,
                ):
                    if not _market_theme_running_fresh():
                        raise asyncio.CancelledError()

                    try:
                        provider=json.loads(
                            job.provider_status_json
                            or "{}"
                        )
                    except Exception:
                        provider={}

                    provider.update(
                        {
                            "catalog_page":
                                int(
                                    event.get(
                                        "page"
                                    )
                                    or 0
                                ),
                            "catalog_count":
                                int(
                                    event.get(
                                        "theme_count"
                                    )
                                    or 0
                                ),
                            "current_status":
                                event.get(
                                    "status"
                                )
                                or "catalog",
                        }
                    )

                    job.provider_status_json=_bounded_provider_json(
                        provider
                    )
                    job.message=(
                        event.get(
                            "message"
                        )
                        or job.message
                    )
                    commit_or_rollback(db)

                catalog=await client.catalog(
                    progress_cb=
                        catalog_progress,
                )

                if not catalog:
                    raise RuntimeError(
                        "시장 테마 목록을 한 건도 파싱하지 못했습니다."
                    )

                provider={
                    "source":
                        "Npay Finance / InfoStock",
                    "catalog_pages":
                        client.last_catalog_pages,
                    "theme_count":
                        len(catalog),
                    "theme_links":
                        0,
                    "unique_member_stocks":
                        0,
                    "current_status":
                        "members",
                    "current_attempt":
                        1,
                }

                job.phase="members"
                job.stage_label="시장 테마 구성종목"
                job.item_total=len(
                    catalog
                )
                job.provider_status_json=_bounded_provider_json(
                    provider
                )
                job.message=(
                    f"시장 테마 {len(catalog):,}개 확인 · "
                    "구성종목 동기화 시작"
                )
                commit_or_rollback(db)

                seen=set()
                member_union=set()
                total_links=0
                failures=[]

                for index,item in enumerate(
                    catalog,
                    1,
                ):
                    if not _market_theme_running_fresh():
                        raise asyncio.CancelledError()

                    theme_no=str(
                        item["theme_no"]
                    )
                    theme_code=str(
                        item["theme_code"]
                    )
                    theme_name=str(
                        item["theme_name"]
                    )

                    seen.add(
                        theme_code
                    )

                    job.current_code=theme_code
                    job.current_name=theme_name

                    members=None
                    diagnostics={}
                    final_error=None

                    for attempt in (
                        1,
                        2,
                    ):
                        if not _market_theme_running_fresh():
                            raise asyncio.CancelledError()

                        provider.update(
                            {
                                "current_status":
                                    "requesting",
                                "current_theme_no":
                                    theme_no,
                                "current_attempt":
                                    attempt,
                                "current_member_count":
                                    0,
                            }
                        )

                        job.provider_status_json=_bounded_provider_json(
                            provider
                        )

                        job.message=(
                            f"[{index:,}/{len(catalog):,}] "
                            f"{theme_name} · 구성종목 조회 "
                            f"({attempt}/2)"
                        )
                        commit_or_rollback(db)

                        try:
                            (
                                members,
                                diagnostics,
                            )=await client.members(
                                theme_no
                            )

                            final_error=None
                            break

                        except asyncio.CancelledError:
                            raise

                        except Exception as exc:
                            final_error=exc

                            if attempt < 2:
                                provider[
                                    "current_status"
                                ]="retry_wait"

                                job.message=(
                                    f"[{index:,}/{len(catalog):,}] "
                                    f"{theme_name} · 조회 실패 · "
                                    "0.8초 후 재시도"
                                )
                                job.provider_status_json=json.dumps(
                                    provider,
                                    ensure_ascii=False,
                                )
                                commit_or_rollback(db)
                                await asyncio.sleep(
                                    0.8
                                )

                    if members is None:
                        job.failed+=1

                        failure={
                            "theme_no":
                                theme_no,
                            "theme_name":
                                theme_name,
                            "stage":
                                "http_or_parse",
                            "error":
                                _sync_error_text(
                                    final_error
                                ),
                        }

                        failures.append(
                            failure
                        )

                        provider.update(
                            {
                                "current_status":
                                    "failed",
                                "current_error":
                                    failure[
                                        "error"
                                    ],
                                "failures":
                                    failures[-10:],
                            }
                        )

                    else:
                        if not _market_theme_running_fresh():
                            raise asyncio.CancelledError()

                        provider.update(
                            {
                                "current_status":
                                    "parsed",
                                "current_member_count":
                                    len(
                                        members
                                    ),
                                "current_candidate_tables":
                                    diagnostics.get(
                                        "candidate_tables",
                                        0,
                                    ),
                                "current_all_stock_links":
                                    diagnostics.get(
                                        "all_stock_links",
                                        0,
                                    ),
                            }
                        )

                        job.provider_status_json=_bounded_provider_json(
                            provider
                        )

                        job.message=(
                            f"[{index:,}/{len(catalog):,}] "
                            f"{theme_name} · "
                            f"{len(members):,}개 종목 파싱 완료"
                        )
                        commit_or_rollback(db)

                        provider[
                            "current_status"
                        ]="db_saving"

                        job.provider_status_json=_bounded_provider_json(
                            provider
                        )
                        commit_or_rollback(db)

                        saved=await _persist_theme_members(
                            item,
                            members,
                            "infostock",
                        )

                        if not saved.get(
                            "ok"
                        ):
                            job.failed+=1

                            failure={
                                "theme_no":
                                    theme_no,
                                "theme_name":
                                    theme_name,
                                "stage":
                                    "db_save",
                                "error":
                                    _truncate_utf8(
                                        saved.get(
                                            "error"
                                        )
                                        or "시장 테마 DB 저장 실패",
                                        1400,
                                    ),
                            }

                            failures.append(
                                failure
                            )

                            provider.update(
                                {
                                    "current_status":
                                        "failed",
                                    "current_error":
                                        failure[
                                            "error"
                                        ],
                                    "failures":
                                        failures[-100:],
                                }
                            )

                        else:
                            codes=(
                                saved.get(
                                    "member_codes"
                                )
                                or []
                            )

                            member_union.update(
                                codes
                            )
                            total_links+=len(
                                codes
                            )
                            job.success+=1

                            provider.update(
                                {
                                    "current_status":
                                        "done",
                                    "current_member_count":
                                        len(
                                            codes
                                        ),
                                    "current_db_elapsed":
                                        saved.get(
                                            "elapsed_seconds",
                                            0,
                                        ),
                                    "theme_links":
                                        total_links,
                                    "unique_member_stocks":
                                        len(
                                            member_union
                                        ),
                                    "current_error":
                                        "",
                                }
                            )

                    job.item_completed=index

                    # 100% is reserved for successful finalization.
                    collection_pct=(
                        index
                        / max(
                            len(catalog),
                            1,
                        )
                        * 99.0
                    )
                    job.progress_value=collection_pct

                    elapsed=max(
                        time.monotonic()
                        - started,
                        0.1,
                    )

                    job.eta_seconds=(
                        elapsed
                        * (
                            99.0
                            - collection_pct
                        )
                        / collection_pct
                        if 0
                        < collection_pct
                        < 99
                        else 0
                    )

                    job.failures_json=_bounded_failures_json(
                        failures,
                        max_items=32,
                    )
                    job.provider_status_json=_bounded_provider_json(
                        provider
                    )
                    commit_or_rollback(db)

            # If every detail page failed, do NOT enter expensive finalization
            # or show a false 100%. Expose the first actual failure.
            if job.success == 0:
                first_error=(
                    failures[0]["error"]
                    if failures
                    else "구성종목을 한 건도 저장하지 못했습니다."
                )

                provider.update(
                    {
                        "current_status":
                            "failed",
                        "first_error":
                            first_error,
                        "failure_count":
                            job.failed,
                    }
                )

                job.provider_status_json=_bounded_provider_json(
                    provider
                )
                job.running=False
                job.phase="failed"
                job.stage_label="실패"
                job.current_code=""
                job.current_name=""
                job.eta_seconds=0
                job.last_error=(
                    f"시장 테마 {job.failed:,}개가 모두 실패했습니다. "
                    f"첫 오류: {first_error}"
                )
                job.message=(
                    "시장 테마 구성종목 동기화에 실패했습니다. "
                    "오류 상세를 확인해주세요."
                )
                job.finished_at=datetime.now()
                commit_or_rollback(db)
                return

            # Explicit finalization phase.
            job.phase="finalizing"
            job.stage_label="최종 정리"
            job.current_code=""
            job.current_name=""
            job.progress_value=99.0
            job.eta_seconds=0

            provider.update(
                {
                    "current_status":
                        "finalizing",
                    "current_member_count":
                        0,
                }
            )
            job.provider_status_json=json.dumps(
                provider,
                ensure_ascii=False,
            )
            job.message=(
                "구성종목 수집 완료 · "
                "테마 정리 및 커버리지 계산 중"
            )
            commit_or_rollback(db)

            finalized=await _finalize_market_theme_sync(
                seen
            )

            if not finalized.get(
                "ok"
            ):
                raise RuntimeError(
                    "시장 테마 최종화 실패: "
                    + str(
                        finalized.get(
                            "error"
                        )
                        or "unknown"
                    )
                )

            market_cov=finalized[
                "market_coverage"
            ]
            combined_cov=finalized[
                "combined_coverage"
            ]

            provider.update(
                {
                    "current_status":
                        "completed",
                    "coverage":
                        market_cov,
                    "combined_coverage":
                        combined_cov,
                    "theme_links":
                        finalized[
                            "link_count"
                        ],
                    "stored_theme_count":
                        finalized[
                            "theme_count"
                        ],
                    "failure_count":
                        job.failed,
                }
            )

            job.provider_status_json=json.dumps(
                provider,
                ensure_ascii=False,
            )
            job.running=False
            job.phase=(
                "completed"
                if job.failed == 0
                else "partial"
            )
            job.stage_label=(
                "완료"
                if job.failed == 0
                else "일부 실패"
            )
            job.progress_value=100
            job.eta_seconds=0
            job.current_code=""
            job.current_name=""

            job.last_error=(
                ""
                if job.failed == 0
                else (
                    f"{job.failed:,}개 시장 테마 실패 · "
                    + (
                        failures[0]["error"]
                        if failures
                        else ""
                    )
                )
            )

            job.message=(
                "시장 테마 동기화 완료 · "
                f"성공 {job.success:,} / 실패 {job.failed:,} · "
                f"시장테마 연결 "
                f"{market_cov.get('linked_stocks',0):,}/"
                f"{market_cov.get('active_stocks',0):,} · "
                f"통합 커버리지 "
                f"{combined_cov.get('coverage_percent',0):.1f}%"
            )
            job.finished_at=datetime.now()
            commit_or_rollback(db)

        except asyncio.CancelledError:
            try:
                db.rollback()
            except Exception:
                pass
            if job:
                try:
                    job=_market_theme_job(db)
                except Exception:
                    job=None
            if job:
                job.running=False
                job.phase="cancelled"
                job.stage_label="중지됨"
                job.current_code=""
                job.current_name=""
                job.eta_seconds=0
                job.message=(
                    "시장 테마 동기화를 중지했습니다. "
                    "완료된 관계는 유지됩니다."
                )
                job.finished_at=datetime.now()
                commit_or_rollback(db)

            raise

        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            if job:
                try:
                    job=_market_theme_job(db)
                except Exception:
                    job=None
            if job:
                job.running=False
                job.phase="failed"
                job.stage_label="실패"
                job.current_code=""
                job.current_name=""
                job.eta_seconds=0
                job.last_error=_sync_error_text(exc, 3000)
                job.message=(
                    "시장 테마 동기화 중단"
                )
                job.finished_at=datetime.now()
                commit_or_rollback(db)

        finally:
            db.close()


def _reconcile_market_theme_sync_on_boot():
    db=SessionLocal()

    try:
        job=(
            db.query(
                FullMarketSyncState
            )
            .filter(
                FullMarketSyncState.key
                == MARKET_THEME_SYNC_KEY
            )
            .first()
        )

        if not job:
            return

        if not job.running:
            return

        job.running=False
        job.phase="cancelled"
        job.stage_label="중지됨"
        job.current_code=""
        job.current_name=""
        job.eta_seconds=0
        job.message=(
            "백엔드 재시작으로 이전 시장 테마 작업을 종료 처리했습니다."
        )
        job.finished_at=datetime.now()
        commit_or_rollback(db)

    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass

        print(
            "[WARN] market theme boot reconcile failed:",
            repr(exc),
        )

    finally:
        db.close()


_reconcile_market_theme_sync_on_boot()


@app.get("/api/admin/market-theme-sync/status")
def admin_market_theme_status(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    return _market_theme_json(_market_theme_job(db))


@app.post("/api/admin/market-theme-sync/start")
async def admin_market_theme_start(
    u:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    global _market_theme_sync_task

    if _market_theme_sync_task and not _market_theme_sync_task.done():
        raise HTTPException(409,"시장 테마 동기화가 이미 실행 중입니다.")

    if _theme_sync_task and not _theme_sync_task.done():
        raise HTTPException(409,"키움 테마 동기화 완료 후 시장 테마를 실행해주세요.")

    job=_market_theme_job(db)
    if job.running:
        job.running=False
        job.phase="cancelled"
        commit_or_rollback(db)

    _market_theme_sync_task=asyncio.create_task(
        _run_market_theme_sync(u.id)
    )

    return {
        "ok":True,
        "message":"시장 테마 동기화를 시작했습니다. 인포스탁 국내 테마와 구성종목을 실제 데이터로 저장합니다.",
    }


@app.post("/api/admin/market-theme-sync/stop")
async def admin_market_theme_stop(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    global _market_theme_sync_task

    job=_market_theme_job(
        db
    )

    was_running=bool(
        job.running
    )

    job.running=False
    job.phase="cancelled"
    job.stage_label="중지됨"
    job.current_code=""
    job.current_name=""
    job.eta_seconds=0
    job.message=(
        "시장 테마 동기화를 중지했습니다. "
        "완료된 관계는 유지됩니다."
    )
    job.finished_at=datetime.now()
    commit_or_rollback(db)

    if (
        _market_theme_sync_task
        and not _market_theme_sync_task.done()
    ):
        _market_theme_sync_task.cancel()

    return {
        "ok":
            True,
        "already_stopped":
            not was_running,
        "message":
            (
                "시장 테마 동기화를 중지했습니다."
                if was_running
                else "현재 시장 테마 동기화는 이미 중지된 상태입니다."
            ),
    }


@app.get("/api/admin/market-theme-sync/coverage")
def admin_market_theme_coverage(
    limit:int=Query(30,ge=1,le=200),
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    return {
        "market":_theme_source_coverage_stats(db,"infostock",limit),
        "kiwoom":_theme_source_coverage_stats(db,"kiwoom",limit),
        "combined":_combined_theme_coverage_stats(db,limit),
    }


@app.get("/api/admin/theme-db/status")
def admin_theme_db_status(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    return _safe_theme_db_stats(
        db
    )


@app.post("/api/admin/theme-db/repair")
def admin_theme_db_repair(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    try:
        schema=(
            _require_theme_schema_ready()
        )
    except Exception as exc:
        raise HTTPException(
            500,
            {
                "message":(
                    "테마 DB 실제 컬럼 확인/복구에 실패했습니다."
                ),
                "error":f"{type(exc).__name__}: {exc}",
            },
        )

    stats = (
        _safe_theme_db_stats(db)
    )

    if not schema["ok"]:
        raise HTTPException(
            500,
            {
                "message":
                    "테마 DB 테이블 생성에 실패했습니다.",
                "schema":
                    schema,
                "stats":
                    stats,
            },
        )

    return {
        "ok":True,
        "message":(
            "테마 DB 테이블 확인/복구가 완료되었습니다."
            + (
                " 추가된 컬럼: "
                + ", ".join(
                    schema.get("changes") or []
                )
                if schema.get("changes")
                else ""
            )
        ),
        "schema":
            schema,
        "stats":
            stats,
    }


@app.get("/api/admin/theme-sync/coverage")
def admin_theme_sync_coverage(
    limit:int=Query(30,ge=1,le=200),
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    return _theme_coverage_stats(db,sample_limit=limit)


@app.get("/api/admin/theme-diagnostic/{code}")
def admin_theme_diagnostic(
    code:str,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    stock=(
        db.query(Stock)
        .filter(
            Stock.code==code,
            Stock.is_active==True,
        )
        .first()
    )

    if not stock:
        raise HTTPException(404,"활성 종목을 찾지 못했습니다.")

    themes=_stock_theme_items(db,stock.code)

    return {
        "stock":{
            "code":stock.code,
            "name":stock.name,
            "market":stock.market,
            "sector":stock.sector,
        },
        "official_themes":themes,
        "official_theme_count":len(themes),
        "fallback":_stock_theme_fallback(stock),
        "note":(
            "official_themes가 비어 있으면 전체 ka90001/ka90002 연속조회 DB에서 "
            "키움 공식 테마 구성종목으로 반환되지 않은 상태입니다."
        ),
    }


@app.get("/api/admin/theme-sync/status")
def admin_theme_sync_status(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    job=_theme_sync_job(db)

    provider_now=_theme_sync_provider_from_row(
        job
    )

    # v3.27.4 orphan signature:
    # ka90001 finished, provider was recreated without run_id, the worker
    # cancelled itself before the first ka90002, but DB running stayed true.
    orphaned_missing_run_id=(
        bool(job.running)
        and not str(
            provider_now.get("run_id")
            or ""
        )
        and int(job.item_total or 0) > 0
        and int(job.item_completed or 0) == 0
        and str(job.phase or "")
        in (
            "themes",
            "theme-first",
            "theme-retry",
        )
    )

    if orphaned_missing_run_id:
        provider_now.update(
            {
                "run_id":
                    "orphan-cancel-"
                    + str(
                        time.time_ns()
                    ),
                "stop_requested":
                    False,
                "current_status":
                    "cancelled",
                "current_status_message":
                    "이전 버전의 run_id 누락 고아 작업을 자동 정리했습니다.",
                "restart_after_epoch":
                    0,
            }
        )

        job.provider_status_json=json.dumps(
            provider_now,
            ensure_ascii=False,
        )
        job.running=False
        job.phase="cancelled"
        job.stage_label="중지됨"
        job.current_code=""
        job.current_name=""
        job.eta_seconds=0
        job.message=(
            "이전 버전의 0/N 테마 동기화 고아 상태를 "
            "자동으로 정리했습니다."
        )
        job.finished_at=datetime.now()
        commit_or_rollback(db)

    # Legacy versions could persist stop_requested forever even though
    # running was already false. Upgrade that stale record in-place.
    if (
        not bool(job.running)
        and str(job.phase or "")
        == "stop_requested"
    ):
        provider=_theme_sync_provider_from_row(
            job
        )
        provider.update(
            {
                "run_id":
                    "status-cancel-"
                    + str(
                        time.time_ns()
                    ),
                "stop_requested":
                    False,
                "current_status":
                    "cancelled",
                "current_status_message":
                    "이전 중지 요청 상태를 자동 정리했습니다.",
                "restart_after_epoch":
                    0,
            }
        )
        job.provider_status_json=json.dumps(
            provider,
            ensure_ascii=False,
        )
        job.phase="cancelled"
        job.stage_label="중지됨"
        job.current_code=""
        job.current_name=""
        job.message=(
            "이전 테마 동기화 중지 상태를 정리했습니다."
        )
        job.finished_at=datetime.now()
        commit_or_rollback(db)

    return _theme_sync_json(
        job
    )


THEME_NORMALIZE_KEY="theme_normalize"
_theme_normalize_task=None
_theme_normalize_lock=asyncio.Lock()


def _theme_normalize_job(db: Session):
    job=db.query(FullMarketSyncState).filter(FullMarketSyncState.key==THEME_NORMALIZE_KEY).first()
    if not job:
        job=FullMarketSyncState(key=THEME_NORMALIZE_KEY,job_type="theme_normalize",running=False,phase="idle",stage_label="대기")
        db.add(job);commit_or_rollback(db);db.refresh(job)
    return job


def _theme_normalize_json(job):
    try: provider=json.loads(job.provider_status_json or "{}")
    except Exception: provider={}
    try: failures=json.loads(job.failures_json or "[]")
    except Exception: failures=[]
    return {
        "running":bool(job.running),"phase":job.phase or "idle","stage_label":job.stage_label or "",
        "item_total":int(job.item_total or 0),"item_completed":int(job.item_completed or 0),
        "progress":round(float(job.progress_value or 0),1),"success":int(job.success or 0),"failed":int(job.failed or 0),
        "current_name":job.current_name or "","message":job.message or "","last_error":job.last_error or "",
        "started_at":job.started_at.isoformat() if job.started_at else None,
        "finished_at":job.finished_at.isoformat() if job.finished_at else None,
        "provider_status":provider,"failures":failures[-12:],
    }


def _clean_canonical_theme_name(value):
    value=re.sub(r"\s+"," ",str(value or "").strip())
    value=re.sub(r"^[·•\-–—]+|[·•\-–—]+$","",value).strip()
    return value[:80]



def _compact_text(value, limit=220):
    value=re.sub(r"\s+"," ",str(value or "").strip())
    return value[:limit]


def _business_theme_context(db: Session, stocks, previous_by_code=None):
    """Evidence for stock-level actual-business and investment-theme classification.

    previous_by_code preserves the last successful StockLog classification while
    a full rebuild clears writable theme columns. This lets the new run reuse
    previously verified evidence instead of throwing it away before re-ranking.
    """
    previous_by_code=previous_by_code or {}
    codes=[stock.code for stock in stocks]
    theme_map=_theme_map_for_codes(db,codes,limit=6)
    news_map={code:[] for code in codes}; report_map={code:[] for code in codes}
    if codes:
        news_rows=(db.query(NewsCache).filter(NewsCache.stock_code.in_(codes)).order_by(NewsCache.published_dt.desc(),NewsCache.fetched_at.desc()).limit(max(60,len(codes)*4)).all())
        for row in news_rows:
            bucket=news_map.setdefault(row.stock_code,[])
            if len(bucket)<3: bucket.append(_compact_text(row.description or row.title,180))
        report_rows=(db.query(BrokerReportCache).filter(BrokerReportCache.stock_code.in_(codes)).order_by(BrokerReportCache.report_dt.desc(),BrokerReportCache.fetched_at.desc()).limit(max(40,len(codes)*3)).all())
        for row in report_rows:
            bucket=report_map.setdefault(row.stock_code,[])
            if len(bucket)<2: bucket.append(_compact_text(row.brief_summary or row.title,180))
    payload=[]
    for stock in stocks:
        provider_themes=[]
        for item in theme_map.get(stock.code,[]):
            if item.get("source")=="classification": continue
            name=str(item.get("raw_name") or item.get("name") or item.get("display_name") or "").strip()
            if name and name not in provider_themes: provider_themes.append(name)
        previous=previous_by_code.get(stock.code) or {}
        try:
            aliases=json.loads(stock.name_aliases_json or "[]")
            if not isinstance(aliases,list): aliases=[]
        except Exception:
            aliases=[]
        payload.append({
            "code":stock.code,"name":stock.name,
            "official_industry":stock.industry_name or stock.sector or "",
            "sector":stock.sector or "",
            "provider_themes":provider_themes[:8],
            "recent_news":news_map.get(stock.code,[])[:4],
            "recent_reports":report_map.get(stock.code,[])[:3],
            "existing_business":stock.primary_business or previous.get("primary_business") or "",
            "existing_investment_theme":previous.get("investment_theme") or stock.investment_theme or "",
            "previous_theme_group":previous.get("theme_group") or "",
            "legacy_primary_theme":previous.get("primary_theme") or stock.primary_theme or "",
            "name_aliases":[str(x or "").strip() for x in aliases if str(x or "").strip()][:8],
        })
    return payload


def _apply_business_theme_result(stock: Stock, result: dict):
    primary_business=_compact_text(result.get("primary_business"),160)
    primary_theme=_clean_canonical_theme_name(result.get("primary_theme"))
    secondary=result.get("secondary_themes") if isinstance(result.get("secondary_themes"),list) else []
    secondary=[_clean_canonical_theme_name(x) for x in secondary if _clean_canonical_theme_name(x)]
    secondary=list(dict.fromkeys(secondary))[:5]
    try: confidence=max(0.0,min(100.0,float(result.get("confidence") or 0)))
    except Exception: confidence=0.0
    if not primary_theme: return False
    stock.primary_business=primary_business or stock.primary_business
    stock.investment_theme=primary_theme
    stock.investment_themes_json=json.dumps([primary_theme]+[x for x in secondary if x!=primary_theme],ensure_ascii=False)
    stock.classification_confidence=confidence or None
    stock.classification_reason=_compact_text(result.get("reason"),600)
    stock.classification_source_summary=_compact_text(result.get("source_summary"),800)
    stock.classification_updated_at=datetime.now()
    return True



def _json_text_list(value):
    try:
        parsed=json.loads(value or "[]")
    except Exception:
        parsed=[]
    if not isinstance(parsed,list):
        return []
    return [str(x or "").strip() for x in parsed if str(x or "").strip()]


def _stock_taxonomy_payload(stock: Stock):
    """Return durable parent/sub-theme data with backward-compatible fallback."""
    primary=str(getattr(stock,"theme_group",None) or "").strip()
    groups=_json_text_list(getattr(stock,"theme_groups_json",None))
    subthemes=_json_text_list(getattr(stock,"theme_subthemes_json",None))
    if primary:
        if primary not in groups:
            groups.insert(0,primary)
        return {
            "primary":primary,
            "groups":list(dict.fromkeys(groups))[:3],
            "subthemes":list(dict.fromkeys(subthemes))[:8],
            "engine_version":str(getattr(stock,"theme_engine_version",None) or ""),
            "confidence":float(getattr(stock,"classification_confidence",0) or 0),
        }

    # Verified company overrides apply immediately after upgrade, even before the
    # first full rebuild. This prevents known exchange-industry mismatches such
    # as COSMAX=화학 from leaking back into Smart Analysis.
    override=classify_stock_context({"name":str(getattr(stock,"name","") or "")})
    if override and str(override.get("source_summary") or "").startswith("StockLog 표준 테마 사전"):
        primary=str(override.get("theme_group") or "").strip()
        return {
            "primary":primary,
            "groups":list(override.get("theme_groups") or ([primary] if primary else [])),
            "subthemes":list(override.get("subthemes") or []),
            "engine_version":str(override.get("engine_version") or THEME_ENGINE_VERSION),
            "confidence":float(override.get("confidence") or 0),
        }

    # Old v3.65/v3.66 rows are normalized through the fixed taxonomy rather than
    # exposed as arbitrary top-level labels.
    legacy=str(getattr(stock,"investment_theme",None) or "").strip()
    mapped=map_theme_name(legacy) if legacy else []
    if mapped:
        primary=str(mapped[0].get("group") or "").strip()
        subs=[str(x.get("subtheme") or "").strip() for x in mapped if str(x.get("subtheme") or "").strip()!=primary]
        return {"primary":primary,"groups":[primary],"subthemes":list(dict.fromkeys(subs))[:8],"engine_version":"legacy-normalized","confidence":float(getattr(stock,"classification_confidence",0) or 0)}
    return {"primary":"","groups":[],"subthemes":[],"engine_version":"","confidence":0.0}


def _apply_theme_engine_result(stock: Stock, result: dict):
    primary=_clean_canonical_theme_name(result.get("theme_group"))
    if not primary:
        return False
    raw_groups=result.get("theme_groups") if isinstance(result.get("theme_groups"),list) else [primary]
    raw_subs=result.get("subthemes") if isinstance(result.get("subthemes"),list) else []
    primary,groups,subs=normalize_stored_theme_payload(primary,raw_groups,raw_subs)
    try:
        confidence=max(0.0,min(100.0,float(result.get("confidence") or 0)))
    except Exception:
        confidence=0.0
    stock.primary_business=_compact_text(result.get("primary_business"),160) or stock.primary_business
    stock.theme_group=primary
    stock.theme_groups_json=json.dumps(groups,ensure_ascii=False)
    stock.theme_subthemes_json=json.dumps(subs,ensure_ascii=False)
    stock.theme_engine_version=_compact_text(result.get("engine_version") or THEME_ENGINE_VERSION,80)
    evidence=result.get("evidence") if isinstance(result.get("evidence"),list) else []
    stock.theme_engine_evidence_json=json.dumps(evidence[:40],ensure_ascii=False)
    # Backward-compatible fields now mean: primary parent + visible detail list.
    stock.investment_theme=primary
    stock.investment_themes_json=json.dumps([primary]+subs,ensure_ascii=False)
    stock.classification_confidence=confidence or None
    stock.classification_reason=_compact_text(result.get("reason"),900)
    stock.classification_source_summary=_compact_text(result.get("source_summary"),900)
    stock.classification_updated_at=datetime.now()
    return True


def _classification_is_verified(stock: Stock, minimum_confidence: float = 60.0) -> bool:
    tax=_stock_taxonomy_payload(stock)
    theme=str(tax.get("primary") or "").strip()
    if not theme:
        return False
    try:
        confidence=float(tax.get("confidence") or getattr(stock,"classification_confidence",0) or 0)
    except Exception:
        confidence=0.0
    reason=str(getattr(stock,"classification_reason","") or "")
    if "임시 사용" in reason or "공급사 테마 기반 임시" in reason:
        return False
    return confidence >= minimum_confidence


async def _classify_stock_business_themes(db: Session, job, theme_work_total:int, failures:list):
    """Rebuild every stock with the deterministic StockLog Theme Engine."""
    stocks=(db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .order_by(Stock.market_cap.desc(),Stock.code.asc()).all())
    # Classify the complete analysis universe. Stocks without enough evidence are
    # counted as a valid no-theme state instead of silently disappearing from
    # coverage statistics. Provider membership is loaded per batch below.
    total=len(stocks)
    if not total:
        return {"total":0,"processed":0,"classified":0,"engine_classified":0,"strong_classified":0,"fallback_classified":0,"low_confidence":0,"no_theme":0,"unresolved":0,"errors":0,"coverage":100.0}

    # Preserve the previous successful classification as weak evidence before
    # clearing writable fields. A rebuild must not lose information merely
    # because it is rebuilding those same columns.
    previous_by_code={
        stock.code:{
            "theme_group":str(stock.theme_group or "").strip(),
            "investment_theme":str(stock.investment_theme or "").strip(),
            "primary_theme":str(stock.primary_theme or "").strip(),
            "primary_business":str(stock.primary_business or "").strip(),
        }
        for stock in stocks
    }

    # Full rebuild: stale free-form values are cleared from storage, but the
    # snapshot above remains available as low/medium-weight evidence.
    for stock in stocks:
        stock.theme_group=None
        stock.theme_groups_json=None
        stock.theme_subthemes_json=None
        stock.theme_engine_version=None
        stock.theme_engine_evidence_json=None
        stock.investment_theme=None
        stock.investment_themes_json=None
        stock.classification_confidence=None
        stock.classification_reason=None
        stock.classification_source_summary=None
        stock.classification_updated_at=None
    commit_or_rollback(db)

    batch_size=40
    combined_total=max(1,theme_work_total+total)
    classified=0; strong_classified=0; fallback_classified=0; low_confidence=0; no_theme=0; unresolved=0; processed=0
    no_theme_examples=[]
    job.item_total=combined_total
    for batch_index,start in enumerate(range(0,total,batch_size),1):
        batch=stocks[start:start+batch_size]
        contexts=_business_theme_context(db,batch,previous_by_code=previous_by_code)
        job.phase="classifying_stocks"
        job.stage_label="기업 표준 테마 분류"
        job.current_name=f"{batch[0].name} ~ {batch[-1].name}"
        job.message=f"{start:,}/{total:,}개 종목 · 사업/공급사 테마/뉴스/리포트를 표준 테마 체계에 매핑하고 있습니다."
        job.item_completed=theme_work_total+start
        job.progress_value=min(99.0,(job.item_completed/combined_total)*100)
        provider=json.loads(job.provider_status_json or "{}")
        provider.update({
            "current_status":"stock_theme_engine",
            "classification_batch":batch_index,
            "classification_total":total,
            "classification_processed":processed,
            "classified":classified,
            "engine_classified":classified,
            "strong_classified":strong_classified,
            "fallback_classified":fallback_classified,
            "low_confidence":low_confidence,
            "no_theme":no_theme,
            "unresolved":unresolved,
            "errors":len(failures),
            "no_theme_examples":no_theme_examples[-12:],
            "theme_engine_version":THEME_ENGINE_VERSION,
        })
        job.provider_status_json=_bounded_provider_json(provider)
        commit_or_rollback(db)

        for stock,ctx in zip(batch,contexts):
            try:
                result=classify_stock_context(ctx)
                if result and _apply_theme_engine_result(stock,result):
                    classified+=1
                    mode=str(result.get("classification_mode") or "evidence")
                    if mode=="industry_fallback":
                        fallback_classified+=1
                    else:
                        strong_classified+=1
                    if float(stock.classification_confidence or 0)<70:
                        low_confidence+=1
                else:
                    # No trustworthy theme is a valid business state, not a sync
                    # failure. Keep the stock searchable and let future provider/
                    # DART/news evidence promote it automatically on the next run.
                    no_theme+=1
                    unresolved+=1
                    if len(no_theme_examples)<24:
                        no_theme_examples.append({"code":stock.code,"name":stock.name,"industry":stock.industry_name or stock.sector or ""})
                    stock.classification_reason="현재 수집된 근거만으로 특정 투자테마를 강제로 부여하지 않았습니다. 이후 테마·사업정보가 보강되면 자동 재분류됩니다."
                    stock.classification_source_summary="StockLog Theme Engine · 정상 무테마"
                    stock.classification_updated_at=datetime.now()
            except Exception as exc:
                unresolved+=1
                failures.append({"stage":"theme_engine_stock","code":stock.code,"name":stock.name,"error":_sync_error_text(exc)})
                stock.classification_reason="표준 테마 분류 중 예외가 발생해 자동 분류하지 않았습니다."
                stock.classification_source_summary="StockLog Theme Engine · 오류 검수 필요"
                stock.classification_updated_at=datetime.now()

        completed=min(total,start+len(batch)); processed=completed
        job.item_completed=theme_work_total+completed
        job.progress_value=min(99.5,(job.item_completed/combined_total)*100)
        job.success=theme_work_total+classified
        job.failed=len(failures)
        provider=json.loads(job.provider_status_json or "{}")
        provider.update({
            "current_status":"stock_theme_engine_saved",
            "classification_total":total,
            "classification_processed":processed,
            "classified":classified,
            "engine_classified":classified,
            "strong_classified":strong_classified,
            "fallback_classified":fallback_classified,
            "low_confidence":low_confidence,
            "no_theme":no_theme,
            "unresolved":unresolved,
            "errors":len(failures),
            "no_theme_examples":no_theme_examples[-12:],
            "theme_engine_version":THEME_ENGINE_VERSION,
        })
        job.provider_status_json=_bounded_provider_json(provider)
        job.failures_json=_bounded_failures_json(failures)
        coverage=(classified/max(1,processed))*100.0 if processed else 0.0
        job.message=(f"기업 분류 {completed:,}/{total:,}개 완료 · 표준 테마 {classified:,}개 "
                     f"(강한 근거 {strong_classified:,} / 업종 보조 {fallback_classified:,}) · 무테마 {no_theme:,}개 · 오류 {len(failures):,}개")
        commit_or_rollback(db)
    coverage=(classified/max(1,total))*100.0 if total else 100.0
    return {"total":total,"processed":processed,"classified":classified,"engine_classified":classified,"strong_classified":strong_classified,"fallback_classified":fallback_classified,"low_confidence":low_confidence,"no_theme":no_theme,"unresolved":unresolved,"errors":len(failures),"coverage":round(coverage,2),"no_theme_examples":no_theme_examples}


async def _run_theme_normalize(admin_id:int):
    """Rebuild provider canonical names and every stock theme without Gemini."""
    global _theme_normalize_task
    current_task=asyncio.current_task()
    if not (_theme_normalize_task and not _theme_normalize_task.done()):
        _theme_normalize_task=current_task
    async with _theme_normalize_lock:
        db=SessionLocal();job=None;failures=[]
        try:
            schema=ensure_v3621_theme_canonical_schema()
            ensure_v367_theme_engine_schema()
            job=_theme_normalize_job(db)
            rows=db.query(Theme).filter(Theme.is_active==True).order_by(Theme.name.asc()).all()
            names=[]
            for row in rows:
                name=str(row.name or "").strip()
                if name and name not in names:
                    names.append(name)
            classification_estimate=int(db.query(Stock).filter(*_stocklog_public_clauses()).count())
            combined_estimate=max(1,len(names)+classification_estimate)
            job.running=True;job.phase="preparing";job.stage_label="표준 테마 체계 준비"
            job.item_total=len(names)+classification_estimate;job.item_completed=0;job.progress_value=0;job.success=0;job.failed=0
            job.current_name="";job.last_error="";job.failures_json="[]";job.started_at=datetime.now();job.finished_at=None
            job.requested_by_user_id=admin_id
            job.provider_status_json=_bounded_provider_json({
                "canonical_storage":bool(schema.get("available")),"batch":0,"batches":math.ceil(len(names)/100) if names else 0,
                "mapped":0,"changed":0,"canonical_count":0,"grouped_count":0,"examples":[],"current_status":"preparing",
                "theme_engine_version":THEME_ENGINE_VERSION,"taxonomy_groups":len(taxonomy_groups()),
            })
            job.message=f"활성 공급사 테마 {len(names):,}개를 StockLog 표준 테마 체계로 변환할 준비를 하고 있습니다."
            commit_or_rollback(db)

            mapping={}
            total_batches=max(1,math.ceil(len(names)/100)) if names else 0
            started=time.monotonic()
            for batch_index,start_index in enumerate(range(0,len(names),100),1):
                batch=names[start_index:start_index+100]
                job.phase="mapping_taxonomy";job.stage_label="공급사 테마 표준화";job.current_name=f"{batch[0]} ~ {batch[-1]}"
                job.message=f"{batch_index}/{total_batches} 묶음 · 공급사 테마를 상위 표준 테마로 매핑하고 있습니다."
                provider=json.loads(job.provider_status_json or "{}")
                provider.update({"batch":batch_index,"batches":total_batches,"current_status":"taxonomy_mapping","current_batch_size":len(batch)})
                job.provider_status_json=_bounded_provider_json(provider);commit_or_rollback(db)

                batch_mapping={}
                for raw in batch:
                    canonical=_clean_canonical_theme_name(canonical_group_for_theme(raw) or raw)
                    batch_mapping[raw]=canonical or raw
                    mapping[raw]=canonical or raw
                if schema.get("available"):
                    for raw,canonical in batch_mapping.items():
                        db.execute(text("UPDATE `themes` SET `canonical_name`=:canonical WHERE `is_active`=1 AND `name`=:raw"),{"canonical":canonical,"raw":raw})
                else:
                    for row in rows:
                        raw=str(row.name or "").strip()
                        if raw in batch_mapping:
                            row.name=batch_mapping[raw]
                completed=min(len(names),start_index+len(batch))
                elapsed=max(0.001,time.monotonic()-started)
                job.item_completed=completed
                job.progress_value=(completed/combined_estimate)*100.0
                job.success=completed;job.failed=len(failures)
                job.eta_seconds=max(0,(elapsed/max(1,completed))*(len(names)-completed)) if completed else 0
                canonical_count=len(set(mapping.values()))
                changed=sum(1 for raw,canonical in mapping.items() if raw!=canonical)
                examples=[{"from":r,"to":c} for r,c in mapping.items() if r!=c][-8:]
                provider.update({
                    "mapped":len(mapping),"changed":changed,"canonical_count":canonical_count,
                    "grouped_count":max(0,len(mapping)-canonical_count),"current_status":"taxonomy_saved","examples":examples,
                })
                job.provider_status_json=_bounded_provider_json(provider)
                job.message=f"공급사 테마 {completed:,}/{len(names):,}개 표준화 · 현재 대표 테마 {canonical_count:,}개"
                commit_or_rollback(db)

            classification_stats=await _classify_stock_business_themes(db,job,len(names),failures)

            display_rows=_theme_display_rows(db)
            canonical_count=len(set(row["display_name"] for row in display_rows if row.get("display_name")))
            raw_count=len(set(row["raw_name"] for row in display_rows if row.get("raw_name")))
            changed=sum(1 for row in display_rows if row.get("display_name")!=row.get("raw_name"))
            job.running=False;job.phase="completed";job.stage_label="표준 테마 재구축 완료";job.progress_value=100
            job.item_total=len(names)+classification_stats.get("total",0)
            job.item_completed=len(names)+classification_stats.get("processed",classification_stats.get("total",0))
            job.success=len(names)+classification_stats.get("classified",0)
            job.finished_at=datetime.now();job.eta_seconds=0
            provider=json.loads(job.provider_status_json or "{}")
            provider.update({
                "current_status":"completed","canonical_count":canonical_count,"raw_count":raw_count,"changed":changed,
                "grouped_count":max(0,raw_count-canonical_count),"classified":classification_stats.get("classified",0),
                "classification_total":classification_stats.get("total",0),"classification_processed":classification_stats.get("processed",0),
                "engine_classified":classification_stats.get("engine_classified",0),"strong_classified":classification_stats.get("strong_classified",0),
                "fallback_classified":classification_stats.get("fallback_classified",0),"low_confidence":classification_stats.get("low_confidence",0),
                "no_theme":classification_stats.get("no_theme",0),"unresolved":classification_stats.get("unresolved",0),
                "errors":classification_stats.get("errors",len(failures)),"classification_coverage":classification_stats.get("coverage",0),
                "no_theme_examples":classification_stats.get("no_theme_examples",[])[:12],
                "theme_engine_version":THEME_ENGINE_VERSION,"taxonomy_groups":len(taxonomy_groups()),
            })
            job.provider_status_json=_bounded_provider_json(provider)
            job.failures_json=_bounded_failures_json(failures)
            job.message=(f"StockLog 표준 테마 재구축 완료 · 공급사 테마 {raw_count:,}개 → 대표명 {canonical_count:,}개 · "
                         f"표준 테마 {classification_stats.get('classified',0):,}개 "
                         f"(강한 근거 {classification_stats.get('strong_classified',0):,} / 업종 보조 {classification_stats.get('fallback_classified',0):,}) · "
                         f"무테마 {classification_stats.get('no_theme',0):,}개 · 실제 오류 {classification_stats.get('errors',0):,}개")
            commit_or_rollback(db)
        except asyncio.CancelledError:
            rollback_quietly(db)
            try:
                job=_theme_normalize_job(db)
                job.running=False;job.phase="cancelled";job.stage_label="중지됨"
                job.current_name="";job.eta_seconds=0
                job.message="표준 테마 재구축을 중지했습니다. 이미 저장된 결과는 유지됩니다."
                job.finished_at=datetime.now();commit_or_rollback(db)
            except Exception:
                rollback_quietly(db)
            raise
        except Exception as exc:
            try: db.rollback()
            except Exception: pass
            try:
                job=_theme_normalize_job(db);job.running=False;job.phase="failed";job.stage_label="표준 테마 재구축 실패";job.last_error=_sync_error_text(exc);job.message=f"테마 재구축 중 오류가 발생했습니다: {_sync_error_text(exc)}";job.finished_at=datetime.now();commit_or_rollback(db)
            except Exception:
                try: db.rollback()
                except Exception: pass
            logger.exception("theme normalization failed")
        finally:
            db.close()
            if _theme_normalize_task is current_task:
                _theme_normalize_task=None


@app.get("/api/admin/theme-normalize/status")
def admin_theme_normalize_status(u:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _theme_normalize_task
    job=_theme_normalize_job(db)
    if job.running and not (_theme_normalize_task and not _theme_normalize_task.done()):
        # A backend restart cannot resume an in-memory Gemini task. Make that
        # explicit instead of leaving the administrator staring at a permanent
        # "running" state.
        job.running=False;job.phase="failed";job.stage_label="중단됨";job.last_error="백엔드 재시작으로 이전 표준 테마 재구축 작업이 중단되었습니다.";job.message=job.last_error;job.finished_at=datetime.now();commit_or_rollback(db)
    return _theme_normalize_json(job)


@app.post("/api/admin/theme-normalize")
async def admin_theme_normalize(u:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _theme_normalize_task
    if _theme_normalize_task and not _theme_normalize_task.done(): raise HTTPException(409,"표준 테마 재구축이 이미 진행 중입니다.")
    job=_theme_normalize_job(db)
    if job.running:
        job.running=False;job.phase="interrupted";job.finished_at=datetime.now();commit_or_rollback(db)
    job.running=True;job.phase="queued";job.stage_label="표준 테마 재구축 준비";job.progress_value=0;job.current_name="";job.last_error=""
    job.message="StockLog 표준 테마 엔진으로 전체 종목을 다시 분류합니다.";job.requested_by_user_id=u.id;job.started_at=datetime.now();job.finished_at=None
    commit_or_rollback(db)
    _theme_normalize_task=asyncio.create_task(_run_theme_normalize(u.id))
    return {"ok":True,"message":"StockLog 표준 테마 재구축을 시작했습니다. 진행상황을 실시간으로 표시합니다."}


@app.post("/api/admin/theme-sync/start")
async def admin_theme_sync_start(
    u:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    global _theme_sync_task

    if (
        _theme_sync_task
        and not _theme_sync_task.done()
    ):
        raise HTTPException(
            409,
            "이미 테마 동기화 작업이 진행 중입니다.",
        )

    stop_state=_theme_sync_stop_state()

    remaining=(
        stop_state.get(
            "restart_after_epoch",
            0,
        )
        - time.time()
    )

    if remaining > 0:
        raise HTTPException(
            409,
            (
                "이전 키움 요청 정리 대기 중입니다. "
                f"약 {math.ceil(remaining)}초 후 다시 시작해주세요."
            ),
        )

    run_id=(
        "theme-"
        + str(u.id)
        + "-"
        + str(time.time_ns())
    )

    if (
        _full_market_task
        and not _full_market_task.done()
    ):
        raise HTTPException(
            409,
            "키움/DART 데이터 동기화가 진행 중입니다. "
            "완료 후 테마 동기화를 실행해주세요.",
        )

    try:
        schema=(
            _require_theme_schema_ready()
        )
    except Exception as exc:
        raise HTTPException(
            500,
            {
                "message":(
                    "테마 동기화 시작 전 DB 컬럼 검증에 실패했습니다."
                ),
                "error":f"{type(exc).__name__}: {exc}",
            },
        )

    # Clear a persisted error from a previous failed run immediately.
    old_job=(
        db.query(FullMarketSyncState)
        .filter(
            FullMarketSyncState.key
            == THEME_SYNC_KEY
        )
        .first()
    )

    if old_job:
        try:
            old_provider=json.loads(
                old_job.provider_status_json
                or "{}"
            )
        except Exception:
            old_provider={}

        old_provider["run_id"]=run_id
        old_provider["cancelled_run_id"]=""
        old_provider["stop_requested"]=False
        old_provider["restart_after_epoch"]=0
        old_provider["current_status"]="starting"
        old_provider["current_status_message"]="새 테마 동기화를 준비 중입니다."

        old_job.provider_status_json=json.dumps(
            old_provider,
            ensure_ascii=False,
        )
        old_job.last_error=""
        old_job.message="새 테마 동기화를 준비 중입니다."
        old_job.phase="starting"
        old_job.running=False
        commit_or_rollback(db)

    if not old_job:
        old_job=_theme_sync_job(db)
        old_provider={
            "run_id":run_id,
            "stop_requested":False,
            "restart_after_epoch":0,
            "current_status":"starting",
            "current_status_message":"새 테마 동기화를 준비 중입니다.",
        }
        old_job.provider_status_json=json.dumps(
            old_provider,
            ensure_ascii=False,
        )
        old_job.running=False
        old_job.phase="starting"
        commit_or_rollback(db)

    client_for(u,db)

    _theme_sync_task=asyncio.create_task(
        _run_theme_sync(
            u.id,
            run_id,
        )
    )

    return {
        "ok":True,
        "message":(
            "키움 전체 테마 동기화를 시작했습니다. "
            "ka90001 목록 후 각 테마의 ka90002를 순차 처리합니다."
        ),
    }


@app.post("/api/admin/theme-sync/stop")
async def admin_theme_sync_stop(
    _:User=Depends(admin_user),
):
    global _theme_sync_task

    state=_write_theme_sync_stop_request()

    task_cancelled=False

    if (
        _theme_sync_task
        and not _theme_sync_task.done()
    ):
        _theme_sync_task.cancel()
        task_cancelled=True

    if state["already_cancelled"]:
        return {
            "ok":True,
            "already_stopped":True,
            "message":
                "테마 동기화는 이미 중지된 상태입니다.",
        }

    remaining=max(
        0,
        math.ceil(
            state["restart_after_epoch"]
            - time.time()
        ),
    )

    return {
        "ok":True,
        "cancelled":True,
        "task_cancelled":
            task_cancelled,
        "restart_after_seconds":
            remaining,
        "message":(
            "테마 동기화를 종료했습니다. "
            "완료된 테마 데이터는 유지됩니다. "
            + (
                f"새 동기화는 약 {remaining}초 후 시작할 수 있습니다."
                if remaining
                else ""
            )
        ),
    }


FULL_MARKET_SYNC_KEY="full_market"
FULL_MARKET_MARKETS=[("0","KOSPI"),("10","KOSDAQ")]
JOB_LABELS={"kiwoom":"키움 실제 시세·지표","dart":"OpenDART 재무","all":"전체 데이터"}

def _full_market_job(db):
    job=db.query(FullMarketSyncState).filter(FullMarketSyncState.key==FULL_MARKET_SYNC_KEY).first()
    if not job:
        job=FullMarketSyncState(key=FULL_MARKET_SYNC_KEY);db.add(job);commit_or_rollback(db);db.refresh(job)
    return job

def _provider_status(job):
    try:return json.loads(job.provider_status_json or "{}")
    except:return {}

def _full_market_json(job):
    try:failures=json.loads(job.failures_json or "[]")
    except:failures=[]
    return {
        "running":bool(job.running),"job_type":job.job_type or "all",
        "job_label":JOB_LABELS.get(job.job_type or "all",job.job_type or "all"),
        "phase":job.phase,"stage_label":job.stage_label or "",
        "item_total":job.item_total,"item_completed":job.item_completed,
        "success":job.success,"failed":job.failed,
        "progress":round(float(job.progress_value or 0),2),
        "current_code":job.current_code,"current_name":job.current_name,
        "current_market":job.current_market,"eta_seconds":round(float(job.eta_seconds or 0),1),
        "message":job.message,"last_error":job.last_error,
        "provider_status":_provider_status(job),"failures":failures[-30:],
        "started_at":job.started_at.isoformat() if job.started_at else None,
        "updated_at":job.updated_at.isoformat() if job.updated_at else None,
        "finished_at":job.finished_at.isoformat() if job.finished_at else None,
    }

def _analysis_exclusion_reason(item):
    """Return why a security is outside StockLog's public investment universe.

    Primary rule: when a KRX KIND listed-company snapshot was successfully
    loaded, only verified KOSPI/KOSDAQ listed-company codes are eligible.
    Name/type rules are a second guard and also provide a safe fallback if KIND
    is temporarily unavailable. Raw rows are retained only for historical/FK
    integrity; excluded rows must not be discoverable or newly traded.
    """
    name=str(item.get("name") or "").strip()
    upper=name.upper().replace(" ","")
    market=str(item.get("market") or "").upper()

    if market not in set(STOCKLOG_PUBLIC_MARKETS):
        return "KOSPI·KOSDAQ아님"

    # If the exchange-operated listed-company master was available, membership
    # in that verified company list is mandatory. This removes ETFs/ETNs/ELWs,
    # preferred/other classes and other listed products without guessing names.
    if bool(item.get("strict_kind_master")) and not bool(item.get("kind_verified")):
        return "KRX일반상장법인아님"

    if "ETN" in upper:
        return "ETN"
    if "ETF" in upper:
        return "ETF"
    if "스팩" in name or "SPAC" in upper or "기업인수목적" in name:
        return "SPAC"
    if "리츠" in name or "REIT" in upper or "부동산투자회사" in name:
        return "REITs"
    if "선박투자" in name or "투자회사" in name or name in {"맥쿼리인프라"}:
        return "투자상품형종목"

    # Fallback only: these product families matter when KIND is unavailable.
    etf_prefixes=(
        "KODEX","TIGER","RISE","ACE","SOL","HANARO","KOSEF",
        "ARIRANG","TIMEFOLIO","PLUS","FOCUS","WON","WOORI",
        "1Q","KBSTAR","TREX","SMART","MASTER",
    )
    if upper.startswith(etf_prefixes):
        return "ETF"

    # Preferred/other share classes are not part of the default ranking/trading
    # universe. KIND normally excludes them; suffix matching protects fallback.
    if re.search(r"(?:\d+)?우(?:B|C)?$", upper):
        return "우선주"

    return ""

def _classify_raw_universe(items):
    eligible=[]
    excluded=[]
    reasons={}
    for item in items:
        reason=_analysis_exclusion_reason(item)
        copied=dict(item)
        copied["is_analysis_eligible"]=not bool(reason)
        copied["analysis_exclusion_reason"]=reason or None
        if reason:
            excluded.append(copied)
            reasons[reason]=reasons.get(reason,0)+1
        else:
            eligible.append(copied)
    return eligible,excluded,reasons

def _upsert_stock_master(db,items):
    if not items:return
    codes=[x["code"] for x in items]
    existing={x.code:x for x in db.query(Stock).filter(Stock.code.in_(codes)).all()}
    now=datetime.now()
    for item in items:
        st=existing.get(item["code"])
        eligible=bool(item.get("is_analysis_eligible",True))
        reason=item.get("analysis_exclusion_reason")
        incoming_name=str(item.get("name") or "").strip()
        incoming_verified=bool(item.get("name_verified",True))
        incoming_source=str(item.get("name_source") or item.get("source") or "KIWOOM")
        incoming_aliases=[str(x).strip() for x in (item.get("name_aliases") or []) if str(x).strip()]
        if not st:
            st=Stock(
                code=item["code"],name=incoming_name or item["code"],market=item["market"],
                sector="기타",category="종합",is_active=True,
                is_analysis_eligible=eligible,analysis_exclusion_reason=reason,
                name_aliases_json=json.dumps([],ensure_ascii=False),
                name_source=incoming_source,
                name_verified_at=now if incoming_verified else None,
            );db.add(st); existing[item["code"]]=st
        else:
            aliases=_stock_name_aliases(st)
            for alias in incoming_aliases:
                if alias != incoming_name and alias not in aliases:
                    aliases.append(alias)
            current_name=str(st.name or "").strip()
            # Only verified master data may change an existing display name.
            if incoming_name and incoming_verified and incoming_name != current_name:
                if current_name and current_name not in aliases:
                    aliases.append(current_name)
                st.name=incoming_name
                st.name_changed_at=now
                st.name_verified_at=now
                st.name_source=incoming_source
            elif not st.name_source:
                st.name_source=incoming_source
            aliases=[a for a in aliases if a and a != str(st.name or "").strip()]
            st.name_aliases_json=json.dumps(aliases[:20],ensure_ascii=False)
            st.market=item["market"];st.is_active=True
            st.is_analysis_eligible=eligible
            st.analysis_exclusion_reason=reason
        st.universe_last_seen_at=now
        st.universe_missing_count=0
        st.updated_at=now
    commit_or_rollback(db)

def _deactivate_missing_stocks(db,active_codes,*,missing_threshold:int=3):
    """Deactivate only after repeated provider omissions.

    A single ka10099 snapshot can occasionally omit one or a few securities.
    v3.68.2 immediately deactivated those rows, which made valid KOSPI/KOSDAQ
    names disappear from Smart search. Keep previously active rows for up to
    ``missing_threshold-1`` consecutive misses and deactivate only on the
    threshold.
    """
    deactivated=0
    retained=0
    threshold=max(2,int(missing_threshold or 3))
    for st in db.query(Stock).filter(Stock.is_active==True).all():
        if st.code in active_codes:
            continue
        st.universe_missing_count=int(st.universe_missing_count or 0)+1
        if st.universe_missing_count>=threshold:
            st.is_active=False
            deactivated+=1
        else:
            retained+=1
    commit_or_rollback(db)
    return {"deactivated":deactivated,"retained":retained,"threshold":threshold}

async def _collect_clean_universe(cli,db,job):
    raw_universe=[];seen=set();counts={}
    for mt,mn in FULL_MARKET_MARKETS:
        job.phase="universe";job.stage_label="종목 Universe";job.message=f"키움 {mn} 실제 종목목록 확인 중";commit_or_rollback(db)
        _sync_diag("INFO",f"UNIVERSE_{mn}_START",{
            "market_type":str(mt),
            "kiwoom_runtime":cli.runtime_status(),
        })
        started_at=time.monotonic()
        try:
            rows=await cli.stock_info_list(mt,mn)
        except Exception as exc:
            _sync_diag("ERROR",f"UNIVERSE_{mn}_FAILED",{
                "market_type":str(mt),
                "elapsed_seconds":round(time.monotonic()-started_at,3),
                "kiwoom_runtime":cli.runtime_status(),
            },exc=exc)
            raise
        rows=[x for x in rows if re.fullmatch(r"\d{6}",str(x.get("code","")))]
        counts[mn]=len(rows)
        _sync_diag("INFO",f"UNIVERSE_{mn}_DONE",{
            "rows":len(rows),
            "elapsed_seconds":round(time.monotonic()-started_at,3),
            "kiwoom_runtime":cli.runtime_status(),
        })
        for row in rows:
            if row["code"] not in seen:
                seen.add(row["code"]);raw_universe.append(row)

    kiwoom_total=len(raw_universe)
    kind_rows=[]
    kind_error=""
    try:
        # KRX KIND is a second, exchange-operated listed-company master. Merge
        # it before any deactivation decision so a valid company cannot vanish
        # because one Kiwoom ka10099 snapshot omitted it.
        _sync_diag("INFO","UNIVERSE_KIND_START",{"kiwoom_rows":len(raw_universe)})
        kind_started=time.monotonic()
        kind_rows=await asyncio.to_thread(fetch_kind_company_master, force=True)
        raw_universe,merge_stats=merge_company_master(raw_universe,kind_rows)
        for _row in raw_universe:
            _row["strict_kind_master"]=True
        _sync_diag("INFO","UNIVERSE_KIND_DONE",{
            "kind_rows":len(kind_rows),
            "merged_rows":len(raw_universe),
            "elapsed_seconds":round(time.monotonic()-kind_started,3),
        })
        seen={str(x.get("code") or "") for x in raw_universe}
    except Exception as exc:
        kind_error=f"{exc.__class__.__name__}: {exc}"
        _sync_diag("WARNING","UNIVERSE_KIND_FAILED",{
            "kiwoom_rows":len(raw_universe),
            "error":kind_error,
        },exc=exc)
        merge_stats={
            "primary_total":kiwoom_total,
            "merged_total":len(raw_universe),
            "kind_added_missing_from_primary":0,
            "kind_verified_existing":0,
        }
        logger.warning("KRX KIND Universe 보강 실패: %s",kind_error)

    raw_total=len(raw_universe)
    existing_active=db.query(Stock).filter(Stock.is_active==True).count()

    # Wide sanity bounds: ka10099 contains listed securities, not just companies.
    if raw_total < 2000 or raw_total > 7000:
        raise RuntimeError(
            "키움 원본 Universe 개수가 비정상입니다. "
            +f"총 {raw_total:,}개 / "
            +" / ".join(f"{k} {v:,}개" for k,v in counts.items())
            +". DB 반영을 중단했습니다."
        )
    if counts.get("KOSPI",0)<500 or counts.get("KOSDAQ",0)<500:
        raise RuntimeError(
            "키움 시장별 Universe가 비정상적으로 적습니다. "
            +" / ".join(f"{k} {v:,}개" for k,v in counts.items())
            +". 일시적인 API 누락 가능성이 있어 DB 반영을 중단했습니다."
        )
    # A sudden collapse versus the existing DB is a stronger failure signal than
    # an absolute total count. Increases are intentionally allowed.
    if existing_active>=2000 and raw_total < int(existing_active*0.55):
        raise RuntimeError(
            f"키움 Universe가 기존 활성 {existing_active:,}개 대비 "
            f"{raw_total:,}개로 급감했습니다. DB 보호를 위해 반영을 중단했습니다."
        )

    analysis_universe,excluded,reasons=_classify_raw_universe(raw_universe)
    analysis_total=len(analysis_universe)
    if analysis_total<1200:
        raise RuntimeError(
            f"StockLog 분석 대상 종목이 {analysis_total:,}개로 지나치게 적습니다. "
            "증권 종류 분류 결과를 확인해주세요. DB 반영을 중단했습니다."
        )

    # Preserve raw master rows for historical/FK safety, but only the verified
    # public universe is synchronized/analyzed/exposed to users.
    classified=analysis_universe+excluded
    _upsert_stock_master(db,classified)
    missing_state=_deactivate_missing_stocks(db,seen,missing_threshold=3)
    status=_provider_status(job)
    status["universe"]={
        "raw_total":raw_total,
        "analysis_total":analysis_total,
        "excluded_total":len(excluded),
        "total":raw_total,
        "markets":counts,
        "exclusion_reasons":reasons,
        "previous_active":existing_active,
        "deactivated_old_rows":int(missing_state.get("deactivated") or 0),
        "retained_missing_rows":int(missing_state.get("retained") or 0),
        "missing_deactivate_threshold":int(missing_state.get("threshold") or 3),
        "kiwoom_raw_total":kiwoom_total,
        "krx_kind_total":len(kind_rows),
        "krx_kind_error":kind_error or None,
        "krx_kind_added_missing_from_kiwoom":int(merge_stats.get("kind_added_missing_from_primary") or 0),
        "krx_kind_verified_existing":int(merge_stats.get("kind_verified_existing") or 0),
        "official_name_changes":int(merge_stats.get("official_name_changes") or 0),
        "unverified_name_overwrites_blocked":int(merge_stats.get("unverified_name_overwrites_blocked") or 0),
    }
    job.provider_status_json=json.dumps(status,ensure_ascii=False);commit_or_rollback(db)
    job.message=(
        f"종목 마스터 {raw_total:,}개 확인 · StockLog 분석 대상 {analysis_total:,}개 "
        f"· 제외 {len(excluded):,}개"
        + (f" · KRX가 키움 누락 {int(merge_stats.get('kind_added_missing_from_primary') or 0):,}개 보강" if kind_rows else "")
    );commit_or_rollback(db)
    return analysis_universe

def _set_progress(job,db,done,total,pct,started):
    job.item_completed=int(done);job.item_total=int(total);job.progress_value=max(0,min(100,float(pct)))
    elapsed=max(time.monotonic()-started,.1)
    job.eta_seconds=elapsed*(100-pct)/pct if 0<pct<100 else 0
    commit_or_rollback(db)

BULK_PROVIDER_CIRCUIT_THRESHOLD=6

async def _provider_call_with_retry(call_factory,max_attempts:int=3):
    """Execute an external provider coroutine with bounded transient retries."""
    retries=0
    last_exc=None
    for attempt in range(1,max_attempts+1):
        try:
            return await call_factory(),retries,"ok",None
        except Exception as exc:
            last_exc=exc
            kind=classify_flow_error(exc)
            if kind=="no_data":
                return None,retries,"no_data",exc
            if kind!="transient" or attempt>=max_attempts:
                return None,retries,kind,exc
            retries+=1
            await asyncio.sleep(retry_delay_seconds(attempt))
    return None,retries,"hard",last_exc


def _sync_provider_counters(status:dict,key:str):
    current=status.get(key) if isinstance(status.get(key),dict) else {}
    defaults={
        "retried":0,"transient_recovered":0,"skipped":0,"cached":0,
        "hard_failures":0,"deferred":0,
    }
    defaults.update(current)
    status[key]=defaults
    return defaults

async def _run_kiwoom_part(admin_id,db,job,start_pct,span,started):
    # Fail before issuing any provider requests if a deployment is missing a
    # required helper.  This prevents one code defect from being retried once per
    # symbol and producing thousands of duplicate diagnostic entries.
    _sync_diag("INFO","KIWOOM_RUNTIME_VALIDATE_START")
    _validate_kiwoom_sync_runtime()
    _sync_diag("INFO","KIWOOM_RUNTIME_VALIDATE_DONE")
    _sync_diag("INFO","KIWOOM_ADMIN_LOAD_START",{"admin_id":admin_id})
    admin=db.query(User).filter(User.id==admin_id).first()
    if not admin:
        raise RuntimeError("관리자 계정을 찾지 못했습니다.")
    _,cli=client_for(admin,db)
    commit_or_rollback(db)
    _sync_diag("INFO","KIWOOM_ADMIN_LOAD_DONE",{
        "use_mock":bool(cli.use_mock),
        "token_cached":bool(cli.token),
        "kiwoom_runtime":cli.runtime_status(),
    })
    _sync_diag("INFO","KIWOOM_TOKEN_START",{"kiwoom_runtime":cli.runtime_status()})
    token_started=time.monotonic()
    try:
        token_info=await cli.issue_token()
    except Exception as exc:
        _sync_diag("ERROR","KIWOOM_TOKEN_FAILED",{
            "elapsed_seconds":round(time.monotonic()-token_started,3),
            "kiwoom_runtime":cli.runtime_status(),
        },exc=exc)
        raise
    _sync_diag("INFO","KIWOOM_TOKEN_READY",{
        "cached":bool(token_info.get("cached")) if isinstance(token_info,dict) else False,
        "elapsed_seconds":round(time.monotonic()-token_started,3),
        "kiwoom_runtime":cli.runtime_status(),
    })

    _sync_diag("INFO","KIWOOM_UNIVERSE_START",{"kiwoom_runtime":cli.runtime_status()})
    universe=await _collect_clean_universe(cli,db,job)
    _sync_diag("INFO","KIWOOM_UNIVERSE_DONE",{"stocks":len(universe),"kiwoom_runtime":cli.runtime_status()})
    n=len(universe)
    job.item_total=n;job.item_completed=0
    commit_or_rollback(db)

    failures=json.loads(job.failures_json or "[]")
    provider=_provider_status(job)
    stats=_sync_provider_counters(provider,"kiwoom")
    stats.setdefault("deferred_price_stocks",0)
    stats.setdefault("deferred_metric_stocks",0)
    stats.setdefault("provider_circuit_open",False)
    stats.setdefault("provider_circuit_reason","")
    price_consecutive_transient=0
    price_circuit_open=False

    _sync_diag("INFO","KIWOOM_INDEX_START",{"api_id":"ka20006","kiwoom_runtime":cli.runtime_status()})
    index_started=time.monotonic()
    result,retries,outcome,exc=await _provider_call_with_retry(
        lambda: cli.daily_kospi_chart(max_rows=500)
    )
    _sync_diag("INFO" if outcome in ("ok","no_data") else "ERROR","KIWOOM_INDEX_DONE",{
        "outcome":outcome,
        "retries":retries,
        "elapsed_seconds":round(time.monotonic()-index_started,3),
        "kiwoom_runtime":cli.runtime_status(),
    },exc=exc if outcome not in ("ok","no_data") else None)
    stats["retried"]+=retries
    if outcome=="ok":
        kr,_=result
        if kr:
            _upsert_price_rows(db,KOSPI_CACHE_CODE,kr)
            if retries:
                stats["transient_recovered"]+=1
        else:
            stats["skipped"]+=1
    elif outcome=="no_data":
        stats["skipped"]+=1
    else:
        rollback_quietly(db)
        job.failed=int(job.failed or 0)+1
        stats["hard_failures"]+=1
        failures.append({"code":KOSPI_CACHE_CODE,"name":"KOSPI","phase":"kiwoom-index","error":_sync_error_text(exc or RuntimeError(outcome),500)})

    max_rows=int(os.getenv("FULL_MARKET_DAILY_MAX_ROWS","500"))
    for i,item in enumerate(universe,1):
        job.phase="kiwoom-prices";job.stage_label="실제 일봉"
        job.current_code=item["code"];job.current_name=item["name"];job.current_market=item["market"]
        job.message=f"키움 일봉 {item['name']} ({item['code']})"
        commit_or_rollback(db)

        result,retries,outcome,exc=await _provider_call_with_retry(
            lambda code=item["code"]: cli.daily_stock_chart(code,max_rows=max_rows)
        )
        stats["retried"]+=retries
        if outcome=="ok":
            price_consecutive_transient=0
            rows,_=result
            if not rows:
                stats["skipped"]+=1
            else:
                try:
                    _upsert_price_rows(db,item["code"],rows)
                    st=db.query(Stock).filter(Stock.code==item["code"]).first()
                    if st:
                        _update_real_market_metrics(st,rows)
                        recalculate_price_multiples(st)
                        st.category=classify_stock(st)
                        st.score=compute_score(st)[0]
                        commit_or_rollback(db)
                    job.success=int(job.success or 0)+1
                    if retries:
                        stats["transient_recovered"]+=1
                except Exception as save_exc:
                    rollback_quietly(db)
                    # A programming/deployment defect is not a per-stock failure.
                    # Abort immediately so it is captured once by the unified
                    # runner instead of repeated for every symbol in the universe.
                    if _sync_programming_error(save_exc):
                        _sync_error_text(save_exc,1200)
                        raise RuntimeError(
                            f"Kiwoom price synchronization code failure at {item['name']} ({item['code']}): {save_exc}"
                        ) from save_exc
                    job.failed=int(job.failed or 0)+1
                    stats["hard_failures"]+=1
                    failures.append({"code":item["code"],"name":item["name"],"phase":"kiwoom-prices-save","error":_sync_error_text(save_exc,500)})
        elif outcome=="no_data":
            price_consecutive_transient=0
            stats["skipped"]+=1
        elif outcome=="transient":
            rollback_quietly(db)
            price_consecutive_transient+=1
            stats["deferred"]+=1
            stats["deferred_price_stocks"]+=1
            failures.append({
                "code":item["code"],"name":item["name"],"phase":"kiwoom-prices",
                "kind":"transient","deferred":True,
                "error":_sync_error_text(exc or RuntimeError(outcome),500),
            })
            if provider_circuit_should_open(price_consecutive_transient,threshold=BULK_PROVIDER_CIRCUIT_THRESHOLD):
                price_circuit_open=True
                stats["provider_circuit_open"]=True
                stats["provider_circuit_reason"]=(
                    f"키움 시세가 {price_consecutive_transient}개 종목 연속 일시 실패하여 남은 요청을 다음 실행으로 보류합니다."
                )
        else:
            rollback_quietly(db)
            price_consecutive_transient=0
            job.failed=int(job.failed or 0)+1
            stats["hard_failures"]+=1
            failures.append({"code":item["code"],"name":item["name"],"phase":"kiwoom-prices","error":_sync_error_text(exc or RuntimeError(outcome),500)})

        failures=failures[-64:]
        job.failures_json=_bounded_failures_json(failures)
        if i%10==0 or i==n:
            provider["kiwoom"]=stats
            job.provider_status_json=_bounded_provider_json(provider)
        _set_progress(job,db,i,n,start_pct+span*(i/max(n,1)*.5),started)
        if i==1 or i%100==0 or i==n:
            _sync_diag("INFO","KIWOOM_PRICES_PROGRESS",{
                "completed":i,"total":n,"current_code":item["code"],"current_name":item["name"],
                "success":int(job.success or 0),"failed":int(job.failed or 0),
                "kiwoom_runtime":cli.runtime_status(),
            })

        if price_circuit_open:
            remaining=max(0,n-i)
            stats["deferred"]+=remaining
            stats["deferred_price_stocks"]+=remaining
            provider["kiwoom"]=stats
            job.provider_status_json=_bounded_provider_json(provider)
            job.message=stats["provider_circuit_reason"]
            commit_or_rollback(db)
            _sync_diag("WARNING","KIWOOM_PRICE_CIRCUIT_OPEN",{
                "completed":i,"total":n,"deferred":remaining,"reason":stats["provider_circuit_reason"]
            })
            break

    metric_universe=universe
    if price_circuit_open:
        # A provider-wide outage detected in the price phase is not useful to
        # probe another 2,500 times in the metrics phase. Defer that phase too.
        metric_universe=[]
        stats["deferred"]+=n
        stats["deferred_metric_stocks"]+=n
    metric_consecutive_transient=0
    metric_circuit_open=False
    _sync_diag("INFO","KIWOOM_METRICS_PHASE_START",{"stocks":len(metric_universe),"kiwoom_runtime":cli.runtime_status()})
    for i,item in enumerate(metric_universe,1):
        job.phase="kiwoom-metrics";job.stage_label="PER·PBR·EPS·BPS"
        job.current_code=item["code"];job.current_name=item["name"];job.current_market=item["market"]
        job.message=f"키움 지표 {item['name']} ({item['code']})"
        commit_or_rollback(db)

        metrics,retries,outcome,exc=await _provider_call_with_retry(
            lambda code=item["code"]: cli.stock_basic_metrics(code)
        )
        stats["retried"]+=retries
        if outcome=="ok":
            metric_consecutive_transient=0
            if not metrics:
                stats["skipped"]+=1
            else:
                try:
                    st=db.query(Stock).filter(Stock.code==item["code"]).first()
                    if st:
                        _apply_kiwoom_stock_metrics(st,metrics)
                        st.category=classify_stock(st)
                        st.score=compute_score(st)[0]
                        commit_or_rollback(db)
                    job.success=int(job.success or 0)+1
                    if retries:
                        stats["transient_recovered"]+=1
                except Exception as save_exc:
                    rollback_quietly(db)
                    if _sync_programming_error(save_exc):
                        _sync_error_text(save_exc,1200)
                        raise RuntimeError(
                            f"Kiwoom metrics synchronization code failure at {item['name']} ({item['code']}): {save_exc}"
                        ) from save_exc
                    job.failed=int(job.failed or 0)+1
                    stats["hard_failures"]+=1
                    failures.append({"code":item["code"],"name":item["name"],"phase":"kiwoom-metrics-save","error":_sync_error_text(save_exc,500)})
        elif outcome=="no_data":
            metric_consecutive_transient=0
            stats["skipped"]+=1
        elif outcome=="transient":
            rollback_quietly(db)
            metric_consecutive_transient+=1
            stats["deferred"]+=1
            stats["deferred_metric_stocks"]+=1
            failures.append({
                "code":item["code"],"name":item["name"],"phase":"kiwoom-metrics",
                "kind":"transient","deferred":True,
                "error":_sync_error_text(exc or RuntimeError(outcome),500),
            })
            if provider_circuit_should_open(metric_consecutive_transient,threshold=BULK_PROVIDER_CIRCUIT_THRESHOLD):
                metric_circuit_open=True
                stats["provider_circuit_open"]=True
                stats["provider_circuit_reason"]=(
                    f"키움 종목지표가 {metric_consecutive_transient}개 종목 연속 일시 실패하여 남은 요청을 다음 실행으로 보류합니다."
                )
        else:
            rollback_quietly(db)
            metric_consecutive_transient=0
            job.failed=int(job.failed or 0)+1
            stats["hard_failures"]+=1
            failures.append({"code":item["code"],"name":item["name"],"phase":"kiwoom-metrics","error":_sync_error_text(exc or RuntimeError(outcome),500)})

        failures=failures[-64:]
        job.failures_json=_bounded_failures_json(failures)
        if i%10==0 or i==len(metric_universe):
            provider["kiwoom"]=stats
            job.provider_status_json=_bounded_provider_json(provider)
        _set_progress(job,db,i,n,start_pct+span*(.5+i/max(n,1)*.5),started)
        if i==1 or i%100==0 or i==len(metric_universe):
            _sync_diag("INFO","KIWOOM_METRICS_PROGRESS",{
                "completed":i,"total":len(metric_universe),"current_code":item["code"],"current_name":item["name"],
                "success":int(job.success or 0),"failed":int(job.failed or 0),
                "kiwoom_runtime":cli.runtime_status(),
            })

        if metric_circuit_open:
            remaining=max(0,len(metric_universe)-i)
            stats["deferred"]+=remaining
            stats["deferred_metric_stocks"]+=remaining
            provider["kiwoom"]=stats
            job.provider_status_json=_bounded_provider_json(provider)
            job.message=stats["provider_circuit_reason"]
            commit_or_rollback(db)
            _sync_diag("WARNING","KIWOOM_METRIC_CIRCUIT_OPEN",{
                "completed":i,"total":len(metric_universe),"deferred":remaining,"reason":stats["provider_circuit_reason"]
            })
            break

    stats.update({"ok":int(stats.get("hard_failures") or 0)==0 and not bool(stats.get("deferred")),"stocks":n})
    _sync_diag("INFO","KIWOOM_PART_DONE",{
        "stocks":n,"success":int(job.success or 0),"failed":int(job.failed or 0),
        "stats":stats,"kiwoom_runtime":cli.runtime_status(),
    })
    provider["kiwoom"]=stats
    job.provider_status_json=_bounded_provider_json(provider)
    job.failures_json=_bounded_failures_json(failures)
    commit_or_rollback(db)

async def _run_dart_part(db,job,start_pct,span,started):
    if not (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip():
        raise RuntimeError("OpenDART API 키가 설정되지 않았습니다.")

    universe=(db.query(Stock).filter(
        *_stocklog_public_clauses()
    ).order_by(Stock.code.asc()).all())
    if not universe:
        raise RuntimeError("활성 종목 Universe가 없습니다. 먼저 키움 데이터 가져오기를 실행해주세요.")

    n=len(universe)
    job.item_total=n;job.item_completed=0;job.phase="dart-corp";job.stage_label="DART 고유번호"
    job.message="OpenDART corp_code 매핑 중"
    commit_or_rollback(db)
    try:
        result=await asyncio.wait_for(sync_dart_corp_codes(db),timeout=120)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("OpenDART corpCode 동기화가 120초를 초과했습니다.") from exc
    if not result.get("configured"):
        raise RuntimeError(result.get("message","OpenDART 설정 필요"))

    failures=json.loads(job.failures_json or "[]")
    provider=_provider_status(job)
    stats=_sync_provider_counters(provider,"dart")
    stats.setdefault("no_corp_code",0)
    stats.setdefault("no_financials",0)
    stats.setdefault("optional_warnings",0)
    stats.setdefault("provider_circuit_open",False)
    stats.setdefault("provider_circuit_reason","")
    ttl_hours=max(1,int(os.getenv("DART_FINANCIAL_SYNC_TTL_HOURS","24")))
    cutoff=datetime.now()-timedelta(hours=ttl_hours)
    stats["cache_ttl_hours"]=ttl_hours
    dart_consecutive_transient=0

    for i,st in enumerate(universe,1):
        job.phase="dart-financials";job.stage_label="실제 재무제표"
        job.current_code=st.code;job.current_name=st.name;job.current_market=st.market
        job.message=f"OpenDART 재무 {st.name} ({st.code})"
        commit_or_rollback(db)

        try:
            db.refresh(st)
            has_recent_financial=(
                st.dart_financials_updated_at is not None
                and st.dart_financials_updated_at>=cutoff
                and db.query(FinancialQuarter.id).filter(FinancialQuarter.stock_code==st.code).first() is not None
            )
            # Snapshot reads are now complete. HTTP calls below obtain provider
            # credentials through their own short-lived session/cache instead of
            # keeping this long-running synchronization session checked out.
            commit_or_rollback(db)
            if has_recent_financial:
                dart_consecutive_transient=0
                stats["cached"]+=1
                job.success=int(job.success or 0)+1
                _set_progress(job,db,i,n,start_pct+span*(i/max(n,1)),started)
                continue

            if not st.corp_code:
                dart_consecutive_transient=0
                stats["skipped"]+=1
                stats["no_corp_code"]+=1
                _set_progress(job,db,i,n,start_pct+span*(i/max(n,1)),started)
                continue

            # Company profile enriches classification but is not required for
            # financial synchronization.  Do not fail a stock solely because
            # this optional endpoint is unavailable.
            try:
                profile=await fetch_dart_company_profile(st,db=None)
                if profile:
                    _apply_dart_industry_profile(st,profile)
                    commit_or_rollback(db)
            except Exception as optional_exc:
                rollback_quietly(db)
                if classify_flow_error(optional_exc)=="transient" and any(
                    token in str(optional_exc).lower() for token in ("사용한도","한도 초과","quota")
                ):
                    raise
                stats["optional_warnings"]+=1

            rows,retries,outcome,exc=await _provider_call_with_retry(
                lambda stock=st: fetch_dart_financials(stock,None)
            )
            stats["retried"]+=retries
            if outcome=="no_data" or (outcome=="ok" and not rows):
                dart_consecutive_transient=0
                stats["skipped"]+=1
                stats["no_financials"]+=1
                _set_progress(job,db,i,n,start_pct+span*(i/max(n,1)),started)
                continue
            if outcome!="ok":
                raise exc or RuntimeError(outcome)
            dart_consecutive_transient=0
            if retries:
                stats["transient_recovered"]+=1

            upsert_financials(st.code,rows,db)

            share_info=None
            try:
                share_info=await fetch_dart_share_count(st,rows,db=None)
            except Exception as optional_exc:
                rollback_quietly(db)
                if classify_flow_error(optional_exc)=="transient" and any(
                    token in str(optional_exc).lower() for token in ("사용한도","한도 초과","quota")
                ):
                    raise
                stats["optional_warnings"]+=1

            valuation=calculate_dart_valuation(st,rows,share_info)
            if apply_dart_valuation(st,valuation):
                try:
                    dividend=await fetch_dart_dividend_yield(st,rows,db=None)
                    if dividend and dividend.get("yield") is not None:
                        st.dividend_yield=dividend["yield"]
                except Exception as optional_exc:
                    rollback_quietly(db)
                    if classify_flow_error(optional_exc)=="transient" and any(
                        token in str(optional_exc).lower() for token in ("사용한도","한도 초과","quota")
                    ):
                        raise
                    stats["optional_warnings"]+=1
            else:
                # Missing valuation inputs are a data-quality limitation, not
                # an API/transaction failure.  Financial rows are still valid.
                stats["skipped"]+=1

            st.dart_financials_updated_at=datetime.now()
            st.category=classify_stock(st)
            st.score=compute_score(st)[0]
            st.updated_at=datetime.now()
            commit_or_rollback(db)
            job.success=int(job.success or 0)+1

        except Exception as ex:
            rollback_quietly(db)
            kind=classify_flow_error(ex)
            quota_exhausted=(kind=="transient" and is_quota_like_error(ex))
            if quota_exhausted:
                remaining=max(0,n-i+1)
                stats["deferred"]+=remaining
                stats["deferred_reason"]="OpenDART 사용한도에 도달해 남은 종목을 다음 동기화로 보류했습니다."
                stats["provider_circuit_open"]=True
                stats["provider_circuit_reason"]=stats["deferred_reason"]
                job.message=(
                    f"OpenDART 사용한도 도달 · 남은 {remaining:,}종목은 실패 처리하지 않고 다음 실행으로 보류합니다."
                )
                provider["dart"]=stats
                job.provider_status_json=_bounded_provider_json(provider)
                job.failures_json=_bounded_failures_json(failures)
                commit_or_rollback(db)
                break

            if kind=="transient":
                dart_consecutive_transient+=1
                stats["deferred"]+=1
                failures.append({
                    "code":st.code,"name":st.name,"phase":"dart-financials",
                    "kind":"transient","deferred":True,"error":_sync_error_text(ex,500),
                })
                failures=failures[-64:]
                if provider_circuit_should_open(dart_consecutive_transient,threshold=BULK_PROVIDER_CIRCUIT_THRESHOLD):
                    remaining=max(0,n-i)
                    stats["deferred"]+=remaining
                    stats["provider_circuit_open"]=True
                    stats["provider_circuit_reason"]=(
                        f"OpenDART가 {dart_consecutive_transient}개 종목 연속 일시 실패하여 "
                        f"남은 {remaining:,}종목을 다음 동기화로 보류했습니다."
                    )
                    stats["deferred_reason"]=stats["provider_circuit_reason"]
                    job.message=stats["provider_circuit_reason"]
                    provider["dart"]=stats
                    job.provider_status_json=_bounded_provider_json(provider)
                    job.failures_json=_bounded_failures_json(failures)
                    commit_or_rollback(db)
                    break
                job.failures_json=_bounded_failures_json(failures)
                _set_progress(job,db,i,n,start_pct+span*(i/max(n,1)),started)
                continue

            dart_consecutive_transient=0
            job.failed=int(job.failed or 0)+1
            stats["hard_failures"]+=1
            failures.append({
                "code":st.code,"name":st.name,"phase":"dart-financials",
                "kind":kind,"error":_sync_error_text(ex,500),
            })
            failures=failures[-64:]

        job.failures_json=_bounded_failures_json(failures)
        if i%10==0 or i==n:
            provider["dart"]=stats
            job.provider_status_json=_bounded_provider_json(provider)
        _set_progress(job,db,i,n,start_pct+span*(i/max(n,1)),started)

    stats.update({
        "ok":int(stats.get("hard_failures") or 0)==0 and not bool(stats.get("deferred")),
        "stocks":n,
    })
    provider["dart"]=stats
    job.provider_status_json=_bounded_provider_json(provider)
    job.failures_json=_bounded_failures_json(failures)
    commit_or_rollback(db)

async def _run_market_data_sync(admin_id,mode,rebuild_scores=True):
    _sync_diag("INFO","MARKET_DATA_SYNC_WAIT_LOCK",{"mode":mode})
    async with _full_market_lock:
        _sync_diag("INFO","MARKET_DATA_SYNC_LOCK_ACQUIRED",{"mode":mode})
        db=SessionLocal();job=None;started=time.monotonic()
        try:
            job=_full_market_job(db);job.running=True;job.job_type=mode;job.phase="starting";job.stage_label="준비";job.item_total=0;job.item_completed=0;job.progress_value=0;job.success=0;job.failed=0;job.current_code="";job.current_name="";job.current_market="";job.eta_seconds=0;job.message=f"{JOB_LABELS[mode]} 수집 시작";job.failures_json="[]";job.provider_status_json="{}";job.last_error="";job.requested_by_user_id=admin_id;job.started_at=datetime.now();job.finished_at=None;commit_or_rollback(db)
            if mode=="kiwoom":await _run_kiwoom_part(admin_id,db,job,0,100,started)
            elif mode=="dart":await _run_dart_part(db,job,0,100,started)
            elif mode=="all":
                await _run_kiwoom_part(admin_id,db,job,0,67,started)
                await _run_dart_part(db,job,67,33,started)
            else:raise RuntimeError(f"지원하지 않는 mode {mode}")
            provider=_provider_status(job)
            ki_stats=provider.get("kiwoom") if isinstance(provider.get("kiwoom"),dict) else {}
            dart_stats=provider.get("dart") if isinstance(provider.get("dart"),dict) else {}
            skipped=int(ki_stats.get("skipped") or 0)+int(dart_stats.get("skipped") or 0)
            cached=int(dart_stats.get("cached") or 0)
            deferred=(
                int(ki_stats.get("deferred") or 0)
                +int(dart_stats.get("deferred") or 0)
            )
            retried=int(ki_stats.get("retried") or 0)+int(dart_stats.get("retried") or 0)
            has_warnings=(int(job.failed or 0)>0 or deferred>0)
            job.running=False
            job.phase="partial" if has_warnings else "completed"
            job.stage_label="완료(보강 필요)" if deferred and not int(job.failed or 0) else ("완료" if not has_warnings else "완료(일부 실패)")
            job.current_code="";job.current_name="";job.current_market="";job.progress_value=100;job.eta_seconds=0
            job.message=(
                f"{JOB_LABELS[mode]} 수집 완료 · 성공 {int(job.success or 0):,} / "
                f"정상 스킵 {skipped:,} / 캐시 {cached:,} / 자동 재시도 {retried:,} / "
                f"다음 실행 보류 {deferred:,} / 최종 실패 {int(job.failed or 0):,}"
            )
            # Individual market/financial syncs refresh Smart scores for convenience.
            # Unified sync controls this as its own selectable stage.
            if rebuild_scores:
                try:
                    provider["smart_score_cache"]=_rebuild_smart_score_cache(db)
                    job.provider_status_json=_bounded_provider_json(provider)
                    job.message += " · 스마트 점수 갱신"
                except Exception as cache_exc:
                    rollback_quietly(db)
                    job=_full_market_job(db)
                    provider=_provider_status(job)
                    provider["smart_score_cache_warning"]=_sync_error_text(cache_exc,500)
                    job.provider_status_json=_bounded_provider_json(provider)
                    logger.exception("smart score cache rebuild after market sync failed")
            job.finished_at=datetime.now()
            commit_or_rollback(db)
        except asyncio.CancelledError:
            rollback_quietly(db)
            try:
                job=_full_market_job(db)
                job.running=False;job.phase="cancelled";job.stage_label="중지"
                job.message="관리자 요청으로 중지되었습니다. 이미 저장된 데이터는 유지됩니다."
                job.finished_at=datetime.now();commit_or_rollback(db)
            except Exception:
                rollback_quietly(db)
                logger.exception("market sync cancellation state persistence failed mode=%s",mode)
            raise
        except Exception as ex:
            logger.exception("market data sync failed mode=%s",mode)
            rollback_quietly(db)
            # rollback() expires ORM state. Never read the old `job` object here:
            # doing so caused a second pool checkout timeout while handling the
            # first timeout, leaving running=true forever. Re-fetch explicitly.
            try:
                job=_full_market_job(db)
                job.running=False;job.phase="failed";job.stage_label="실패"
                job.last_error=_sync_error_text(ex,3000)
                job.message=f"{JOB_LABELS.get(mode,mode)} 수집 중단"
                job.finished_at=datetime.now();commit_or_rollback(db)
            except Exception:
                rollback_quietly(db)
                logger.exception("market sync failure state persistence failed mode=%s",mode)
        finally:db.close()

CLASSIFICATION_SYNC_KEY="classification_sync"
_classification_sync_task=None
_classification_sync_lock=asyncio.Lock()

# A full KOSPI/KOSDAQ company-profile pass can contain thousands of OpenDART
# requests. Keep the primary pass visibly below 100%, reserve a small tail for
# bounded retries/finalization, and never let provider degradation pin the UI at
# 99% for hours.
CLASSIFICATION_MAIN_PROGRESS_MAX=92.0
CLASSIFICATION_RETRY_PROGRESS_MAX=98.5
CLASSIFICATION_BAD_BATCH_CIRCUIT_THRESHOLD=3
CLASSIFICATION_TAIL_RETRY_LIMIT=12
CLASSIFICATION_TAIL_RETRY_BUDGET_SECONDS=90.0
CLASSIFICATION_TAIL_RETRY_TIMEOUT_SECONDS=6.0


def _classification_job(db: Session):
    job=(
        db.query(FullMarketSyncState)
        .filter(FullMarketSyncState.key==CLASSIFICATION_SYNC_KEY)
        .first()
    )
    if not job:
        job=FullMarketSyncState(
            key=CLASSIFICATION_SYNC_KEY,
            running=False,
            phase="idle",
            job_type="classification",
        )
        db.add(job)
        commit_or_rollback(db)
        db.refresh(job)
    return job


def _classification_json(job):
    try:
        provider=json.loads(job.provider_status_json or "{}")
    except Exception:
        provider={}
    return {
        "running":bool(job.running),
        "phase":job.phase,
        "stage_label":job.stage_label,
        "item_total":job.item_total,
        "item_completed":job.item_completed,
        "progress":job.progress_value,
        "success":job.success,
        "failed":job.failed,
        "current_code":job.current_code,
        "current_name":job.current_name,
        "eta_seconds":job.eta_seconds,
        "message":job.message,
        "last_error":job.last_error,
        "provider_status":provider,
        "updated_at":job.updated_at.isoformat() if job.updated_at else None,
        "started_at":job.started_at.isoformat() if job.started_at else None,
        "finished_at":job.finished_at.isoformat() if job.finished_at else None,
    }


def _classification_running():
    db=SessionLocal()
    try:
        job=(
            db.query(FullMarketSyncState)
            .filter(FullMarketSyncState.key==CLASSIFICATION_SYNC_KEY)
            .first()
        )
        return bool(job and job.running)
    finally:
        db.close()


async def _run_classification_sync(admin_id:int, progress_callback=None):
    async with _classification_sync_lock:
        db=SessionLocal()
        job=None
        started=time.monotonic()

        def _progress(stage:str, processed:int=0, total:int=0, message:str=""):
            _sync_diag(
                "INFO",
                f"CLASSIFICATION_{stage}",
                {"processed":int(processed or 0),"total":int(total or 0),"message":message},
            )
            if progress_callback:
                try:
                    progress_callback(stage,int(processed or 0),int(total or 0),message)
                except Exception:
                    logger.debug("classification progress callback failed",exc_info=True)

        try:
            _progress("STAGE_START",0,0,"종목 사업분류 동기화를 시작합니다.")
            if not (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip():
                raise RuntimeError("OpenDART API 키가 설정되지 않았습니다.")
            commit_or_rollback(db)
            _progress("DART_CREDENTIAL_READY",0,0,"OpenDART API 설정 확인 완료")

            job=_classification_job(db)
            job.running=True
            job.phase="corp-code"
            job.job_type="classification"
            job.stage_label="기업 연결"
            job.item_total=0
            job.item_completed=0
            job.progress_value=0
            job.success=0
            job.failed=0
            job.current_code=""
            job.current_name=""
            job.eta_seconds=0
            job.last_error=""
            job.message="OpenDART 상장사 고유번호를 확인합니다."
            job.provider_status_json=json.dumps(
                {"source":"OpenDART 기업개황","classified":0,"coverage":{}},
                ensure_ascii=False,
            )
            job.requested_by_user_id=admin_id
            job.started_at=datetime.now()
            job.finished_at=None
            commit_or_rollback(db)

            _progress("CORP_CODE_START",0,0,"OpenDART 상장사 고유번호를 갱신합니다.")
            try:
                result=await asyncio.wait_for(sync_dart_corp_codes(db),timeout=120)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("OpenDART corpCode 동기화가 120초를 초과했습니다.") from exc
            if not result.get("configured"):
                raise RuntimeError(result.get("message") or "OpenDART 설정 필요")
            _progress(
                "CORP_CODE_DONE",
                int(result.get("mapped") or 0),
                int(result.get("available") or 0),
                f"기업 고유번호 확인 완료 · 신규/변경 {int(result.get('mapped') or 0):,}개",
            )

            # Classification is an analysis dataset. Non-analysis instruments
            # (ETFs/ETNs and other excluded symbols) must not create a warning
            # for the administrator merely because OpenDART has no company profile.
            universe=(
                db.query(Stock)
                .filter(*_stocklog_public_clauses())
                .order_by(Stock.code.asc())
                .all()
            )
            if not universe:
                raise RuntimeError("활성 종목 Universe가 없습니다.")

            total=len(universe)
            _progress("UNIVERSE_READY",0,total,f"활성 종목 {total:,}개 분류 시작")
            job.phase="industry"
            job.stage_label="사업분류 보강"
            job.item_total=total
            job.item_completed=0
            job.message=f"OpenDART 업종코드로 {total:,}개 종목을 확인합니다."
            commit_or_rollback(db)

            # `dart_misses` are enrichment misses, not synchronization failures.
            # A stock can still have a perfectly usable classification from an
            # official theme, its saved sector, or a deterministic name hint.
            failures=[]
            dart_misses=[]
            transient_failures=[]
            processed=0
            classified=0
            operational_errors=0
            deferred_provider_errors=0
            deferred_unqueried=0
            provider_circuit_open=False
            provider_circuit_reason=""
            consecutive_bad_batches=0
            batch_size=5

            async def _fetch_profile_with_retry(stock, client):
                last_exc=None
                for attempt in range(2):
                    try:
                        result=await fetch_dart_company_profile(stock,client=client,db=None)
                        if result:
                            return result
                        # Status 013/no-industry returns None; provider/auth/rate errors
                        # raise so they can be retried or classified as actionable.
                        if attempt==0:
                            await asyncio.sleep(.35)
                    except Exception as exc:
                        last_exc=exc
                        if attempt==0:
                            await asyncio.sleep(.35)
                            continue
                        raise
                if last_exc:
                    raise last_exc
                return None

            async with httpx.AsyncClient(timeout=15) as client:
                for start_index in range(0,total,batch_size):
                    batch=universe[start_index:start_index+batch_size]

                    if batch:
                        job.current_code=batch[0].code
                        job.current_name=batch[0].name
                    job.message=f"[{processed:,}/{total:,}] 사업분류 확인 중"
                    commit_or_rollback(db)

                    pending=[]
                    slots=[]

                    for stock in batch:
                        db.refresh(stock)
                        if stock.corp_code:
                            slots.append(True)
                            pending.append(
                                _fetch_profile_with_retry(stock,client)
                            )
                        else:
                            slots.append(False)

                    # db.refresh() above started a read transaction. Release it
                    # before the concurrent OpenDART batch waits on the network.
                    commit_or_rollback(db)
                    if pending:
                        try:
                            responses=await asyncio.wait_for(
                                asyncio.gather(*pending,return_exceptions=True),
                                timeout=30,
                            )
                        except asyncio.TimeoutError:
                            responses=[RuntimeError("OpenDART 기업개황 배치 조회 30초 초과") for _ in pending]
                            _sync_diag(
                                "WARNING",
                                "CLASSIFICATION_BATCH_TIMEOUT",
                                {"batch_start":start_index,"batch_size":len(batch),"pending":len(pending)},
                            )
                    else:
                        responses=[]

                    response_errors=[x for x in responses if isinstance(x,Exception)]
                    quota_error=next((x for x in response_errors if is_quota_like_error(x)),None)
                    all_requested_transient=bool(responses) and len(response_errors)==len(responses) and all(
                        classify_flow_error(x)=="transient" for x in response_errors
                    )
                    if quota_error is not None:
                        provider_circuit_open=True
                        provider_circuit_reason=f"OpenDART 사용한도/호출제한 감지: {_sync_error_text(quota_error,300)}"
                    elif all_requested_transient:
                        consecutive_bad_batches+=1
                        if provider_circuit_should_open(
                            consecutive_bad_batches,
                            threshold=CLASSIFICATION_BAD_BATCH_CIRCUIT_THRESHOLD,
                        ):
                            provider_circuit_open=True
                            provider_circuit_reason=(
                                f"OpenDART 연속 {consecutive_bad_batches}개 배치가 일시 실패하여 "
                                "남은 요청을 다음 실행으로 보류합니다."
                            )
                    else:
                        consecutive_bad_batches=0
                    response_iter=iter(responses)

                    for stock,has_request in zip(batch,slots):
                        processed+=1

                        if not has_request:
                            dart_misses.append({
                                "code":stock.code,
                                "name":stock.name,
                                "reason":"OpenDART 기업 연결 정보 없음",
                            })
                            continue

                        response=next(response_iter)

                        if isinstance(response,Exception):
                            if classify_flow_error(response)=="transient":
                                transient_failures.append({
                                    "code":stock.code,
                                    "name":stock.name,
                                    "reason":f"OpenDART 1차 조회 일시 오류: {response}",
                                })
                            else:
                                operational_errors+=1
                                failures.append({
                                    "code":stock.code,
                                    "name":stock.name,
                                    "reason":f"OpenDART 1차 조회 오류: {response}",
                                })
                            continue

                        if not response:
                            dart_misses.append({
                                "code":stock.code,
                                "name":stock.name,
                                "reason":"OpenDART 공식 업종코드 없음",
                            })
                            continue

                        if _apply_dart_industry_profile(stock,response):
                            job.success+=1
                            classified+=1
                        else:
                            dart_misses.append({
                                "code":stock.code,
                                "name":stock.name,
                                "reason":"OpenDART 업종 매핑 불가",
                            })

                    commit_or_rollback(db)

                    job.item_completed=processed
                    pct=(processed/max(total,1))*CLASSIFICATION_MAIN_PROGRESS_MAX
                    job.progress_value=pct

                    elapsed=max(time.monotonic()-started,.1)
                    rate=processed/elapsed if processed else 0
                    job.eta_seconds=((total-processed)/rate) if rate>0 and processed<total else 0

                    job.provider_status_json=json.dumps(
                        {
                            "source":"OpenDART 기업개황",
                            "classified":classified,
                            "dart_miss_count":len(dart_misses),
                            "operational_error_count":operational_errors,
                            "retry_pending_count":len(transient_failures),
                            "deferred_unqueried_count":deferred_unqueried,
                            "provider_circuit_open":provider_circuit_open,
                            "provider_circuit_reason":provider_circuit_reason,
                            "consecutive_bad_batches":consecutive_bad_batches,
                            "failure_count":operational_errors,
                            "failure_sample":failures[-20:],
                            "dart_miss_sample":dart_misses[-20:],
                        },
                        ensure_ascii=False,
                    )
                    commit_or_rollback(db)
                    # Persisted job progress is mirrored to the unified parent and
                    # sampled into the diagnostic log. Avoid one log line per stock.
                    if processed<=batch_size or processed==total or processed%100==0:
                        _progress(
                            "PROGRESS",
                            processed,
                            total,
                            f"사업분류 {processed:,}/{total:,} · OpenDART 확인 {classified:,} · 보조분류 후보 {len(dart_misses):,} · 재시도 대기 {len(transient_failures):,}",
                        )
                    elif progress_callback:
                        try:
                            progress_callback(
                                "PROGRESS",processed,total,
                                f"사업분류 {processed:,}/{total:,}",
                            )
                        except Exception:
                            logger.debug("classification progress callback failed",exc_info=True)

                    if provider_circuit_open:
                        deferred_unqueried=max(0,total-processed)
                        deferred_provider_errors+=deferred_unqueried
                        job.message=(
                            f"OpenDART 일시 제한 감지 · 조회하지 못한 {deferred_unqueried:,}개 종목은 "
                            "다음 전체 동기화에서 자동 보강합니다."
                        )
                        job.provider_status_json=json.dumps(
                            {
                                "source":"OpenDART 기업개황",
                                "classified":classified,
                                "dart_miss_count":len(dart_misses),
                                "operational_error_count":operational_errors,
                                "retry_pending_count":len(transient_failures),
                                "deferred_unqueried_count":deferred_unqueried,
                                "provider_circuit_open":True,
                                "provider_circuit_reason":provider_circuit_reason,
                                "consecutive_bad_batches":consecutive_bad_batches,
                                "failure_count":operational_errors,
                                "failure_sample":failures[-20:],
                                "dart_miss_sample":dart_misses[-20:],
                            },
                            ensure_ascii=False,
                        )
                        commit_or_rollback(db)
                        _progress(
                            "PROVIDER_CIRCUIT_OPEN",
                            processed,total,
                            f"{provider_circuit_reason} · 다음회차 보강 {deferred_unqueried:,}개",
                        )
                        break
                    await asyncio.sleep(.08)

            # OpenDART occasionally slows down near the end of a large company-profile run.
            # Retry only a small, time-bounded tail. A provider outage/quota event must
            # never turn the final 1% into an hours-long sequential retry loop.
            retry_candidates=list(transient_failures)
            retry_queue=[]
            retry_deferred_immediately=0
            retry_budget_deferred=0
            retry_attempted=0
            retry_resolved=0

            if retry_candidates:
                if provider_circuit_open:
                    retry_deferred_immediately=len(retry_candidates)
                    deferred_provider_errors+=retry_deferred_immediately
                else:
                    retry_queue=retry_candidates[:CLASSIFICATION_TAIL_RETRY_LIMIT]
                    retry_deferred_immediately=max(0,len(retry_candidates)-len(retry_queue))
                    deferred_provider_errors+=retry_deferred_immediately

            if retry_queue:
                retry_total=len(retry_queue)
                job.phase="industry-retry"
                job.stage_label="OpenDART 재확인"
                job.item_total=retry_total
                job.item_completed=0
                job.progress_value=CLASSIFICATION_MAIN_PROGRESS_MAX
                job.current_code=""
                job.current_name=""
                job.eta_seconds=CLASSIFICATION_TAIL_RETRY_BUDGET_SECONDS
                job.message=(
                    f"일시 조회 실패 {len(retry_candidates):,}개 중 최대 {retry_total:,}개만 "
                    f"{int(CLASSIFICATION_TAIL_RETRY_BUDGET_SECONDS)}초 안에서 재확인합니다."
                )
                job.provider_status_json=json.dumps({
                    "source":"OpenDART 기업개황",
                    "classified":classified,
                    "dart_miss_count":len(dart_misses),
                    "retry_pending_count":len(retry_candidates),
                    "retry_queue_count":retry_total,
                    "retry_limit":CLASSIFICATION_TAIL_RETRY_LIMIT,
                    "retry_budget_seconds":CLASSIFICATION_TAIL_RETRY_BUDGET_SECONDS,
                    "retry_deferred_immediately":retry_deferred_immediately,
                    "deferred_unqueried_count":deferred_unqueried,
                    "provider_circuit_open":provider_circuit_open,
                    "provider_circuit_reason":provider_circuit_reason,
                    "operational_error_count":operational_errors,
                    "failure_count":operational_errors,
                },ensure_ascii=False)
                commit_or_rollback(db)
                _progress(
                    "RETRY_START",0,retry_total,
                    f"OpenDART 재확인 {retry_total:,}개 시작 · 시간 예산 {int(CLASSIFICATION_TAIL_RETRY_BUDGET_SECONDS)}초",
                )

                def _is_transient_dart_error(exc):
                    if isinstance(exc,(httpx.TimeoutException,httpx.NetworkError,httpx.RemoteProtocolError)):
                        return True
                    return classify_flow_error(exc)=="transient"

                async def _fetch_profile_slow_retry(stock, client):
                    last_exc=None
                    for attempt in range(2):
                        try:
                            return await asyncio.wait_for(
                                fetch_dart_company_profile(stock,client=client,db=None),
                                timeout=CLASSIFICATION_TAIL_RETRY_TIMEOUT_SECONDS,
                            )
                        except Exception as exc:
                            last_exc=exc
                            if attempt==0:
                                await asyncio.sleep(.6)
                    if last_exc:
                        raise last_exc
                    return None

                retry_started=time.monotonic()
                retry_deadline=retry_started+CLASSIFICATION_TAIL_RETRY_BUDGET_SECONDS
                async with httpx.AsyncClient(timeout=CLASSIFICATION_TAIL_RETRY_TIMEOUT_SECONDS) as retry_client:
                    for retry_index,item in enumerate(retry_queue,1):
                        remaining_budget=retry_deadline-time.monotonic()
                        if remaining_budget<=1.0:
                            retry_budget_deferred=retry_total-retry_attempted
                            deferred_provider_errors+=retry_budget_deferred
                            _progress(
                                "RETRY_BUDGET_EXHAUSTED",retry_attempted,retry_total,
                                f"재확인 시간 예산 종료 · 남은 {retry_budget_deferred:,}개는 다음회차 보강",
                            )
                            break

                        stock=db.query(Stock).filter(Stock.code==item.get("code")).first()
                        commit_or_rollback(db)
                        if not stock:
                            retry_attempted+=1
                            operational_errors+=1
                            failures.append({**item,"reason":"재확인 대상 종목을 DB에서 찾을 수 없음"})
                            continue

                        job.current_code=stock.code
                        job.current_name=stock.name
                        job.item_completed=retry_attempted
                        job.message=(
                            f"OpenDART 재확인 {retry_index:,}/{retry_total:,} · "
                            f"남은 시간 약 {max(0,int(remaining_budget))}초"
                        )
                        commit_or_rollback(db)

                        retry_attempted+=1
                        try:
                            profile=await _fetch_profile_slow_retry(stock,retry_client)
                            if profile:
                                if _apply_dart_industry_profile(stock,profile):
                                    classified+=1
                                    retry_resolved+=1
                                else:
                                    dart_misses.append({
                                        "code":stock.code,"name":stock.name,
                                        "reason":"OpenDART 재확인 후 업종 매핑 불가",
                                    })
                            else:
                                dart_misses.append({
                                    "code":stock.code,"name":stock.name,
                                    "reason":"OpenDART 재확인 결과 공식 업종코드 없음",
                                })
                        except Exception as exc:
                            if _is_transient_dart_error(exc):
                                deferred_provider_errors+=1
                                failures.append({
                                    "code":stock.code,
                                    "name":stock.name,
                                    "reason":f"OpenDART 일시 오류 · 다음 실행에서 재보강: {exc}",
                                    "deferred":True,
                                })
                            else:
                                operational_errors+=1
                                failures.append({
                                    "code":stock.code,
                                    "name":stock.name,
                                    "reason":f"OpenDART 재확인 실패: {exc}",
                                })
                        commit_or_rollback(db)

                        retry_pct=(
                            CLASSIFICATION_MAIN_PROGRESS_MAX
                            +(CLASSIFICATION_RETRY_PROGRESS_MAX-CLASSIFICATION_MAIN_PROGRESS_MAX)
                            *(retry_attempted/max(1,retry_total))
                        )
                        job.progress_value=min(CLASSIFICATION_RETRY_PROGRESS_MAX,retry_pct)
                        job.item_completed=retry_attempted
                        job.eta_seconds=max(0,retry_deadline-time.monotonic())
                        job.provider_status_json=json.dumps({
                            "source":"OpenDART 기업개황",
                            "classified":classified,
                            "dart_miss_count":len(dart_misses),
                            "retry_pending_count":max(0,retry_total-retry_attempted),
                            "retry_queue_count":retry_total,
                            "retry_attempted_count":retry_attempted,
                            "retry_resolved_count":retry_resolved,
                            "retry_deferred_immediately":retry_deferred_immediately,
                            "retry_budget_deferred":retry_budget_deferred,
                            "deferred_unqueried_count":deferred_unqueried,
                            "deferred_provider_error_count":deferred_provider_errors,
                            "provider_circuit_open":provider_circuit_open,
                            "provider_circuit_reason":provider_circuit_reason,
                            "operational_error_count":operational_errors,
                            "failure_count":operational_errors,
                            "failure_sample":failures[-20:],
                        },ensure_ascii=False)
                        commit_or_rollback(db)
                        _progress(
                            "RETRY_PROGRESS",retry_attempted,retry_total,
                            f"OpenDART 재확인 {retry_attempted:,}/{retry_total:,} · 복구 {retry_resolved:,} · 다음회차 보강 {deferred_provider_errors:,} · 실제 오류 {operational_errors:,}",
                        )
                        await asyncio.sleep(.25)

                job.current_code=""
                job.current_name=""
                _progress(
                    "RETRY_DONE",retry_attempted,retry_total,
                    f"OpenDART 재확인 종료 · 시도 {retry_attempted:,} · 복구 {retry_resolved:,} · 다음회차 보강 {deferred_provider_errors:,} · 실제 오류 {operational_errors:,}",
                )
            elif retry_candidates:
                _progress(
                    "RETRY_SKIPPED",0,len(retry_candidates),
                    f"OpenDART 공급사 제한 상태라 재확인을 생략하고 {len(retry_candidates):,}개를 다음 실행으로 보류합니다.",
                )

            job.phase="finalizing"
            job.stage_label="커버리지 계산"
            job.progress_value=99
            job.item_total=total
            job.item_completed=total
            job.current_code=""
            job.current_name=""
            job.eta_seconds=0
            job.message="사업분류 저장 완료 · 대표 분류 커버리지를 계산합니다."
            commit_or_rollback(db)

            _progress("FINALIZING_START",total,total,"대표 분류 커버리지를 계산합니다.")
            coverage=_classification_coverage_stats(
                db,sample_limit=50,analysis_eligible_only=True,
            )
            unresolved=int(coverage.get("weak_fallback_stocks") or 0)
            fallback_resolved=max(0,len(dart_misses)-unresolved)
            # Only non-transient synchronization/provider failures should make the
            # administrator re-run the job. Missing industry evidence and temporary
            # provider slowdowns are represented as fallback/deferred enrichment.
            actionable_failures=int(operational_errors)
            job.failed=actionable_failures

            job.provider_status_json=json.dumps(
                {
                    "source":"OpenDART 기업개황",
                    "classified":classified,
                    "dart_miss_count":len(dart_misses),
                    "fallback_resolved_count":fallback_resolved,
                    "weak_fallback_count":unresolved,
                    "operational_error_count":operational_errors,
                    "deferred_provider_error_count":deferred_provider_errors,
                    "deferred_unqueried_count":deferred_unqueried,
                    "retry_candidate_count":len(retry_candidates),
                    "retry_attempted_count":retry_attempted,
                    "retry_resolved_count":retry_resolved,
                    "retry_deferred_immediately":retry_deferred_immediately,
                    "retry_budget_deferred":retry_budget_deferred,
                    "provider_circuit_open":provider_circuit_open,
                    "provider_circuit_reason":provider_circuit_reason,
                    "failure_count":actionable_failures,
                    "failure_sample":failures[-20:],
                    "dart_miss_sample":dart_misses[-20:],
                    "coverage":coverage,
                },
                ensure_ascii=False,
            )
            job.running=False
            has_deferred=deferred_provider_errors>0
            job.phase="completed" if actionable_failures==0 and not has_deferred else "partial"
            job.stage_label=(
                "완료"
                if actionable_failures==0 and not has_deferred
                else ("완료 · 다음회차 보강" if actionable_failures==0 else "일부 조회 오류")
            )
            job.progress_value=100
            job.eta_seconds=0
            job.current_code=""
            job.current_name=""
            job.message=(
                f"종목 분류 완료 · 대표 분류 "
                f"{coverage.get('effective_classified_stocks',0):,}/"
                f"{coverage.get('active_stocks',0):,} "
                f"({coverage.get('coverage_percent',0):.1f}%)"
                + (f" · 보조분류 {fallback_resolved:,}개" if fallback_resolved else "")
                + (f" · 기타 사업 {unresolved:,}개" if unresolved else "")
                + (f" · 다음회차 보강 {deferred_provider_errors:,}개" if deferred_provider_errors else "")
            )
            job.last_error=(
                ""
                if actionable_failures==0
                else f"OpenDART 통신/처리 오류 {actionable_failures:,}건이 남아 재확인이 필요합니다."
            )
            job.finished_at=datetime.now()
            commit_or_rollback(db)
            _progress(
                "DONE",total,total,
                f"사업분류 완료 · OpenDART {classified:,} · 보조분류 {fallback_resolved:,} · 기타 사업 {unresolved:,} · 다음회차 보강 {deferred_provider_errors:,} · 실제 오류 {actionable_failures:,}",
            )

        except asyncio.CancelledError:
            _sync_diag("WARNING","CLASSIFICATION_CANCELLED",{"elapsed_seconds":round(time.monotonic()-started,2)})
            if job:
                job.running=False
                job.phase="cancelled"
                job.stage_label="중지됨"
                job.current_code=""
                job.current_name=""
                job.eta_seconds=0
                job.message="종목 분류 보강을 중지했습니다. 저장된 분류는 유지됩니다."
                job.finished_at=datetime.now()
                commit_or_rollback(db)
            raise

        except Exception as exc:
            _sync_diag(
                "ERROR","CLASSIFICATION_FATAL",
                {"elapsed_seconds":round(time.monotonic()-started,2)},
                exc=exc,
            )
            if job:
                job.running=False
                job.phase="failed"
                job.stage_label="실패"
                job.current_code=""
                job.current_name=""
                job.eta_seconds=0
                job.last_error=f"{type(exc).__name__}: {exc}"
                job.message="종목 사업분류 보강 중단"
                job.finished_at=datetime.now()
                commit_or_rollback(db)
        finally:
            db.close()


@app.get("/api/admin/classification-sync/status")
def classification_sync_status(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    job=_classification_job(db)

    # An in-process task cannot survive a backend restart.
    if (
        job.running
        and (
            _classification_sync_task is None
            or _classification_sync_task.done()
        )
    ):
        job.running=False
        job.phase="cancelled"
        job.stage_label="중지됨"
        job.message="백엔드 재시작으로 이전 분류 작업을 종료 처리했습니다."
        job.finished_at=datetime.now()
        commit_or_rollback(db)

    return _classification_json(job)


@app.post("/api/admin/classification-sync/start")
async def classification_sync_start(
    u:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    global _classification_sync_task

    if not (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip():
        raise HTTPException(
            400,
            "관리자 > 외부 API 관리에서 OpenDART API 키를 먼저 설정해주세요.",
        )

    if _classification_sync_task and not _classification_sync_task.done():
        raise HTTPException(409,"종목 분류 보강이 이미 실행 중입니다.")

    if _full_market_task and not _full_market_task.done():
        raise HTTPException(409,"시장 데이터 동기화가 끝난 후 실행해주세요.")

    job=_classification_job(db)
    if job.running:
        job.running=False
        job.phase="cancelled"
        commit_or_rollback(db)

    _classification_sync_task=asyncio.create_task(
        _run_classification_sync(u.id)
    )

    return {
        "ok":True,
        "message":"종목 분류 보강을 시작했습니다. 테마 미연결 종목도 실제 사업 업종으로 분류합니다.",
    }


@app.post("/api/admin/classification-sync/stop")
async def classification_sync_stop(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    global _classification_sync_task

    job=_classification_job(db)
    job.running=False
    job.phase="cancelled"
    job.stage_label="중지됨"
    job.current_code=""
    job.current_name=""
    job.eta_seconds=0
    job.message="종목 분류 보강을 중지했습니다. 저장된 분류는 유지됩니다."
    job.finished_at=datetime.now()
    commit_or_rollback(db)

    if _classification_sync_task and not _classification_sync_task.done():
        _classification_sync_task.cancel()

    return {"ok":True,"message":"종목 분류 보강을 중지했습니다."}


@app.get("/api/admin/classification-sync/coverage")
def classification_sync_coverage(
    limit:int=Query(30,ge=0,le=200),
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    return _classification_coverage_stats(db,sample_limit=limit)




# v3.42 unified synchronization -------------------------------------------------
# The standalone "score recalculation" button is intentionally not part of the
# new admin UI. Stock.score is already recalculated whenever Kiwoom price/basic
# metrics or OpenDART financials are refreshed. The legacy endpoint is kept for
# backward compatibility, while the nightly/full pipeline makes it unnecessary
# in normal operation.
UNIFIED_SYNC_KEY="unified_full_sync"
SYNC_SCHEDULE_KEY="unified_full_sync"
DEFAULT_SYNC_TIMES=["22:00"]
SYNC_SCOPE_ORDER=[
    "kiwoom","dart","kiwoom_themes","market_themes",
    "classification","theme_engine","flow","smart_scores",
]
SYNC_SCOPE_LABELS={
    "kiwoom":"키움 시세",
    "dart":"DART 재무",
    "kiwoom_themes":"키움 테마",
    "market_themes":"시장 테마",
    "classification":"종목 분류",
    "theme_engine":"표준 테마",
    "flow":"수급 데이터",
    "smart_scores":"스마트 분석 점수",
}
_unified_sync_task=None
_nightly_sync_watcher_task=None
_unified_sync_lock=asyncio.Lock()


def _normalize_sync_times(values):
    try:
        return normalize_run_times(values)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


def _normalize_sync_scopes(values, *, allow_default=True):
    if values is None and allow_default:
        return list(SYNC_SCOPE_ORDER)
    raw=list(values or [])
    scopes=[]
    for value in raw:
        key=str(value or "").strip()
        if key not in SYNC_SCOPE_LABELS:
            raise HTTPException(422,f"지원하지 않는 동기화 항목입니다: {key}")
        if key not in scopes:
            scopes.append(key)
    if not scopes:
        raise HTTPException(422,"동기화 항목을 하나 이상 선택해주세요.")
    return [key for key in SYNC_SCOPE_ORDER if key in scopes]


def _sync_schedule_row(db:Session):
    row=db.query(SyncScheduleSetting).filter(SyncScheduleSetting.key==SYNC_SCHEDULE_KEY).first()
    if not row:
        row=SyncScheduleSetting(
            key=SYNC_SCHEDULE_KEY,
            enabled=True,
            run_times_json=json.dumps(DEFAULT_SYNC_TIMES,ensure_ascii=False),
            sync_scopes_json=json.dumps(SYNC_SCOPE_ORDER,ensure_ascii=False),
            flow_universe_limit=0,
            flow_history_days=20,
        )
        db.add(row)
        commit_or_rollback(db)
        db.refresh(row)
    elif not str(getattr(row,"sync_scopes_json","") or "").strip():
        row.sync_scopes_json=json.dumps(SYNC_SCOPE_ORDER,ensure_ascii=False)
        commit_or_rollback(db)
        db.refresh(row)
    return row


def _schedule_times(row):
    try:
        values=json.loads(row.run_times_json or "[]")
        return _normalize_sync_times(values)
    except HTTPException:
        return list(DEFAULT_SYNC_TIMES)
    except Exception:
        return list(DEFAULT_SYNC_TIMES)


def _schedule_scopes(row):
    try:
        values=json.loads(getattr(row,"sync_scopes_json","") or "[]")
        return _normalize_sync_scopes(values)
    except Exception:
        return list(SYNC_SCOPE_ORDER)


def _next_schedule_run(row,now=None):
    if not row.enabled:
        return None
    now=now or datetime.now(ZoneInfo("Asia/Seoul"))
    times=_schedule_times(row)
    for value in times:
        hour,minute=map(int,value.split(":"))
        candidate=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if candidate>now:
            return candidate
    hour,minute=map(int,times[0].split(":"))
    return (now+timedelta(days=1)).replace(hour=hour,minute=minute,second=0,microsecond=0)


def _sync_schedule_json(row):
    times=_schedule_times(row)
    scopes=_schedule_scopes(row)
    next_run=_next_schedule_run(row)
    return {
        "enabled":bool(row.enabled),
        "timezone":"Asia/Seoul",
        "run_times":times,
        "run_count":len(times),
        "label":(" · ".join(times) if row.enabled else "자동 동기화 꺼짐"),
        "next_run_at":next_run.isoformat() if next_run else None,
        "flow_universe_limit":int(row.flow_universe_limit or 0),
        "flow_history_days":int(row.flow_history_days or 20),
        "scopes":scopes,
        "scope_labels":[SYNC_SCOPE_LABELS[x] for x in scopes],
        "updated_at":row.updated_at.isoformat() if row.updated_at else None,
        "watcher_running":bool(_nightly_sync_watcher_task and not _nightly_sync_watcher_task.done()),
    }


def _unified_sync_job(db: Session):
    job=(
        db.query(FullMarketSyncState)
        .filter(FullMarketSyncState.key==UNIFIED_SYNC_KEY)
        .first()
    )
    if not job:
        job=FullMarketSyncState(
            key=UNIFIED_SYNC_KEY,
            running=False,
            phase="idle",
            job_type="unified",
            stage_label="대기",
            provider_status_json="{}",
        )
        db.add(job)
        commit_or_rollback(db)
        db.refresh(job)
    return job


def _unified_provider(job):
    try:
        return json.loads(job.provider_status_json or "{}")
    except Exception:
        return {}


def _sync_step_severity(step):
    severity=str((step or {}).get("severity") or "").strip().lower()
    if severity in {"success","info","retry","error"}:
        return severity
    status=(step or {}).get("status")
    if status is not None and status!="partial":
        return "success"
    message=str((step or {}).get("message") or "")
    if re.search(r"(?:오류|실패)\s*[1-9]",message) or "확인 필요" in message:
        return "error"
    if "다음회차 보강" in message and not re.search(r"다음회차 보강\s*0",message):
        return "retry"
    return "info"


def _unified_sync_json(job,db:Session,schedule_row=None):
    provider=_unified_provider(job)
    schedule=_sync_schedule_json(schedule_row or _sync_schedule_row(db))
    steps=[{**step,"severity":_sync_step_severity(step)} for step in provider.get("steps",[]) if isinstance(step,dict)]
    warnings=[{**warning,"severity":_sync_step_severity(warning)} for warning in provider.get("warnings",[]) if isinstance(warning,dict)]
    issue_count=sum(1 for item in warnings if item.get("severity")=="error")
    retry_count=sum(1 for item in warnings if item.get("severity")=="retry")
    notice_count=sum(1 for item in warnings if item.get("severity")=="info")
    auto_scheduler_message=str(provider.get("auto_scheduler_message") or "")
    if not job.running and "실행 중" in auto_scheduler_message:
        slot=str(provider.get("last_auto_slot") or "").split("@",1)[-1]
        if job.phase in {"completed","success_with_warnings"}:
            auto_scheduler_message=f"{slot+' ' if slot else ''}자동 동기화를 완료했습니다."
        elif job.phase=="failed":
            auto_scheduler_message=f"{slot+' ' if slot else ''}자동 동기화가 일부 단계에서 중단되었습니다."
        elif job.phase in {"cancelled","interrupted"}:
            auto_scheduler_message=f"{slot+' ' if slot else ''}자동 동기화가 종료되었습니다."
    return {
        "running":bool(job.running),
        "phase":job.phase,
        "stage_label":job.stage_label,
        "progress":float(job.progress_value or 0),
        "item_total":int(job.item_total or 0),
        "item_completed":int(job.item_completed or 0),
        "success":int(job.success or 0),
        "failed":int(job.failed or 0),
        "current_code":job.current_code or "",
        "current_name":job.current_name or "",
        "eta_seconds":float(job.eta_seconds or 0),
        "message":job.message or "",
        "last_error":job.last_error or "",
        "started_at":job.started_at.isoformat() if job.started_at else None,
        "finished_at":job.finished_at.isoformat() if job.finished_at else None,
        "updated_at":job.updated_at.isoformat() if job.updated_at else None,
        "failure_recorded_at":job.finished_at.isoformat() if job.phase=="failed" and job.finished_at else None,
        "legacy_payload_overflow_failure":bool(
            job.phase=="failed"
            and "Data too long for column 'failures_json'" in str(job.last_error or "")
        ),
        "last_success_at":provider.get("last_success_at"),
        "last_auto_date":provider.get("last_auto_date"),
        "last_auto_slot":provider.get("last_auto_slot"),
        "auto_pending_slot":provider.get("auto_pending_slot"),
        "auto_pending_since":provider.get("auto_pending_since"),
        "auto_last_attempt_at":provider.get("auto_last_attempt_at"),
        "auto_last_started_at":provider.get("auto_last_started_at"),
        "auto_scheduler_message":auto_scheduler_message,
        "trigger":provider.get("trigger",""),
        "run_id":provider.get("run_id",""),
        "selected_scopes":provider.get("selected_scopes",SYNC_SCOPE_ORDER),
        "selected_scope_labels":[SYNC_SCOPE_LABELS.get(x,x) for x in provider.get("selected_scopes",SYNC_SCOPE_ORDER)],
        "steps":steps,
        "warnings":warnings,
        "warning_count":len(warnings),
        "issue_count":issue_count,
        "retry_count":retry_count,
        "notice_count":notice_count,
        "schedule":schedule,
    }


def _sync_task_alive(task):
    return bool(task and not task.done())


def _any_individual_sync_running():
    return any([
        _sync_task_alive(_full_market_task),
        _sync_task_alive(_theme_sync_task),
        _sync_task_alive(_market_theme_sync_task),
        _sync_task_alive(_classification_sync_task),
        _sync_task_alive(_flow_sync_task),
        _sync_task_alive(_theme_normalize_task),
    ])


def _find_sync_admin(db: Session, require_kiwoom:bool=True):
    query=db.query(User).filter(User.is_admin==True,User.is_active==True)
    if require_kiwoom:
        query=query.join(KiwoomCredential,KiwoomCredential.user_id==User.id)
    return query.order_by(User.id.asc()).first()


def _prepare_theme_run(db: Session,admin_id:int):
    run_id=f"theme-unified-{admin_id}-{time.time_ns()}"
    job=_theme_sync_job(db)
    provider=_provider_status(job)
    provider.update({
        "run_id":run_id,
        "cancelled_run_id":"",
        "stop_requested":False,
        "restart_after_epoch":0,
        "current_status":"starting",
        "current_status_message":"전체 동기화에서 테마 동기화를 준비 중입니다.",
    })
    job.provider_status_json=json.dumps(provider,ensure_ascii=False)
    job.running=False
    job.phase="starting"
    job.last_error=""
    job.requested_by_user_id=admin_id
    commit_or_rollback(db)
    return run_id


def _sync_step_snapshot(key,label,selected=True,status=None,progress=0,message=""):
    if status is None:
        status="pending" if selected else "skipped"
    return {
        "key":key,
        "label":label,
        "selected":bool(selected),
        "status":status,
        "progress":progress,
        "message":message or ("이번 실행 제외" if not selected else ""),
        "started_at":None,
        "finished_at":None,
        "warning_count":0,
        "severity":"success",
    }


async def _run_unified_sync(
    admin_id:int,
    trigger:str="manual",
    scheduled_slot:str="",
    flow_universe_limit:int|None=None,
    flow_history_days:int|None=None,
    scopes:list[str]|None=None,
):
    global _full_market_task,_theme_sync_task,_market_theme_sync_task,_classification_sync_task,_flow_sync_task
    diagnostic_file=begin_sync_diagnostic(
        "unified-sync",
        run_id=f"{trigger}-{admin_id}-{time.time_ns()}",
        metadata={"admin_id":admin_id,"trigger":trigger,"scheduled_slot":scheduled_slot,"requested_scopes":scopes},
    )
    diagnostic_token=activate_sync_diagnostic(diagnostic_file)
    async with _unified_sync_lock:
        db=SessionLocal()
        job=None
        current_step_key=""
        selected_scopes=[]
        steps=[]
        try:
            schedule=_sync_schedule_row(db)
            selected_scopes=_normalize_sync_scopes(scopes if scopes is not None else _schedule_scopes(schedule))
            selected_set=set(selected_scopes)
            resolved_flow_limit=int(
                schedule.flow_universe_limit if flow_universe_limit is None
                else flow_universe_limit
            )
            resolved_history_days=int(
                schedule.flow_history_days if flow_history_days is None
                else flow_history_days
            )
            steps=[
                _sync_step_snapshot(key,SYNC_SCOPE_LABELS[key],selected=key in selected_set)
                for key in SYNC_SCOPE_ORDER
            ]
            step_map={x["key"]:x for x in steps}
            run_id=f"{trigger}-{admin_id}-{time.time_ns()}"
            job=_unified_sync_job(db)
            provider=_unified_provider(job)
            for stale_key in ("failed_stage","failed_error","smart_score_cache_warning"):
                provider.pop(stale_key,None)
            if scheduled_slot:
                provider["last_auto_slot"]=scheduled_slot
                provider["last_auto_date"]=scheduled_slot.split("@",1)[0]
                provider["auto_last_started_at"]=datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
                provider.pop("auto_pending_slot",None)
                provider.pop("auto_pending_since",None)
                provider["auto_scheduler_message"]=f"{scheduled_slot.split('@',1)[-1]} 자동 동기화를 실행 중입니다."
            provider.update({
                "run_id":run_id,
                "trigger":trigger,
                "selected_scopes":selected_scopes,
                "steps":steps,
                "warnings":[],
                "warning_count":0,
                "flow_universe_limit":resolved_flow_limit,
                "flow_history_days":resolved_history_days,
                "diagnostic_log":diagnostic_file,
            })
            append_sync_diagnostic(
                diagnostic_file,"INFO","UNIFIED_SYNC_START",
                details={"trigger":trigger,"selected_scopes":selected_scopes,"flow_universe_limit":resolved_flow_limit,"flow_history_days":resolved_history_days},
            )
            job.running=True
            job.phase="running"
            job.stage_label="준비"
            job.progress_value=0
            job.item_total=0
            job.item_completed=0
            job.success=0
            job.failed=0
            job.current_code=""
            job.current_name=""
            job.current_market=""
            job.eta_seconds=0
            job.message=f"선택한 {len(selected_scopes)}개 항목 동기화를 시작했습니다."
            job.last_error=""
            job.started_at=datetime.now()
            job.finished_at=None
            job.provider_status_json=_bounded_provider_json(provider)
            commit_or_rollback(db)

            def _overall_progress(extra=0.0):
                completed=sum(1 for x in steps if x.get("selected") and x.get("status") in ("done","partial"))
                return min(99.0,((completed+extra)/max(1,len(selected_scopes)))*100.0)

            def _persist(message=None):
                provider["steps"]=steps
                if message is not None:
                    job.message=message
                job.provider_status_json=_bounded_provider_json(provider)
                commit_or_rollback(db)

            def _begin(key,message):
                nonlocal current_step_key
                current_step_key=key
                step=step_map[key]
                step.update(status="running",progress=1,message=message,started_at=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),finished_at=None)
                job.stage_label=step["label"]
                job.progress_value=max(1.0,_overall_progress(0.04))
                job.item_total=0;job.item_completed=0;job.current_code="";job.current_name="";job.current_market="";job.eta_seconds=0
                _persist(f"{step['label']} 진행 중")

            def _finish(key,status="done",message="완료",warning_count=0,severity="success"):
                nonlocal current_step_key
                step=step_map[key]
                step.update(status=status,progress=100,message=message,finished_at=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),warning_count=max(0,int(warning_count or 0)),severity=severity)
                job.progress_value=_overall_progress()
                current_step_key=""
                result_label={"error":"완료 · 일부 오류","retry":"완료 · 다음 실행에서 자동 보완","info":"완료 · 데이터 없음 포함"}.get(severity,"완료")
                _persist(f"{step['label']} {result_label}")

            # 1) Kiwoom price/universe
            if "kiwoom" in selected_set:
                _begin("kiwoom","시세와 종목 정보를 갱신합니다.")
                _sync_diag("INFO","UNIFIED_KIWOOM_STAGE_START")
                _full_market_task=asyncio.current_task()
                await _run_market_data_sync(admin_id,"kiwoom",rebuild_scores=False)
                _sync_diag("INFO","UNIFIED_KIWOOM_STAGE_RETURNED")
                market_job=_full_market_job(db);db.refresh(market_job)
                if market_job.phase not in ("completed","partial"):
                    raise RuntimeError(market_job.last_error or market_job.message or "키움 시세 동기화 실패")
                market_meta=_provider_status(market_job)
                ki_meta=market_meta.get("kiwoom") if isinstance(market_meta.get("kiwoom"),dict) else {}
                deferred=int(ki_meta.get("deferred") or 0)
                hard_fail=int(market_job.failed or 0)
                warn=hard_fail+deferred
                message=(
                    "완료" if not warn
                    else (f"완료 · 다음회차 자동 보완 {deferred:,}개" if deferred and not hard_fail else f"완료 · 일부 오류 {hard_fail:,}개"+(f" · 자동 보완 {deferred:,}개" if deferred else ""))
                )
                _finish("kiwoom","partial" if warn else "done",message,warn,classify_sync_result(hard_failures=hard_fail,deferred=deferred))

            # 2) OpenDART financials
            if "dart" in selected_set:
                _begin("dart","재무와 밸류 지표를 갱신합니다.")
                _full_market_task=asyncio.current_task()
                await _run_market_data_sync(admin_id,"dart",rebuild_scores=False)
                market_job=_full_market_job(db);db.refresh(market_job)
                if market_job.phase not in ("completed","partial"):
                    raise RuntimeError(market_job.last_error or market_job.message or "DART 재무 동기화 실패")
                market_meta=_provider_status(market_job)
                dart_meta=market_meta.get("dart") if isinstance(market_meta.get("dart"),dict) else {}
                deferred=int(dart_meta.get("deferred") or 0)
                hard_fail=int(market_job.failed or 0)
                warn=hard_fail+deferred
                message=(
                    "완료" if not warn
                    else (f"완료 · 다음회차 자동 보완 {deferred:,}개" if deferred and not hard_fail else f"완료 · 일부 오류 {hard_fail:,}개"+(f" · 자동 보완 {deferred:,}개" if deferred else ""))
                )
                _finish("dart","partial" if warn else "done",message,warn,classify_sync_result(hard_failures=hard_fail,deferred=deferred))

            # 3) Kiwoom themes
            if "kiwoom_themes" in selected_set:
                _begin("kiwoom_themes","키움 테마와 구성 종목을 갱신합니다.")
                run_id=_prepare_theme_run(db,admin_id)
                _theme_sync_task=asyncio.current_task()
                await _run_theme_sync(admin_id,run_id)
                theme_job=_theme_sync_job(db);db.refresh(theme_job)
                if theme_job.phase not in ("completed","partial"):
                    raise RuntimeError(theme_job.last_error or theme_job.message or "키움 테마 동기화 실패")
                theme_provider=_theme_sync_provider_from_row(theme_job)
                warn=int(theme_provider.get("warning_count") or theme_job.failed or 0)
                _finish("kiwoom_themes","partial" if warn else "done","완료" if not warn else f"완료 · 일부 테마 오류 {warn:,}개",warn,classify_sync_result(hard_failures=warn))

            # 4) Market themes
            if "market_themes" in selected_set:
                _begin("market_themes","시장 테마를 갱신합니다.")
                _market_theme_sync_task=asyncio.current_task()
                await _run_market_theme_sync(admin_id)
                mt_job=_market_theme_job(db);db.refresh(mt_job)
                if mt_job.phase not in ("completed","partial"):
                    raise RuntimeError(mt_job.last_error or mt_job.message or "시장 테마 동기화 실패")
                warn=int(mt_job.failed or 0)
                _finish("market_themes","partial" if warn else "done","완료" if not warn else f"완료 · 일부 테마 오류 {warn:,}개",warn,classify_sync_result(hard_failures=warn))

            # 5) Business classification
            if "classification" in selected_set:
                _begin("classification","종목 사업 분류를 갱신합니다.")
                _sync_diag("INFO","UNIFIED_CLASSIFICATION_STAGE_START")

                def _classification_parent_progress(stage,processed,total,message):
                    step=step_map["classification"]
                    stage_key=str(stage or "").upper()
                    if stage_key.startswith("RETRY"):
                        fraction=(processed/max(1,total)) if total>0 else 0.0
                        pct=(
                            CLASSIFICATION_MAIN_PROGRESS_MAX
                            +(CLASSIFICATION_RETRY_PROGRESS_MAX-CLASSIFICATION_MAIN_PROGRESS_MAX)*fraction
                        )
                    elif stage_key.startswith("FINALIZING"):
                        pct=99.0
                    elif stage_key=="DONE":
                        pct=99.5
                    elif stage_key=="PROVIDER_CIRCUIT_OPEN":
                        pct=CLASSIFICATION_MAIN_PROGRESS_MAX
                    elif total>0:
                        pct=(processed/max(1,total))*CLASSIFICATION_MAIN_PROGRESS_MAX
                    else:
                        pct=float(step.get("progress") or 1.0)
                    pct=min(99.5,max(1.0,pct))
                    step.update(status="running",progress=round(pct,1),message=message or step.get("message"))
                    completed=sum(1 for x in steps if x.get("selected") and x.get("status") in ("done","partial"))
                    job.progress_value=min(99.0,((completed+(pct/100.0))/max(1,len(selected_scopes)))*100.0)
                    if total>0:
                        job.item_total=int(total)
                        job.item_completed=int(processed)
                    provider["steps"]=steps
                    job.provider_status_json=_bounded_provider_json(provider)
                    # The child classification session owns its own commits. The
                    # parent session only writes the lightweight aggregate state.
                    commit_or_rollback(db)

                _classification_sync_task=asyncio.current_task()
                await _run_classification_sync(admin_id,progress_callback=_classification_parent_progress)
                _sync_diag("INFO","UNIFIED_CLASSIFICATION_STAGE_RETURNED")
                cls_job=_classification_job(db);db.refresh(cls_job)
                if cls_job.phase not in ("completed","partial"):
                    raise RuntimeError(cls_job.last_error or cls_job.message or "종목 분류 동기화 실패")
                cls_meta=_classification_json(cls_job).get("provider_status") or {}
                cls_deferred=int(cls_meta.get("deferred_provider_error_count") or 0)
                warn=int(cls_job.failed or 0)+cls_deferred
                cls_message=(
                    "완료"
                    if not warn
                    else (
                        f"완료 · 다음회차 자동 보완 {cls_deferred:,}개"
                        if int(cls_job.failed or 0)==0 and cls_deferred
                        else f"완료 · 일부 오류 {int(cls_job.failed or 0):,}개"+(f" · 자동 보완 {cls_deferred:,}개" if cls_deferred else "")
                    )
                )
                _finish("classification","partial" if warn else "done",cls_message,warn,classify_sync_result(hard_failures=int(cls_job.failed or 0),deferred=cls_deferred))

            # 6) Deterministic StockLog Theme Engine
            if "theme_engine" in selected_set:
                _begin("theme_engine","StockLog 표준 테마를 재구축합니다.")
                await _run_theme_normalize(admin_id)
                db.expire_all()
                tn_job=_theme_normalize_job(db);db.refresh(tn_job)
                tn_meta=_theme_normalize_json(tn_job).get("provider_status") or {}
                if tn_job.phase!="completed":
                    raise RuntimeError(tn_job.last_error or tn_job.message or "표준 테마 재구축 실패")
                unresolved=int(tn_meta.get("unresolved") or 0)
                no_theme=int(tn_meta.get("no_theme") or unresolved)
                hard_errors=int(tn_meta.get("errors") or tn_job.failed or 0)
                fallback=int(tn_meta.get("fallback_classified") or 0)
                _finish(
                    "theme_engine","partial" if hard_errors else "done",
                    "완료" if not hard_errors else f"완료 · 실제 오류 {hard_errors:,}개",
                    hard_errors,
                    classify_sync_result(hard_failures=hard_errors),
                )
                window_count=int(tn_meta.get("engine_classified") or tn_meta.get("classified") or 0)
                provider["theme_engine"]={
                    "classified":window_count,"unresolved":unresolved,"no_theme":no_theme,
                    "fallback_classified":fallback,"errors":hard_errors,
                    "coverage":float(tn_meta.get("classification_coverage") or 0),
                }

            # 7) Investor flow
            if "flow" in selected_set:
                flow_target="전체 분석종목" if resolved_flow_limit==0 else f"상위 {resolved_flow_limit:,}종목"
                _begin("flow",f"{flow_target} 수급 데이터를 갱신합니다.")
                _flow_sync_task=asyncio.current_task()
                await _run_flow_sync(admin_id,resolved_flow_limit,resolved_history_days)
                flow_job=_flow_state(db);db.refresh(flow_job)
                flow_meta=_flow_status_json(flow_job).get("provider_status") or {}
                if flow_job.phase not in ("done","completed","partial"):
                    raise RuntimeError(flow_job.last_error or flow_job.message or "수급 동기화 실패")
                hard_fail=int(flow_job.failed or 0)
                missing=int(flow_meta.get("missing_data") or 0)
                deferred=int(flow_meta.get("deferred") or 0)
                warn=hard_fail+missing+deferred
                _finish(
                    "flow","partial" if warn else "done",
                    "완료" if not warn else f"완료 · 데이터 없음 {missing:,} / 다음회차 보강 {deferred:,} / 오류 {hard_fail:,}",
                    warn,
                    classify_sync_result(hard_failures=hard_fail,deferred=deferred,missing_data=missing),
                )
                provider["flow_summary"]={
                    "success":int(flow_job.success or 0),
                    "skipped":int(flow_meta.get("skipped") or 0),
                    "missing_data":missing,
                    "deferred":deferred,
                    "failed":hard_fail,
                    "eligible_total":int(flow_meta.get("eligible_total") or 0),
                    "selected_total":int(flow_meta.get("selected_total") or 0),
                    "outside_selection":int(flow_meta.get("outside_selection") or 0),
                    "selected_coverage_percent":flow_meta.get("selected_coverage_percent"),
                    "diagnostic_log":flow_meta.get("diagnostic_log"),
                }

            # 8) Smart score cache
            if "smart_scores" in selected_set:
                _begin("smart_scores","스마트 분석 점수를 계산합니다.")
                smart_total=int(_smart_score_cache_stats(db).get("total") or 0)
                job.item_total=smart_total
                job.item_completed=0
                commit_or_rollback(db)

                def _smart_cache_progress(done,total):
                    pct=round(done/max(1,total)*100,1)
                    step_map["smart_scores"].update(status="running",progress=pct,message=f"{done:,}/{total:,}종목")
                    completed=sum(1 for x in steps if x.get("selected") and x.get("status") in ("done","partial"))
                    job.progress_value=min(99.0,((completed+(pct/100))/max(1,len(selected_scopes)))*100.0)
                    job.item_total=int(total);job.item_completed=int(done)
                    provider["steps"]=steps
                    job.provider_status_json=_bounded_provider_json(provider)
                    commit_or_rollback(db)

                try:
                    smart_cache=_rebuild_smart_score_cache(db,progress_callback=_smart_cache_progress)
                    provider["smart_score_cache"]=smart_cache
                    _finish("smart_scores","done",f"완료 · {int(smart_cache.get('cached') or 0):,}종목")
                except Exception as cache_exc:
                    logger.exception("smart score cache stage failed")
                    rollback_quietly(db)
                    job=_unified_sync_job(db)
                    provider=_unified_provider(job)
                    # Restore our in-memory step list after rollback/reload.
                    provider["steps"]=steps
                    provider["smart_score_cache_warning"]=_sync_error_text(cache_exc,700)
                    _finish("smart_scores","partial","기존 점수 유지 · 다음 실행에서 다시 계산",1,"retry")

            warnings=[x for x in steps if x.get("status")=="partial"]
            provider["steps"]=steps
            provider["warnings"]=[{
                "key":x.get("key"),
                "label":x.get("label"),
                "message":x.get("message"),
                "warning_count":int(x.get("warning_count") or 0),
                "severity":_sync_step_severity(x),
            } for x in warnings]
            provider["warning_count"]=len(warnings)
            provider["issue_count"]=sum(1 for x in warnings if _sync_step_severity(x)=="error")
            provider["retry_count"]=sum(1 for x in warnings if _sync_step_severity(x)=="retry")
            provider["notice_count"]=sum(1 for x in warnings if _sync_step_severity(x)=="info")
            provider["last_success_at"]=datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
            provider["last_completed_scopes"]=selected_scopes
            job.running=False
            job.phase="success_with_warnings" if warnings else "completed"
            job.stage_label=("완료 · 일부 오류" if provider["issue_count"] else ("완료 · 자동 보완 예정" if provider["retry_count"] else "완료 · 일부 데이터 없음")) if warnings else "완료"
            job.progress_value=100
            job.last_error=""
            job.current_code="";job.current_name="";job.current_market="";job.eta_seconds=0
            result_parts=[]
            if provider["issue_count"]:result_parts.append(f"일부 오류 {provider['issue_count']}단계")
            if provider["retry_count"]:result_parts.append(f"자동 보완 예정 {provider['retry_count']}단계")
            if provider["notice_count"]:result_parts.append(f"데이터 없음 포함 {provider['notice_count']}단계")
            job.message=f"선택한 {len(selected_scopes)}개 항목 동기화를 완료했습니다."+(f" {' · '.join(result_parts)}." if result_parts else "")
            if trigger=="schedule":
                slot_label=str(scheduled_slot or provider.get("last_auto_slot") or "").split("@",1)[-1]
                provider["auto_scheduler_message"]=f"{slot_label+' ' if slot_label else ''}자동 동기화를 완료했습니다."
            job.finished_at=datetime.now()
            job.provider_status_json=_bounded_provider_json(provider)
            commit_or_rollback(db)
        except asyncio.CancelledError:
            append_sync_diagnostic(diagnostic_file,"WARNING","UNIFIED_SYNC_CANCELLED",details={"trigger":trigger,"current_step":current_step_key})
            rollback_quietly(db)
            try:
                job=_unified_sync_job(db)
                provider=_unified_provider(job)
                saved_steps=provider.get("steps") or steps
                now_iso=datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
                for step in saved_steps:
                    if step.get("status")=="running":
                        step.update(status="cancelled",finished_at=now_iso,message="관리자 중지")
                    elif step.get("selected") and step.get("status")=="pending":
                        step.update(status="not_run",message="중지로 미실행")
                provider["steps"]=saved_steps
                if trigger=="schedule":
                    slot_label=str(scheduled_slot or provider.get("last_auto_slot") or "").split("@",1)[-1]
                    provider["auto_scheduler_message"]=f"{slot_label+' ' if slot_label else ''}자동 동기화가 중지되었습니다."
                job.running=False;job.phase="cancelled";job.stage_label="중지";job.message="전체 동기화를 중지했습니다.";job.finished_at=datetime.now();job.provider_status_json=_bounded_provider_json(provider);commit_or_rollback(db)
            except Exception:
                rollback_quietly(db)
            raise
        except Exception as exc:
            append_sync_diagnostic(
                diagnostic_file,"ERROR","UNIFIED_SYNC_FATAL",
                details={"trigger":trigger,"current_step":current_step_key,"selected_scopes":selected_scopes},
                exc=exc,
            )
            logger.exception("unified sync failed trigger=%s",trigger)
            rollback_quietly(db)
            try:
                job=_unified_sync_job(db)
                provider=_unified_provider(job)
                saved_steps=provider.get("steps") or steps
                now_iso=datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
                for step in saved_steps:
                    if step.get("status")=="running" or (current_step_key and step.get("key")==current_step_key):
                        step.update(status="failed",progress=min(99,float(step.get("progress") or 0)),finished_at=now_iso,message=_sync_error_text(exc,300),warning_count=1)
                    elif step.get("selected") and step.get("status")=="pending":
                        step.update(status="not_run",message="앞 단계 오류로 미실행")
                provider["steps"]=saved_steps
                provider["failed_stage"]=SYNC_SCOPE_LABELS.get(current_step_key,job.stage_label)
                provider["failed_error"]=_sync_error_text(exc,1400)
                if trigger=="schedule":
                    slot_label=str(scheduled_slot or provider.get("last_auto_slot") or "").split("@",1)[-1]
                    provider["auto_scheduler_message"]=f"{slot_label+' ' if slot_label else ''}자동 동기화가 {provider['failed_stage'] or '일부'} 단계에서 중단되었습니다."
                job.running=False;job.phase="failed";job.stage_label=provider["failed_stage"] or "오류";job.last_error=_sync_error_text(exc,3000);job.message=f"{provider['failed_stage'] or '동기화'} 단계에서 중단되었습니다.";job.finished_at=datetime.now();job.provider_status_json=_bounded_provider_json(provider);commit_or_rollback(db)
            except Exception:
                rollback_quietly(db)
        finally:
            current=asyncio.current_task()
            if _full_market_task is current:_full_market_task=None
            if _theme_sync_task is current:_theme_sync_task=None
            if _market_theme_sync_task is current:_market_theme_sync_task=None
            if _classification_sync_task is current:_classification_sync_task=None
            if _flow_sync_task is current:_flow_sync_task=None
            try:
                append_sync_diagnostic(
                    diagnostic_file,"INFO","UNIFIED_SYNC_FINISH",
                    details={"trigger":trigger,"phase":getattr(job,"phase",None),"stage":getattr(job,"stage_label",None)},
                )
            except Exception:
                pass
            db.close()
            deactivate_sync_diagnostic(diagnostic_token)


def _schedule_slot_datetime(slot_key:str):
    try:
        date_part,time_part=str(slot_key or "").split("@",1)
        return datetime.strptime(f"{date_part} {time_part}","%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def _schedule_updated_at_local(schedule):
    value=getattr(schedule,"updated_at",None)
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return value.astimezone(ZoneInfo("Asia/Seoul"))


async def _nightly_full_sync_loop():
    global _unified_sync_task
    while True:
        try:
            now=datetime.now(ZoneInfo("Asia/Seoul"))
            db=SessionLocal()
            try:
                schedule=_sync_schedule_row(db)
                job=_unified_sync_job(db)
                provider=_unified_provider(job)
                if schedule.enabled:
                    run_times=_schedule_times(schedule)
                    slot_key=select_due_run_slot(
                        run_times,
                        date_iso=now.date().isoformat(),
                        current_hhmm=now.strftime("%H:%M"),
                        last_auto_slot=provider.get("last_auto_slot", ""),
                    )
                    # Saving a schedule must not immediately execute a time that was already
                    # in the past before the save.  Backend restarts, however, keep the same
                    # updated_at value so genuinely missed slots remain eligible for catch-up.
                    configured_at=_schedule_updated_at_local(schedule)
                    slot_at=_schedule_slot_datetime(slot_key) if slot_key else None
                    if slot_at and configured_at and slot_at < configured_at:
                        slot_key=None

                    if slot_key:
                        busy=_sync_task_alive(_unified_sync_task) or _any_individual_sync_running()
                        provider["auto_pending_slot"]=slot_key
                        provider["auto_pending_since"]=provider.get("auto_pending_since") or now.isoformat()
                        if busy:
                            pending_time=slot_key.split("@",1)[-1]
                            message=f"{pending_time} 자동 동기화 회차가 대기 중입니다. 현재 작업이 끝나면 자동으로 실행합니다."
                            if provider.get("auto_scheduler_message")!=message:
                                provider["auto_scheduler_message"]=message
                                job.provider_status_json=_bounded_provider_json(provider)
                                commit_or_rollback(db)
                        else:
                            schedule_scopes=_schedule_scopes(schedule)
                            require_kiwoom=bool(set(schedule_scopes)&{"kiwoom","kiwoom_themes","flow"})
                            admin=_find_sync_admin(db,require_kiwoom=require_kiwoom)
                            if admin:
                                provider["auto_last_attempt_at"]=now.isoformat()
                                provider["auto_scheduler_message"]=f"{slot_key.split('@',1)[-1]} 자동 동기화를 시작합니다."
                                job.provider_status_json=_bounded_provider_json(provider)
                                commit_or_rollback(db)
                                _unified_sync_task=asyncio.create_task(
                                    _run_unified_sync(
                                        admin.id,
                                        "schedule",
                                        slot_key,
                                        int(schedule.flow_universe_limit or 0),
                                        int(schedule.flow_history_days or 20),
                                        schedule_scopes,
                                    )
                                )
                            else:
                                scheduler_message="자동 동기화에 사용할 활성 관리자 거래 연동을 찾지 못했습니다. 설정을 확인하면 같은 회차를 다시 시도합니다."
                                job_message=f"{slot_key.split('@',1)[-1]} 자동 동기화 회차가 설정 확인을 기다리고 있습니다."
                                if provider.get("auto_scheduler_message")!=scheduler_message or job.message!=job_message:
                                    provider["auto_scheduler_message"]=scheduler_message
                                    job.provider_status_json=_bounded_provider_json(provider)
                                    job.last_error="자동 동기화에 사용할 관리자 계정 또는 키움 거래 연동 설정이 없습니다."
                                    job.message=job_message
                                    commit_or_rollback(db)
                    elif provider.get("auto_pending_slot"):
                        # A pending marker is no longer meaningful once the slot has actually
                        # started or the saved schedule no longer considers it due.
                        last_slot=str(provider.get("last_auto_slot") or "")
                        if last_slot and str(provider.get("auto_pending_slot"))<=last_slot:
                            provider.pop("auto_pending_slot",None)
                            provider.pop("auto_pending_since",None)
                            provider.pop("auto_scheduler_message",None)
                            job.provider_status_json=_bounded_provider_json(provider)
                            commit_or_rollback(db)
                elif provider.get("auto_pending_slot"):
                    provider.pop("auto_pending_slot",None)
                    provider.pop("auto_pending_since",None)
                    provider["auto_scheduler_message"]="자동 전체 동기화가 꺼져 있습니다."
                    job.provider_status_json=_bounded_provider_json(provider)
                    commit_or_rollback(db)
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduled full sync watcher failed")
        await asyncio.sleep(15)


@app.on_event("startup")
async def start_nightly_full_sync_watcher():
    global _nightly_sync_watcher_task
    if _nightly_sync_watcher_task is None or _nightly_sync_watcher_task.done():
        _nightly_sync_watcher_task=asyncio.create_task(_nightly_full_sync_loop())


@app.on_event("shutdown")
async def stop_nightly_full_sync_watcher():
    global _nightly_sync_watcher_task,_unified_sync_task
    for task in (_nightly_sync_watcher_task,_unified_sync_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass


@app.get("/api/admin/unified-sync/status")
def admin_unified_sync_status(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _unified_sync_task
    job=_unified_sync_job(db)
    # A persisted running flag cannot survive a backend restart.
    if job.running and not _sync_task_alive(_unified_sync_task):
        provider=_unified_provider(job)
        steps=provider.get("steps") or []
        now_iso=datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        for step in steps:
            if step.get("status")=="running":
                step.update(status="cancelled",finished_at=now_iso,message="백엔드 재시작으로 중지")
            elif step.get("selected") and step.get("status")=="pending":
                step.update(status="not_run",message="재시작으로 미실행")
        provider["steps"]=steps
        job.provider_status_json=_bounded_provider_json(provider)
        job.running=False
        job.phase="cancelled"
        job.stage_label="중지"
        job.message="백엔드 재시작으로 이전 전체 동기화를 종료 처리했습니다."
        job.finished_at=datetime.now()
        commit_or_rollback(db)
    return _unified_sync_json(job,db)


@app.post("/api/admin/unified-sync/start")
async def admin_unified_sync_start(
    body:UnifiedSyncStartIn|None=None,
    u:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    global _unified_sync_task
    if _sync_task_alive(_unified_sync_task) or _any_individual_sync_running():
        raise HTTPException(409,"다른 동기화 작업이 진행 중입니다.")
    schedule=_sync_schedule_row(db)
    scopes=_normalize_sync_scopes(body.scopes if body and body.scopes is not None else SYNC_SCOPE_ORDER)
    if set(scopes)&{"kiwoom","kiwoom_themes","flow"}:
        client_for(u,db)
    if set(scopes)&{"dart","classification"}:
        if not (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip():
            raise HTTPException(400,"DART 재무 또는 종목 분류를 실행하려면 OpenDART API 키가 필요합니다.")
    flow_limit=(body.flow_universe_limit if body and body.flow_universe_limit is not None else int(schedule.flow_universe_limit or 0))
    history_days=(body.flow_history_days if body and body.flow_history_days is not None else int(schedule.flow_history_days or 20))
    _unified_sync_task=asyncio.create_task(
        _run_unified_sync(u.id,"manual","",int(flow_limit),int(history_days),scopes)
    )
    labels=[SYNC_SCOPE_LABELS[x] for x in scopes]
    return {
        "ok":True,
        "message":f"선택한 {len(scopes)}개 항목 동기화를 시작했습니다: {', '.join(labels)}",
        "scopes":scopes,
    }


@app.get("/api/admin/unified-sync/schedule")
def admin_unified_sync_schedule(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    return _sync_schedule_json(_sync_schedule_row(db))


@app.put("/api/admin/unified-sync/schedule")
def admin_save_unified_sync_schedule(
    body:SyncScheduleSettingsIn,
    admin:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    row=_sync_schedule_row(db)
    run_times=_normalize_sync_times(body.run_times)
    row.enabled=bool(body.enabled)
    scopes=_normalize_sync_scopes(body.scopes)
    row.run_times_json=json.dumps(run_times,ensure_ascii=False)
    row.sync_scopes_json=json.dumps(scopes,ensure_ascii=False)
    row.flow_universe_limit=int(body.flow_universe_limit)
    row.flow_history_days=int(body.flow_history_days)
    row.updated_by_user_id=admin.id
    row.updated_at=datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    commit_or_rollback(db)
    db.refresh(row)
    return {"ok":True,"message":"자동 동기화 설정을 저장했습니다.","schedule":_sync_schedule_json(row)}


@app.post("/api/admin/unified-sync/stop")
async def admin_unified_sync_stop(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _unified_sync_task
    job=_unified_sync_job(db)
    if not _sync_task_alive(_unified_sync_task):
        if not job.running:
            raise HTTPException(409,"현재 실행 중인 전체 동기화가 없습니다.")
        provider=_unified_provider(job)
        now_iso=datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        for step in provider.get("steps") or []:
            if step.get("status")=="running":
                step.update(status="cancelled",finished_at=now_iso,message="실행 프로세스 종료로 중지")
            elif step.get("selected") and step.get("status")=="pending":
                step.update(status="not_run",message="중지로 미실행")
        job.running=False;job.phase="interrupted";job.stage_label="이전 실행 종료"
        job.message="실행 프로세스가 없는 이전 동기화 상태를 정리했습니다. 새 동기화를 시작할 수 있습니다."
        job.finished_at=datetime.now();job.provider_status_json=_bounded_provider_json(provider)
        commit_or_rollback(db)
        return {"ok":True,"already_stopped":True,"message":"이전 동기화 상태를 정리했습니다. 새 동기화를 시작할 수 있습니다."}
    provider=_unified_provider(job)
    if not job.running:
        _unified_sync_task.cancel()
        job.phase="cancelled";job.stage_label="중지";job.message="동기화 시작 요청을 취소했습니다."
        job.finished_at=datetime.now();commit_or_rollback(db)
        return {"ok":True,"message":"동기화 시작 요청을 취소했습니다."}
    provider["stop_requested"]=True
    provider["stop_requested_at"]=datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    job.phase="stopping";job.stage_label="중지 중";job.message="현재 처리 중인 요청을 정리한 뒤 안전하게 중지합니다."
    job.provider_status_json=_bounded_provider_json(provider)
    commit_or_rollback(db)
    _unified_sync_task.cancel()
    return {"ok":True,"message":"동기화 중지 요청을 보냈습니다. 현재 요청을 정리하고 있습니다."}


@app.get("/api/admin/market-data/status")
def full_market_status(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    job=_full_market_job(db)
    if job.running and not _sync_task_alive(_full_market_task):
        job.running=False;job.phase="cancelled";job.stage_label="중지됨"
        job.current_code="";job.current_name="";job.current_market="";job.eta_seconds=0
        job.message="백엔드 재시작 또는 작업 종료로 이전 시장 데이터 동기화를 종료 처리했습니다."
        job.finished_at=datetime.now();commit_or_rollback(db)
    return _full_market_json(job)

def _ensure_no_market_job():
    if _full_market_task and not _full_market_task.done():
        raise HTTPException(
            409,
            "이미 데이터 수집 작업이 진행 중입니다.",
        )

    if _theme_sync_task and not _theme_sync_task.done():
        raise HTTPException(
            409,
            "키움 전체 테마 동기화가 진행 중입니다. 완료 후 실행해주세요.",
        )

@app.post("/api/admin/market-data/start/kiwoom")
async def start_kiwoom_sync(u:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _full_market_task;_ensure_no_market_job();client_for(u,db)
    _full_market_task=asyncio.create_task(_run_market_data_sync(u.id,"kiwoom"))
    return {"ok":True,"message":"키움 종목목록·일봉·투자지표 수집을 시작했습니다."}

@app.post("/api/admin/market-data/start/dart")
async def start_dart_sync(u:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _full_market_task;_ensure_no_market_job()
    if not (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip():raise HTTPException(400,"관리자 > 외부 API 관리에서 OpenDART API 키를 먼저 설정해주세요.")
    if db.query(Stock).filter(*_stocklog_public_clauses()).count()==0:raise HTTPException(409,"분석 대상 종목이 없습니다. 먼저 키움 데이터 가져오기를 실행해주세요.")
    _full_market_task=asyncio.create_task(_run_market_data_sync(u.id,"dart"))
    return {"ok":True,"message":"OpenDART 실제 재무 수집을 시작했습니다."}

@app.post("/api/admin/market-data/start/all")
async def start_all_sync(u:User=Depends(admin_user),db:Session=Depends(get_db)):
    global _full_market_task;_ensure_no_market_job();client_for(u,db)
    if not (get_provider_credentials(PROVIDER_DART,db).get("api_key") or "").strip():raise HTTPException(400,"전체 데이터 가져오기는 OpenDART API 키가 필요합니다. 관리자 > 외부 API 관리에서 설정해주세요.")
    _full_market_task=asyncio.create_task(_run_market_data_sync(u.id,"all"))
    return {"ok":True,"message":"키움 완료 후 OpenDART를 순서대로 실행합니다."}

@app.post("/api/admin/market-data/start")
async def legacy_start(u:User=Depends(admin_user),db:Session=Depends(get_db)):
    return await start_all_sync(u,db)

@app.post("/api/admin/market-data/stop")
async def stop_full_market_sync(_:User=Depends(admin_user)):
    global _full_market_task
    if not _full_market_task or _full_market_task.done():raise HTTPException(409,"현재 실행 중인 데이터 수집 작업이 없습니다.")
    _full_market_task.cancel();return {"ok":True,"message":"중지 요청을 보냈습니다."}


class ExternalApiSettingsIn(BaseModel):
    client_id: str = ""
    client_secret: str = ""
    api_key: str = ""
    enabled: bool = True


def _normalize_external_provider(provider: str) -> str:
    value=(provider or "").strip().lower().replace("-","_")
    aliases={
        "naver":PROVIDER_NAVER,
        "naver_news":PROVIDER_NAVER,
        "dart":PROVIDER_DART,
        "opendart":PROVIDER_DART,
        "gemini":PROVIDER_GEMINI,
        "google_gemini":PROVIDER_GEMINI,
        "finnhub":PROVIDER_FINNHUB,
        "alpha":PROVIDER_ALPHA_VANTAGE,
        "alphavantage":PROVIDER_ALPHA_VANTAGE,
        "alpha_vantage":PROVIDER_ALPHA_VANTAGE,
        "sec":PROVIDER_SEC_EDGAR,
        "sec_edgar":PROVIDER_SEC_EDGAR,
    }
    normalized=aliases.get(value)
    if not normalized:
        raise HTTPException(404,"지원하지 않는 외부 API입니다.")
    return normalized


def _external_api_admin_payload(db: Session) -> dict:
    return {
        "naver":{
            **provider_public_status(PROVIDER_NAVER,db),
            "usage":usage_stats(PROVIDER_NAVER,db),
        },
        "dart":{
            **provider_public_status(PROVIDER_DART,db),
            "usage":usage_stats(PROVIDER_DART,db),
        },
        "gemini":{
            **provider_public_status(PROVIDER_GEMINI,db),
            "usage":usage_stats(PROVIDER_GEMINI,db),
        },
        "overseas":{
            "free_only":True,
            "finnhub":{
                **provider_public_status(PROVIDER_FINNHUB,db),
                "usage":usage_stats(PROVIDER_FINNHUB,db),
            },
            "alpha_vantage":{
                **provider_public_status(PROVIDER_ALPHA_VANTAGE,db),
                "usage":usage_stats(PROVIDER_ALPHA_VANTAGE,db),
            },
            "sec_edgar":{
                **provider_public_status(PROVIDER_SEC_EDGAR,db),
                "usage":usage_stats(PROVIDER_SEC_EDGAR,db),
            },
            "note":"Finnhub 시세를 우선 사용하고 Alpha Vantage는 무료 일일 한도 내 보조, SEC EDGAR는 공시 전용으로 사용합니다.",
        },
        "note":"호출량은 StockLog 서버가 해당 키로 실행한 요청을 기준으로 집계합니다.",
    }


def _repair_external_api_admin_session(db: Session) -> None:
    # A failed SELECT/INSERT leaves a SQLAlchemy session in rollback-only state.
    # Repair the v3.40 schema and reset the request session before one retry.
    try:
        db.rollback()
    except Exception:
        pass
    ensure_external_api_schema()
    try:
        db.expire_all()
    except Exception:
        pass


@app.get("/api/admin/external-apis")
def admin_external_apis(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    """Masked configuration + StockLog-recorded usage. Secrets never leave backend."""
    try:
        return _external_api_admin_payload(db)
    except SQLAlchemyError:
        logger.exception("external API admin read failed; repairing schema and retrying")
        _repair_external_api_admin_session(db)
        return _external_api_admin_payload(db)


@app.put("/api/admin/external-apis/{provider}")
def admin_save_external_api(
    provider:str,
    body:ExternalApiSettingsIn,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    normalized=_normalize_external_provider(provider)

    # Normalize copied console values before encryption.  This prevents an
    # invisible newline/space from becoming part of an API credential.
    clean_client_id=(body.client_id or "").strip()
    clean_client_secret=(body.client_secret or "").strip()
    clean_api_key=(body.api_key or "").strip()

    def _save_once() -> None:
        if normalized==PROVIDER_NAVER:
            existing=get_provider_credentials(PROVIDER_NAVER,db)
            if not clean_client_id and not existing.get("client_id"):
                raise HTTPException(400,"네이버 Client ID를 입력해 주세요.")
            if not clean_client_secret and not existing.get("client_secret"):
                raise HTTPException(400,"네이버 Client Secret을 입력해 주세요.")
            save_provider_credentials(
                normalized,db,
                client_id=clean_client_id or existing.get("client_id", ""),
                client_secret=clean_client_secret or existing.get("client_secret", ""),
                enabled=body.enabled,
            )
        elif normalized==PROVIDER_SEC_EDGAR:
            existing=get_provider_credentials(normalized,db)
            if not clean_client_id and not existing.get("contact"):
                raise HTTPException(400,"SEC EDGAR 요청 식별용 이메일 또는 연락처를 입력해 주세요.")
            save_provider_credentials(
                normalized,db,
                client_id=clean_client_id or existing.get("contact", ""),
                enabled=body.enabled,
            )
        else:
            existing=get_provider_credentials(normalized,db)
            if not clean_api_key and not existing.get("api_key"):
                label={PROVIDER_GEMINI:"Gbot",PROVIDER_DART:"OpenDART",PROVIDER_FINNHUB:"Finnhub",PROVIDER_ALPHA_VANTAGE:"Alpha Vantage"}.get(normalized,"외부")
                raise HTTPException(400,f"{label} API Key를 입력해 주세요.")
            save_provider_credentials(
                normalized,db,
                api_key=clean_api_key or existing.get("api_key", ""),
                enabled=body.enabled,
            )

    try:
        _save_once()
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("external API credential save failed; repairing schema and retrying")
        _repair_external_api_admin_session(db)
        _save_once()
    except Exception as exc:
        db.rollback()
        logger.exception("external API credential encryption/save failed provider=%s",normalized)
        raise HTTPException(500,f"외부 API 설정 저장에 실패했습니다: {type(exc).__name__}")

    return {
        "ok":True,
        "message":"MySQL에 암호화하여 저장했습니다.",
        "config":provider_public_status(normalized,db),
    }


@app.delete("/api/admin/external-apis/{provider}")
def admin_delete_external_api(
    provider:str,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    normalized=_normalize_external_provider(provider)
    delete_provider_credentials(normalized,db)
    return {
        "ok":True,
        "message":"MySQL에 저장된 API 설정을 삭제했습니다. .env 값이 있으면 fallback으로 사용됩니다.",
        "config":provider_public_status(normalized,db),
    }


@app.post("/api/admin/external-apis/{provider}/test")
async def admin_test_external_api(
    provider:str,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    normalized=_normalize_external_provider(provider)
    creds=get_provider_credentials(normalized,db)
    if creds.get("source") in ("none","disabled"):
        raise HTTPException(400,"API 설정이 없거나 비활성화되어 있습니다.")
    commit_or_rollback(db)

    ok=False
    message=""
    try:
        async with httpx.AsyncClient(timeout=15,follow_redirects=True) as client:
            if normalized==PROVIDER_NAVER:
                response=await tracked_get(
                    client,PROVIDER_NAVER,"admin-test/search-news",
                    NAVER_API_HUB_NEWS_URL,
                    request_kind="manual",
                    params={"query":"삼성전자","display":1,"start":1,"sort":"date"},
                    headers=naver_api_hub_headers(
                        creds.get("client_id", ""),
                        creds.get("client_secret", ""),
                    ),
                )
                response.raise_for_status()
                payload=response.json()
                ok=isinstance(payload.get("items"),list)
                message="NAVER API HUB 뉴스 검색 연결이 정상입니다." if ok else "NAVER API HUB 응답 형식을 확인할 수 없습니다."
            elif normalized==PROVIDER_DART:
                end=datetime.now().date()
                begin=end-timedelta(days=7)
                response=await tracked_get(
                    client,PROVIDER_DART,"admin-test/list",
                    "https://opendart.fss.or.kr/api/list.json",
                    request_kind="manual",
                    params={
                        "crtfc_key":creds.get("api_key", ""),
                        "bgn_de":begin.strftime("%Y%m%d"),
                        "end_de":end.strftime("%Y%m%d"),
                        "page_no":1,
                        "page_count":1,
                    },
                )
                response.raise_for_status()
                payload=response.json()
                status=str(payload.get("status") or "")
                ok=status in ("000","013")
                message="OpenDART API 연결이 정상입니다." if ok else f"OpenDART 인증/응답 오류: {payload.get('message') or status}"
            elif normalized==PROVIDER_FINNHUB:
                response=await tracked_get(client,normalized,"admin-test/quote","https://finnhub.io/api/v1/quote",request_kind="manual",params={"symbol":"AAPL","token":creds.get("api_key","")})
                response.raise_for_status();payload=response.json();ok=float(payload.get("c") or 0)>0
                message="Finnhub 해외 시세 연결이 정상입니다." if ok else "Finnhub에서 유효한 AAPL 시세를 받지 못했습니다."
            elif normalized==PROVIDER_ALPHA_VANTAGE:
                response=await tracked_get(client,normalized,"admin-test/global-quote","https://www.alphavantage.co/query",request_kind="manual",params={"function":"GLOBAL_QUOTE","symbol":"IBM","apikey":creds.get("api_key","")})
                response.raise_for_status();payload=response.json();quote=payload.get("Global Quote") or {};ok=float(quote.get("05. price") or 0)>0
                message="Alpha Vantage 해외 시세 연결이 정상입니다." if ok else str(payload.get("Information") or payload.get("Note") or "Alpha Vantage 응답 또는 무료 한도를 확인해주세요.")
            elif normalized==PROVIDER_SEC_EDGAR:
                response=await tracked_get(client,normalized,"admin-test/company-tickers","https://www.sec.gov/files/company_tickers.json",request_kind="manual",headers={"User-Agent":f"StockLog/{creds.get('contact','')}","Accept-Encoding":"gzip, deflate"})
                response.raise_for_status();payload=response.json();ok=isinstance(payload,dict) and bool(payload)
                message="SEC EDGAR 무료 공시 연결이 정상입니다." if ok else "SEC EDGAR 응답을 확인하지 못했습니다."
            else:
                response=await tracked_get(
                    client,PROVIDER_GEMINI,"admin-test/models",
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    request_kind="manual",
                    headers={"x-goog-api-key":creds.get("api_key","")},
                )
                response.raise_for_status()
                payload=response.json()
                names=[str(x.get("name") or "") for x in (payload.get("models") or []) if isinstance(x,dict)]
                preferred_models=("gemini-3.6-flash","gemini-3.5-flash-lite","gemini-2.5-flash")
                available=[name.removeprefix("models/") for name in names]
                matched=next((m for m in preferred_models if m in available), "")
                ok=bool(matched)
                message=("Gbot AI 연결이 정상입니다." if ok else "Gbot 분석 엔진 연결을 확인하지 못했습니다.")
    except Exception as exc:
        ok=False
        message=("Gbot 연결 테스트에 실패했습니다." if normalized==PROVIDER_GEMINI else f"연결 테스트 실패: {exc}")

    set_provider_test_result(normalized,db,ok,message)
    if not ok:
        raise HTTPException(400,message)
    return {
        "ok":True,
        "message":message,
        "config":provider_public_status(normalized,db),
        "usage":usage_stats(normalized,db),
    }


@app.get("/api/admin/external-apis/{provider}/usage")
def admin_external_api_usage(
    provider:str,
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    return usage_stats(_normalize_external_provider(provider),db)


@app.get("/api/admin/external-apis/diagnostics/schema")
def admin_external_api_schema_diagnostics(
    _:User=Depends(admin_user),
):
    return {"ok":True,"schema":external_api_schema_diagnostics()}


def _kiwoom_runtime_snapshot():
    clients=[]
    for user_id,entry in list(_kiwoom_client_cache.items()):
        cli=(entry or {}).get("client")
        if not cli:
            continue
        status=cli.runtime_status()
        status["user_id"]=user_id
        clients.append(status)
    rank={"auth_error":4,"cooldown":3,"warning":2,"ok":1}
    worst=max(clients,key=lambda x:rank.get(x.get("state"),0),default=None)
    return {
        "state":(worst or {}).get("state","ok"),
        "cooldown_seconds":max([float(x.get("cooldown_seconds") or 0) for x in clients] or [0]),
        "last_error":(worst or {}).get("last_error","") or "",
        "last_success_at":max([x.get("last_success_at") or "" for x in clients] or [""]) or None,
        "queued":sum(int(x.get("queued") or 0) for x in clients),
        "active_clients":len(clients),
        "message":{
            "ok":"키움 API 정상",
            "cooldown":"호출 제한 대기 중",
            "auth_error":"키움 인증 오류",
            "warning":"키움 API 일부 오류",
        }.get((worst or {}).get("state","ok"),"키움 API 상태 확인"),
    }


@app.get("/api/admin/kiwoom-runtime")
def admin_kiwoom_runtime(_:User=Depends(admin_user)):
    return _kiwoom_runtime_snapshot()


_SYNC_OVERVIEW_KEYS = {
    "market": FULL_MARKET_SYNC_KEY,
    "theme_sync": THEME_SYNC_KEY,
    "market_theme_sync": MARKET_THEME_SYNC_KEY,
    "classification_sync": CLASSIFICATION_SYNC_KEY,
    "unified_sync": UNIFIED_SYNC_KEY,
    "theme_normalize": THEME_NORMALIZE_KEY,
    "flow_sync": "investor_flow",
}
_sync_overview_cache = {}
_sync_overview_cache_lock = threading.Lock()
_sync_overview_last_error_log_at = 0.0


def _empty_sync_row(key: str):
    return FullMarketSyncState(
        key=key, running=False, phase="idle", job_type="", stage_label="대기",
        provider_status_json="{}", failures_json="[]",
    )

def _default_sync_schedule_for_monitor():
    return SyncScheduleSetting(
        key=SYNC_SCHEDULE_KEY, enabled=True,
        run_times_json=json.dumps(DEFAULT_SYNC_TIMES,ensure_ascii=False),
        sync_scopes_json=json.dumps(SYNC_SCOPE_ORDER,ensure_ascii=False),
        flow_universe_limit=0, flow_history_days=20,
    )

def _effective_sync_snapshot(payload:dict,task,label:str):
    """Hide orphaned persisted running flags from the read-only monitor.

    The detailed status endpoints repair these rows in the database, but the
    administrator dashboard intentionally uses one lightweight overview call.
    A process restart must therefore not leave that dashboard permanently
    locked in a running state.
    """
    data=dict(payload or {})
    if data.get("running") and not _sync_task_alive(task):
        data.update({
            "running":False,
            "phase":"interrupted",
            "stage_label":"이전 실행 종료",
            "message":f"서버 재시작으로 이전 {label} 작업이 종료되었습니다. 새 동기화를 시작할 수 있습니다.",
            "eta_seconds":0,
            "orphaned_run":True,
            "recovery_available":True,
        })
    return data

def _build_sync_overview_snapshot(db: Session):
    """Read all monitor state with two SELECTs and no writes/repair side effects."""
    keys=list(_SYNC_OVERVIEW_KEYS.values())
    rows=db.query(FullMarketSyncState).filter(FullMarketSyncState.key.in_(keys)).all()
    by_key={row.key:row for row in rows}
    schedule=(db.query(SyncScheduleSetting)
              .filter(SyncScheduleSetting.key==SYNC_SCHEDULE_KEY).first())
    if schedule is None:
        schedule=_default_sync_schedule_for_monitor()

    market=by_key.get(FULL_MARKET_SYNC_KEY) or _empty_sync_row(FULL_MARKET_SYNC_KEY)
    theme=by_key.get(THEME_SYNC_KEY) or _empty_sync_row(THEME_SYNC_KEY)
    market_theme=by_key.get(MARKET_THEME_SYNC_KEY) or _empty_sync_row(MARKET_THEME_SYNC_KEY)
    classification=by_key.get(CLASSIFICATION_SYNC_KEY) or _empty_sync_row(CLASSIFICATION_SYNC_KEY)
    unified=by_key.get(UNIFIED_SYNC_KEY) or _empty_sync_row(UNIFIED_SYNC_KEY)
    normalize=by_key.get(THEME_NORMALIZE_KEY) or _empty_sync_row(THEME_NORMALIZE_KEY)
    flow=by_key.get("investor_flow") or _empty_sync_row("investor_flow")

    unified_json=_effective_sync_snapshot(_unified_sync_json(unified,db,schedule_row=schedule),_unified_sync_task,"전체 동기화")
    return {
        "market":_effective_sync_snapshot(_full_market_json(market),_full_market_task,"시장 데이터 동기화"),
        "theme_sync":_effective_sync_snapshot(_theme_sync_json(theme),_theme_sync_task,"키움 테마 동기화"),
        "market_theme_sync":_effective_sync_snapshot(_market_theme_json(market_theme),_market_theme_sync_task,"시장 테마 동기화"),
        "classification_sync":_effective_sync_snapshot(_classification_json(classification),_classification_sync_task,"종목 분류 동기화"),
        "unified_sync":unified_json,
        "theme_normalize":_effective_sync_snapshot(_theme_normalize_json(normalize),_theme_normalize_task,"표준 테마 재구축"),
        "flow_sync":_effective_sync_snapshot(_flow_status_json(flow),_flow_sync_task,"수급 데이터 동기화"),
        "kiwoom_runtime":_kiwoom_runtime_snapshot(),
        "db_pool":database_pool_status(),
        "monitor_pool":monitor_pool_status(),
        "server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "degraded":False,
    }

@app.get("/api/admin/sync-overview")
async def admin_sync_overview(_:User=Depends(admin_monitor_user)):
    """Fast sync monitor isolated from AnyIO's shared worker pool and main DB pool."""
    started=time.monotonic()

    def _read_snapshot():
        db=MonitorSessionLocal()
        try:
            return _build_sync_overview_snapshot(db)
        finally:
            db.close()

    try:
        # Monitor pool itself fails in ~2s; this outer guard also protects against
        # driver/network stalls that do not respect SQLAlchemy's pool timeout.
        monitor_task=asyncio.create_task(run_monitor_blocking(_read_snapshot))
        done,_=await asyncio.wait({monitor_task},timeout=3.0)
        if not done:
            monitor_task.cancel()
            raise TimeoutError("sync overview monitor timeout")
        data=monitor_task.result()
        data["monitor_ms"]=round((time.monotonic()-started)*1000,1)
        with _sync_overview_cache_lock:
            _sync_overview_cache.clear();_sync_overview_cache.update(data)
        return data
    except Exception as exc:
        global _sync_overview_last_error_log_at
        with _sync_overview_cache_lock:
            cached=dict(_sync_overview_cache)
        now_mono=time.monotonic()
        if now_mono-_sync_overview_last_error_log_at>=60:
            _sync_overview_last_error_log_at=now_mono
            filename=begin_sync_diagnostic(
                "sync-overview",
                run_id=f"monitor-{time.time_ns()}",
                metadata={"cached_snapshot_available":bool(cached)},
            )
            append_sync_diagnostic(
                filename,"ERROR","SYNC_OVERVIEW_MONITOR_FALLBACK",
                details={
                    "elapsed_ms":round((now_mono-started)*1000,1),
                    "main_pool":database_pool_status(),
                    "monitor_pool":monitor_pool_status(),
                },
                exc=exc,
            )
        if cached:
            runtime_tasks={
                "market":(_full_market_task,"시장 데이터 동기화"),
                "theme_sync":(_theme_sync_task,"키움 테마 동기화"),
                "market_theme_sync":(_market_theme_sync_task,"시장 테마 동기화"),
                "classification_sync":(_classification_sync_task,"종목 분류 동기화"),
                "unified_sync":(_unified_sync_task,"전체 동기화"),
                "theme_normalize":(_theme_normalize_task,"표준 테마 재구축"),
                "flow_sync":(_flow_sync_task,"수급 데이터 동기화"),
            }
            for key,(task,label) in runtime_tasks.items():
                cached[key]=_effective_sync_snapshot(cached.get(key) or {},task,label)
            cached.update({
                "degraded":True,
                "degraded_reason":_sync_error_text(exc,500),
                "server_time":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                "monitor_ms":round((time.monotonic()-started)*1000,1),
            })
            return cached
        raise HTTPException(503,"동기화 상태 저장소에 일시적으로 연결할 수 없습니다.")

@app.get("/api/admin/status")
def admin_status(
    _:User=Depends(admin_user),
    db:Session=Depends(get_db),
):
    st=(
        db.query(SyncState)
        .filter(
            SyncState.key=="stocks"
        )
        .first()
    )

    active=(
        db.query(Stock)
        .filter(Stock.is_active==True)
        .count()
    )
    analysis_active=(
        db.query(Stock)
        .filter(*_stocklog_public_clauses())
        .count()
    )

    inactive=(
        db.query(Stock)
        .filter(
            Stock.is_active==False
        )
        .count()
    )

    markets={
        name:
        db.query(Stock)
        .filter(
            *_stocklog_public_clauses(),
            Stock.market==name,
        )
        .count()
        for name in STOCKLOG_PUBLIC_MARKETS
    }

    theme_stats = (
        _safe_theme_db_stats(db)
    )

    classification_stats=_classification_coverage_stats(
        db,
        sample_limit=0,
        analysis_eligible_only=True,
    )

    return {
        "users":
            db.query(User).count(),
        "stocks":
            analysis_active,
        "raw_stocks":
            active,
        "excluded_stocks":
            max(0,active-analysis_active),
        "inactive_stocks":
            inactive,
        "markets":
            markets,
        "themes":
            theme_stats["themes"],
        "stock_theme_links":
            theme_stats["stock_theme_links"],
        "kiwoom_themes":
            theme_stats["kiwoom_themes"],
        "market_themes":
            theme_stats["market_themes"],
        "kiwoom_theme_links":
            theme_stats["kiwoom_theme_links"],
        "market_theme_links":
            theme_stats["market_theme_links"],
        "dart_industry_stocks":
            classification_stats["dart_industry_stocks"],
        "effective_classified_stocks":
            classification_stats["effective_classified_stocks"],
        "classification_coverage_percent":
            classification_stats["coverage_percent"],
        "themes_table":
            theme_stats[
                "themes_table"
            ],
        "stock_themes_table":
            theme_stats[
                "stock_themes_table"
            ],
        "theme_db_error":
            theme_stats[
                "theme_db_error"
            ],
        "running":
            bool(st.running)
            if st
            else False,
        "last_success_at":
            (
                st.last_success_at.isoformat()
                if st
                and st.last_success_at
                else None
            ),
        "last_error":
            st.last_error
            if st
            else "",
    }


@app.post("/api/admin/sync/stocks")
async def sync_stocks(_:User=Depends(admin_user),db:Session=Depends(get_db)):
    if _sync_lock.locked():
        raise HTTPException(409,"이미 종목 동기화가 진행 중입니다.")
    st=db.query(SyncState).filter(SyncState.key=="stocks").first()
    cooldown=int(os.getenv("SYNC_COOLDOWN_SECONDS","60"))
    if st.last_success_at and (datetime.now()-st.last_success_at).total_seconds()<cooldown:
        remain=cooldown-int((datetime.now()-st.last_success_at).total_seconds())
        raise HTTPException(429,f"{remain}초 후 다시 동기화할 수 있습니다.")
    async with _sync_lock:
        st.running=True;st.last_started_at=datetime.now();st.last_error="";commit_or_rollback(db)
        try:
            rows=db.query(Stock).filter(*_stocklog_public_clauses()).all()
            for s in rows:
                s.category=classify_stock(s)
                s.score=compute_score(s)[0]
                s.updated_at=datetime.now()
            st.running=False;st.last_finished_at=datetime.now();st.last_success_at=datetime.now()
            commit_or_rollback(db)
            return {"ok":True,"updated":len(rows),"message":"KOSPI·KOSDAQ 일반 상장종목의 카테고리와 스마트 점수를 갱신했습니다."}
        except Exception as e:
            st.running=False;st.last_finished_at=datetime.now();st.last_error=str(e);commit_or_rollback(db)
            raise HTTPException(500,str(e))
