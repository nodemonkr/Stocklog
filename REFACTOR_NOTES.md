# StockLog v3.34.1 Refactor Notes

## 이번 리팩토링에서 반영한 핵심

1. **환경설정 중앙화**
   - `backend/app/config.py` 추가
   - 프로젝트 루트 `.env`와 `backend/.env`를 실행 위치와 무관하게 로드
   - `APP_ENV`, DB URL, JWT, CORS, SQL echo 설정을 한 곳에서 관리

2. **JWT/암호화 키 설정 오류 수정**
   - 기존 `.env`의 `JWT_SECRET`을 실제 인증/암호화 코드가 사용하도록 수정
   - 예전 버전이 기본 `SECRET_KEY`로 암호화했을 가능성을 고려해 기존 키움 credential 복호화 fallback 유지
   - 새로 저장하는 credential은 현재 `JWT_SECRET` 사용

3. **DB 연결 안정화**
   - MySQL `pool_pre_ping` 유지 + `pool_recycle=1800` 적용
   - SQLAlchemy session의 `expire_on_commit=False`로 commit 직후 불필요한 재조회 감소

4. **500 오류 추적성/보안 개선**
   - 요청별 `X-Request-ID` 발급
   - 서버 로그에는 traceback 기록
   - production에서는 SQL/credential 등 내부 예외 문자열을 클라이언트에 직접 노출하지 않음
   - development에서는 기존처럼 원인 확인이 가능하도록 오류 타입/메시지 포함

5. **실행환경 자가복구 강화**
   - `run-backend.sh`: venv 폴더 존재 여부가 아니라 실제 Python 가상환경과 핵심 패키지 import를 검증
   - 손상된 복사 venv는 자동 재생성
   - requirements 해시가 같아도 패키지가 빠져 있으면 재설치
   - `run-frontend.sh`: `node_modules` 폴더만 보지 않고 Vite 실행파일과 package-lock 해시 확인
   - 불완전한 node_modules는 삭제 후 `npm ci`로 재구성
   - `restart-all.sh`의 중복 npm 설치 로직 제거

6. **AI Bot 실제 장애 수정**
   - 백업 로그에서 `AttributeError: 'OllamaAnalyst' object has no attribute 'analyze'` 확인
   - `ai_analyst.py`의 `analyze()`가 클래스 밖으로 빠져 있던 들여쓰기 오류 수정
   - AST 검증으로 `OllamaAnalyst`가 `__init__`, `status`, `analyze` 메서드를 실제 보유하는지 확인

7. **프로젝트 위생**
   - `.gitignore` 추가: 실제 `.env`, venv, node_modules, logs, pid, runtime, backup 제외
   - `check-project.sh` 추가: Python 문법, shell 문법, frontend dependency 상태, 대형 파일 현황 점검

## 확인한 구조적 기술부채

현재 기능은 상당히 많이 들어가 있지만 아래 파일이 지나치게 큽니다.

- `backend/app/main.py`: 약 11k lines
- `backend/app/kiwoom.py`: 약 2.7k lines
- `backend/app/providers.py`: 약 2k lines
- `frontend/src/App.jsx`: 약 6k lines
- `frontend/src/style.css`: 약 6.5k lines

한 번에 파일을 대규모 분리하면 현재 정상 동작하던 Kiwoom/DART/AI 흐름을 깨뜨릴 위험이 높아, 이번 패키지에서는 먼저 설정/보안/실행환경/오류추적 같은 공통 기반을 안정화했습니다. 다음 단계는 API router와 React page/component를 기능 단위로 분리하는 방식이 적절합니다.

## 권장 다음 분리 순서

Backend:
- `routers/auth.py`
- `routers/kiwoom.py`
- `routers/stocks.py`
- `routers/smart.py`
- `routers/ai.py`
- `routers/admin.py`
- `services/market_sync.py`
- `services/stock_detail.py`

Frontend:
- `pages/PortfolioPage.jsx`
- `pages/SmartAnalysisPage.jsx`
- `pages/AdminPage.jsx`
- `components/StockDetailModal.jsx`
- `components/charts/StockChart.jsx`
- `hooks/useKiwoomSync.js`
- `utils/formatters.js`

이 순서면 API contract를 유지한 채 파일 책임만 순차적으로 줄일 수 있습니다.


## 2026-08-19 CPU Ollama tuning
- Default Ollama context reduced from 8192 to 4096 for CPU-only inference.
- Default output limit reduced from 750 to 420 tokens.
- Ollama read timeout increased from 300s to 600s.
- AI context news/report payload compacted to reduce prompt-evaluation time.
- Existing deployments with explicit values in `backend/.env` should update those values manually.


## v3.35.0 - CPU AI fast path
- AI context is now precomputed/condensed before Ollama inference.
- Default Ollama context reduced to 2048 and output budget to 240 tokens.
- Full JSON Schema is no longer sent to Ollama; JSON mode + local normalization is used.
- AI analysis uses cached real news only, so it does not block on RSS retrieval.
- Live broker-report lookup is skipped by default (`AI_INCLUDE_LIVE_REPORTS=false`).
- Price history used for AI indicators reduced from 500 to 260 bars.
- Valuation, financial, momentum and news direction hints are calculated deterministically in FastAPI.
- Existing AI result cache remains enabled; unchanged contexts reuse the stored analysis.

## v3.63.0 안정화 리팩터링
- DB commit/flush 공통 rollback 정책 도입 (`app/db_utils.py`)
- sync retry/schedule 정책 분리 (`app/sync_policy.py`)
- import-time data seed/cleanup을 startup 단계로 이동
- 관리자 자동 동기화 스케줄 영속화 및 수급 전체동기화 통합
- OpenDART 캐시/한도 보류, 키움/수급 일시 오류 재시도
- 프론트 GET 통신 1회 재시도, request-id, auth-expired 공통 처리
- readiness endpoint 및 production JWT 기본키 차단
