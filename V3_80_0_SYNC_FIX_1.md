# StockLog v3.80.0 Sync Fix 1 — 전체 동기화 99% 정체/공급사 장애 보호

적용일: 2026-08-30

## 증상과 원인

관리자 `전체 동기화`에서 `종목 분류`가 `2,525 / 2,525`, `99%`까지 도달한 뒤 장시간 끝나지 않는 현상을 점검했다.
기존 사업분류는 OpenDART 기업개황 1차 순회가 끝나면 진행률을 정확히 99%로 표시한 뒤, 1차 조회에서 쌓인 모든 일시 오류를 개수 제한과 전체 시간 예산 없이 순차 재시도했다. 개별 대상은 최대 2회, 호출당 최대 25초까지 기다릴 수 있어 OpenDART가 느리거나 호출 한도 상태이면 99%에서 매우 오래 머물 수 있었다.

브라우저 Network의 `sync-overview`와 `fill-events` 반복은 재귀 오류가 아니라 상태 polling이었다. 백엔드가 99%에서 끝나지 않으니 정상 polling이 무한 반복처럼 보인 것이다.

## 수정 사항

- 종목 분류 1차 조회 진행률을 `0~92%`로 분리
- 재확인 단계 `92~98.5%`, 최종화 `99%`, 완료 `100%`
- OpenDART 재확인 최대 12종목
- 재확인 전체 시간 예산 최대 90초
- 재확인 개별 호출 timeout 6초, 각 대상 최대 2회
- OpenDART 사용한도/429/rate limit/status=020 즉시 circuit breaker
- 종목 분류 3개 배치 연속 전체 일시실패 시 남은 요청 다음회차 보강
- DART 재무 6종목 연속 일시실패 시 남은 요청 다음회차 보강
- DART corpCode 다운로드 최대 120초
- 키움 시세/종목지표/수급도 공급사 장애 시 6종목 연속 일시실패 circuit breaker
- 일시 공급사 장애는 hard failure와 분리해 `다음회차 보강`으로 기록
- 관리자 `sync-overview` polling: 활성 탭 약 3초, 비활성 탭 약 10초
- 관리자 페이지에서는 전역 `fill-events` polling 중지
- 동기화 진행 카드에 backend message와 `마지막 진행` heartbeat 표시
- 45초 이상 backend state 업데이트가 없으면 heartbeat 경고 톤 표시

## 다른 동기화 점검

- 키움 테마: continuation page 상한 및 페이지 timeout, 후순위 bounded retry가 이미 존재
- 시장 테마: HTTP timeout 및 각 테마 최대 2회 시도 존재
- 표준 테마: 외부 공급사 대기 없이 DB/규칙 기반
- 스마트 점수: 로컬 DB 계산
- 야간 자동 전체동기화 watcher: busy 검사로 중복 full-sync 실행 방지
- `/api/admin/sync-overview`: 별도 monitor pool과 timeout guard 사용. 첨부 화면의 `degraded:false`는 monitor 경로가 정상이라는 뜻이다.

## 적용 후 기대 동작

OpenDART가 정상일 때는 92%까지 1차 전체 조회 후 필요한 소수만 재확인하고 100%로 종료한다. 공급사가 제한/장애 상태라면 수천 종목을 끝까지 반복 호출하지 않고 `완료 · 다음회차 보강 N개`로 해당 단계를 종료하여 전체 동기화 다음 단계로 넘어간다.

현재 99%에 멈춘 실행은 패치 적용 후 `./restart-all.sh`로 백엔드를 재시작하면 startup reconcile에 의해 이전 running 상태가 종료 처리된다. 그 다음 전체 동기화를 새로 실행한다.

## 검증

- `backend/tests/test_sync_policy.py`: 12/12 PASS
- backend Python compile: PASS
- frontend/mobile JS/JSX/TS/TSX parser: PASS
- `App.jsx` TypeScript transpile diagnostics: error 0
- CSS brace balance: PASS
- shell syntax: PASS
- JSON parse: PASS

이 작업환경에서는 npm registry 응답이 없어 실제 `npm ci`/Vite production build를 완료하지 못했다. 운영 서버에서는 `./restart-all.sh`가 실제 frontend production build를 수행하므로 Vite build 성공 로그를 확인한다.
