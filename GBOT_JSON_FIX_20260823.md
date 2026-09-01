# StockLog Gbot JSON 안정화 수정 (2026-08-23)

- 프리미엄 Gbot 상세 분석 출력 한도: 1,900 -> 4,800 tokens
- Gemini 3.x: thinkingLevel=low 적용
- Gemini 2.5 fallback: thinkingBudget=0 적용
- HTTP 200 이후 JSON 파싱 실패 시 한 번만 자동 재생성
- 재생성 출력 한도 최대 6,200+ tokens 확보
- JSON 실패 로그에 finishReason, token usage, 응답 앞/뒤 일부 기록
- Obot은 종목 상세 프리미엄 분석에 사용하지 않음
