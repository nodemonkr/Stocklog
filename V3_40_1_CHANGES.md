# StockLog v3.40.1

## NAVER API HUB 전환

- 네이버 뉴스 검색 엔드포인트를 `https://naverapihub.apigw.ntruss.com/search/v1/news`로 변경했습니다.
- 인증 헤더를 NAVER API HUB 규격으로 변경했습니다.
  - `X-NCP-APIGW-API-KEY-ID`: Client ID
  - `X-NCP-APIGW-API-KEY`: Client Secret
- 관리자 페이지의 연결 테스트도 동일한 NAVER API HUB 규격을 사용합니다.
- 뉴스 수집기 역시 NAVER API HUB를 기본 네이버 뉴스 소스로 사용합니다.
- MySQL 암호화 저장, 마스킹, 사용량 모니터링, 절약/보호 로직, Google News fallback, OpenDART 연동은 그대로 유지됩니다.
- 기존 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 환경변수 이름은 하위 호환을 위해 유지하지만 값은 NAVER API HUB에서 발급된 Client ID/Client Secret이어야 합니다.

## 보안

관리자 API는 Secret 원문을 프론트로 다시 반환하지 않습니다. Client Secret을 외부에 노출했다면 NAVER API HUB 콘솔에서 재발급 후 새 값을 저장하세요.
