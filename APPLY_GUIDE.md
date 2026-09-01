# StockLog v2 적용 가이드

## 0. 기존 프로젝트 백업

```bash
cd ~
cp -a StockLog StockLog_backup_$(date +%Y%m%d_%H%M%S)
```

기존 DB 파일이 있다면 별도로 한 번 더 백업합니다.

```bash
find ~/StockLog -maxdepth 3 -type f \( -name "*.db" -o -name "*.sqlite*" \) -ls
```

## 1. 압축 해제

```bash
cd ~
unzip StockLog_v2_full.zip
```

기존 폴더를 완전히 교체하려면 백업 후:

```bash
mv StockLog StockLog_old
mv StockLog_v2_full StockLog
cd ~/StockLog
```

## 2. 환경파일

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

최소한 아래 `SECRET_KEY`는 운영 전에 반드시 긴 랜덤 값으로 변경하세요.

```env
SECRET_KEY=change-this-long-random-secret
```

SQLite 기본값은 별도 DB 설치 없이 바로 실행됩니다.

MySQL을 사용할 경우:

```env
DATABASE_URL=mysql+pymysql://stocklog:비밀번호@127.0.0.1:3306/stocklog?charset=utf8mb4
```

## 3. 실행

```bash
chmod +x *.sh
./start-all.sh
```

로그:

```bash
tail -f logs/backend.log
tail -f logs/frontend.log
```

종료:

```bash
./stop-all.sh
```

## 4. 관리자 로그인

```text
admin / admin
```

최초 실행 때 자동 생성됩니다.

## 5. 키움 모의투자 연결

StockLog 로그인 후:

```text
설정 > 키움 모의투자
```

에 키움 REST API의 App Key와 Secret Key를 입력합니다.

StockLog은 모의투자 연결 시:

```text
https://mockapi.kiwoom.com
```

을 사용합니다.

키움 사이트에서 REST API 사용 신청 및 모의투자 이용 준비를 먼저 해야 합니다.
페이지 안에도 동일한 안내를 넣어 두었습니다.

## 6. 뉴스

네이버 개발자센터에서 검색 API 애플리케이션을 만든 후:

```env
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
```

입력하면 종목 상세에서 실제 최신 뉴스를 가져옵니다.

키가 없으면 데모 뉴스가 나옵니다.

## 7. 재무

OpenDART 인증키:

```env
DART_API_KEY=
```

입력 시 corp_code가 등록된 종목은 OpenDART 주요계정을 조회합니다.

키가 없거나 corp_code가 없는 종목은 DB의 재무 샘플 데이터를 사용합니다.

## 8. 종목 동기화 전략

관리자 페이지에서 종목 동기화를 누르면 다음 구조를 사용합니다.

1. 종목 Universe 확보
2. KOSPI / KOSDAQ 모두 저장
3. 관리/스팩 등 제외 가능
4. 스마트 분석은 전체 Universe에서 계산
5. 뉴스/재무처럼 비용이 큰 데이터는 상세 조회 또는 상위 후보에 집중

즉 모든 종목에 매번 뉴스·재무 API를 호출하지 않아서 호출량을 줄입니다.

## 9. 기존 DB를 그대로 쓰려면

현재 v2는 새 테이블을 `create_all()`로 생성합니다.
기존 StockLog의 stocks 테이블 컬럼 구조가 이 버전과 다르면 기존 DB에 바로 연결하지 말고 새 DB에서 먼저 검증하세요.

검증 후 기존 데이터 마이그레이션을 진행하는 편이 안전합니다.


## v3로 올린 뒤 프론트 의존성 갱신

ECharts가 추가되었으므로 기존 `node_modules`를 사용하는 경우 아래를 한 번 실행하세요.

```bash
cd ~/StockLog/frontend
rm -rf node_modules package-lock.json
npm install
```

그 다음 프로젝트 루트에서:

```bash
cd ~/StockLog
./stop-all.sh
./start-all.sh
```

백엔드의 기존 v2 SQLite DB를 그대로 사용하는 경우에도 `seed()`가 일봉 개수를 확인하여
240일 이동평균 계산에 필요한 데모 일봉을 자동 보강합니다.

실제 운영 데이터에서는 데모 KOSPI 값을 사용하지 말고 관리자 동기화에서 KOSPI 일봉을 저장하여
`/api/stocks/{code}/detail`의 `kospi` 값을 실제 지수 데이터로 교체하는 것을 권장합니다.


## v3.2 변경사항

- 차트 기본 배율을 최근 구간 중심으로 조정해 과도하게 촘촘해 보이던 문제 완화
- 키움 설정 페이지에 저장 상태(마스킹된 App Key / Secret Key / 계좌 / 저장시각) 표시
- 키움 App Key / Secret Key를 비워두고 저장하면 기존 값 유지
- 모의투자 잔고 조회에 짧은 캐시와 429 대응 메시지 추가
- 종목명/종목코드 검색 후 모의투자 화면에서 선택 종목 차트 표시
- `/api/stocks/search`, `/api/stocks/{code}/chart` API 추가


## v3.3 적용 후

키움 설정에서 더 이상 계좌번호를 입력하지 않습니다.

1. App Key 입력
2. Secret Key 입력
3. `키 저장 + 계좌 자동등록`
4. 오른쪽 `자동 등록 계좌`에 마스킹된 계좌번호가 표시되는지 확인

기존 v3.2에서 키만 이미 저장한 경우에는 `계좌 다시 찾기` 버튼을 누르면
저장된 키를 DB에서 읽어 계좌번호를 자동 조회하고 저장합니다.


## v3.5 적용 후 확인

1. 키움 설정에서 App Key / Secret Key 및 자동 계좌가 정상인지 확인
2. 모의투자 페이지로 이동
3. `키움 계좌 강제 동기화` 클릭
4. `동기화 진단 보기`에서 성공한 TR 확인

예:

```text
성공: kt00004, ka10170, ka10076
실패: kt00017 - RC9000 ...
```

실제 성공 TR은 키움 모의계정/서비스 제공범위에 따라 달라질 수 있습니다.

v3.5에서는 StockLog 자체 1억원 장부를 사용하지 않습니다.
DB의 `kiwoom_account_snapshots` 테이블은 키움 계좌의 마지막 성공
조회 결과를 캐시하는 용도로만 사용합니다.


## v3.7 동기화 UX / TR 필수값 보완

- 강제 동기화 중 전체 화면 로딩 오버레이 표시
- 강제 동기화 버튼을 `동기화 중...`으로 변경 및 중복 클릭 차단
- `kt00016`: `fr_dt` / `to_dt`
- `ka10085`: `stex_tp`
- `ka10170`: `ottks_tp`
- `kt00009`: `stk_bond_tp`
- `kt00002`: `start_dt` / `end_dt`
- 주문/체결 계열에도 기본 필수 파라미터 후보 추가

동기화 진단에서 `필수 입력 값이 존재하지 않습니다` 오류가 줄어들고,
다음으로 필요한 필드가 있으면 키움 응답에 그대로 표시됩니다.


## v3.8 강제 동기화 / MySQL 캐시 자동 초기화

### 자동 초기화
v3.8 최초 백엔드 실행 시 `kiwoom_account_snapshots`의 기존 데이터를 자동으로 1회 삭제합니다.

`sync_state.key = kiwoom_snapshot_reset_v3_8` 마커가 생성되므로 이후 서버 재시작 때는 반복 삭제하지 않습니다.

### 강제 동기화
`GET /api/kiwoom/portfolio?force=true`

실행 순서:

1. 해당 사용자의 기존 `kiwoom_account_snapshots` 행 삭제
2. DB commit
3. 키움 모의계좌 API 새 호출
4. 성공 시 새로운 snapshot 저장
5. 실패 시 과거 snapshot으로 fallback하지 않음

따라서 강제 동기화 실패 후 예전 진단/예전 업데이트 시간이 다시 표시되지 않습니다.

### 상태 확인
`GET /api/kiwoom/sync-status`

응답에서:
- `snapshot_exists`
- `snapshot_last_success_at`
- `v38_auto_reset_done`
- `v38_auto_reset_at`

을 확인할 수 있습니다.


## v3.8.1 중요 수정

v3.8의 `backend/app/kiwoom.py`에서 `probe_account_trs()`가
`KiwoomRestClient` 클래스 밖으로 잘못 빠져 있었고,
그 결과 `normalize_snapshot()` / `sync_account()`도 실제 클래스 메서드로
등록되지 않는 들여쓰기 오류가 있었습니다.

v3.8.1에서는 클래스 구조를 수정했으며 AST 검사로 아래 메서드가
실제로 `KiwoomRestClient`에 존재하는지 검증합니다.

- probe_account_trs
- normalize_snapshot
- sync_account
- order

또한 v3.8.1 최초 실행 시 과거 snapshot을 다시 한 번 자동 초기화하도록
reset marker를 `kiwoom_snapshot_reset_v3_8_1`로 갱신했습니다.


## v3.9 검증 TR 중심 동기화

사용자의 실제 키움 모의계좌에서 아래 TR이 성공 확인되었습니다.

핵심:
- kt00004
- kt00003
- ka10085
- ka10076
- ka10075
- kt00008

v3.9부터 이 6개를 핵심 계좌 동기화 TR로 사용합니다.

모의투자에서 RC9000이 확인된 아래 TR은 더 이상 호출하지 않습니다.
- kt00016
- kt00002
- kt00005

추가 보조 TR:
- ka10170: `ch_crd_tp` 파라미터 후보 추가
- kt00009: `sell_tp` 파라미터 후보 추가

보조 TR이 실패하더라도 핵심 6개가 성공하면 계좌 동기화 자체는 정상으로 유지됩니다.

v3.9 최초 실행 시 이전 snapshot 진단을 자동으로 한 번 초기화합니다.


## v3.10 변경사항

