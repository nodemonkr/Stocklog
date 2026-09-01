# StockLog v3.76.4 변경사항

## 동기화 상태 조회 안정화
- `/api/admin/sync-overview`를 메인 DB 풀과 분리된 2-connection 전용 monitor pool로 이동했습니다.
- 7개 동기화 상태를 한 번의 상태 SELECT와 한 번의 스케줄 SELECT로 읽습니다.
- 상태 조회 과정에서는 orphan 상태 보정 같은 DB 쓰기를 수행하지 않습니다.
- monitor DB 조회가 일시 실패하면 마지막 정상 snapshot을 degraded 상태로 반환합니다.
- monitor 오류 TXT는 동일 장애가 지속될 때 60초에 한 번만 상세 기록합니다.

## 수급 동기화 연결 반환
- 수급 종목 한 건의 DB 저장을 완료할 때마다 commit하여 다음 Kiwoom HTTP 대기 전에 main DB connection을 반드시 반환합니다.
- 5종목 단위 commit 때문에 네트워크 대기 중 connection이 점유되던 경로를 제거했습니다.

## 관리자 프론트
- 관리자 진입 시 sync-overview를 먼저 읽고, 동기화 진행 중이면 무거운 정적 관리자 통계 요청을 뒤로 미룹니다.
- sync-overview polling 실패 시 1.8초 -> 3.6초 -> 7.2초 -> 최대 15초로 지수 backoff합니다.
- 동일 관리자 동기화 오류는 브라우저 탭 간 localStorage 기준 60초 중복 억제합니다.
- production bundle asset hash를 변경해 이전 JS 캐시 재사용을 방지했습니다.

## 배포
- restart-all.sh는 npm registry가 일시 불가하더라도 동봉된 검증 production dist로 배포를 계속할 수 있습니다.
- backend/frontend 표시 버전을 v3.76.4로 통일했습니다.
