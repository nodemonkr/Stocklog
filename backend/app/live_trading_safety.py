from __future__ import annotations


LIVE_ACTIVATION_TEXT = "실전투자 활성화"
LIVE_DEACTIVATION_TEXT = "실전투자 비활성화"
LIVE_ORDER_TEXT = "실전주문"
LIVE_AUTO_START_TEXT = "실전자동매매 시작"


class LiveTradingSafetyError(ValueError):
    pass


def require_confirmation(actual: str | None, expected: str) -> None:
    if str(actual or "").strip() != expected:
        raise LiveTradingSafetyError(f"확인 문구 '{expected}'를 정확히 입력해주세요.")


def validate_live_order_limits(
    *,
    side: str,
    quantity: int,
    reference_price: float,
    max_order_amount: float,
    buying_power: float = 0,
    held_quantity: int = 0,
) -> float:
    if side not in {"buy", "sell"}:
        raise LiveTradingSafetyError("매수/매도 구분이 올바르지 않습니다.")
    if int(quantity) <= 0:
        raise LiveTradingSafetyError("주문 수량은 1주 이상이어야 합니다.")
    if float(reference_price) <= 0:
        raise LiveTradingSafetyError(
            "주문금액 안전 검증에 필요한 최신 가격이 없습니다. 실계좌를 새로고침한 뒤 다시 시도해주세요."
        )
    estimated = float(reference_price) * int(quantity)
    if estimated > float(max_order_amount):
        raise LiveTradingSafetyError(
            f"실전 1회 주문 안전한도 {int(max_order_amount):,}원을 초과했습니다. 서버 설정에서 한도를 조정할 수 있습니다."
        )
    if side == "buy" and float(buying_power) > 0 and estimated > float(buying_power):
        raise LiveTradingSafetyError("예상 주문금액이 마지막으로 확인한 실계좌 주문가능금액을 초과합니다.")
    if side == "sell" and int(quantity) > max(0, int(held_quantity)):
        raise LiveTradingSafetyError(
            f"실계좌 보유수량 {max(0, int(held_quantity)):,}주보다 많이 매도할 수 없습니다."
        )
    return estimated