### 모의투자 페이지 최초 진입 로딩
페이지 최초 진입의 `load(false)`에서도 `syncing=true`를 사용하므로,
키움 계좌 조회가 진행되는 동안 강제 동기화와 동일한 전체화면 로딩 오버레이를 표시합니다.

### kt00009 필수 파라미터 보완
키움 응답에서 추가로 확인된 `qry_tp`를 후보 Body에 추가했습니다.

### 진단 UI 안정화
핵심 6개 TR이 성공하면 `핵심 계좌 동기화 정상`으로 표시합니다.
보조 TR 실패는 빨간 경고로 노출하지 않고 `추가 조회 상세 보기` 안에서
중립적인 상태로만 표시합니다.

실제 오류 원문은 백엔드 snapshot diagnostics에는 계속 저장되므로
문제 분석이 필요할 때는 API/로그에서 확인할 수 있습니다.


## v3.11.1 Smart 페이지 안정화

v3.11의 차트 변경 범위를 축소하고 v3.10 기반 차트 구조로 복구했습니다.

유지한 시각성 개선:
- 거래량 영역 높이 확대
- 거래량 막대 폭 확대
- 거래량 막대 색 대비 강화
- 거래량 패널 날짜축 표시

추가 안정화:
- Smart API try/catch
- 응답 Array 검증
- 오류 발생 시 흰 화면 대신 오류 카드 표시
- 초기 데이터 로딩 상태 표시


## v3.11.2 Smart white-screen fix

v3.11.1 차트 교체 과정에서 `DetailedStockChart()`와 `Smart()` 사이에 있던
아래 두 컴포넌트가 누락되어 브라우저에서 런타임 오류가 발생했습니다.

- `Delta`
- `FinancialCell`

브라우저 오류:
`Uncaught ReferenceError: FinancialCell is not defined`

v3.11.2에서 두 컴포넌트를 복구했습니다.


## v3.12 금융 차트 UI 재설계

네이버 증권/TradingView 계열의 금융 차트 사용성을 참고해 차트 구조를 다시 설계했습니다.

- 기간 버튼: 1개월 / 3개월 / 6개월 / 1년 / 전체
- 기본 표시: 캔들 + 20일선 + 60일선 + 거래량
- 기본 숨김: 240일선 / KOSPI
- 각 이동평균선, 거래량, KOSPI를 개별 ON/OFF 가능
- KOSPI가 주가 차트를 가리는 문제를 줄이기 위해 기본 OFF
- 거래량 패널을 충분한 높이로 분리
- 거래량은 상승 빨강 / 하락 파랑
- 가격 Y축은 오른쪽으로 이동
- 툴팁을 흰색 금융정보 카드 스타일로 변경
- 확대/축소 slider 유지


## v3.12.1 차트 레이아웃 재조정

사용자가 제공한 예시 화면처럼 보이도록 차트 레이아웃을 다시 맞췄습니다.

- 상단 범례 고정
- 주가 축 왼쪽 / KOSPI 축 오른쪽
- 거래량 별도 하단 패널
- 툴바 제거
- 기본으로 주가/20일/60일/240일/거래량/KOSPI 모두 표시
- 빨강/파랑 캔들, 보라색 계열 거래량, 노란 KOSPI 라인


## v3.13 실제 시장데이터 전환

- 데모 PriceBar 생성 제거
- 기존 데모 PriceBar/FinancialQuarter/NewsCache를 최초 실행 시 1회 자동 삭제
- 종목 일봉: 키움 REST `ka10081` `/api/dostk/chart`
- KOSPI 일봉: 키움 REST `ka20006` `/api/dostk/chart`
- 실제 OHLCV를 MySQL `price_bars`에 캐시
- 최신 실제 종가로 `stocks.price` 및 전일 대비 등락률 갱신
- Naver/DART 실제 API가 실패하면 합성 데이터로 대체하지 않고 빈 결과 처리
- 실제 차트 API가 실패하고 캐시도 없으면 명시적 오류 반환
- 데모 fallback 없음


## v3.14 모의투자 주문 UI

- 종목명/코드 입력 시 180ms debounce 자동완성
- 일부 글자만 입력해도 최대 12개 종목 즉시 표시
- 정확일치/접두일치 종목을 우선 정렬
- 종목 선택 시 실제 키움 일봉 기준 최신 시세 카드 표시
- 현재가(최신 종가), 전일대비, 등락률, 시가/고가/저가/전일종가/거래량/기준일 표시
- 매수/매도 탭, 시장가/지정가, 수량 +/- 조작
- 지정가 선택 시 현재가를 주문가격 기본값으로 세팅
- 예상 주문금액과 예수금/보유수량 표시
- 오른쪽에 실제 일봉 차트 배치


## v3.15 관리자 전체 종목 실데이터 구축

관리자 페이지에 `전체 종목 데이터 가져오기` 기능을 추가했습니다.

동작 순서:
1. 키움 `ka10099`로 KOSPI / KOSDAQ / KONEX 종목 목록 수집
2. `stock_universe`에 신규 종목 추가 및 기존 종목명/시장 갱신
3. 키움 `ka20006` 실제 KOSPI 일봉 저장
4. 각 종목별 `ka10081` 실제 일봉 최대 500개 저장
5. 최신 종가/등락률/20일 모멘텀/연환산 변동성/스마트 점수 갱신

긴 작업은 FastAPI 백그라운드 asyncio task로 실행됩니다.
관리자 화면은 2초마다 진행 상태를 조회합니다.

진행 상태는 새 MySQL 테이블 `full_market_sync_state`에 저장되며 서버 재시작 시 실행 중이던 작업은 `interrupted`로 정리됩니다.

환경변수:
`FULL_MARKET_DAILY_MAX_ROWS=500`


## v3.17 데이터 출처 분리

- Kiwoom ka10001: 현재가 / PER / PBR / EPS / BPS / 시가총액 / 배당수익률 등
- Kiwoom ka10081: 실제 OHLCV 일봉
- OpenDART: 매출 / 영업이익 / 순이익 / 자산 / 부채 / 자본 등 실제 재무제표
- Naver: 종목 상세 진입 시 뉴스 On-demand 수집

ROE는 Kiwoom 응답에 실제 값이 있으면 Kiwoom을 우선하고, 없으면 OpenDART 실재무로 계산합니다.

v3.17부터 seed의 임의 가격/PER/PBR/ROE/시총 등은 사용하지 않습니다.
기존 DB의 과거 seed 지표도 최초 실행 시 한 번 제거합니다.

전체 데이터 구축 단계:
1. 실제 일봉
2. Kiwoom PER/PBR/EPS/BPS 등
3. OpenDART 실제 재무제표


## v3.18 Google News RSS 뉴스/감성 분석

Naver News Search API 의존성을 제거했습니다.

### 뉴스 동작
1. 종목 상세 클릭
2. MySQL 뉴스 캐시 확인
3. NEWS_CACHE_SECONDS 이내면 DB 뉴스 즉시 표시
4. TTL이 지났으면 Google News RSS 검색
5. 종목 관련 뉴스 필터링
6. 제목/요약 금융 키워드 기반 감성 분석
7. 같은 기사 dedupe_key 기준 UPSERT
8. 긍정/중립/부정 및 감성 점수 표시

### 기사별 표시
- 언론사
- 발행시각
- 제목
- RSS 요약
- 긍정 / 중립 / 부정
- 감성점수 (-1.0 ~ +1.0)
- 판단에 영향을 준 금융 키워드
- 클릭 시 Google News의 해당 기사 링크를 새 탭에서 엶

### 전체 뉴스심리
최근 표시 뉴스의 평균 감성점수로:
- +0.15 이상: 긍정
- -0.15 이하: 부정
- 그 사이: 중립

### .env
Naver News 키는 더 이상 필요하지 않습니다.

```
NEWS_CACHE_SECONDS=3600
NEWS_DISPLAY_COUNT=20
```

Google News RSS는 별도 API Key 없이 조회합니다.
외부 RSS 조회가 실패한 경우 가짜 뉴스를 생성하지 않고,
기존 MySQL에 저장된 실제 뉴스만 표시합니다.


## v3.18.1 Backend boot fix

수정:
- `kiwoom_metrics_updated_at`
- `dart_financials_updated_at`

위 컬럼이 잘못 `User` 모델에 들어가 있던 문제를 수정했습니다.
두 컬럼은 `Stock(stock_universe)` 모델에 위치합니다.

기존 MySQL에는 `users` 테이블 컬럼을 추가할 필요가 없습니다.
백엔드 시작 시 v3.17/v3.18 스키마 보강 로직이 `stock_universe`에 필요한 컬럼을 추가합니다.

또한 `stop-all.sh`가 과거 수동 테스트로 남아 있는 StockLog `--port 8000` uvicorn 프로세스도 정리합니다.


## v3.19 스마트종목/상세/증권사 리포트 개선

### 스마트종목
카드형 UI를 표/리스트형으로 변경했습니다.
한 화면에서 종목명, 현재가, 등락률, PER, PBR, ROE,
20일 모멘텀, 카테고리, 스마트점수를 비교할 수 있습니다.

### 상세 모달
- 모달 외부 영역 클릭 시 닫힘
- ESC 키로 닫힘
- 우측 상단 X 유지
- 종합 차트는 최하단 배치

### 사업성과 / 밸류에이션 자동 보강
종목 상세 진입 시:
- PER/PBR/EPS/BPS가 비어 있으면 Kiwoom ka10001 재조회
- 재무제표 DB가 비어 있고 DART_API_KEY가 있으면
  corp_code 매핑 후 OpenDART 실제 재무를 다시 조회
- 실제 데이터가 끝내 없으면 가짜 값 대신 상세 화면에서 원인 표시

### 증권사 리포트
Naver Finance의 '종목분석 리포트' 페이지에서 최근 리포트 링크를
On-demand로 최대 BROKER_REPORT_COUNT건 표시합니다.
리포트 본문/PDF는 StockLog가 저장하거나 재배포하지 않으며
제목, 증권사, 작성일과 외부 링크만 제공합니다.

기본:
BROKER_REPORT_COUNT=5


