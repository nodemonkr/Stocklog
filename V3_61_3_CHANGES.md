# StockLog v3.61.3

- FullMarketSyncState 전체 ORM flush에 46KB JSON 강제 상한 적용
- failures_json/provider_status_json 저장 경로와 무관하게 Data too long 방지
- 레거시 themes.theme_name NOT NULL DB에서 ALTER 권한 없이도 이중 컬럼 저장
- 실패 기록 발생 시각을 관리자 화면에 표시
- 과거 failures_json 용량 초과 기록을 과거 실패로 명확히 안내
