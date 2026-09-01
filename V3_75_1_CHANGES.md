# StockLog v3.75.1

## 자동 모의투자 자금 계산 수정

- 키움 주문가능금액 전용 조회가 지원되지 않거나 값을 확인하지 못한 경우, `buying_power=0` placeholder를 실제 0원으로 오인하던 문제를 수정했습니다.
- `buying_power_available=true`일 때만 키움 주문가능금액을 사용하고, 그렇지 않으면 동기화된 계좌 현금(`cash`)을 자동매매 주문 가능 현금 기준으로 사용합니다.
- 자동매매 상태 화면에 실제 자동매매가 사용하는 현금 기준과 fallback 여부를 표시합니다.
- 자금 안전장치로 매수가 차단될 경우 주문가능 현금, 미체결 매수, 최소 현금 유지액, 자동운용 잔여 한도, 종목별 잔여 한도, 최종 계산 가능 금액, 현재가를 이력에 남깁니다.

## Gemini fallback 갱신

- 신규 사용자에게 제공되지 않는 `gemini-2.5-flash-lite` fallback을 `gemini-3.5-flash-lite`로 변경했습니다.
- 기본 fallback 순서는 `gemini-3.6-flash -> gemini-3.5-flash-lite -> gemini-2.5-flash`입니다.
