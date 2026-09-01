from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from .database import SessionLocal, engine
from .models import ApiUsageDaily, ApiUsageLog, ExternalApiCredential
from .security import decrypt_secret, encrypt_secret
from .db_utils import commit_or_rollback, flush_or_rollback

PROVIDER_NAVER = "naver_news"
PROVIDER_DART = "opendart"
PROVIDER_GEMINI = "gemini"
PROVIDER_FINNHUB = "finnhub"
PROVIDER_ALPHA_VANTAGE = "alpha_vantage"
PROVIDER_SEC_EDGAR = "sec_edgar"

# Free-plan safety envelopes. Alpha Vantage documents 25 requests/day for a
# standard free key. StockLog stops at that boundary instead of producing
# accidental paid expectations or repeatedly hammering a rejected endpoint.
ALPHA_VANTAGE_FREE_DAILY_LIMIT = 25

# StockLog-side guardrails for a free-only Gemini deployment. These are
# deliberately application limits, not claims about Google's project quota.
GEMINI_APP_DAILY_GUARD = max(1, int(os.getenv("GEMINI_APP_DAILY_GUARD", "200")))
GEMINI_BACKGROUND_GUARD = max(0, int(os.getenv("GEMINI_BACKGROUND_GUARD", "120")))

NAVER_DAILY_LIMIT = 25_000
NAVER_MONTHLY_FREE_LIMIT = 775_000
NAVER_WARN_AT = 15_000
NAVER_THROTTLE_AT = 20_000
NAVER_HARD_GUARD_AT = 24_950
NAVER_API_HUB_NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"

# External-API usage accounting writes to SQL. Keep those writes away from
# FastAPI/AnyIO's default worker pool so thousands of DART/Kiwoom telemetry
# events cannot starve admin status and diagnostic endpoints.
_EXTERNAL_API_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stocklog-api-telemetry")


async def _run_external_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_EXTERNAL_API_EXECUTOR, partial(func, *args, **kwargs))