## v3.19.1 증권사 리포트 링크 수정

네이버 금융 종목분석 상세 페이지의 현재 정상 경로는
`https://finance.naver.com/research/company_read.naver?...` 입니다.

v3.19에서는 상대 URL을 `https://finance.naver.com`에 붙이면서 `/research/`가 빠져
404가 발생할 수 있었습니다. v3.19.1에서는 `/research/` 기준으로 URL을 생성하고
`searchType=itemCode&itemCode=<종목코드>` 파라미터도 유지합니다.

## v3.20 관리자 동기화 분리
- 13,215는 실제 종목 수가 아니라 기존 `n*3` 작업단계 총합이었습니다.
- 관리자 UI는 이제 실제 unique 종목 수만 표시합니다.
- ka10099 parser는 실제 list + 정확한 6자리 코드만 허용합니다.
- KOSPI/KOSDAQ/KONEX만 Universe에 포함하고 ETF/ELW/K-OTC 시장은 제외합니다.
- 키움 / DART / 전체 버튼을 분리했습니다.
- 전체 버튼은 키움 완료 후 DART를 순차 실행합니다.
- 기존 Universe 밖 DB 종목은 삭제하지 않고 비활성화합니다.


## v3.21 DART 기반 밸류에이션

### 원천
Kiwoom = 실제 시장가격/시세
OpenDART = 실제 재무 + 주식수

OpenDART `stockTotqySttus.json`의 유통주식수를 우선 사용하고,
없으면 발행주식수를 사용합니다.

### 계산
EPS = 연간 순이익 / 주식수
BPS = 최신 자기자본 / 주식수
ROE = 연간 순이익 / 최신 자기자본 × 100
PER = Kiwoom 현재가 / EPS
PBR = Kiwoom 현재가 / BPS

FY 순이익을 우선하며 FY가 아직 없는 경우에만
최근 분기/반기 누적 실적을 단순 연환산합니다.

### 실시간 반영
DART 동기화에서 종목 하나가 완료될 때마다:
재무 UPSERT -> 주식수 -> 밸류에이션 계산 -> 점수 계산 -> COMMIT.

따라서 전체 DART 작업이 끝나기 전에도 완료된 종목부터
스마트분석 API 결과에 실제 값이 나타납니다.

Kiwoom 가격을 나중에 다시 동기화하면 기존 EPS/BPS를 이용해
PER/PBR/시가총액을 현재 가격으로 다시 계산합니다.

스마트분석 페이지는 15초마다 silent refresh하여
동기화 중 DB 변경사항을 화면에 반영합니다.

### 메시지창
브라우저 기본 alert/confirm을 사용하지 않습니다.
StockLog 커스텀 확인/성공/경고/오류 dialog를 사용합니다.


## v3.21.1 재시작 안정화

기존 문제:
- `run-backend.sh`가 매 restart마다 `pip install -r requirements.txt`
- `start-all.sh`는 1초 후 PID만 살아 있으면 backend OK 처리
- `restart-all.sh`는 3초 후 바로 `/health` 호출
- 따라서 pip install 중인 shell PID를 backend가 시작된 것으로 오판할 수 있었음

수정:
- requirements.txt SHA-256을 `.venv/.requirements.sha256`에 저장
- requirements가 변경된 경우에만 pip install
- backend는 실제 `/health` 200 응답까지 최대 90초 기다림
- frontend는 실제 HTTP 응답까지 최대 60초 기다림
- 시작 중 프로세스가 죽으면 즉시 로그 마지막 100~120줄 출력
- backend READY 이후 frontend 시작
- 옛 `v3.1 started`, `v3.18.1 배지` 문구 제거
- 성공했을 때만 `StockLog v3.21.1 READY` 출력

환경변수로 대기시간 조정 가능:
`BACKEND_START_TIMEOUT=90`
`FRONTEND_START_TIMEOUT=60`


## v3.22 스마트 지표 / DART 성과지표 보완

### 스마트 목록 즉시 반영
종목 상세 API는 필요한 경우 해당 종목의 DART 밸류에이션을 on-demand 계산해 DB에 저장합니다.
v3.22에서는 상세 조회 성공 직후 `stocklog:data-updated` 이벤트를 발생시키고,
스마트분석 페이지가 즉시 `/api/smart/value`를 재조회합니다.
기존 15초 silent refresh도 유지합니다.

### DART 추가 계산
DART 실제 재무를 이용해 아래 값을 stock_universe에 저장합니다.
- 매출 성장률: 최신 기간과 전년 동기 비교 우선, 없으면 직전 이용가능 기간 fallback
- 영업이익률: 최신 영업이익 / 최신 매출 × 100
- 배당수익률: OpenDART `alotMatter.json` 사업보고서의 보통주 현금배당수익률(%)

기존:
EPS / BPS / ROE / PER / PBR

추가:
매출 성장률 / 영업이익률 / 배당수익률

DART 동기화는 종목 하나마다 이 값을 계산하고 COMMIT하므로 완료된 종목부터 즉시 API에 반영됩니다.


## v3.23 숫자/재무/뉴스 가독성 개선

### 지표 숫자
PER/PBR/ROE/배당수익률/매출성장률/영업이익률은 화면에서 소수점 첫째 자리까지만 표시합니다.
DB 원본 정밀도는 그대로 유지합니다.

### 사업성과/분기 재무
OpenDART 실제 공시 데이터를 카드형으로 단순화했습니다.
현재 StockLog는 증권사 컨센서스/실적 추정치를 수집하지 않으므로 '-'는 추정치 의미가 아닙니다.
'-' 또는 '비교 데이터 없음'은 해당 값 또는 비교 기준 공시 데이터가 없는 경우입니다.

### 뉴스 심리 점수
내부 점수 -1.0~+1.0은 유지하지만 화면은 정수 -100~+100점으로 표시합니다.
- +18 ~ +100: 긍정
- -17 ~ +17: 중립
- -18 ~ -100: 부정

이 점수는 금융 키워드 기반 상대 심리지표이며 주가 예측 확률이 아닙니다.


## v3.23.1 종목 상세 흰 화면 수정

원인:
- v3.23 재무 카드 UI에서 `money(value)`를 호출했으나 money 함수가 정의되어 있지 않아
  StockDetail 렌더링 시 `ReferenceError: money is not defined`가 발생했습니다.

수정:
- `financialAmount()` 포맷터 추가
- DART 원화 금액을 조원/억원/만원/원 단위로 보기 좋게 표시
- undefined `money()` 호출 제거
- analysis/reasons/risks 응답이 일부 비어 있어도 상세 전체가 흰 화면으로 죽지 않도록 방어 처리


## v3.23.2 Kiwoom 메서드 복구
- `_normalize_stock_master_rows`, `stock_info_list`, `order`를 KiwoomRestClient 클래스 내부로 정상 복구했습니다.
- 매수 kt10000 / 매도 kt10001 / `/api/dostk/ordr`를 사용합니다.


## v3.24 스마트 분석 3개 모드

### AI 추천
실적·밸류에이션·모멘텀·배당을 합산하는 StockLog 종합 알고리즘입니다.
실제 생성형 AI/머신러닝 가격예측 모델은 아니며 화면에 그 사실을 명시합니다.

### 워렌 버핏 스타일
ROE, 영업이익률, 매출 성장, PER/PBR을 중심으로 장기 우량주 관점의 규칙 기반 점수를 계산합니다.

### 나만의 공식
사용자별 MySQL `smart_formulas` 테이블에 조건을 저장합니다.
- PER 최대
- PBR 최대
- ROE 최소
- 매출성장률 최소
- 영업이익률 최소
- 배당수익률 최소
- 20일 모멘텀 최소
- 시가총액 최소

비워둔 조건은 제외하고, 설정한 모든 조건을 만족하는 종목만 표시합니다.


## v3.25
스마트 검색 자동완성, 뉴스 최신순, 대표 테마 배지, Kiwoom ka90001/ka90002 강세테마 페이지를 추가했습니다.

## v3.25.1 TrendingUp import 수정

오류:
`Uncaught ReferenceError: TrendingUp is not defined`

원인:
강세 테마 메뉴에서 `<TrendingUp />` 아이콘을 사용했지만
`lucide-react` import 목록에 `TrendingUp`이 누락되어 앱 첫 렌더링에서 중단되었습니다.

수정:
- `TrendingUp` import 추가
- v3.25.1 버전 반영


## v3.25.2 LAN CORS / 테마 API 점검

증상:
프론트를 `http://192.168.x.x:5174`로 접속하면 백엔드 `:8100` 요청이
브라우저 CORS 정책에 의해 차단되었습니다.

수정:
- localhost / 127.0.0.1 허용
- 사설망 10.x.x.x 허용
- 사설망 172.16~31.x.x 허용
- 사설망 192.168.x.x 허용
- 포트 번호 자유 허용
- Bearer token 방식이므로 `allow_credentials=False`
- `/api/themes` 및 `/api/themes/{theme_code}` 라우트가 실제 backend에 존재하는지 검증


## v3.25.3 테마 500/CORS 오류 분리

브라우저에서 `/api/themes`가 500일 때 `No Access-Control-Allow-Origin`만 보여
실제 Kiwoom 오류를 확인하기 어려운 문제를 수정했습니다.

- CORS `allow_origins=["*"]` (Bearer token 기반, credential cookie 미사용)
- ka90001/ka90002 예외를 HTTP 502 JSON으로 변환
- 실제 Kiwoom 오류 메시지를 frontend에 전달
- 최후의 unhandled 500도 JSON + Access-Control-Allow-Origin 헤더로 반환
- 따라서 이후에는 CORS 메시지가 아니라 실제 `ka90001 ... 실패: ...` 내용 확인 가능


## v3.25.4 ka90001 qry_tp 필수값 수정

실제 Kiwoom 응답:
`1511: 필수입력 파라미터=qry_tp`

