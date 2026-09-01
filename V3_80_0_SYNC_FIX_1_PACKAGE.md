# StockLog v3.80.0 Sync Fix 1 — Full package

패키징일: 2026-08-30

이 전체 패키지는 Mobile 3.80.0 기준 전체 프로젝트에 `V3_80_0_SYNC_FIX_1.md`의 동기화 안정화 수정까지 합친 배포본입니다.

핵심 수정:
- 종목 분류 OpenDART 99% tail retry를 제한시간/개수 bounded retry로 변경
- OpenDART quota/rate-limit/연속 일시 실패 circuit breaker
- DART 재무 corpCode timeout 및 연속 장애 보호
- 키움 시세/지표/수급 연속 장애 보호와 다음 회차 보강 처리
- 관리자 전체동기화 heartbeat 및 정체 표시
- 관리자 화면 polling 완화 및 fill-events polling 억제

배포 전 기존 운영 DB와 `.env`를 별도 백업하는 것을 권장합니다.
적용 후 `./restart-all.sh`를 실행하고 frontend production build와 backend health를 확인하세요.
