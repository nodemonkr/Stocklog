# StockLog v3.76.1 — 동기화 정지 / 로딩 고착 안정화 리팩터링

## 이번 점검의 핵심 원인

2026-08-25 백업에 포함된 `logs/backend.log`를 기준으로 최근 장애 구간에는
`QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`
오류가 461회 기록되어 있었습니다.

장시간 동기화 자체만의 문제가 아니라 다음 조건이 겹치면서 DB 연결 풀이 고갈되는 구조였습니다.

1. 관리자 화면이 동기화 중 여러 status API를 약 1.2초마다 동시에 폴링함.
2. 느린 요청이 끝나기 전에 다음 폴링 묶음이 시작되어 요청이 중첩됨.
3. 인증용 `User` SELECT 트랜잭션이 요청 종료까지 유지되어, Kiwoom/OpenDART/Gemini 같은 외부 HTTP 대기 시간에도 DB 연결을 점유할 수 있었음.
4. DART/뉴스/리포트/공시 및 일부 키움 실시간 조회도 DB 조회 직후 외부 API를 기다리는 경로가 있었음.
5. 전역 체결 알림과 보유종목 WebSocket도 DB 연결을 길게 잡을 수 있었음. 특히 WebSocket은 연결 수명이 길어 치명적일 수 있었음.
6. 시장 동기화 실패 처리에서 `rollback()` 후 만료된 ORM 객체를 다시 읽으면서 DB 연결을 또 요구해 2차 pool timeout이 발생할 수 있었음.
7. 백엔드가 재시작되거나 작업 태스크가 비정상 종료되면 일부 상태 row의 `running=true`가 남아 UI가 영구적으로 진행 중이라고 판단할 수 있었음.
8. 초기 `/api/auth/me` 확인이 글로벌 120초 timeout/retry 정책의 영향을 받아 DB가 밀릴 때 `StockLog 로딩 중...`이 매우 오래 유지될 수 있었음.

기존에 추가되어 있던 `financial_quarters` nullable 보정과 `failures_json/provider_status_json` 크기 제한·MEDIUMTEXT 보정은 유지했습니다. 이번 버전은 그 방어와 별개로 실제 최근 로그에서 확인된 연결 풀 고갈과 상태 고착 경로를 정리하는 데 초점을 맞췄습니다.

## 백엔드 변경

- MySQL QueuePool을 StockLog 동시 작업량에 맞게 환경설정 가능하도록 변경
  - `DB_POOL_SIZE=12`
  - `DB_MAX_OVERFLOW=8`
  - `DB_POOL_TIMEOUT_SECONDS=8`
  - `DB_POOL_RECYCLE_SECONDS=1800`
  - `pool_pre_ping`, `pool_use_lifo` 적용
- `/api/admin/sync-overview` 추가
  - 시장/테마/시장테마/사업분류/통합/정규화/수급/키움 런타임 상태를 한 요청으로 반환
  - DB pool telemetry도 함께 반환
- 인증 `current_user`의 read-only SELECT가 끝나면 즉시 commit하여 요청 전체 시간 동안 연결을 점유하지 않도록 변경
- 외부 네트워크 대기 전에 DB transaction을 끝내도록 주요 경로 정리
  - Kiwoom 계좌/주문/매수가능금액/체결조회/호가/투자자수급/테마/실시간 WebSocket
  - OpenDART 재무/기업개황/corpCode/공시
  - Naver/Google 뉴스 및 증권사 리포트
  - Gemini Gbot 분석
  - 자동매매/예약감시/백그라운드 체결 확인
- `external_api.py`의 사용량 기록 및 quota 조회 SQL을 `asyncio.to_thread`로 옮겨 DB가 일시적으로 바쁠 때 async event loop 전체가 멈추지 않도록 변경
- 시장 데이터 동기화 예외/취소 처리에서 rollback 이후 ORM 객체를 명시적으로 재조회하도록 변경
  - 실패 상태 기록 중 다시 pool timeout이 나면서 `running=true`가 남는 경로 차단