수정:
- ka90001 요청은 항상 `{"qry_tp":"0"}` 사용
- qry_tp 없는 잘못된 후보 요청 제거
- 실패 시 실제 request body와 Kiwoom 오류 표시
- 응답 구조가 예상과 다르면 top_keys / sample_keys 표시


## v3.25.5 ka90001 date_tp 필수값 반영

실제 Kiwoom 응답:
`1511: 필수입력 파라미터=date_tp`

ka90001 요청 body를 아래로 고정했습니다.
- `qry_tp: "0"` : 전체 테마 조회
- `date_tp: "1"` : 강세 테마 당일 기준
- `thema_nm: ""` : 전체 조회이므로 특정 테마명 미지정

더 이상 필수값이 빠진 후보 요청을 보내지 않습니다.
실패 시 실제 request body와 Kiwoom 오류가 그대로 표시됩니다.


## v3.25.6 Kiwoom 테마 필수 파라미터 일괄 수정

실제 Kiwoom 오류 흐름에서 확인된 ka90001 필수값을
한 번에 모두 포함하도록 변경했습니다.

ka90001:
- qry_tp = "0"
- date_tp = "1"
- thema_nm = ""
- flu_pl_amt_tp = "1"
- stk_cd = ""

또한 ka90001 성공 직후 ka90002에서 다시 필수값 오류가
발생하지 않도록 ka90002도 아래 형식으로 고정했습니다.

ka90002:
- date_tp = "1"
- thema_grp_cd = 선택한 테마코드

후보 파라미터명을 여러 번 시도하는 코드는 제거했습니다.
실패 시 실제 request body와 Kiwoom 오류를 그대로 표시합니다.
응답 파싱 문제가 생기면 sample_keys와 sample 값까지 표시합니다.


## v3.25.7 ka90001/ka90002 거래소구분(stex_tp) 반영

실제 Kiwoom 오류:
`1511: 필수입력 파라미터=stex_tp`

Kiwoom 국내주식 REST 거래소구분 값:
- 1 = KRX
- 2 = NXT
- 3 = 통합

StockLog 강세테마는 KRX 기준으로 사용하므로 아래를 적용했습니다.

ka90001:
- qry_tp = 0
- date_tp = 1
- thema_nm = ''
- flu_pl_amt_tp = 1
- stk_cd = ''
- stex_tp = 1

ka90002:
- date_tp = 1
- thema_grp_cd = 선택 테마코드
- stex_tp = 1

ka90001 성공 후 ka90002에서 동일한 stex_tp 누락 오류가 발생하지 않도록 둘 다 수정했습니다.


## v3.26 복수 테마 / 뉴스·리포트 연관 테마

### DB
- `themes`: Kiwoom ka90001 실제 테마
- `stock_themes`: 종목 ↔ 복수 테마 관계
- 기존 `primary_theme`은 호환용 대표 테마로 유지

### 관리자
`키움 전체 테마 동기화`
1. ka90001 테마 목록
2. 각 테마별 ka90002 구성종목
3. `themes`, `stock_themes` 저장
4. 종목별 대표 테마 갱신

키움 호출 제한을 고려해 백그라운드 순차 작업이며 진행률/예상시간/실패건을 표시합니다.

### 화면
- 스마트 종목: 실제 키움 테마 최대 2개
- 종목 자동완성: 실제 키움 테마 최대 2개
- 모의투자 종목 검색: 실제 키움 테마 최대 2개
- 종목 상세: 모든 키움 공식 테마
- 가치주/성장주/배당주는 `투자 스타일`로 별도 유지

### 뉴스·리포트 연관 테마
- 후보 테마명은 `themes` 테이블의 실제 Kiwoom 테마만 사용
- 근거 텍스트는 실제 Google News RSS 기사 제목/요약 + 실제 증권사 리포트 제목
- 뉴스에서 임의의 새 테마명을 생성하지 않음
- 점수와 근거 문서 수를 표시


## v3.26.1 Smart 500 / theme DB safe fallback

증상:
`GET /api/smart/recommend/ai ... 500`

v3.26에서 Smart API가 종목 추천 전에 새 `themes / stock_themes`
메타데이터를 조회하도록 바뀌면서, 테마 DB가 아직 준비되지 않았거나
조회 예외가 발생하면 스마트 분석 전체가 500으로 중단될 수 있었습니다.

수정:
- `Theme.__table__.create(checkfirst=True)`
- `StockTheme.__table__.create(checkfirst=True)`
- 테마 DB 오류가 나도 `_theme_map_for_codes()`는 `{}` 반환
- DB 오류 후 `db.rollback()`하여 같은 요청의 Smart 쿼리 계속 사용
- 뉴스/리포트 연관 테마도 DB 오류 시 빈 배열 fallback
- main.py의 `re` import 누락 수정
- `/api/admin/theme-db/status` 진단 API 추가

중요:
테마 데이터는 부가기능입니다.
키움 전체 테마 동기화를 아직 하지 않았더라도 AI/버핏/나만의 공식
스마트 종목 리스트는 정상 동작해야 합니다.


## v3.26.2 관리자 status 500 수정

증상:
`GET /api/admin/status 500`

수정:
- `/api/admin/status`에서 themes/stock_themes count를 안전하게 처리
- 테마 테이블이 없거나 쿼리 오류여도 관리자 status는 200 유지
- 오류 시 db.rollback 후 테마 개수는 0으로 표시
- `theme_db_error`로 실제 원인 보존
- `/api/admin/theme-db/repair` 추가
- 테마 전체 동기화 시작 전 스키마 자동 확인/복구
- Admin `Promise.all`을 `Promise.allSettled`로 변경
- 관리자 API 하나가 실패해도 나머지 화면 계속 표시
- 초기 load promise rejection catch


## v3.26.3 themes 컬럼 자동 마이그레이션

실제 오류:
`pymysql.err.OperationalError (1054): Unknown column 'is_active'`

원인:
MySQL에 `themes` 테이블은 이미 존재했지만 이전/부분 버전에서 만든
테이블이라 최신 모델의 `is_active` 컬럼이 없었습니다.

`Table.create(checkfirst=True)`는 테이블이 존재하면 아무 작업도 하지
않으므로 기존 테이블에 새 컬럼을 추가할 수 없습니다.

v3.26.3 수정:
- backend 시작 시 themes / stock_themes 테이블 존재 확인
- 기존 테이블의 실제 컬럼 목록 검사
- 누락 컬럼만 `ALTER TABLE ... ADD COLUMN`으로 자동 추가
- 기존 테마/종목-테마 데이터는 삭제하지 않음
- 테마 동기화 시작 전에도 같은 마이그레이션 재검사
- 관리자 `테마 DB 확인/복구` 버튼에서도 동일 마이그레이션 수행

themes 검사 컬럼:
id, theme_code, name, change_rate, stock_count, is_active, updated_at

stock_themes 검사 컬럼:
id, stock_code, theme_code, theme_name, source, updated_at


## v3.26.4 themes.is_active 하드 마이그레이션

동일한 `Unknown column 'is_active'` 오류가 반복되어 SQLAlchemy inspector에
의존하지 않고 MySQL의 실제 `SHOW COLUMNS` 결과를 기준으로 수정합니다.

- `SHOW COLUMNS FROM themes`
- `SHOW COLUMNS FROM stock_themes`
- 누락 컬럼이면 즉시 `ALTER TABLE ... ADD COLUMN`
- ALTER 직후 다시 SHOW COLUMNS로 실제 생성 여부 검증
- 테마 동기화 시작 전 `_require_theme_schema_ready()` 강제 실행
- 긴 ka90002 수집이 끝난 뒤 최종 `UPDATE themes SET is_active=...` 직전에도 다시 검증
- 새 동기화 시작 시 이전 FullMarketSyncState.last_error 즉시 초기화
- 성공 시 last_error도 명시적으로 비움

따라서 과거 오류가 화면에 남아 새 오류처럼 보이는 문제와 실제 누락 컬럼 문제를 모두 분리합니다.


## v3.27 전체 테마 연속조회 / 누락 검증

- ka90001 cont-yn/next-key 마지막 페이지까지 조회
- 각 ka90002도 cont-yn/next-key 마지막 페이지까지 조회
- next-key 누락/반복 감지
- 페이지 간 테마/종목 중복 제거
- 테마별 ka90002 최대 3회 재시도
- 전체 페이지 성공한 테마만 DB 관계 교체
- 실패 테마는 이전 정상 관계 보존
- 활성 Universe 대비 공식 테마 연결 커버리지 계산
- 관리자 화면에 ka90001 page / ka90002 누적 page / 연결 종목 / 미분류 / coverage 표시

표시 원칙:
1. 키움 공식 테마 → 실제 공식 테마
2. 공식 테마 없음 + 실제 업종 존재 → `업종 · ...`
3. 둘 다 없음 → `키움 테마 미분류`

가치주/성장주/배당주 같은 투자 스타일은 테마 대체값으로 표시하지 않습니다.

진단 API:
- GET /api/admin/theme-sync/coverage
- GET /api/admin/theme-diagnostic/{code}


## v3.27.1 느린 테마가 전체 동기화를 막지 않도록 개선

- ka90001/ka90002 테마 요청은 request당 HTTP timeout 10초
- 일반 Kiwoom 계좌/시세 API는 기존 25초 유지
- 1차 수집에서는 각 테마를 1회만 시도
- timeout/오류 테마는 즉시 다음 테마로 넘기고 retry queue에 저장
- 전체 테마 1차 순회 완료 후 실패 테마만 후순위 재수집
- 후순위 재수집 최대 2회
- 재수집 사이 1.25초 대기
- 429 발생 시 현재 상태를 관리자 화면에 표시
- 현재 ka90002 페이지 / 단계 / 시도 횟수 / 테마 경과시간 표시
- 완전한 continuation page 수집에 성공한 경우에만 해당 테마 DB 관계 교체
- 최종 실패 테마는 기존 정상 관계 유지


## v3.27.2 테마 동기화 DB 기반 중지 제어

