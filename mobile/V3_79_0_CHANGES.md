# StockLog Mobile V3.79.0 — Auto Trading Diagnostics & Guarded Learning

> **현재 모바일 최우선 기준 문서 — 2026-08-28**
>
> `V3_78_1_CHANGES.md`의 Expo SDK 57 / React Native 0.86.3 / EAS / API fallback 기준과 `V3_78_0_CHANGES.md`의 웹 기능 parity를 그대로 계승한다.

## 이번 변경

자동매매 화면에서 거래가 없었던 날도 실제 엔진 작동 여부를 판별할 수 있도록 진단을 추가했다.

- watcher heartbeat
- 오늘 자동매매 cycle 수
- 정상/오류/rate-limit 수
- 후보 검토 수
- Gbot BUY/SELL/HOLD 수
- guard 차단 수
- 실제 주문 수
- Kiwoom/Gbot 정상 회차 수
- 마지막 정상 회차

백엔드는 `auto_trading_cycles`에 **0건 판단 회차까지** 저장한다.

## Gbot 실패 학습 메모리

Gbot 자동매수 건은 `auto_trading_outcomes`에 진입 당시 snapshot을 남긴다. 이후 현재수익률/최대상승/최대낙폭/청산수익률을 추적하고 손실 조건에 해당하면 Gemini 사후감사를 실행한다.

단일 손실은 자동 매수금지 규칙이 되지 않는다. 2회 이상 반복된 실패 태그와 최근 손실의 reusable lesson을 다음 Gbot 판단의 `learning_memory`로 전달하되 **현재 최신 데이터와 일치할 때만 위험 감점**하도록 프롬프트에 제한을 둔다.

매수 이후 새로 발생한 뉴스/공시는 `post_entry_event`로 분리하여 당시 판단에서 알 수 없던 사건을 진입 실패로 잘못 학습하지 않도록 했다.

## 신규 API

- `GET /api/trading/auto/cycles`
- `GET /api/trading/auto/learning`
- `POST /api/trading/auto/learning/review-ready`

`restart-mobile.sh`의 backend route audit에도 위 API를 추가했다.

## 앱 버전

- App: **3.79.0**
- Expo: `~57.0.16`
- React Native: `0.86.3`
- 포트/네트워크 정책: 변경 없음
  - 8100 FastAPI 직접 연결 우선
  - 실패 시 3000 `/api`, `/ws` fallback
  - 5174는 Vite 웹 프론트

## 회귀 방지

- WebView를 다시 도입하지 않는다.
- 실제 계좌 주문 허용 정책을 변경하지 않는다. 기존 키움 모의투자 제한을 유지한다.
- 실패 사례로부터 LLM이 소스코드/하드 규칙을 자동 변경하지 않는다.
- 손익 한 건만으로 새 매수 금지 규칙을 만들지 않는다.
- 사후학습 기능 장애가 자동매매 주문 파이프라인을 중단시키지 않도록 별도 watcher 작업으로 유지한다.

루트의 `AUTO_TRADING_DIAGNOSTICS_LEARNING_20260828.md`에서 백엔드 학습 구조를 함께 확인한다.