- 테마/시장테마/사업분류/테마정규화 취소 신호를 삼키지 않고 상위 통합 동기화까지 전달
- 프로세스 시작 시 `FullMarketSyncState.running=true`로 남아 있는 모든 과거 in-process 작업을 자동 `cancelled` 처리
- 시장 데이터와 수급 status API에도 살아 있는 asyncio task가 없으면 고아 `running` 상태를 자동 복구하는 2차 방어 유지
- `/health` 서비스 버전을 v3.76.1로 정리

## 프론트엔드 변경

- 관리자 동기화 폴링을 여러 API 동시 호출 방식에서 `/api/admin/sync-overview` 단일 요청 방식으로 변경
- 이전 요청이 끝나기 전 다음 polling을 만들지 않는 single-flight 구조 적용
- 동기화 중 polling 간격을 약 1.8초로 조정하고, 완료 후에만 무거운 관리자 통계/정책을 한 번 다시 조회
- 초기 로그인 복원 `/api/auth/me`
  - 10초 하드 timeout
  - GET 자동 재시도 제외
  - 일시적인 서버/DB 지연 시 토큰을 삭제하지 않음
  - `StockLog 연결 지연` + `다시 연결` 복구 UI 표시
- v3.76.1 표시 및 로딩/복구 화면 스타일 추가

## production dist 처리

점검 샌드박스에서는 외부 npm registry DNS가 차단되어 `npm ci`/Vite 재빌드를 완료할 수 없었습니다. 하지만 기존 `frontend/dist`를 그대로 두면 Caddy가 v3.76.0의 오래된 다중 polling/무한 로딩 코드를 계속 서비스할 수 있으므로, 최종 전달본의 production bundle에도 이번 핵심 변경을 반영했습니다.

- production JS에 `/api/admin/sync-overview` 단일 polling, single-flight, 인증 10초 timeout/복구 UI, GET retry opt-out 및 v3.76.1 표시 반영
- production CSS에 연결 지연 복구 화면 스타일 반영
- 브라우저 immutable cache가 이전 asset을 재사용하지 않도록 새 asset 파일명으로 교체하고 `frontend/dist/index.html` 참조 갱신
- production JS는 `node --check`로 문법 검증 완료
- 실제 서버에서 npm 접근이 가능한 경우 `./restart-all.sh`를 실행하면 현재 `frontend/src`에서 정식 Vite bundle을 빌드하며, 빌드 성공 후에만 `dist.next`를 기존 `dist`와 원자적으로 교체합니다.

## 검증 결과

- backend 전체 Python `compileall`: 통과
- backend/app + backend/tests 전체 AST parse: 통과
- 모든 `.sh` 파일 `bash -n`: 통과
- frontend/src 전체 JS/JSX parser 검사: 통과
- 최종 production JS `node --check`: 통과
- SQLite smoke import에서 `/api/admin/sync-overview` 라우트 등록 확인
- 기존 pytest 전체 실행 결과: **44 passed / 5 failed**
  - 동일한 5개 실패를 수정 전 원본 백업에도 같은 환경으로 재실행하여 재현함
  - 3개는 과거 Obot+Gbot dual 동작을 기대하는 테스트와 현재 Gbot-only 프리미엄 분석 정책의 차이
  - 2개는 과거 `관망` verdict 유지 기대와 현재 evidence 기반 최종 verdict 보정 정책의 차이
  - 따라서 이번 동기화/DB/로딩 리팩터링으로 새로 발생한 테스트 회귀는 확인되지 않음

## 운영 권장

- 배포 후 최초 한 번 `./restart-all.sh`로 백엔드/프론트를 재기동하는 것을 권장합니다.
- 운영 `.env`에서 DB pool 값을 별도로 설정하지 않으면 이번 버전의 기본값(12/8/8초/1800초)이 적용됩니다.
- 관리자 화면의 `/api/admin/sync-overview` 응답 내 `db_pool` 항목으로 연결 풀 사용량을 확인할 수 있습니다.
