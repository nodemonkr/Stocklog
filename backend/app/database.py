from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

DATABASE_URL = settings.database_url
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine_kwargs = {
    "pool_pre_ping": True,
    "connect_args": connect_args,
    "echo": settings.sql_echo,
}

# Long-running StockLog synchronization shares the process with account,
# reservation and auto-trading workers.  SQLAlchemy's old defaults (pool 5,
# overflow 10, timeout 30s) allowed a slow admin polling burst to occupy all
# connections and then block the API for minutes.  Keep modest headroom, use
# LIFO so idle MySQL connections can age out, and fail fast enough for the UI
# to recover instead of accumulating overlapping requests.
if DATABASE_URL.startswith("mysql"):
    engine_kwargs.update({
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        "pool_recycle": settings.db_pool_recycle_seconds,
        "pool_use_lifo": True,
    })

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

# Reserve a tiny pool exclusively for the administrator synchronization monitor.
# Long-running market/flow/AI workers never use this pool, so progress/status and
# diagnostic downloads remain responsive even if the main application pool is
# temporarily saturated.  This is deliberately small to avoid masking connection
# leaks by simply opening many more database connections.
if DATABASE_URL.startswith("mysql"):
    monitor_connect_args = dict(connect_args)
    if DATABASE_URL.startswith("mysql+pymysql"):
        monitor_connect_args.update({"connect_timeout": 2, "read_timeout": 3, "write_timeout": 3})
    monitor_engine_kwargs = {
        "pool_pre_ping": True,
        "connect_args": monitor_connect_args,
        "echo": settings.sql_echo,
        "pool_size": 2,
        "max_overflow": 0,
        "pool_timeout": 2,
        "pool_recycle": settings.db_pool_recycle_seconds,
        "pool_use_lifo": True,
    }
    monitor_engine = create_engine(DATABASE_URL, **monitor_engine_kwargs)
    MonitorSessionLocal = sessionmaker(
        bind=monitor_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
else:
    monitor_engine = engine
    MonitorSessionLocal = SessionLocal


_monitor_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="stocklog-monitor")


async def run_monitor_blocking(func, *args, **kwargs):
    """Run monitor-only blocking work outside FastAPI/AnyIO's shared worker pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_monitor_executor, partial(func, *args, **kwargs))


class Base(DeclarativeBase):
    pass


def database_pool_status() -> dict:
    """Best-effort QueuePool telemetry for the admin sync diagnostics panel."""
    pool = engine.pool

    def _read(name: str):
        value = getattr(pool, name, None)
        if value is None:
            return None
        try:
            return value() if callable(value) else value
        except Exception:
            return None

    return {
        "class": type(pool).__name__,
        "size": _read("size"),
        "checked_in": _read("checkedin"),
        "checked_out": _read("checkedout"),
        "overflow": _read("overflow"),
        "configured_pool_size": settings.db_pool_size if DATABASE_URL.startswith("mysql") else None,
        "configured_max_overflow": settings.db_max_overflow if DATABASE_URL.startswith("mysql") else None,
        "configured_timeout_seconds": settings.db_pool_timeout_seconds if DATABASE_URL.startswith("mysql") else None,
    }


def monitor_pool_status() -> dict:
    """Telemetry for the isolated admin synchronization-monitor pool."""
    pool = monitor_engine.pool

    def _read(name: str):
        value = getattr(pool, name, None)
        if value is None:
            return None
        try:
            return value() if callable(value) else value
        except Exception:
            return None

    return {
        "class": type(pool).__name__,
        "size": _read("size"),
        "checked_in": _read("checkedin"),
        "checked_out": _read("checkedout"),
        "overflow": _read("overflow"),
        "configured_pool_size": 2 if DATABASE_URL.startswith("mysql") else None,
        "configured_max_overflow": 0 if DATABASE_URL.startswith("mysql") else None,
        "configured_timeout_seconds": 2 if DATABASE_URL.startswith("mysql") else None,
    }


def get_db():
    """Yield a request-scoped Session and guarantee rollback on request errors.

    SQLAlchemy marks a Session as failed after a flush error. Explicitly
    rolling back here prevents a failed request from leaking a poisoned
    transaction into cleanup/error-handling code.
    """
    db = SessionLocal()
    try:
        yield db
    except BaseException:
        try:
            db.rollback()
        finally:
            db.close()
        raise
    else:
        db.close()
