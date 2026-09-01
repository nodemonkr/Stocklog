"""Pure synchronization policies.

This module contains decisions that do not require FastAPI or SQLAlchemy so
retry/schedule behavior can be tested without booting the application.
"""
from __future__ import annotations

import re


DEFAULT_RUN_TIMES = ("22:00",)
MAX_RUNS_PER_DAY = 6


def normalize_run_times(values, *, max_runs: int = MAX_RUNS_PER_DAY) -> list[str]:
    """Validate, deduplicate and sort HH:MM values."""
    cleaned: list[str] = []
    for raw in values or []:
        value = str(raw or "").strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError(f"자동 동기화 시간 형식이 올바르지 않습니다: {value or '(빈 값)'}")
        if value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        raise ValueError("자동 동기화 시간을 한 개 이상 설정해주세요.")
    if len(cleaned) > max_runs:
        raise ValueError(f"자동 동기화는 하루 최대 {max_runs}회까지 설정할 수 있습니다.")
    return sorted(cleaned)


def select_due_run_slot(values, *, date_iso: str, current_hhmm: str, last_auto_slot: str = "") -> str | None:
    """Return the latest scheduled slot that is due and has not started yet.

    Unlike an exact-minute comparison, this keeps a missed slot eligible after
    its minute has passed.  If several slots were missed while another long
    synchronization was running, only the latest one is returned so the server
    does not build an expensive backlog of stale full-sync jobs.
    """
    times = normalize_run_times(values)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date_iso or "")):
        raise ValueError("자동 동기화 기준 날짜 형식이 올바르지 않습니다.")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(current_hhmm or "")):
        raise ValueError("자동 동기화 기준 시간 형식이 올바르지 않습니다.")

    due = [f"{date_iso}@{value}" for value in times if value <= current_hhmm]
    if not due:
        return None
    last = str(last_auto_slot or "").strip()
    remaining = [slot for slot in due if not last or slot > last]
    return remaining[-1] if remaining else None


def classify_flow_error(exc: Exception | str | None) -> str:
    """Classify investor-flow errors as expected absence, transient, or hard."""
    text_value = str(exc or "").lower()
    no_data_tokens = (
        "데이터가 없습니다",
        "이력 데이터가 없습니다",
        "조회 데이터가 없습니다",
        "no data",
        "not found",
    )
    if any(token in text_value for token in no_data_tokens):
        return "no_data"

    transient_tokens = (
        "429",
        "too many",
        "rate limit",
        "timeout",
        "timed out",
        "connection",
        "temporar",
        "502",
        "503",
        "504",
        "접근토큰",
        "호출 제한",
        "사용한도",
        "한도 초과",
        "quota",
    )
    if any(token in text_value for token in transient_tokens):
        return "transient"
    return "hard"


def retry_delay_seconds(attempt: int, *, base: float = 0.7, cap: float = 3.0) -> float:
    """Bounded exponential backoff for external sync retries."""
    safe_attempt = max(1, int(attempt or 1))
    return min(float(cap), float(base) * (2 ** (safe_attempt - 1)))


def is_quota_like_error(exc: Exception | str | None) -> bool:
    """Return True for provider quota/rate-limit failures that should stop a bulk loop."""
    text_value = str(exc or "").lower()
    tokens = (
        "status=020",
        "status 020",
        "사용한도",
        "한도 초과",
        "요청 한도",
        "호출 제한",
        "too many",
        "rate limit",
        "quota",
        "429",
    )
    return any(token in text_value for token in tokens)


def provider_circuit_should_open(
    consecutive_transient_failures: int,
    *,
    threshold: int = 8,
) -> bool:
    """Bound a bulk sync when the same provider is continuously unavailable."""
    return max(0, int(consecutive_transient_failures or 0)) >= max(1, int(threshold or 1))


def classify_sync_result(
    *,
    hard_failures: int = 0,
    deferred: int = 0,
    missing_data: int = 0,
) -> str:
    """Return the administrator-facing severity for a completed sync stage.

    Provider-side data absence is a valid result, not an operational failure.
    Temporary items that will be retried on a later run are kept separate from
    failures that may require an administrator to intervene.
    """
    if max(0, int(hard_failures or 0)):
        return "error"
    if max(0, int(deferred or 0)):
        return "retry"
    if max(0, int(missing_data or 0)):
        return "info"
    return "success"
