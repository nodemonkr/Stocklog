# StockLog Mobile V3.80.0 — Native UX / Stability / Web Parity Audit

> **현재 모바일 최우선 기준 문서 — 2026-08-30**
>
> V3.79.0의 자동매매 진단·실패학습, V3.78.1의 Expo SDK 57 / React Native 0.86.3, V3.78.0의 WebView 제거·웹 기능 parity 기준을 모두 계승한다.

## 네트워크 / 빌드 기준

- FastAPI/Uvicorn: `8100`
- Vite web: `5174`
- 외부 web gateway: `3000`
- 모바일 primary API: `http://somensomes.iptime.org:8100`
- 모바일 fallback API: `http://somensomes.iptime.org:3000`
- WebView 사용 금지. React Native 네이티브 UI + FastAPI 직접 호출 구조 유지.
- Expo SDK `~57.0.16`, React Native `0.86.3`
- App version: **3.80.0**

## 1. 홈 모의투자 요약 강화

홈에서 다음 정보를 한 번에 표시한다.

- 모의투자 총 자산
- 구매 가능 자산
- 금일 순익
- 금일 순익률
- 총 순익
- 총 순익률
- 보유 종목 수

금일 지표는 backend `summary.day_profit`, `summary.day_return_rate`를 사용하고 총 지표는 `summary.profit_loss`, `summary.return_rate`를 사용한다.

## 2. 스마트분석 종목 상세 안정화

기존 상세화면에는 loading 분기 뒤에 `useMemo`가 있어 데이터가 도착하기 전/후 React Hook 호출 순서가 달라질 수 있었다. 이 구조를 제거했다.

상세 진입은 이제 단계적으로 수행된다.

1. `/quote` + `/chart/cached`로 현재가/저장 차트를 먼저 표시
2. `/detail`의 재무·수급·뉴스를 추가 로딩
3. AI 상태/일일 사용량은 상세본문과 별도로 로딩

무거운 상세 API 하나가 느려도 화면 전체가 빈 로딩 상태로 장시간 고정되지 않는다. 상세 일부 실패 시 현재가/차트를 유지한 채 재시도 UI를 제공한다.

API primary(8100) 실패 후 fallback(3000) 요청에도 동일 timeout을 적용하여 fallback에서 무한 대기하지 않는다.

## 3. 테마 상세 UX

테마 목록 하단에 구성종목을 계속 붙이는 구조를 제거했다.

테마 선택 시 별도 native modal에서 다음을 제공한다.

- 테마명 / 등락률 / 구성종목 수
- backend 테마 설명
- Gbot 테마 요약
- 강점/위험요인(응답 제공 시)
- 관련 종목 목록
- 관련 종목 → 종목 상세 바로 이동

테마 자동 갱신은 분석 탭이 실제 focus 상태일 때만 실행한다.

## 4. 수급 분석 웹 parity

웹 `FlowAnalysis`의 동작 규칙을 모바일에 맞췄다.

- 일반회원 기본 1일
- `flow_advanced` 회원 기본 7일
- 일반회원의 3/5/7/20일 버튼은 실제 disabled 처리하여 403 API 호출 방지
- 외국인 / 기관 / 개인
- 금융투자 / 투신 / 연기금 / 보험 / 은행 / 사모펀드
- 시장, 정렬, 검색
- 쌍끌이 / 3일+ 연속매수 / 수급반전 / 외국인매수 / 기관매수
- 최근 거래일 series 상세

## 5. 화면 새로고침/폴링 안정화

아래 자동 polling은 화면이 실제 focus 상태일 때만 실행한다.

- 포트폴리오
- 자동매매
- 분석 테마
- 스마트분석 시장지표
- 예약주문
- 관리자 동기화 제어

포트폴리오와 자동매매의 background polling은 기존 데이터를 유지하는 silent refresh로 변경했다. 자동 갱신 시 전체 Loading UI가 다시 나타나 사용 중 화면을 흔들지 않는다.

AI 분석 진행상태 polling과 전역 체결알림은 목적상 유지한다. 체결알림은 AppState가 active일 때만 네트워크를 사용한다.

## 6. 스마트분석 시장 요약

웹 스마트분석 상단과 동일하게 `/api/market-overview` 기반 주요 시장지표를 추가했다. 화면을 보고 있는 동안 30초 단위 silent refresh한다.

## 7. 웹 ↔ 모바일 API 자동 대조

`mobile/scripts/audit-api-parity.mjs` 추가.

- 모바일 TS/TSX에서 `/api/...` 참조 수집
- backend Python에서 `/api/...` route shape 수집
- `{code}` / `${code}` 같은 동적 segment를 정규화 후 대조
- 현재 기준: mobile 95 API shapes ↔ backend 139 API shapes, missing 0

`npm run audit:api`로 실행할 수 있으며 `restart-mobile.sh`의 검증 단계에서도 실행한다.

## 정적 검증 기준

패키징 전 다음을 통과시켰다.

- mobile TS/TSX 35 files TypeScript parser: syntax error 0
- local-source TypeScript audit: error 0
- `npm run check:styles`: PASS
- `npm run audit:api`: PASS
- backend Python compile: PASS
- `restart-mobile.sh`, `restart-all.sh` bash syntax: PASS
- WebView-era runtime reference: 0
- frontend `App.jsx` parser: syntax error 0

이 작업환경은 npm registry 접근이 제한될 수 있으므로 실제 서버에서는 `./restart-mobile.sh --skip-build`로 installed Expo dependency 기반 TypeScript + Expo Doctor까지 확인한 후 `./restart-mobile.sh preview`로 EAS APK를 빌드한다.
