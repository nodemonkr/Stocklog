# StockLog v3.76.10 변경사항

## 관리자 동기화 상태/진단 응답성
- `/api/admin/sync-overview`를 AnyIO 공용 worker pool에서 분리하고 전용 monitor executor + monitor DB pool에서 실행합니다.
- monitor 조회는 3초 상한을 두고, 장애 시 마지막 정상 snapshot을 즉시 반환합니다.
- `/api/admin/sync-error-logs`, 개별 TXT 다운로드, frontend client-event 인증도 monitor 경로로 분리했습니다.
- 외부 API usage telemetry DB 기록을 전용 2-thread executor로 분리해 DART/뉴스 대량 호출이 FastAPI 공용 worker를 고갈시키지 않도록 했습니다.
- 진단 전송 endpoint 자체의 오류는 다시 진단 전송하지 않아 recursive/duplicate TXT 생성을 막습니다.

## 동기화 진단 로그 일괄 다운로드
- 관리자 진단 패널에 `전체 ZIP 다운로드`를 추가했습니다.
- `/api/admin/sync-error-logs/download-all?limit=250`에서 최근 로그를 ZIP으로 묶습니다.
- ZIP 생성은 monitor executor에서 수행해 이벤트 루프를 막지 않습니다.

## OpenDART 사업분류 후반 오류 복구
- 기업개황 1차 대량 조회의 일시 오류는 곧바로 최종 실패로 집계하지 않고 `재시도 대기`로 분리합니다.
- 1차 전체 처리가 끝난 뒤 저속 순차 재확인을 수행합니다.
- OpenDART 비정상 status를 `None`으로 숨기지 않고 status/message를 예외로 노출하여 재시도 판단이 가능하도록 했습니다.
- timeout/연결지연/요청한도 같은 일시 공급사 오류는 저속 재확인 후에도 남으면 `다음회차 보강`으로 보류하며, 코드/DB/비일시 오류만 `확인 필요` 대상으로 집계합니다.

## 프론트 오류 중복 억제
- `/sync-error-logs` 자체 실패는 interceptor 진단 대상으로 삼지 않아 진단 시스템이 자기 오류를 다시 TXT로 생성하는 재귀를 막습니다.
- 목록/개별/일괄 다운로드 실패는 화면 메시지만 표시합니다.
