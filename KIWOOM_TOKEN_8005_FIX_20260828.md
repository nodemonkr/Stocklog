# StockLog Kiwoom 8005 Token Recovery Hotfix — 2026-08-28

## 증상

키움 REST 호출에서 다음 오류가 발생하고 수급/시세/계좌/테마 등 키움 기반 데이터가 중단됨.

`RuntimeError: 연결 서비스Error: [3](인증에 실패했습니다[8005:Token이 유효하지 않습니다])`

## 원인

기존 `backend/app/kiwoom.py`는 HTTP 401일 때만 토큰을 강제 재발급했습니다.
하지만 키움 REST 실응답은 무효/만료 토큰에 HTTP 200을 반환하면서 JSON 본문에
`return_code=3`, `return_msg=...8005:Token이 유효하지 않습니다...` 형태로 오류를 줄 수 있습니다.

또한 기존 코드는 `expires_dt`를 저장만 하고 캐시 토큰의 실제 만료 판단에 사용하지 않았습니다.
따라서 장시간 실행 시 24시간이 지난 토큰 문자열을 계속 재사용할 수 있었습니다.

## 수정 사항

- 키움 `expires_dt` (`YYYYMMDDHHMMSS` 포함) 파싱
- 토큰 만료 5분 전 선제 갱신
- `8005`/invalid-token 본문 응답 감지
- 인증 실패 시 새 토큰 발급 후 원래 REST 요청 정확히 1회 재시도
- 동시에 여러 요청이 같은 만료 토큰에서 실패해도 토큰 발급은 single-flight 처리
- REST/계좌동기화/테마/수급/체결 폴링/관리자 전체동기화의 토큰 유효성 정책 통일
- 포트폴리오 실시간 WebSocket이 별도 OAuth client를 만들지 않고 사용자별 REST client/token을 공유
- 관리자 진단 runtime_status에 토큰 값 자체는 노출하지 않고 `token_expires_dt`, `token_valid_seconds`만 제공
- 회귀 테스트 `backend/tests/test_kiwoom_token_refresh.py` 추가

## 즉시 적용 후 확인

프로젝트 최상단에서:

```bash
./restart-all.sh
```

이후 웹/앱에서 키움 연결 테스트 또는 수급 조회를 다시 실행합니다.

정상이라면 8005가 발생하더라도 서버가 내부적으로 토큰을 한 번 갱신한 뒤 원 요청을 재시도합니다.
사용자가 App Key/Secret Key를 매번 다시 입력할 필요는 없습니다.

## 계속 실패할 때 확인할 별도 오류

- 8001/8002: App Key/Secret Key 자체 오류
- 8010: 토큰 발급 IP와 API 요청 IP 불일치
- 8030/8031: 실전/모의 환경 불일치
- 8040/8050: 단말기 인증 문제

현재 StockLog UI는 모의투자 연결을 사용하므로 키움 모의 REST/WebSocket 도메인을 사용합니다.
