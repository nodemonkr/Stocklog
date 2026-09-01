# StockLog v3.76.7 변경사항

## Classification 동기화 가시성/정지 방지

- 통합 동기화에서 classification 단계 시작/반환 및 내부 단계 진단 로그 추가
- OpenDART corpCode 동기화 120초 상한 추가
- 기업개황 5종목 배치 조회 30초 상한 추가
- 100종목 단위 CLASSIFICATION_PROGRESS 진단 로그 추가
- classification 자식 진행률을 unified-sync 부모 진행률에 실시간 반영
- standalone 중지 요청은 asyncio task cancellation을 기준으로 처리하고 매 배치 DB 상태 polling 제거
- 장시간 정상 작업과 실제 정지를 관리자 화면/진단 TXT에서 구분 가능하도록 개선
