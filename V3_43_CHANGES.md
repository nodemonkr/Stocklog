# StockLog v3.43.0

## Kiwoom Universe 안정화

- Kiwoom `ka10099` 결과를 상장회사 수가 아닌 **원본 상장증권 Universe**로 취급합니다.
- 기존 `1,500~3,500개` 절대 상한 검사를 제거하고, 넓은 현실 범위 + 시장별 최소 수 + 기존 DB 대비 급감 여부로 검증합니다.
- 4,033개처럼 ETF/ETN/우선주/KONEX 등이 포함된 정상적인 원본 결과를 더 이상 단순 총량만으로 차단하지 않습니다.

## 원본 Universe / 분석 Universe 분리

- `stock_universe`에 `is_analysis_eligible`, `analysis_exclusion_reason`을 자동 추가합니다.
- 원본 상장증권은 검색 가능한 상태로 보존합니다.
- 스마트 분석과 DART/키움 심층 동기화는 KOSPI/KOSDAQ의 기업 분석 대상만 사용합니다.
- ETF, ETN, SPAC, REITs, 대표적인 ETF 브랜드 상품, 우선주, KONEX 등은 기본 분석 대상에서 제외합니다.
- 관리자 상태에 원본 수, 분석 대상 수, 제외 수, 제외 사유별 건수를 기록합니다.

## DB 보호 로직

- 시장별 목록이 비정상적으로 적거나 기존 활성 Universe 대비 45% 이상 급감했을 때만 DB 반영을 중단합니다.
- 종목 수 증가 자체는 오류로 판단하지 않습니다.
