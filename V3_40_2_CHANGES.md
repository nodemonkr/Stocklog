# StockLog v3.40.2

## 관리자 외부 API MySQL 500 오류 수정

- `external_api_credentials`, `api_usage_daily`, `api_usage_logs`가 이전 개발 버전의 부분 스키마로 이미 존재하는 경우에도 필요한 컬럼을 자동 보강합니다.
- SQLAlchemy `create_all()`이 기존 테이블 컬럼을 변경하지 않는 문제를 보완하는 idempotent 스키마 repair 로직을 추가했습니다.
- `/api/admin/external-apis` 조회 중 DB 오류가 발생하면 rollback → 스키마 repair → 1회 재시도합니다.
- `PUT /api/admin/external-apis/{provider}` 저장 중 DB 오류도 동일하게 자동 복구 후 재시도합니다.
- Client ID / Secret / DART key는 저장 전에 앞뒤 공백 및 줄바꿈을 제거합니다.
- 관리자용 `/api/admin/external-apis/diagnostics/schema` 진단 엔드포인트를 추가했습니다.
- NAVER API HUB 엔드포인트/헤더는 v3.40.1 규격을 그대로 유지합니다.

## NAVER API HUB

- URL: `https://naverapihub.apigw.ntruss.com/search/v1/news`
- Client ID header: `X-NCP-APIGW-API-KEY-ID`
- Client Secret header: `X-NCP-APIGW-API-KEY`
