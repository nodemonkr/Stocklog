# StockLog 자동매매 진단 + Gbot 실패학습 메모리 — 2026-08-28

## 목적

이번 변경은 두 문제를 동시에 해결한다.

1. 주문이 없던 날에 **정상적으로 감시/판단했으나 거래가 없었던 것인지**, 아니면 watcher/Gbot/Kiwoom 중간 단계가 실제로 멈춘 것인지 앱/웹에서 바로 판별한다.
2. Gbot 자동매수 뒤 손실이 발생했을 때 당시 입력과 판단 근거를 보존하고, 사후 성과를 붙여 **반복되는 실패 패턴만** 다음 매수 판단에 위험 메모리로 제공한다.

## 1. 자동매매 회차 감사 로그

새 테이블: `auto_trading_cycles`

매 회차마다 아래 항목을 저장한다. Gbot이 0건을 반환하거나 후보가 0개여도 행을 남긴다.

- cycle id / scheduled·manual·holding_review
- 시작/종료시각, 성공/오류/rate-limit/skipped
- Kiwoom 계좌 동기화 성공 여부
- Gbot 호출 성공 여부
- 후보 수 / 보유 검토 수
- BUY / SELL / HOLD / guard 차단 / 실제 주문 수
- 최종 message / error

자동매매 상태 API는 watcher heartbeat와 오늘 집계를 함께 반환한다.

- 오늘 실행 회수
- 정상/오류/rate-limit 회차
- 후보 종목 수
- Gbot 판단 수
- BUY/SELL/HOLD/차단/주문 수
- Kiwoom 정상 회차 / Gbot 정상 회차
- watcher 실행 여부 / heartbeat 나이 / 마지막 scan 상태
- 마지막 정상 회차

따라서 `주문 0건`과 `판단 자체 0건`을 구분할 수 있다.

## 2. 손실 사례 경험 메모리

새 테이블: `auto_trading_outcomes`

Gbot BUY 주문이 broker에 접수된 시점에 learning case를 만들고 실제 체결이 확인되면 entry price/quantity/time을 보정한다.

### 매수 당시 저장하는 정보

- 종목 / cycle / decision id
- Gbot confidence / reason / evidence / risks / exit plan
- 후보 종목 정량 snapshot
- smart score
- 가격/모멘텀/변동성
- 외국인·기관 수급
- 최근 뉴스·공시·리포트 요약
- 당시 risk setting
- Gbot signal / allocation hint

### 이후 추적

- 현재 수익률
- 최대 상승폭(Max Gain)
- 최대 낙폭(Max Drawdown)
- 청산 수익률
- 분석 대기/완료 상태

기본 사후분석 후보 기준은 보수적으로 설정한다.

- 손실 청산: `-0.5% 이하`
- 미청산: 매수 2시간 이후 `-3% 이하`
- 미청산: 매수 1시간 이후 최대낙폭 `-5% 이하`

매수 직후의 작은 음수 변동은 실패로 학습하지 않는다.

## 3. hindsight bias 방지

사후분석은 `entry_snapshot`과 `post_entry_events`를 분리한다.

매수 뒤 새로 발생한 뉴스/공시는 당시 Gbot이 알 수 없던 정보다. Gemini reviewer는 이를 `post_entry_event`로 별도 분류하며, 이것만이 주된 원인이라면 당시 진입 판단을 `avoidable_error`로 취급하지 않도록 지시한다.

## 4. 다음 매수에 반영하는 방법

사후감사 결과에서 `root_causes`, `missed_signals`, `false_assumptions`, `reusable_lessons`, `verdict`를 구조화 JSON으로 저장한다.

위험 태그 예:

- `chasing_momentum`
- `weak_flow`
- `excessive_volatility`
- `weak_fundamentals`
- `news_risk`
- `disclosure_risk`
- `low_coverage`
- `valuation_risk`
- `market_regime`
- `timing_error`
- `post_entry_event`
- `insufficient_evidence`

다음 `_auto_gbot_decisions()` 요청에는 최근 reviewed 손실·유의미한 낙폭과 **2회 이상 반복된 태그**를 `learning_memory`로 제공한다.

중요: 이 메모리는 하드 매수금지 목록이 아니다. 프롬프트에서 다음 원칙을 강제한다.

- 한 번의 손실을 일반화하지 않는다.
- 반복 패턴이 현재 종목의 최신 데이터와 실제로 일치할 때만 감점한다.
- 매수 후 돌발 이벤트는 과거 진입 규칙의 실패로 과대평가하지 않는다.
- 과거 손실을 이유로 현재 강한 신호를 무조건 거부하지 않는다.

## 5. 운영 화면

웹과 모바일 자동매매 화면에 다음 블록을 추가했다.

- `오늘 자동매매 진단`
- `Gbot 실패 학습 메모리`
- 분석 대기 건 수
- 반복 실패 패턴
- 최근 손실 사례 / 현재 손익 / 최대낙폭 / 원인 태그 / 학습 문장
- 수동 `대기 사후분석 실행`

사후분석은 자동 watcher에서도 주기적으로 실행하며 Gemini rate limit이면 주문과 분리해 재시도 시간을 늦춘다.

## 6. 데이터베이스 적용

두 테이블은 신규 테이블이므로 기존 데이터 컬럼 ALTER 없이 SQLAlchemy `Base.metadata.create_all()`에서 생성된다.

기존 주문/포트폴리오/자동매매 테이블은 삭제하거나 초기화하지 않는다.

## 7. 다음 단계 권장

현재 버전은 **경험 메모리 기반 위험 보정 1단계**다. 충분한 표본이 쌓이기 전에 LLM이 스스로 매매 규칙/코드를 바꾸게 해서는 안 된다.

권장 2단계는 최소 수십 건 이상의 체결 결과를 모은 뒤 태그별 손익/승률/최대낙폭/시장국면을 통계적으로 계산해, 반복적으로 유의미한 패턴만 deterministic risk penalty로 승격하는 방식이다. 이 단계 역시 shadow evaluation을 거친 뒤 실제 주문 크기에 반영하는 것이 안전하다.

## 8. 2026-08-30 — 경험 메모리 V2 적용

위 2단계의 보수적 초기 버전을 적용했다.

- 정상 변동, 매수 후 돌발정보, 근거 부족, 불명확한 `other` 원인은 다음 매수에 재사용하지 않는다.
- 같은 종목의 같은 날 분할매수는 하나의 독립 경험으로 집계한다.
- 최근 180일 자료만 실행 메모리에 사용한다.
- 실패 패턴과 동일한 진입 조건에서 발생한 성공·회복 사례도 함께 비교한다.
- 3개 이상 독립 사례, 2개 이상 종목, 동일 조건 표본의 손실·낙폭 비율 67% 이상, 평균 수익률 음수 조건을 모두 만족해야 확신도 감점 후보가 된다.
- 현재 후보의 최신 수급·가격·재무·뉴스·공시 데이터에서 같은 조건이 다시 확인될 때만 패턴당 2~5점, 합계 최대 12점을 감점한다.
- 데이터가 오래됐거나 2회만 반복된 패턴은 Gbot 경고로만 제공하고 주문 확신도에는 반영하지 않는다.
- 부분 매도 체결은 매수 learning case에 FIFO로 배분해 수량가중 평균 매도가와 부분 실현손익을 보존한다.

이 보정은 종목 블랙리스트가 아니다. 위험조정 확신도가 사용자의 최소 확신도 아래로 내려간 경우에만 기존 주문 안전장치가 매수를 차단하고, 그렇지 않으면 낮아진 확신도에 따라 목표 매수금액이 줄어든다.
