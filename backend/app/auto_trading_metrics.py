from __future__ import annotations

from datetime import datetime


def krx_market_phase(now: datetime) -> str:
    """Return the regular KRX session phase for a KST-local datetime."""
    if now.weekday() >= 5:
        return "closed"
    minute = now.hour * 60 + now.minute
    if minute < 9 * 60:
        return "preopen"
    if minute < 15 * 60 + 30:
        return "open"
    return "closed"


def auto_position_return_rates(
    *,
    current_price: float,
    average_price: float,
    portfolio_day_return_rate: float = 0.0,
    market_change_rate: float = 0.0,
    day_profit_basis: str = "",
    market_phase: str,
) -> dict[str, float]:
    """Calculate the two percentages shown in the automatic holdings table.

    ``return_rate`` is the price return since the bot's average purchase price.
    ``day_return_rate`` is today's return and is always zero before the regular
    session opens. After the close it keeps using the final available quote.
    """
    current = max(0.0, float(current_price or 0.0))
    average = max(0.0, float(average_price or 0.0))
    cumulative = ((current / average) - 1.0) * 100.0 if current > 0 and average > 0 else 0.0

    if market_phase == "preopen":
        daily = 0.0
    else:
        portfolio_daily = float(portfolio_day_return_rate or 0.0)
        # A position opened today must use the investor's own buy-price return,
        # even when the broader stock moved before the purchase.
        acquired_today = str(day_profit_basis or "").startswith("today_acquired")
        if acquired_today or abs(portfolio_daily) > 0.000001:
            daily = portfolio_daily
        else:
            daily = float(market_change_rate or 0.0)

    return {"return_rate": cumulative, "day_return_rate": daily}
