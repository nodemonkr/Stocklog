"""Central application configuration for StockLog.

Environment variables still take precedence.  We load both the project-level
.env (network/runtime settings) and backend/.env (API/database secrets) so the
application behaves consistently regardless of the shell working directory.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=False)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./stocklog.db")
    jwt_secret: str = (
        os.getenv("JWT_SECRET")
        or os.getenv("SECRET_KEY")
        or "CHANGE_THIS_TO_A_LONG_RANDOM_STRING"
    )
    access_token_expire_minutes: int = _int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 1440)
    cors_origins_raw: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174",
    )
    sql_echo: bool = _bool_env("SQL_ECHO", False)
    # Keep enough headroom for background workers while failing fast under
    # genuine saturation.  The previous SQLAlchemy defaults (5 + 10 overflow,
    # 30s wait) let admin polling requests pile up for minutes during sync.
    db_pool_size: int = max(5, _int_env("DB_POOL_SIZE", 12))
    db_max_overflow: int = max(0, _int_env("DB_MAX_OVERFLOW", 8))
    db_pool_timeout_seconds: int = max(3, _int_env("DB_POOL_TIMEOUT_SECONDS", 8))
    db_pool_recycle_seconds: int = max(300, _int_env("DB_POOL_RECYCLE_SECONDS", 1800))
    # Fixed deep-link target used by the installed StockLog mobile app after
    # browser-based OAuth. Keep this exact, not user-controlled, to avoid an
    # open redirect.
    mobile_social_return_url: str = os.getenv("STOCKLOG_MOBILE_RETURN_URL", "stocklog://auth").strip()

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "prod"}

    @property
    def cors_origins(self) -> list[str]:
        values = [x.strip() for x in self.cors_origins_raw.split(",") if x.strip()]
        return values or ["http://localhost:5174", "http://127.0.0.1:5174"]


settings = Settings()
