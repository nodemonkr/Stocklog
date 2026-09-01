"""Small transaction helpers shared across StockLog services.

The helpers deliberately depend on a tiny Session protocol instead of importing
SQLAlchemy's concrete Session at runtime.  That keeps this module usable from
unit tests and prevents transaction policy from being coupled to the ORM type.
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("stocklog.db")


class TransactionSession(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def flush(self) -> None: ...


def rollback_quietly(db: TransactionSession) -> None:
    """Rollback without replacing the exception that originally caused it."""
    try:
        db.rollback()
    except Exception:
        logger.exception("database rollback failed")


def commit_or_rollback(db: TransactionSession) -> None:
    """Commit once; guarantee a clean session before propagating failures."""
    try:
        db.commit()
    except Exception:
        rollback_quietly(db)
        raise


def flush_or_rollback(db: TransactionSession) -> None:
    """Flush once; guarantee a clean session before propagating failures."""
    try:
        db.flush()
    except Exception:
        rollback_quietly(db)
        raise