def ensure_external_api_schema() -> None:
    """Repair v3.40 external-API tables in-place.

    SQLAlchemy ``create_all`` creates missing tables but deliberately does not
    add columns to tables that already exist.  StockLog has had several
    development snapshots of these tables, so an existing MySQL database may
    contain an older/partial shape.  Keep startup idempotent and add only the
    columns required by the current models.
    """
    # First create any completely missing tables using the canonical models.
    for model in (ExternalApiCredential, ApiUsageDaily, ApiUsageLog):
        model.__table__.create(bind=engine, checkfirst=True)

    required = {
        "external_api_credentials": [
            ("provider", "VARCHAR(40) NULL"),
            ("client_id_enc", "TEXT NULL"),
            ("client_secret_enc", "TEXT NULL"),
            ("api_key_enc", "TEXT NULL"),
            ("is_enabled", "BOOLEAN DEFAULT 1"),
            ("last_test_status", "VARCHAR(20) DEFAULT 'untested'"),
            ("last_test_message", "TEXT NULL"),
            ("last_tested_at", "DATETIME NULL"),
            ("created_at", "DATETIME NULL"),
            ("updated_at", "DATETIME NULL"),
        ],
        "api_usage_daily": [
            ("provider", "VARCHAR(40) NULL"),
            ("usage_date", "VARCHAR(10) NULL"),
            ("total_calls", "INT DEFAULT 0"),
            ("successful_calls", "INT DEFAULT 0"),
            ("failed_calls", "INT DEFAULT 0"),
            ("background_calls", "INT DEFAULT 0"),
            ("interactive_calls", "INT DEFAULT 0"),
            ("manual_calls", "INT DEFAULT 0"),
            ("last_request_at", "DATETIME NULL"),
            ("updated_at", "DATETIME NULL"),
        ],
        "api_usage_logs": [
            ("provider", "VARCHAR(40) NULL"),
            ("endpoint", "VARCHAR(120) NULL"),
            ("request_kind", "VARCHAR(20) DEFAULT 'system'"),
            ("stock_code", "VARCHAR(20) NULL"),
            ("success", "BOOLEAN DEFAULT 1"),
            ("status_code", "INT NULL"),
            ("duration_ms", "DOUBLE DEFAULT 0"),
            ("error_message", "TEXT NULL"),
            ("requested_at", "DATETIME NULL"),
        ],
    }

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table_name, columns in required.items():
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for column_name, ddl_type in columns:
                if column_name not in existing:
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}"
                    ))

        # v3.40 development builds used a legacy ``enabled`` column while the
        # current ORM model uses ``is_enabled``.  Some MySQL installations have
        # the old column as NOT NULL without a default, which makes *every new
        # INSERT* fail even though SQLAlchemy no longer writes that column.
        # Keep the legacy column harmless for backward compatibility instead of
        # dropping it: give it a default and mirror any existing value once.
        ext_columns = {c["name"]: c for c in inspect(engine).get_columns("external_api_credentials")}
        if "enabled" in ext_columns:
            conn.execute(text(
                "UPDATE external_api_credentials "
                "SET enabled = COALESCE(enabled, is_enabled, 1)"
            ))
            conn.execute(text(
                "ALTER TABLE external_api_credentials "
                "MODIFY COLUMN enabled BOOLEAN NOT NULL DEFAULT 1"
            ))

        # Another early v3.40 snapshot stored test errors in a mandatory
        # ``last_error`` column. The current model replaced it with the more
        # general ``last_test_message``. If the legacy column remains NOT NULL
        # without a default, successful connection-test INSERTs fail with 1364.
        if "last_error" in ext_columns:
            conn.execute(text(
                "ALTER TABLE external_api_credentials "
                "MODIFY COLUMN last_error TEXT NULL"
            ))

    # Re-inspect after ALTERs and add useful indexes only when absent.  Index
    # creation failures are non-fatal because they affect speed, not correctness.
    try:
        inspector = inspect(engine)
        with engine.begin() as conn:
            index_specs = {
                "external_api_credentials": [
                    ("ix_external_api_credentials_provider", "provider", True),
                ],
                "api_usage_daily": [
                    ("ix_api_usage_daily_provider", "provider", False),
                    ("ix_api_usage_daily_usage_date", "usage_date", False),
                ],
                "api_usage_logs": [
                    ("ix_api_usage_logs_provider", "provider", False),
                    ("ix_api_usage_logs_requested_at", "requested_at", False),
                ],
            }
            for table_name, specs in index_specs.items():
                existing_indexes = {i.get("name") for i in inspector.get_indexes(table_name)}
                for name, column, unique in specs:
                    if name in existing_indexes:
                        continue
                    unique_sql = "UNIQUE " if unique else ""
                    conn.execute(text(
                        f"CREATE {unique_sql}INDEX {name} ON {table_name} ({column})"
                    ))
    except Exception:
        # Do not prevent StockLog from starting for an optional index repair.
        pass