증상:
`POST /api/admin/theme-sync/stop 409 Conflict`

원인:
- 관리자 진행 상태는 MySQL `FullMarketSyncState.running`을 사용
- 중지 API는 현재 FastAPI 프로세스 메모리의 `_theme_sync_task`만 사용
- 요청이 다른 worker/process에 도착하거나 task reference가 유실되면
  DB는 running인데 stop API는 409를 반환할 수 있음

수정:
- stop API를 idempotent 200 응답으로 변경
- DB `phase=stop_requested` + provider `stop_requested=true`를 중지의 source of truth로 사용
- 같은 프로세스의 asyncio task가 있으면 `.cancel()`로 즉시 중단
- 다른 프로세스의 worker라도 DB stop flag를 읽고 중단
- ka90001/ka90002 progress callback마다 stop flag 확인
- 테마 시작/종료, 1차 루프, retry 루프, retry sleep, 최종 DB cleanup 직전 stop flag 확인
- long-lived SQLAlchemy Session cache를 피하기 위해 stop flag는 매번 별도 SessionLocal로 조회
- 중지 완료 시 `running=false`, `phase=cancelled`, `stage_label=중지됨`
- 중지 버튼 재클릭도 409가 아닌 정상 200
- 새 동기화 시작 시 이전 stop flag 자동 초기화

같은 프로세스면 즉시 cancel되고,
다른 프로세스여도 현재 최대 10초 ka9000x 요청이 끝나는 시점에 DB stop flag를 확인해 중지됩니다.


## v3.27.3 테마 동기화 Hard Stop

증상:
중지 요청을 눌러도 `stop_requested` 상태로 30초 이상 남는 문제.

실제 원인:
- 다른 FastAPI 프로세스에서 stop 요청을 받으면 실행 중 worker의
  asyncio Task를 직접 cancel할 수 없음.
- DB stop flag는 기록되지만 worker가 `self.call()` 안에서 HTTP 응답,
  401 재요청, 429 재요청을 기다리는 동안 progress callback이 실행되지 않음.
- 특히 기존 call()은 401/429 재요청 시 theme의 10초 timeout을 다시
  전달하지 않아 기본 25초 timeout으로 되돌아갈 수 있었음.

수정:
- stop API 호출 즉시 DB `running=false`
- `phase=stop_requested` 동안 frontend 1초 polling 유지
- Kiwoom `_post_once()`를 별도 asyncio task로 실행
- HTTP 대기 중 0.2초마다 silent heartbeat progress callback 실행
- DB stop flag 감지 즉시 in-flight HTTP task.cancel()
- 429 1.25초 wait도 0.2초 단위 interruptible wait로 변경
- 401/429 재요청에도 원래 timeout_seconds 그대로 전달
- silent heartbeat는 DB progress write 없이 stop flag만 확인
- worker가 unwind 완료하면 `phase=cancelled`
- stop 처리 중 새 테마 동기화 시작 차단

동일 프로세스는 task.cancel() fast path를 유지하고,
다른 프로세스에서도 DB stop flag를 약 0.2초 간격으로 확인합니다.


## v3.27.4 Run-ID Hard Cancel

문제:
DB는 `running=false`, `phase=stop_requested`가 되었지만 실제 worker가
최종 cancelled 상태를 기록하지 못하면 관리자 UI가 영구적으로
`중지 처리 중...`에 남을 수 있었습니다.

수정:
- 각 테마 동기화에 고유 `run_id` 부여
- Stop 순간 현재 run_id를 즉시 폐기/교체
- 기존 worker는 다음 heartbeat에서 run_id mismatch로 CancelledError
- 폐기된 worker는 이후 progress/error/cancel 상태를 DB에 덮어쓸 권한 없음
- Stop API 즉시 `phase=cancelled`, `running=false`
- UI는 worker acknowledgement를 기다리지 않고 즉시 중지됨 표시
- 중지 직후 12초 Kiwoom request cooldown 후 새 동기화 가능
- 백엔드 시작 시 이전 버전의 stale stop_requested 자동 cancelled 정리
- status API도 `running=false + stop_requested` legacy 상태 자동 복구
- 중지 버튼은 실제 running 동안만 표시되며 영구 disable 상태 제거

이 구조는 화면 상태와 실제 worker 생명주기를 분리합니다.
오래된 worker가 나중에 깨어나더라도 run_id가 다르므로 새 상태를
덮어쓰지 못합니다.


## v3.27.5 ka90001 이후 0/142 멈춤 수정

증상:
- 전체 테마 142개
- ka90001 2p
- 처리 완료 0/142
- ka90002 0p
- 현재 테마 `-`
- 경과시간만 증가

정확한 원인:
v3.27.4에서 ka90001 완료 후 `provider={...}`를 새로 생성하면서
현재 동기화의 `run_id`를 누락했습니다.

첫 테마 루프 직전 `_raise_if_theme_sync_stop_requested(run_id)`가
DB의 빈 run_id를 다른 generation으로 오판하여 현재 worker가 스스로
CancelledError로 종료되었습니다. 반면 DB에는 running=true가 남아
관리자 화면만 계속 실행 중으로 보였습니다.

수정:
- ka90001 이후 새 provider에 run_id / restart_after_epoch 유지
- 1차 테마 루프 직전 run_id를 DB에 한 번 더 강제 저장
- DB run_id가 빈 값인 것만으로는 generation mismatch 판정하지 않음
- 실제 다른 non-empty run_id일 때만 worker 취소
- 백엔드 재시작 시 이전 running theme 작업 자동 cancelled 정리
- status API에서 v3.27.4의 `running=true + total>0 + completed=0 + run_id 없음`
  고아 상태 자동 복구
- theme-sync status 응답에 run_id 추가

정상 흐름:
ka90001 완료 → run_id 유지 → 첫 테마 이름/코드 저장 →
ka90002 1페이지 요청 → 처리 완료 1/142 → 계속 진행


## v3.27.6 합금철(172) 수신 후 멈춤 수정

관찰:
- [15/142] 합금철
- ka90002 1페이지 수신 완료
- 이후 약 40~50초 진행 정지

분석:
HTTP 수신은 이미 끝났으므로 네트워크 대기가 아닙니다.
기존 코드는 응답 직후 동일 async worker에서 동기식 PyMySQL
DELETE / INSERT / COMMIT을 실행했습니다.
DB lock wait가 발생하면 event loop까지 같이 막혀 화면이 멈춘 것처럼
보이고 stop/status API 반응도 늦어질 수 있습니다.

수정:
- 테마 관계 저장을 별도 SessionLocal로 격리
- asyncio.to_thread()로 sync PyMySQL을 event loop 밖에서 실행
- 세션별 innodb_lock_wait_timeout=4초
- 지원 시 lock_wait_timeout=4초
- DB 잠금/저장 실패는 전체 작업 실패가 아니라 해당 테마 후순위 재시도
- `키움 수신 → 응답 파싱 → MySQL 저장 → 저장 완료` 상태를 별도 표시
- raw/member count, DB 저장시간을 관리자 화면에 표시
- ka90002 전체 수집 성공 후에만 기존 theme relation을 교체

합금철에서 DB 잠금이 재현되더라도 수초 후 오류 상태를 표시하고
다음 테마로 넘어간 뒤 후순위에서 다시 시도합니다.


## v3.28 실제 다중 소스 종목 테마

테마 소스를 분리해 저장합니다.

- `kiwoom`: Kiwoom REST ka90001 / ka90002
- `infostock`: Npay 증권 국내 테마 화면에 표시되는 인포스탁 국내 시장 테마

인포스탁 테마는 코드 충돌 방지를 위해 `INFO:{theme_no}` namespace를 사용합니다.
테마명과 구성종목 코드만 저장하며 테마 설명/편입사유 문장은 복제하지 않습니다.

종목 리스트/검색/Smart:
- 두 실제 소스를 합쳐 표시
- 시장 테마를 우선 표시
- 동일 이름은 중복 배지 제거

종목 상세:
- 시장 테마 · 인포스탁
- 키움 REST 테마
- 업종 / 사업 분류
- 뉴스·리포트 연관 테마

관리자:
`시장 테마 동기화` 패널 추가

권장 순서:
1. 키움 전체 테마 동기화
2. 시장 테마 동기화


## v3.28.1 시장 테마 전체 실패 / 100% 정지 + 반응형 웹

### 시장 테마 수정
v3.28에서 다음 상태가 발생할 수 있었습니다.

- 시장 테마 목록 266개 / 7페이지 완료
- 처리 완료 266 / 266
- 연결 종목 0
- 실패 266
- 진행률 100%인데 마지막 테마에서 계속 실행 중

v3.28.1:
- 구성종목 parser를 `table.type_5` 한 클래스에 의존하지 않음
- `종목명 / 현재가 / 등락률 / 거래량` 헤더를 이용해 실제 구성종목 표 식별
- 인기검색/뉴스의 종목 링크 제외
- browser-like request headers 사용
- 짧은/접근제한 HTML 응답 감지
- 구성종목 0건이면 정상 성공으로 삼지 않고 실제 parse 오류로 기록
- 각 시장 테마 상세조회 최대 2회
- `StockTheme.source`를 전달받은 실제 source로 저장 (`infostock` 버그 수정)
- 수집 진행률은 최대 99%
- 99%에서 `최종 정리 / 커버리지 계산` 별도 표시
- 최종화 완료 후에만 100%
- 모든 테마 실패 시 즉시 failed 상태로 종료하고 첫 실제 오류 노출
- 실패 상세 30건을 관리자 화면에서 확인 가능
- 최종 DB 작업은 asyncio.to_thread + 별도 SessionLocal
- 백엔드 재시작 시 stale market-theme running 상태 자동 cancelled 정리
- 시장 테마 stop API idempotent

