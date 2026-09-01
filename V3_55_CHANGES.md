# StockLog v3.55 변경사항

## Gemini 무료 AI 연동

- Google Gemini Developer API를 StockLog의 1순위 AI 엔진으로 추가했습니다.
- 수동 종목 AI 분석: `gemini-2.5-flash`
- 프리미엄 이상 보유종목 자동 모멘텀: `gemini-2.5-flash-lite`
- Gemini 설정/무료 안전 한도/호출 오류 시 로컬 Ollama로 자동 fallback합니다.
- Ollama까지 사용할 수 없으면 StockLog 정량 데이터 기반 deterministic 분석을 반환해 화면을 깨뜨리지 않습니다.

## 무료 운영 보호

- StockLog 자체 일일 Gemini 안전 한도: 기본 200회 (`GEMINI_APP_DAILY_GUARD`로 변경 가능)
- 백그라운드 자동 AI 안전 한도: 기본 120회 (`GEMINI_BACKGROUND_GUARD`로 변경 가능)
- 위 숫자는 Google의 공식 quota를 의미하지 않고 StockLog가 무료 운영을 위해 자체적으로 더 보수적으로 거는 제한입니다.
- 동일 종목 분석은 기존 MySQL AI 캐시를 계속 재사용하므로 실제 Gemini 호출량을 줄입니다.
- API 호출량/실패/백그라운드 사용량은 관리자 페이지에서 확인할 수 있습니다.

## 관리자 Gemini 설정

관리자 → `외부 API · AI`에 Gemini 카드가 추가되었습니다.

1. Google AI Studio에서 Gemini API Key를 생성합니다.
2. StockLog 관리자 페이지 Gemini AI 카드에 API Key를 입력합니다.
3. 저장 후 `연결 확인`을 실행합니다.
4. 정상 연결되면 StockLog AI 분석은 Gemini를 우선 사용합니다.

API Key는 기존 외부 API 설정과 동일하게 MySQL에 암호화 저장되고 화면에는 원문을 다시 노출하지 않습니다.

## 개인정보/계좌정보 보호

Gemini에는 공개 종목 데이터만 전달합니다.

- 종목명/코드/업종
- PER/PBR/ROE 등 정량 지표
- 가격 모멘텀/이동평균
- StockLog가 수집한 공개 뉴스/공시/리포트의 짧은 요약 정보

보유종목 자동 모멘텀 분석에서도 계좌번호, 회원 ID, 보유수량, 평균매입가 등 개인 포지션 정보는 Gemini prompt에 넣지 않습니다.

## 무료 전용 운영 주의

StockLog 코드가 Google 계정의 결제 상태를 강제로 제어할 수는 없습니다. 유료 과금이 절대 발생하지 않게 운영하려면 Gemini API Key를 만든 Google 프로젝트에 Billing을 연결하지 않은 무료 티어 프로젝트를 사용하세요.

Gemini 무료 티어에 전송한 콘텐츠는 Google 제품 개선에 사용될 수 있으므로 StockLog는 개인 계좌정보를 외부 AI에 보내지 않도록 설계했습니다.