def external_api_schema_diagnostics() -> dict[str, Any]:
    """Small admin-safe schema report used when troubleshooting upgrades."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    names = ("external_api_credentials", "api_usage_daily", "api_usage_logs")
    return {
        name: {
            "exists": name in tables,
            "columns": [c["name"] for c in inspector.get_columns(name)] if name in tables else [],
        }
        for name in names
    }


def naver_api_hub_headers(client_id: str, client_secret: str) -> dict[str, str]:
    """Authentication headers required by NAVER API HUB Search API."""
    return {
        "X-NCP-APIGW-API-KEY-ID": str(client_id or "").strip(),
        "X-NCP-APIGW-API-KEY": str(client_secret or "").strip(),
    }

_USAGE_LOG_RETENTION_DAYS = 14
_last_usage_cleanup_monotonic = 0.0
_CREDENTIAL_CACHE_TTL_SECONDS = 30
_credential_cache: dict[str, tuple[float, dict[str, str]]] = {}


def _mask(value: str, visible: int = 4) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= visible:
        return "•" * len(value)
    return value[:visible] + "•" * max(4, min(12, len(value) - visible))


def _safe_decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return decrypt_secret(value)
    except Exception:
        return ""


def get_provider_credentials(provider: str, db: Session | None = None) -> dict[str, str]:
    """DB credentials first; .env remains a backward-compatible fallback."""
    cached=_credential_cache.get(provider)
    if cached and cached[0]>time.monotonic():
        return dict(cached[1])

    own = db is None
    session = db or SessionLocal()
    result: dict[str,str] = {"source":"none"}
    try:
        row = session.query(ExternalApiCredential).filter(ExternalApiCredential.provider == provider).first()
        if row and not row.is_enabled:
            result={"source":"disabled"}
        elif row and row.is_enabled:
            if provider == PROVIDER_NAVER:
                cid = _safe_decrypt(row.client_id_enc)
                secret = _safe_decrypt(row.client_secret_enc)
                if cid and secret:
                    result={"client_id":cid,"client_secret":secret,"source":"mysql"}
            elif provider in {PROVIDER_DART, PROVIDER_GEMINI, PROVIDER_FINNHUB, PROVIDER_ALPHA_VANTAGE}:
                key = _safe_decrypt(row.api_key_enc)
                if key:
                    result={"api_key":key,"source":"mysql"}
            elif provider == PROVIDER_SEC_EDGAR:
                contact = _safe_decrypt(row.client_id_enc)
                if contact:
                    result={"contact":contact,"source":"mysql"}

        if result.get("source") == "none":
            if provider == PROVIDER_NAVER:
                cid = os.getenv("NAVER_CLIENT_ID", "").strip()
                secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
                result={"client_id":cid,"client_secret":secret,"source":"env" if cid and secret else "none"}
            elif provider == PROVIDER_DART:
                key = os.getenv("DART_API_KEY", "").strip()
                result={"api_key":key,"source":"env" if key else "none"}
            elif provider == PROVIDER_GEMINI:
                key = os.getenv("GEMINI_API_KEY", "").strip()
                result={"api_key":key,"source":"env" if key else "none"}
            elif provider == PROVIDER_FINNHUB:
                key = os.getenv("FINNHUB_API_KEY", "").strip()
                result={"api_key":key,"source":"env" if key else "none"}
            elif provider == PROVIDER_ALPHA_VANTAGE:
                key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
                result={"api_key":key,"source":"env" if key else "none"}
            elif provider == PROVIDER_SEC_EDGAR:
                contact = os.getenv("SEC_EDGAR_CONTACT", "").strip()
                result={"contact":contact,"source":"env" if contact else "none"}

        _credential_cache[provider]=(time.monotonic()+_CREDENTIAL_CACHE_TTL_SECONDS,dict(result))
        return dict(result)
    finally:
        if own:
            session.close()


def provider_public_status(provider: str, db: Session) -> dict[str, Any]:
    row = db.query(ExternalApiCredential).filter(ExternalApiCredential.provider == provider).first()
    resolved = get_provider_credentials(provider, db)
    out: dict[str, Any] = {
        "provider": provider,
        "configured": resolved.get("source") in ("mysql", "env"),
        "source": resolved.get("source", "none"),
        "stored_in_mysql": bool(row and (row.client_id_enc or row.client_secret_enc or row.api_key_enc)),
        "enabled": bool(row.is_enabled) if row else True,
        "last_test_status": row.last_test_status if row else "untested",
        "last_test_message": row.last_test_message if row else "",
        "last_tested_at": row.last_tested_at.isoformat() if row and row.last_tested_at else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }
    if provider == PROVIDER_NAVER:
        out["client_id_masked"] = _mask(resolved.get("client_id", ""))
        out["secret_configured"] = bool(resolved.get("client_secret"))
    elif provider in {PROVIDER_DART, PROVIDER_GEMINI, PROVIDER_FINNHUB, PROVIDER_ALPHA_VANTAGE}:
        out["api_key_masked"] = _mask(resolved.get("api_key", ""))
    elif provider == PROVIDER_SEC_EDGAR:
        contact=resolved.get("contact","")
        out["contact_masked"]=_mask(contact,visible=min(6,len(contact)))
        out["key_required"]=False
    if provider == PROVIDER_GEMINI:
        out["free_only"] = True
        out["manual_model"] = os.getenv("GEMINI_MANUAL_MODEL", "gemini-3.6-flash").strip() or "gemini-3.6-flash"
        out["background_model"] = os.getenv("GEMINI_BACKGROUND_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
        out["app_daily_guard"] = GEMINI_APP_DAILY_GUARD
        out["background_guard"] = GEMINI_BACKGROUND_GUARD
    return out


def save_provider_credentials(provider: str, db: Session, *, client_id: str = "", client_secret: str = "", api_key: str = "", enabled: bool = True) -> None:
    row = db.query(ExternalApiCredential).filter(ExternalApiCredential.provider == provider).first()
    if row is None:
        row = ExternalApiCredential(provider=provider)
        db.add(row)
    if provider == PROVIDER_NAVER:
        if client_id.strip():
            row.client_id_enc = encrypt_secret(client_id.strip())
        if client_secret.strip():
            row.client_secret_enc = encrypt_secret(client_secret.strip())
    elif provider in {PROVIDER_DART, PROVIDER_GEMINI, PROVIDER_FINNHUB, PROVIDER_ALPHA_VANTAGE}:
        if api_key.strip():
            row.api_key_enc = encrypt_secret(api_key.strip())
    elif provider == PROVIDER_SEC_EDGAR:
        if client_id.strip():
            row.client_id_enc=encrypt_secret(client_id.strip())
    row.is_enabled = bool(enabled)
    row.updated_at = datetime.now()
    commit_or_rollback(db)
    _credential_cache.pop(provider,None)


def delete_provider_credentials(provider: str, db: Session) -> None:
    row = db.query(ExternalApiCredential).filter(ExternalApiCredential.provider == provider).first()
    if row:
        db.delete(row)
        commit_or_rollback(db)
    _credential_cache.pop(provider,None)


def set_provider_test_result(provider: str, db: Session, ok: bool, message: str) -> None:
    row = db.query(ExternalApiCredential).filter(ExternalApiCredential.provider == provider).first()
    if row is None:
        row = ExternalApiCredential(provider=provider)
        db.add(row)
    row.last_test_status = "ok" if ok else "error"
    row.last_test_message = str(message or "")[:1000]
    row.last_tested_at = datetime.now()
    commit_or_rollback(db)


def _usage_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def record_api_usage(provider: str, endpoint: str, *, success: bool, status_code: int | None = None, duration_ms: float = 0, request_kind: str = "system", stock_code: str = "", error_message: str = "") -> None:
    """Use an isolated DB session so metrics never commit/rollback caller work."""
    global _last_usage_cleanup_monotonic
    db = SessionLocal()
    try:
        today = _usage_date()
        row = db.query(ApiUsageDaily).filter(ApiUsageDaily.provider == provider, ApiUsageDaily.usage_date == today).first()
        if row is None:
            row = ApiUsageDaily(provider=provider, usage_date=today)
            db.add(row)
            flush_or_rollback(db)
        row.total_calls = int(row.total_calls or 0) + 1
        if success:
            row.successful_calls = int(row.successful_calls or 0) + 1
        else:
            row.failed_calls = int(row.failed_calls or 0) + 1
        kind = request_kind if request_kind in {"background", "interactive", "manual"} else "interactive"
        if kind == "background":
            row.background_calls = int(row.background_calls or 0) + 1
        elif kind == "manual":
            row.manual_calls = int(row.manual_calls or 0) + 1
        else:
            row.interactive_calls = int(row.interactive_calls or 0) + 1
        row.last_request_at = datetime.now()
        db.add(ApiUsageLog(
            provider=provider,
            endpoint=str(endpoint or "")[:120],
            request_kind=kind,
            stock_code=str(stock_code or "")[:20],
            success=bool(success),
            status_code=status_code,
            duration_ms=float(duration_ms or 0),
            error_message=str(error_message or "")[:2000],
            requested_at=datetime.now(),
        ))
        # Keep detailed logs bounded; daily aggregate rows are retained.
        now_mono=time.monotonic()
        if now_mono-_last_usage_cleanup_monotonic>21600:
            db.query(ApiUsageLog).filter(
                ApiUsageLog.requested_at < datetime.now()-timedelta(days=_USAGE_LOG_RETENTION_DAYS)
            ).delete(synchronize_session=False)
            _last_usage_cleanup_monotonic=now_mono
        commit_or_rollback(db)
    except Exception:
        db.rollback()
    finally:
        db.close()


def current_daily_calls(provider: str) -> int:
    db = SessionLocal()
    try:
        row = db.query(ApiUsageDaily).filter(ApiUsageDaily.provider == provider, ApiUsageDaily.usage_date == _usage_date()).first()
        return int(row.total_calls or 0) if row else 0
    finally:
        db.close()


def naver_request_allowed(request_kind: str = "interactive") -> tuple[bool, str]:
    calls = current_daily_calls(PROVIDER_NAVER)
    if calls >= NAVER_DAILY_LIMIT:
        return False, "네이버 검색 API 일일 25,000회 한도에 도달했습니다."
    if calls >= NAVER_HARD_GUARD_AT:
        return False, "네이버 검색 API 한도 보호 구간입니다. 자정 이후 다시 시도해 주세요."
    if request_kind == "background" and calls >= NAVER_THROTTLE_AT:
        return False, "네이버 검색 API 절약 모드로 일반 백그라운드 뉴스 수집을 잠시 중단했습니다."
    return True, ""


async def tracked_get(client, provider: str, endpoint: str, url: str, *, request_kind: str = "interactive", stock_code: str = "", **kwargs):
    if provider == PROVIDER_NAVER:
        # Quota accounting touches SQL; keep async request handling responsive
        # even if the database pool is under temporary pressure.
        allowed, reason = await _run_external_blocking(naver_request_allowed, request_kind)
        if not allowed:
            raise RuntimeError(reason)
    elif provider == PROVIDER_ALPHA_VANTAGE:
        calls=await _run_external_blocking(current_daily_calls,PROVIDER_ALPHA_VANTAGE)
        if calls>=ALPHA_VANTAGE_FREE_DAILY_LIMIT:
            raise RuntimeError("Alpha Vantage 무료 일일 안전 한도(25회)에 도달했습니다. 내일 자동으로 다시 사용할 수 있습니다.")
    started = time.perf_counter()
    try:
        response = await client.get(url, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000
        ok = 200 <= response.status_code < 400
        error_text = "" if ok else response.text[:500]
        # OpenDART commonly returns HTTP 200 even for authentication/API errors.
        # Treat official status 000(success) and 013(no data) as healthy calls.
        if ok and provider == PROVIDER_DART and str(url).lower().endswith(".json"):
            try:
                payload=response.json()
                dart_status=str(payload.get("status") or "")
                if dart_status and dart_status not in {"000","013"}:
                    ok=False
                    error_text=str(payload.get("message") or f"OpenDART status={dart_status}")[:500]
            except Exception:
                pass
        # Usage telemetry has its own SQLAlchemy session. Run it off the async
        # event loop so a temporarily busy DB pool cannot freeze every coroutine.
        await _run_external_blocking(record_api_usage, provider, endpoint, success=ok, status_code=response.status_code, duration_ms=elapsed, request_kind=request_kind, stock_code=stock_code, error_message=error_text)
        return response
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        await _run_external_blocking(record_api_usage, provider, endpoint, success=False, status_code=None, duration_ms=elapsed, request_kind=request_kind, stock_code=stock_code, error_message=str(exc))
        raise


def gemini_request_allowed(request_kind: str = "interactive") -> tuple[bool, str]:
    """Keep StockLog in a conservative free-only operating envelope.

    Google project quotas can change by account/tier, so StockLog enforces its
    own lower daily ceiling and reserves some calls for user-triggered analysis.
    """
    calls = current_daily_calls(PROVIDER_GEMINI)
    if calls >= GEMINI_APP_DAILY_GUARD:
        return False, "StockLog Gbot 일일 안전 한도에 도달했습니다. 자동 요청을 잠시 중단합니다."
    if request_kind == "background" and calls >= GEMINI_BACKGROUND_GUARD:
        return False, "StockLog Gbot 자동 분석 안전 한도에 도달했습니다. 자동 요청을 잠시 중단합니다."
    return True, ""


async def tracked_post(client, provider: str, endpoint: str, url: str, *, request_kind: str = "interactive", stock_code: str = "", **kwargs):
    if provider == PROVIDER_GEMINI:
        allowed, reason = await _run_external_blocking(gemini_request_allowed, request_kind)
        if not allowed:
            raise RuntimeError(reason)
    started = time.perf_counter()
    try:
        response = await client.post(url, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000
        ok = 200 <= response.status_code < 400
        error_text = "" if ok else response.text[:500]
        await _run_external_blocking(record_api_usage, provider, endpoint, success=ok, status_code=response.status_code, duration_ms=elapsed, request_kind=request_kind, stock_code=stock_code, error_message=error_text)
        return response
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        await _run_external_blocking(record_api_usage, provider, endpoint, success=False, status_code=None, duration_ms=elapsed, request_kind=request_kind, stock_code=stock_code, error_message=str(exc))
        raise


def usage_stats(provider: str, db: Session) -> dict[str, Any]:
    today = _usage_date()
    row = db.query(ApiUsageDaily).filter(ApiUsageDaily.provider == provider, ApiUsageDaily.usage_date == today).first()
    now = datetime.now()
    recent_hour = db.query(ApiUsageLog).filter(ApiUsageLog.provider == provider, ApiUsageLog.requested_at >= now - timedelta(hours=1)).count()
    errors = (
        db.query(ApiUsageLog)
        .filter(ApiUsageLog.provider == provider, ApiUsageLog.success == False)
        .order_by(ApiUsageLog.requested_at.desc())
        .limit(5)
        .all()
    )
    total = int(row.total_calls or 0) if row else 0
    successful = int(row.successful_calls or 0) if row else 0
    failed = int(row.failed_calls or 0) if row else 0
    result: dict[str, Any] = {
        "provider": provider,
        "date": today,
        "total_calls": total,
        "successful_calls": successful,
        "failed_calls": failed,
        "recent_hour_calls": recent_hour,
        "background_calls": int(row.background_calls or 0) if row else 0,
        "interactive_calls": int(row.interactive_calls or 0) if row else 0,
        "manual_calls": int(row.manual_calls or 0) if row else 0,
        "last_request_at": row.last_request_at.isoformat() if row and row.last_request_at else None,
        "recent_errors": [
            {
                "endpoint": x.endpoint,
                "message": x.error_message[:300],
                "status_code": x.status_code,
                "requested_at": x.requested_at.isoformat() if x.requested_at else None,
            }
            for x in errors
        ],
    }
    if provider == PROVIDER_NAVER:
        month_prefix=now.strftime("%Y-%m")
        monthly_calls=(
            db.query(func.coalesce(func.sum(ApiUsageDaily.total_calls),0))
            .filter(ApiUsageDaily.provider==provider,ApiUsageDaily.usage_date.like(f"{month_prefix}%"))
            .scalar()
            or 0
        )
        monthly_calls=int(monthly_calls)
        pct = round((total / NAVER_DAILY_LIMIT) * 100, 1)
        level = "normal"
        message = "여유"
        if total >= NAVER_HARD_GUARD_AT:
            level, message = "critical", "한도 보호"
        elif total >= NAVER_THROTTLE_AT:
            level, message = "throttle", "절약 모드"
        elif total >= NAVER_WARN_AT:
            level, message = "warning", "주의"
        result.update({
            "daily_limit": NAVER_DAILY_LIMIT,
            "monthly_free_limit":NAVER_MONTHLY_FREE_LIMIT,
            "monthly_calls":monthly_calls,
            "monthly_remaining_calls":max(0,NAVER_MONTHLY_FREE_LIMIT-monthly_calls),
            "monthly_usage_percent":round((monthly_calls/NAVER_MONTHLY_FREE_LIMIT)*100,1),
            "remaining_calls": max(0, NAVER_DAILY_LIMIT - total),
            "usage_percent": pct,
            "status_level": level,
            "status_message": message,
            "warning_at": NAVER_WARN_AT,
            "throttle_at": NAVER_THROTTLE_AT,
        })
    elif provider == PROVIDER_GEMINI:
        pct=round((total/GEMINI_APP_DAILY_GUARD)*100,1) if GEMINI_APP_DAILY_GUARD else 0
        result.update({
            "daily_limit":GEMINI_APP_DAILY_GUARD,
            "remaining_calls":max(0,GEMINI_APP_DAILY_GUARD-total),
            "usage_percent":pct,
            "background_guard":GEMINI_BACKGROUND_GUARD,
            "status_level":"warning" if failed else "normal",
            "status_message":"무료 안전 한도 관리 중" if not failed else "오류 확인",
            "note":"Google 공식 할당량과 별개로 StockLog가 자체적으로 적용하는 무료 운영 안전 한도입니다.",
        })
    elif provider == PROVIDER_ALPHA_VANTAGE:
        pct=round((total/ALPHA_VANTAGE_FREE_DAILY_LIMIT)*100,1)
        result.update({
            "daily_limit":ALPHA_VANTAGE_FREE_DAILY_LIMIT,
            "remaining_calls":max(0,ALPHA_VANTAGE_FREE_DAILY_LIMIT-total),
            "usage_percent":pct,
            "status_level":"warning" if total>=20 or failed else "normal",
            "status_message":"무료 한도 주의" if total>=20 else "무료 한도 관리 중",
            "note":"Alpha Vantage 표준 무료 키의 공식 25회/일 범위 안에서만 요청합니다.",
        })
    else:
        result.update({"daily_limit": None, "remaining_calls": None, "usage_percent": None, "status_level": "normal" if failed == 0 else "warning", "status_message": "정상" if failed == 0 else "오류 확인"})
    return result