### 반응형 웹
- <=700px에서 기존 sidebar를 숨기지 않고 하단 모바일 navigation으로 전환
- Safe-area 대응
- 관리자/테마동기화 카드 2열 및 초소형 화면 1열
- Smart 표는 가독성을 유지한 horizontal scroll
- 종목 상세는 mobile full-screen sheet
- 차트 toolbar horizontal scroll / mobile chart 높이 조정
- 재무 테이블 horizontal scroll
- 모의투자/검색/설정/관리자 form stack
- 테마/뉴스/업종 source section mobile wrap
- auth 화면 mobile width 대응
- 360px 이하 ultra-narrow 대응


## v3.28.2 Universal Responsive UI

기존 문제:
여러 버전에서 추가된 680/700/720/760/900/980/1050px media query가
동시에 존재해 특정 화면 폭에서 서로 스타일을 덮어쓰며 UI가 깨질 수 있었습니다.

v3.28.2:
- 최종 반응형 규칙을 하나의 체계로 재작성
- 320px ~ 4K/울트라와이드 대응
- viewport-fit=cover / iPhone safe-area 대응
- Desktop 230px sidebar
- 761~1279px compact icon sidebar
- <=760px bottom mobile navigation
- 가로모드/낮은 화면 높이 전용 layout
- fluid clamp padding/font/chart sizing
- auto-fit card grids
- 모든 주요 grid child min-width:0 처리
- 관리자/Smart/테마/모의투자/설정 반응형 정리
- Stock detail mobile full-screen sheet
- Smart 추천표 <=600px 카드형 전환
- 키움 보유종목 <=600px 카드형 전환
- 주문/체결내역 <=600px 카드형 전환
- 재무표는 데이터 손실 없이 horizontal scroll
- 초소형 360px 이하 single-column fallback
- 1600/2200px 이상 large-display 최적화
- 모바일 navigation markup에 nav-label/nav-chevron 추가
- compact sidebar tooltip용 title/aria-label 추가

## v3.29 적용

```bash
cd ~/StockLog
./restart.sh
```

브라우저에서 `Ctrl + Shift + R` 후 `v3.29`를 확인합니다.

외부 접속 주소/포트 안내:

```bash
./network-info.sh
```

모의투자 페이지의 가격은 고정 초 단위 polling이 아니라 키움 `0B` 체결 tick 수신 시 즉시 바뀌며, 계좌 원장만 30초마다 화면을 막지 않고 갱신합니다.


## v3.29.1 stop/restart 오류 수정

증상:
```text
./stop-all.sh: 줄 8: name: 바인딩 해제한 변수
[ERROR] backend: 8100 포트가 이미 사용 중입니다.
```

원인:
`set -u` 상태에서 다음처럼 같은 local 문장 안에서 `$name`을
할당과 동시에 사용했습니다.

```bash
local name="$1" pidfile="$ROOT/.pids/$name.pid" pid=""
```

Bash는 `pidfile=...$name...` 확장 시점에 아직 local `name`이
설정되지 않은 것으로 처리할 수 있어 nounset 오류가 발생했습니다.

수정:
- `local name`, `local pidfile`, `local pid`를 각각 분리
- PID 파일이 없어도 8100 / 5174 잔존 listener 정리
- `fuser` 우선, `lsof` fallback
- 정상 종료 후에도 살아 있으면 SIGKILL fallback
- restart-all.sh는 stop 실패를 무시하지 않음
- 재시작 직전 8100 / 5174 포트가 실제로 비었는지 다시 확인


## v3.29.2 외부 DDNS Host 허용

`stocklog.env`에 외부 DNS/DDNS를 지정하면 Vite host allow-list에 자동 반영됩니다.

예:

```bash
STOCKLOG_PUBLIC_HOST=somensomes.iptime.org
```

이후:

```bash
./restart-all.sh
```

`run-frontend.sh`는 Vite 공식 추가 허용 호스트 환경변수
`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS`도 함께 설정합니다.

보안을 위해 모든 호스트를 무조건 허용하지 않고 지정된 hostname만 허용합니다.
\n\n## v3.29.3 사이드바 / 계좌 총자산 / 보유종목 UI\n\n- Desktop/tablet sidebar를 sticky grid item이 아닌 viewport fixed navigation으로 변경.\n  긴 페이지를 스크롤해도 왼쪽 배경/메뉴가 화면 전체 높이를 유지합니다.\n- 총자산은 브라우저의 `예수금 + 보유종목 평가액` 계산값을 사용하지 않습니다.\n  키움 계좌평가 계열 API snapshot의 total_asset을 기준값으로 사용하고, 이후 0B 실시간\n  체결가가 들어온 종목의 snapshot 대비 평가액 증감만 total_asset에 반영합니다.\n- backend normalize_snapshot은 여러 TR 전체에서 같은 이름의 숫자를 무작위로 찾지 않고\n  계좌평가 TR별 우선순위로 총자산/예수금/매입/평가/손익을 추출합니다.\n- `tot_evlt_amt`를 총자산 후보에서 제거했습니다. 이는 평가금액 계열로 취급합니다.\n- diagnostics.summary_sources에 각 계좌 요약값이 어느 TR/field에서 왔는지 저장합니다.\n- 보유종목은 카드 grid 대신 list + 선택 상세 pane으로 변경했습니다.\n  목록에서 종목 클릭 시 현재가, 평가손익, 수익률, 수량, 평균단가, 매입/평가금액,\n  당일 변동손익, 포트폴리오 비중, 실시간 tick sparkline을 상세 표시합니다.\n

## v3.29.4 모의투자 주문 화면 분리 / 사용자 UI 정리

- 보유종목 영역에 `주식 주문` 버튼 추가
- 선택 보유종목 상세에 `{종목명} 주문하기` 버튼 추가
- 주문 입력/차트/주문·체결 내역을 별도 주문 화면에 통합
- 주문·체결 내역 카드형 디자인 및 체결 진행률 표시
- 모바일에서는 주문 화면 전체화면 전환
- 사용자 화면에서 내부 Kiwoom 요청 식별자(ka/kt 번호, source_tr 등) 숨김
- 내부 요청 정보는 백엔드/진단 데이터에만 유지


## v3.29.5 테마 오류 / 점수 일치 / 상세 매수 / 카테고리 포트폴리오

- 테마 구성종목 저장 시 정의되지 않은 `source` 변수를 사용하던 NameError 수정
- 테마 API 내부 예외는 서버 로그에만 남기고 사용자에게 Python 예외명/내부 요청번호를 노출하지 않음
- Smart 추천 목록과 상세 화면이 `_smart_score_context()` 하나의 점수 함수를 공동 사용
- Smart에서 상세 진입 시 선택한 AI/버핏/나만의 공식 모드도 상세 API에 전달
- 클릭한 목록 점수 컨텍스트도 상세 상단 점수에 유지하여 육안상 즉시 동일하게 표시
- 상세 종목 우측에 `바로 매수` 버튼 추가
- 상세 매수 버튼 -> 모의투자 -> 해당 종목 선택 -> 매수 탭 주문 화면 자동 오픈
- 실제 키움 보유종목에 StockLog 실제 테마/업종 메타데이터 연결
- 대표 카테고리: 시장 테마 우선 -> 다른 실제 테마 -> 업종 -> 투자 스타일 -> 기타
- 카테고리별 평가액 투자 비중 donut chart 추가
- 카테고리별 종목수 / 비중 / 평가액 / 손익 / 수익률 표 추가
- 현재 손익이 가장 큰 카테고리를 별도 요약 표시


## v3.29.6 강세테마 change_rate NULL 스키마 오류 수정

증상:

```text
IntegrityError: Column 'change_rate' cannot be null
```

원인:
현재 SQLAlchemy 모델은 `Theme.change_rate`를 nullable로 정의하지만,
기존 MySQL의 `themes` 테이블이 과거 버전에서 `NOT NULL`로 생성된 경우
컬럼이 이미 존재하기 때문에 기존 컬럼 존재 검사만으로는 수정되지 않았습니다.

수정:
- `SHOW COLUMNS`의 실제 Null 속성까지 검사
- 기존 `themes.change_rate NOT NULL`이면 자동으로:
  `ALTER TABLE themes MODIFY COLUMN change_rate DOUBLE NULL`
- 변경 직후 MySQL에서 NULL 허용 여부 재검증
- 강세테마 상세 조회 직전에도 theme schema 상태 검증
- 키움에서 등락률을 주지 않은 테마는 0.0을 임의 생성하지 않고 NULL로 저장
- SQLAlchemy/PyMySQL 내부 오류/SQL문은 일반 사용자 팝업에 노출하지 않음
- 실제 상세 오류는 backend log에만 남김


## v3.30 대표 사업분류 보강

키움/인포스탁 테마는 모든 상장종목을 반드시 하나 이상 포함시키는
산업분류표가 아닙니다.

기존 StockLog는 실제 테마가 없고 sector도 비어 있으면
`키움 테마 미분류`라고 표시해 미분류가 과도하게 많아 보였습니다.

대표 표시 우선순위:
1. 인포스탁 실제 시장 테마
2. 키움 실제 테마
3. OpenDART 기업개황 induty_code 기반 사업분류
4. 기존 실제 업종
5. 회사명에서 사업이 명확한 경우 제한적 보조분류
6. `사업 · 기타`

테마가 아닌 사업분류를 가짜 테마로 저장하지 않습니다.

새 DB 컬럼:
- industry_code
- industry_name
- industry_source
- industry_updated_at

기존 MySQL은 서버 시작 시 자동 ALTER 됩니다.

관리자 새 기능:
`종목 분류 보강`

API:
- GET  /api/admin/classification-sync/status
- POST /api/admin/classification-sync/start
- POST /api/admin/classification-sync/stop
- GET  /api/admin/classification-sync/coverage

DART_API_KEY가 필요합니다.
5개 단위 병렬조회 + batch pause로 전체 활성 종목을 background에서 보강합니다.
기존 DART 재무 동기화도 기업개황 사업분류를 함께 저장합니다.


## v3.30.1 강세테마 상세 조회 안정화

