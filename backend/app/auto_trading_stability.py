"""Deterministic stability guards for StockLog automatic paper trading.

Gbot remains responsible for investment opinions.  This module only provides
small, testable execution controls that prevent noisy opinions from becoming
rapid in-and-out orders and makes holding-monitor freshness explicit.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def protective_exit_assessment(
    *,
    current_price: float,
    average_price: float,
    stop_loss_pct: float = 0,
    take_profit_pct: float = 0,
    warning_ratio: float = 0.8,
) -> dict:
    """Describe warning and execution thresholds from one authoritative price.

    The holding monitor and the deterministic order guard must consume this
    same result.  Otherwise a fresh broker quote can display a stop warning
    while a stale stock-master price incorrectly decides that no exit is due.
    """

    current = max(0.0, float(current_price or 0))
    average = max(0.0, float(average_price or 0))
    stop = max(0.0, float(stop_loss_pct or 0))
    take = max(0.0, float(take_profit_pct or 0))
    ratio = max(0.1, min(1.0, float(warning_ratio or 0.8)))
    return_rate = ((current / average) - 1.0) * 100.0 if current > 0 and average > 0 else 0.0
    stop_warning = -max(1.0, stop * ratio) if stop > 0 else None
    stop_trigger = -stop if stop > 0 else None
    take_warning = max(1.0, take * ratio) if take > 0 else None
    take_trigger = take if take > 0 else None

    status = "normal"
    label = "정상 범위"
    trigger = ""
    if stop_trigger is not None and return_rate <= stop_trigger:
        status = "stop_triggered"
        label = "손절 기준 도달"
        trigger = f"설정 손절 기준 {stop_trigger:g}% 도달 (현재 {return_rate:.2f}%)"
    elif take_trigger is not None and return_rate >= take_trigger:
        status = "take_triggered"
        label = "익절 기준 도달"
        trigger = f"설정 익절 기준 +{take_trigger:g}% 도달 (현재 {return_rate:.2f}%)"
    elif stop_warning is not None and return_rate <= stop_warning:
        status = "stop_approaching"
        label = "손절 기준 접근"
    elif take_warning is not None and return_rate >= take_warning:
        status = "take_approaching"
        label = "익절 기준 접근"

    return {
        "status": status,
        "label": label,
        "trigger": trigger,
        "current_price": current,
        "average_price": average,
        "return_rate": return_rate,
        "stop_loss_pct": stop,
        "stop_warning_return": stop_warning,
        "stop_trigger_return": stop_trigger,
        "stop_trigger_price": average * (1.0 - stop / 100.0) if stop > 0 and average > 0 else None,
        "stop_distance_pct_points": max(0.0, return_rate - stop_trigger) if stop_trigger is not None else None,
        "take_profit_pct": take,
        "take_warning_return": take_warning,
        "take_trigger_return": take_trigger,
        "take_trigger_price": average * (1.0 + take / 100.0) if take > 0 and average > 0 else None,
        "price_source": "키움 계좌 현재가",
    }


def _seconds_since(value: datetime | None, now: datetime) -> float | None:
    if value is None:
        return None
    return max(0.0, (now - value).total_seconds())


def recent_trade_guard_message(
    *,
    action: str,
    now: datetime,
    recent_same_action_at: datetime | None = None,
    recent_opposite_action_at: datetime | None = None,
    risk_guard: bool = False,
    cooldown_minutes: int = 30,
) -> str:
    """Return a guard reason for rapid repeat/reversal execution.

    Risk-rule exits must always be able to reduce exposure, so they bypass this
    opinion-churn guard.  A BUY after a same-day SELL is held until the next
    trading day; this prevents the observed sell/rebuy loop without preventing
    an urgent SELL after a BUY.
    """

    if risk_guard:
        return ""
    normalized = str(action or "").strip().lower()
    wait_minutes = max(5, int(cooldown_minutes or 30))
    same_age = _seconds_since(recent_same_action_at, now)
    if same_age is not None and same_age < wait_minutes * 60:
        remaining = max(1, int((wait_minutes * 60 - same_age + 59) // 60))
        if normalized == "sell":
            return f"연속 부분매도를 막기 위해 최근 매도 후 {remaining}분 더 관찰합니다."
        if normalized == "buy":
            return f"단기 추가매수를 막기 위해 최근 매수 후 {remaining}분 더 관찰합니다."
    if normalized == "buy" and recent_opposite_action_at and recent_opposite_action_at.date() == now.date():
        return "매도 직후 같은 종목을 다시 사는 회전매매를 막기 위해 다음 거래일까지 재진입하지 않습니다."
    return ""


def stable_entry_guard_message(
    *,
    change_rate: float | None,
    current_return_pct: float | None,
    is_new_position: bool,
    max_rise_pct: float = 5.0,
    max_fall_pct: float = 4.0,
    max_add_loss_pct: float = 1.5,
) -> str:
    """Return a conservative entry guard reason, or an empty string.

    These checks do not predict returns.  They only avoid three unstable entry
    patterns: chasing a sharp daily rise, catching a sharp daily fall, and
    averaging down an already losing automatic position.
    """

    if change_rate is not None:
        daily = float(change_rate)
        if daily >= abs(float(max_rise_pct)):
            return f"당일 {daily:+.2f}% 급등 종목은 추격매수하지 않고 다음 판단까지 관찰합니다."
        if daily <= -abs(float(max_fall_pct)):
            return f"당일 {daily:+.2f}% 급락 종목은 하락 안정 확인 전까지 신규 매수하지 않습니다."
    if not is_new_position and current_return_pct is not None:
        current = float(current_return_pct)
        if current <= -abs(float(max_add_loss_pct)):
            return f"현재 자동 보유 수익률이 {current:+.2f}%여서 손실 중 추가매수(물타기)를 제한합니다."
    return ""


def monitor_health_payload(
    *,
    enabled: bool,
    market_open: bool,
    interval_seconds: int,
    position_count: int,
    last_started_at: datetime | None,
    last_success_at: datetime | None,
    last_failure_at: datetime | None,
    last_error: str,
    checked_positions: int,
    check_count: int,
    now: datetime,
) -> dict:
    """Build a truthful public monitor state from successful checks.

    A watcher being enabled is not evidence that a quote/account check
    succeeded.  The state is only ``verified`` when a recent successful monitor
    pass exists.  Three missed expected intervals are treated as delayed.
    """

    interval = max(30, int(interval_seconds or 60))
    stale_after = max(180, interval * 3)
    age = _seconds_since(last_success_at, now)
    failure_after_success = bool(
        last_failure_at
        and str(last_error or "").strip()
        and (last_success_at is None or last_failure_at > last_success_at)
    )

    if not enabled:
        status, label, message = "stopped", "감시 중지", "자동매매가 중지되어 보유종목 감시도 대기 중입니다."
    elif not market_open:
        status, label, message = "market_closed", "장 마감 대기", "거래시간이 아니어서 마지막 확인 가격을 유지합니다."
    elif failure_after_success:
        status, label, message = "error", "감시 오류", "최근 보유종목 확인이 실패했습니다. 주문 판단은 확인 성공 전까지 보수적으로 대기합니다."
    elif last_success_at is None:
        status, label, message = "waiting", "첫 확인 대기", "자동 감시가 켜졌지만 아직 성공한 계좌·시세 확인 기록이 없습니다."
    elif age is not None and age > stale_after:
        status, label, message = "delayed", "갱신 지연", f"마지막 성공 확인 후 {int(age // 60)}분이 지나 감시 갱신이 지연되고 있습니다."
    else:
        status, label = "verified", "감시 확인됨"
        message = f"키움 계좌 시세로 {max(0, int(checked_positions))}개 자동 보유종목을 실제 확인했습니다."

    return {
        "status": status,
        "label": label,
        "message": message,
        "verified": status == "verified",
        "interval_seconds": interval,
        "stale_after_seconds": stale_after,
        "position_count": max(0, int(position_count or 0)),
        "checked_positions": max(0, int(checked_positions or 0)),
        "check_count": max(0, int(check_count or 0)),
        "last_started_at": last_started_at.isoformat() if last_started_at else None,
        "last_success_at": last_success_at.isoformat() if last_success_at else None,
        "last_failure_at": last_failure_at.isoformat() if last_failure_at else None,
        "last_error": str(last_error or "")[:500],
        "age_seconds": int(age) if age is not None else None,
        "next_expected_at": (last_success_at + timedelta(seconds=interval)).isoformat() if last_success_at else None,
        "source": "키움 계좌 시세",
    }
