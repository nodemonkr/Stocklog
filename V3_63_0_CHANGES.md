# StockLog v3.63.0 Changes

## 목표
v3.62.1을 기준으로 동기화 안정성, DB 트랜잭션, 관리자 운영 기능, 프론트 API 통신과 코드 결합도를 함께 정리한 리팩터링/안정화 버전입니다.

## 1. DB 트랜잭션 안정화
- `backend/app/db_utils.py` 추가
  - `commit_or_rollback()`
  - `flush_or_rollback()`
  - `rollback_quietly()`
- 기존 직접 `db.commit()` 경로를 공통 트랜잭션 정책으로 통일했습니다.
- request-scoped DB dependency(`get_db`)에서 요청 처리 예외 시 반드시 rollback 후 Session을 닫습니다.
- flush/commit 오류 뒤 `PendingRollbackError`가 연쇄되는 가능성을 낮췄습니다.
- 런타임 seed/정리 작업을 module import 시점이 아니라 FastAPI startup 단계로 이동했습니다.

## 2. 동기화 정책 모듈 분리
- `backend/app/sync_policy.py` 추가
- 자동 실행 시간 검증/중복 제거와 외부 공급자 오류 분류, exponential backoff 계산을 FastAPI/SQLAlchemy와 분리했습니다.
- 정책 로직을 독립 unittest로 검증할 수 있습니다.

## 3. 수급 동기화 안정화 및 전체 동기화 통합
- 전체 동기화 순서:
  1. 시세·재무
  2. 키움 테마
  3. 시장 테마
  4. 종목 분류
  5. 수급 데이터
- 수급 대상 수를 관리자에서 300 / 800 / 1,500 / 전체 중 선택할 수 있습니다.
- 수급 `데이터 없음`은 정상 스킵으로 처리합니다.
- 429, timeout, 연결 실패, 일시적 5xx 등은 최대 3회 bounded retry 후에만 최종 실패로 기록합니다.
- 관리자 화면에서 성공 / 데이터 없음 / 재시도 / 최종 실패를 분리해 표시합니다.

## 4. 시세·재무 실패 카운터 품질 개선
- 키움 일봉/기본지표의 일시 오류를 자동 재시도합니다.
- 조회 결과 없음은 기술적 실패와 분리합니다.
- 실패 로그는 bounded JSON 정책으로 보관해 상태 컬럼 크기 문제를 방지합니다.
- OpenDART:
  - 최근 재무가 있으면 기본 24시간 캐시를 재사용합니다 (`DART_FINANCIAL_SYNC_TTL_HOURS`).
  - corp_code 없음 / 최근 재무 없음은 정상 스킵으로 분리합니다.
  - 회사 프로필/배당/주식수 같은 보조 endpoint 실패는 핵심 재무 저장과 분리합니다.
  - `사용한도 초과`가 감지되면 남은 종목을 수천 건의 실패로 쌓지 않고 다음 실행 보류로 기록합니다.
- 관리자에서 정상 스킵 / DART 캐시 / 재시도 / 한도 보류 / 최종 실패를 별도 숫자로 표시합니다.

## 5. 자동 동기화 운영 설정
- `sync_schedule_settings` 영속 설정 모델 추가.
- 관리자에서 자동 동기화 ON/OFF, 하루 실행 횟수(최대 6회), 각 실행 시간, 수급 대상 수를 저장할 수 있습니다.
- 서버 재시작 후에도 설정을 유지합니다.
- 기존 22:00 고정 실행을 DB 설정 기반 watcher로 변경했습니다.

## 6. 관리자 화면 구조 개선
- 데이터 동기화를 최상단 및 기본 펼침으로 배치했습니다.
- 나머지 관리자 주요 영역은 기본 접힘 아코디언으로 정리했습니다.
- 동기화 중 현재 단계, 종목, 처리 건수, 성공/실패, ETA를 계속 표시합니다.

## 7. 프론트 API 통신 개선
- Axios 공통 timeout 120초 적용.
- 모든 요청에 request id를 부여합니다.
- GET 요청만 네트워크/502/503/504에서 한 번 짧게 자동 재시도합니다. POST/PUT/PATCH/DELETE는 자동 재전송하지 않습니다.
- 401 발생 시 인증 만료 event를 발생시켜 stale 로그인 상태를 정리합니다.
- 백엔드도 동일 request id를 로그/응답 헤더에 유지합니다.

## 8. 운영/보안 진단
- `/health`는 프로세스 상태를, `/health/ready`는 DB `SELECT 1`까지 확인합니다.
- production에서 기본 JWT secret을 사용하면 startup을 실패시켜 기본 키로 서비스가 외부 공개되는 것을 막습니다.
- development에서는 경고 로그만 남깁니다.

## 9. 코드 청소
- 편집 과정에 남아 있던 오타성 `ow_sync_task` 전역 변수를 제거했습니다.
- 중복/직접 트랜잭션 경로를 공통 helper로 정리했습니다.
- v3.63.0 버전 문자열과 frontend package metadata를 통일했습니다.

## 검증
- Python 전체 compileall 통과.
- FastAPI route 정적 감사: 125개 route, method/path 중복 0개.
- unittest 14개 통과:
  - 금융 성장률 기존 테스트 4개
  - DB transaction helper 4개
  - sync policy 6개
- TypeScript compiler 기반 JSX/JS syntax 검사 통과:
  - `frontend/src/App.jsx`
  - `frontend/src/api.js`
  - `frontend/src/main.jsx`

## 배포 참고
- 수정본 배포 시 기존 서버의 `.env` / `backend/.env`는 그대로 유지하세요.
- 배포 패키지에는 보안을 위해 실제 `.env`, runtime log, PID, 가상환경, `node_modules`, 오래된 `dist`, 중첩 백업 압축파일을 포함하지 않습니다.
- `run-backend.sh`와 `run-frontend.sh`가 필요한 의존성을 자동으로 설치/복구합니다.