문제:
`GET /api/themes/{theme_code}`가 단순 조회 요청인데도 Theme / StockTheme
DB 저장과 commit을 함께 수행했습니다. 따라서 키움 구성종목 조회가
정상이어도 MySQL 저장 오류가 발생하면 강세테마 화면 전체가 500으로
실패했습니다.

수정:
- 강세테마 상세 GET은 완전 read-only
- GET 요청에서 Theme/StockTheme INSERT/UPDATE/COMMIT 제거
- 테마 DB 저장은 관리자 `키움 전체 테마 동기화`에서만 수행
- 키움 live 구성종목 성공 후 StockLog 종목정보 enrich 실패 시에도
  live 구성종목은 그대로 반환
- 키움 live 상세가 일시 실패하면 이미 동기화된 실제 StockTheme 관계로 fallback
- synthetic/임의 구성종목은 생성하지 않음
- fallback 사용 시 화면에 `최근 정상 동기화 데이터`로 명확히 표시
- 테마를 클릭할 때 팝업으로 화면을 막는 대신 상세 패널 안에서 상태 표시


## v3.30.2 스마트 분석 주요 시장 지표

스마트 분석 최상단에 실제 시장 데이터 카드 5개를 추가했습니다.

- NASDAQ Composite
- KOSPI
- KOSDAQ
- USD/KRW (달러/원)
- USD/JPY (달러/엔)

각 카드:
- 현재값
- 전일 대비
- 등락률
- 실제 데이터가 없으면 `조회 대기`
- 직전 실제 데이터가 있고 최신 갱신만 실패하면 `최근 정상 데이터`

Backend:
- GET /api/market-overview
- Yahoo Finance chart 실제 데이터 사용
- query1 / query2 host fallback
- 30초 서버 캐시
- 각 자산 독립 조회
- 일부 자산 오류가 Smart 페이지 전체를 실패시키지 않음
- synthetic / random fallback 없음

Frontend:
- Smart 추천과 독립적으로 30초마다 background refresh
- desktop 5열
- <=1250px 3열
- <=760px 2열
- <=390px 1열


## v3.30.3 장 종료 후 마지막 실제 지수/환율 유지

시장 마감은 `조회 대기` 조건이 아닙니다.

실제값 조회 우선순위:
1. Yahoo 5일 / 5분 chart — 장 마감 직전 마지막 실제값
2. Yahoo 1개월 / 일봉 history — 마지막 공식 종가
3. 현재 서버 메모리의 마지막 실제값
4. `runtime/market_overview_last_actual.json`에 저장된 마지막 실제값

KOSPI/KOSDAQ/NASDAQ이 CLOSED 상태면 숫자는 유지하고
`장 마감 · 마지막 실제값`으로 표시합니다.

USD/KRW / USD/JPY도 마지막 실제 환율을 유지합니다.

`시장 데이터 연결 대기`는 장 종료 의미가 아니라 외부 공급자 연결 실패 + 
과거 실제 캐시도 전혀 없는 경우에만 표시됩니다.

영속 캐시는 synthetic 값이 아니며 실제 조회에 성공한 값만 저장합니다.


## v3.30.4 DDNS 단일 외부포트 구성

권장 구성:

```text
Internet
  http://somensomes.iptime.org:3000
            |
            | ipTIME NAT
            v
192.168.0.200:5174  (Vite)
       |       |
       |       +-- /ws  -> 127.0.0.1:8100
       +---------- /api -> 127.0.0.1:8100
```

공유기에서는 외부 TCP 3000 -> 내부 192.168.0.200:5174 하나만 포워딩합니다.
8100은 인터넷에 직접 공개하지 않습니다.

설정:

```bash
./configure-external.sh somensomes.iptime.org 3000
./restart-all.sh
```

Vite:
- `stocklog.env`를 config에서 직접 읽음
- run-frontend.sh 환경변수도 병행
- STOCKLOG_PUBLIC_HOST를 exact `server.allowedHosts`로 사용
- `/api` / `/health` HTTP proxy
- `/ws` WebSocket proxy

Frontend:
- VITE_BACKEND_ORIGIN이 없으면 `window.location.origin`을 사용
- 외부 :3000 접속 시 API도 :3000/api로 요청
- WebSocket도 :3000/ws로 요청

따라서 DDNS 사용자에게 별도 8100 포트포워딩이 필요하지 않습니다.


## v3.30.5

### Root network `.env`
Primary file: `~/StockLog/.env`
Legacy `stocklog.env` is still read first for compatibility; root `.env` overrides it.
Backend application secrets remain in `backend/.env`.

### Portfolio holding fix
Unfilled/execution/order-status payloads can no longer create holdings.
Holdings are parsed only from balance/evaluation sources:
`kt00004 -> ka10085 -> kt00003`.
Order history excludes balance sources and requires a real order number.

### Invisible automatic synchronization
30-second background sync:
- no spinner
- no button text change
- no error flash
- no loading overlay
- unchanged payload does not replace React state
- portfolio category chart instance is reused
- chart update animation disabled

Manual refresh still shows normal progress.


## v3.30.6 주문화면 상태 분리

포트폴리오의 실제 보유종목과 주문 화면의 미체결 주문을 시각적으로
완전히 분리했습니다.

주문 화면:
- 선택 종목: `실제 보유 3주` 또는 `미보유`
- 미체결 주문이 있으면 `미체결 N주 · 보유 미반영`
- 별도 `미체결 주문` 영역
- 미체결 카드마다 `보유 미반영` 표시
- `체결 내역`에는 현재 미체결 상태인 주문을 제외하고 실제 체결 완료 내역만 표시

같은 주문이 주문/체결 응답에 중복으로 들어온 경우 frontend에서
`주문번호 + 종목코드` 기준으로 하나로 병합해서 보여줍니다.

내부 API/TR 명칭은 사용자 화면에 표시하지 않습니다.


## v3.31 Professional Order Desk + StockLog 가격감시 예약

### 주문화면
증권 HTS에서 공통적으로 사용하는 정보 구조로 재구성:
- 종목검색
- 현재가 / 시가 / 고가 / 저가 / 전일 / 거래량
- 실제 키움 10호가
- 일반주문 / 가격감시예약
- 시장가 / 지정가
- 현재가 / 매도1 / 매수1 가격 바로입력
- 주문수량 +/- 및 10/25/50/100% 빠른입력
- 예수금 / 실제보유 / 주문가능 추정
- 예상 주문금액
- 미체결 / 체결 / 예약관리 탭

체결내역은 `매수 체결` / `매도 체결`을 명확히 표시.

### 실제 호가
Kiwoom ka10004 `/api/dostk/mrkcond`
- 매도 10호가
- 매수 10호가
- 각 호가 잔량
- 총 매도/매수 잔량

### StockLog 가격감시 예약
이 기능은 키움의 별도 예약주문 API를 사칭하지 않음.
StockLog 서버가 키움 실제 현재가를 주기적으로 확인하고 조건 충족 시
기존 키움 모의투자 매수/매도 주문 API를 한 번 전송함.

예약:
- 매수 / 매도
- 이하 도달 / 이상 도달
- 감시가격
- 수량
- 조건충족 후 시장가 / 지정가
- 지정가 실행가격
- 유효기간 또는 취소할 때까지
- 등록 / 편집 / 취소
- 감시중 / 장외대기 / 주문전송 / 만료 / 취소 / 실패 상태

실행은 KRX 정규장 평일 09:00~15:30에만 수행하여
장 종료 후 마지막 종가로 예약이 잘못 발동하는 것을 방지.

DB:
`trade_reservations`

환경:
`STOCKLOG_RESERVATION_POLL_SECONDS=3` 기본.


## v3.31.1 주식 구매가능 금액 / 주문 기본종목

### 구매가능 금액
`예수금`과 `주식 구매가능 금액`을 분리합니다.

- cash: 계좌 정규화/총자산 fallback용
- buying_power: 키움이 명시적으로 제공한 주문가능금액

우선순위:
1. 주문인출가능금액 계좌 응답
2. 다른 계좌 응답에 명시적으로 존재하는 주문가능금액 필드

StockLog가 보유주식 평가금액을 수동으로 빼서 계산하지 않습니다.
키움 응답에 주문가능금액이 없으면 예수금을 대신 보여주지 않고
`확인 대기`로 표시합니다.

### 주문화면 기본 종목
주식 주문 버튼을 누르면 빈 주문화면을 표시하지 않습니다.

우선순위:
1. 사용자가 주문하기를 누른 보유종목
2. 이전에 선택했던 종목
3. 현재 보유종목 중 평가금액이 가장 큰 종목
4. 보유종목이 없으면 삼성전자(005930)


## v3.31.2 구매가능금액 응답 인식 보강

키움 공식 계좌 API의 주문인출가능금액 TR은 kt00009입니다.
v3.31.1의 TR 선택은 맞았지만 응답 필드 인식이 너무 제한적이었습니다.

수정:
- 주문가능금액 explicit alias 대폭 확장
- kt00009 응답의 order + available/possible + amount 의미 필드를
  semantic하게 탐색
- 수량/가격/수수료/세금/출금가능금액은 자동 후보에서 제외
- generic cash orderable amount 우선
- generic이 없을 때 100% 증거금 주문가능금액 우선
- 예수금/총자산/보유평가액 계산 fallback 없음
- kt00009 기존 요청 body variants 유지
- 기존 variants가 모두 실패할 때 reduced body variants 추가
- 과거 snapshot이 buying_power 미확인 상태면 20초 cache를 bypass하고
  자동으로 다시 Kiwoom 계좌를 조회

진단:
GET /api/kiwoom/buying-power/status
- 금액은 노출하지 않음
- dedicated account response 성공 여부
- 주문가능금액 field 발견 여부만 확인


## v3.31.3 전체 반응형 점검

태블릿에서 Smart -> 종목 상세 진입 시 상세 화면이 왼쪽 사이드바 아래로
들어가 잘리는 문제를 수정했습니다.

