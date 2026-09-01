# StockLog v3.76.2 변경사항

## 핵심 수정: 수급 동기화 완료인데 특정 종목 데이터가 비어 있는 문제

- 수급 동기화의 수동 기본 범위를 기존 `시가총액 상위 800종목`에서 `전체 분석 대상 종목`으로 변경했습니다.
- 수동 수급 범위와 자동 동기화 수급 범위를 서로 다른 상태로 분리했습니다. 자동 동기화 설정이 상위 800종목이라고 해서 수동 전체 동기화까지 암묵적으로 800종목으로 축소되지 않습니다.
- 상위 300/800/1,500종목 방식은 속도가 필요할 때 그대로 사용할 수 있습니다.
- 상위 N 범위를 사용하더라도 종목 상세/프리미엄 AI 분석에서 DB 수급 데이터가 완전히 비어 있으면 관리자 Kiwoom 연결로 해당 종목만 자동 보충 수집합니다.
- 보충 수집은 당일 Kiwoom 응답이 비어 있을 때 최근 이전 평일까지 제한적으로 재시도합니다. 대량 벌크 동기화에는 이 추가 호출을 적용하지 않아 API 호출 폭증을 막습니다.
- 공급자 응답이 `no_data`인 종목을 더 이상 조용히 성공으로 취급하지 않습니다. 기존 캐시가 없으면 `데이터 없음` 경고로 집계합니다.
- 최근 수급 동기화의 전체 분석대상 수, 실제 선택 수, 선택 범위 밖 수, 저장 성공, 데이터 없음, 하드 실패 및 커버리지를 관리자 화면에서 확인할 수 있습니다.
- 수급 동기화 결과에 `partial` 상태를 추가해, 작업 루프는 끝났지만 일부 종목 데이터가 빠진 경우 단순 `완료`와 구분합니다.

## 동기화 진단 TXT

- `runtime/sync-error-logs/`에 동기화 실행별 날짜/시간 기반 TXT 진단 파일을 생성합니다.
- 관리자 페이지의 `동기화 진단 로그 / 백엔드·프론트 오류 TXT` 영역에서 최근 파일을 확인하고 바로 다운로드할 수 있습니다.
- 백엔드 진단 내용:
  - 동기화 종류/실행 ID/시작 시각/PID
  - 현재 단계, 종목코드, 종목명, 처리 위치, 요청 범위
  - 재시도 횟수, 공급자 결과 종류, DB 저장 결과
  - logger/module/function/line/message
  - Exception type/message 및 Python traceback
  - 수급 `no_data`, parse-empty, hard failure, cache rebuild 실패 등
- 프론트 진단 내용:
  - 관리자 동기화 API URL/method/status
  - X-Request-ID
  - API response body
  - 브라우저 URL
  - JavaScript error message/stack
  - window error 및 unhandled promise rejection
- 진단 파일은 최대 250개/90일 기준으로 자동 정리합니다.
- access token, bearer token, API key, client secret, password, JWT secret, 계좌번호는 저장 전에 자동 마스킹합니다.

## 안정성

- 동기화 진단 기록 자체가 실패해도 실제 동기화 작업을 중단시키지 않도록 best-effort 파일 기록 방식으로 구현했습니다.
- AI/종목 상세 수급 보충 수집 전 DB 연결을 반환해 Kiwoom 네트워크 대기 중 DB connection pool을 점유하지 않습니다.
- 프론트 진단 전송은 일반 API interceptor와 분리된 raw Axios 호출을 사용해 진단 오류가 다시 진단 요청을 만드는 재귀를 방지합니다.

## 검증

- Python 전체 `compileall` / AST 검사
- 주요 백엔드 테스트(SQLite override, AI 외부 의존 테스트 제외)
- 프론트 `App.jsx`, `api.js` TypeScript JSX parser 검사
- production bundle JavaScript `node --check`
- 셸 스크립트 `bash -n`
- 최종 tar.gz 무결성, 최상위 `Stocklog/` 구조 및 전체 일반 파일 실행권한 확인
