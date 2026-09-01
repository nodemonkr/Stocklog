# StockLog v3.76.5 변경사항

## Kiwoom 전체 동기화 NameError 수정

- `_run_kiwoom_part()`가 호출하던 `_update_real_market_metrics()` 구현이 누락된 결함을 수정했습니다.
- Kiwoom 일봉에서 현재가, 당일 등락률, 20거래일 모멘텀, 최근 일간 변동성, 발행주식수가 있을 때 시가총액(억원)을 갱신합니다.
- 동기화 시작 전에 필수 helper가 실제 callable인지 검증하여 불완전한 배포본은 외부 API 호출 전에 즉시 실패시킵니다.
- `NameError`, `AttributeError`, `NotImplementedError` 등 코드/배포 결함을 종목별 데이터 오류로 취급하지 않고 첫 발생 즉시 해당 동기화 단계를 중단합니다. 같은 코드 오류를 전 종목에 반복하여 API/DB/로그를 소모하지 않습니다.
- 내부 underscore 함수 호출과 정의를 AST로 대조하여 현재 `main.py`에 정의되지 않은 내부 함수 호출이 0개임을 확인했습니다.

## 검증

- Python 전체 `compileall` 통과
- `main.py` 내부 함수 호출/정의 정적 대조 통과
- shell script `bash -n` 통과
- production JavaScript `node --check` 통과