원인:
- sidebar: fixed, z-index 500
- detail modal: viewport 전체 left:0, z-index 100
- detail width: 100vw 기반
- tablet breakpoint가 1279px 이하에만 적용

수정:
- desktop/tablet StockDetail modal은 sidebar 오른쪽 content 영역에서 시작
- tablet/coarse pointer 장치는 CSS viewport가 커도 compact sidebar 사용
- tablet 기준을 1480px까지 확장
- mobile StockDetail은 bottom navigation 위에 full-screen modal
- detail inner grids, themes, financial tables, reports overflow audit
- order desk tablet에서는 3열 -> 2열 + chart full row
- Smart market indicators tablet 3열 / mobile 2열 / small phone 1열
- DetailedStockChart에 ResizeObserver 추가
- orientation/sidebar/panel width 변화 시 ECharts 자동 resize
- StockDetail 열릴 때 background body scroll lock
- data-heavy tables only scroll inside their own cards; page horizontal overflow 방지


## v3.31.4 페이지 전환 시 종목상세 자동 종료

문제:
`StockDetail`은 App 최상단의 전역 overlay인데 sidebar navigation은
기존에 `setPage(id)`만 호출했습니다.

따라서:
1. 스마트 분석에서 종목상세 열기
2. sidebar의 강세 테마/모의투자/설정 등을 누르기
3. underlying page만 바뀌고 기존 종목상세 overlay는 그대로 유지

태블릿 compact sidebar에서는 이 상태가 특히 명확하게 보였습니다.

수정:
- App-level `navigatePage(id)` 추가
- 모든 sidebar 메뉴는 `navigatePage()` 사용
- 페이지 전환 전에 StockDetail 닫기
- trading이 아닌 곳으로 이동하면 이전 tradeIntent도 정리
- 새 페이지 진입 시 scrollTop=0
- future code path에서 page가 바뀌어도 stale detail이 남지 않도록
  `[page]` defensive effect 추가
- 로그아웃 시 detail/tradeIntent 정리


## v3.31.5 React Hook order hotfix

v3.31.4에서 App의 page-change defensive useEffect가
`if (!user) return <Login .../>` 뒤에 배치되어 로그인 전/후 Hook 개수가
달라지는 문제가 있었습니다.

React Rules of Hooks 위반:
- 로그인 전: 해당 useEffect 호출 안 됨
- 로그인 후: 해당 useEffect 추가 호출
- 결과: `Rendered more hooks than during the previous render`

수정:
- 모든 App-level Hook을 conditional return보다 위로 이동
- 페이지 전환 시 StockDetail 자동 종료 기능은 그대로 유지
- effect는 detail이 이미 null이면 같은 null을 반환해 불필요한 상태 변경 최소화


## v3.32 종목상세 설명력 강화
- 주요 투자/재무지표 hover/focus 설명 툴팁
- 실제 뉴스 제목·요약 기반 기사별 및 긍정/부정 핵심 요약
- 최근 증권사 리포트 제목 + 접근 가능한 공개 상세페이지 기반 방향성/투자의견/목표주가 요약
- 분기재무 비교 방향 버그 수정: 최신 공시를 바로 이전 공시와 비교하고 정확한 비교기간 표시
- 추천점수 단일 source: `_smart_score_context`로 score/recommendation/summary 통일, stale frontend override 제거, 뉴스 refresh에도 smart_mode 유지


## v3.33 Readability + Investor DNA

### Tooltip clipping
MetricInfo now renders the explanation box through React `createPortal`
directly into `document.body`.

- viewport clamped horizontal position
- automatic above/below positioning
- no clipping by detail/card/sidebar overflow
- hover leaves -> immediately closes
- focus/touch also supported
- info icon has more breathing room

### Readability
System Korean font stack changed to:
Pretendard -> Noto Sans KR -> Apple SD Gothic Neo -> Malgun Gothic.

Detail/page/card/news/report/order related small text sizes were raised.

### Price spacing
Detail current price and percentage now use a flex baseline with an explicit
gap, preventing strings such as `18,200원2.94%`.

### Investor DNA
New sidebar page: `투자 성향 분석`

Persistent MySQL table:
`investment_profiles`

20 questions / 5 axes:
1. L/N/S: 장기 / 중립 / 단기
2. A/D: 공격 / 방어
3. G/V: 미래가치 / 현실가치
4. P/H: 빠른 수익실현 / 큰 수익추구
5. F/M: 집중 / 분산

Total combinations: 3 * 2 * 2 * 2 * 2 = 48.

Result:
- five-letter type
- nickname
- each trait explanation
- strengths / cautions
- answer balance percentages
- all 48 type browser
- retest and account-level persistence

This page is explicitly presented as a self-reflection tool, not an official
financial suitability assessment.


## v3.34 StockLog AI Bot / Ollama

### Architecture

Actual data:
- Stock identity / market / sector / OpenDART industry
- real market & Kiwoom themes
- PER / PBR / EPS / BPS / ROE / dividend / growth / margin
- peer medians from the same StockLog universe
- latest 4 OpenDART financial periods
- actual Kiwoom daily chart context
- 1/5/20/60 day returns
- MA20 / MA60 / MA240 position
- 20-day relative volume
- 52-week high distance
- actual Google News RSS summaries
- actual Naver Finance broker report summaries
- KOSPI / KOSDAQ / NASDAQ / USDKRW / USDJPY market context
- current StockLog quantitative score/reasons

These are compacted into STOCK_CONTEXT before Ollama analysis.

### AI model

Default:
OLLAMA_MODEL=qwen3:4b-instruct

API:
POST /api/chat

Structured JSON schema response is used.

### Hallucination guard

System prompt requires:
- use only STOCK_CONTEXT facts
- no unseen latest events
- no invented company facts
- explicitly report missing data
- explain disagreement with StockLog quantitative score

### Cache

MySQL:
ai_stock_analysis

Unique:
(stock_code, mode)

Default TTL:
3 hours

Market snapshot is intentionally excluded from the context hash because
30-second index/FX updates would otherwise invalidate expensive CPU analysis
continuously. The full market snapshot is still supplied to the AI when a new
analysis is generated.

### Smart page

The Smart quantitative engine remains the fast first-stage ranker.

AI:
- cached AI opinion is displayed in the Smart list
- button: "상위 10개 AI 분석"
- backend processes the list sequentially (one local CPU analysis at a time)
- UI polls progress/cache without blocking the Smart page

### Detail

Stock detail automatically requests the current AI analysis.
If a fresh cache exists it returns immediately.
Otherwise Ollama generates a new structured analysis.

Displays:
- AI positive/neutral/risk view
- judgment clarity (NOT probability of future return)
- one-line conclusion
- positive factors
- risk factors
- company / valuation / financial / momentum / news / reports / market views
- quantitative vs AI agreement
- missing-data disclosure

### Important

AI is interpretation only.
Python/StockLog remains responsible for numerical calculations and ranking.
No synthetic market/news/report/financial facts are generated.


## v3.34.1 CPU AI async hotfix

v3.34.0 waited for the complete Qwen response inside one browser HTTP request.
On the i5-6500T CPU host, context building + model generation could exceed the
frontend 120-second timeout and show only a generic load error.

Changes:
- detail AI uses POST start + GET status polling
- AI generation runs in backend background task
- browser never waits on a multi-minute model request
- status polling every 3 seconds, up to 6 minutes
- one global CPU generation lock
- stages: queued / context / running / ready / failed
- Ollama read timeout 300 seconds
- num_ctx default 8192
- think=false
- Structured Output schema with JSON-mode compatibility retry
- robust JSON extraction
- safe stage-specific errors stored in MySQL
- `/api/ai/status` now reports running Ollama models and generation_busy
- `./ai-diagnose.sh` added

## CPU AI 빠른 분석 설정 (v3.35.0)
기존 `backend/.env` 또는 실제 서비스 환경변수에 아래 값을 적용하세요.

```env
AI_ANALYST_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b-instruct
OLLAMA_NUM_CTX=2048
OLLAMA_NUM_PREDICT=240
OLLAMA_TIMEOUT_SECONDS=90
OLLAMA_KEEP_ALIVE=10m
AI_ANALYSIS_CACHE_HOURS=3
AI_INCLUDE_LIVE_REPORTS=false
AI_INCLUDE_MARKET_CONTEXT=true
```

`AI_INCLUDE_LIVE_REPORTS=false`는 AI 분석 요청이 네이버 리포트 조회를 기다리지 않게 합니다. 리포트 화면 자체의 기존 조회 기능은 그대로 유지됩니다.

## v3.40 외부 API 관리자 연동

1. 기존 DB를 삭제하지 말고 새 코드를 적용합니다.
2. `./restart.sh`로 재시작하면 신규 테이블이 자동 생성됩니다.
3. 관리자 계정으로 로그인합니다.
4. **관리자 > 외부 API 연동 · 사용량 모니터링**에서 다음을 저장합니다.
   - 네이버 뉴스: Client ID, Client Secret
   - OpenDART: API Key
5. 각각 `연결 테스트`를 눌러 정상 상태를 확인합니다.
6. 기존 `.env` 값은 fallback이므로 즉시 삭제할 필요가 없습니다. 관리자 저장이 정상 동작하는 것을 확인한 뒤 필요하면 제거하세요.

> `JWT_SECRET`은 암호화 키 파생에도 사용됩니다. 이미 MySQL에 외부 API 키를 저장한 뒤 JWT_SECRET을 바꾸면 다시 입력해야 할 수 있습니다.


## v3.40.1 NAVER API HUB 전환

네이버 뉴스 검색은 기존 `openapi.naver.com` 방식이 아니라 NAVER API HUB를 사용합니다.

- Endpoint: `https://naverapihub.apigw.ntruss.com/search/v1/news`
- Client ID header: `X-NCP-APIGW-API-KEY-ID`
- Client Secret header: `X-NCP-APIGW-API-KEY`

관리자 > 외부 API 연동에서 NAVER API HUB의 Application 인증정보를 저장한 뒤 연결 테스트를 실행하세요.
