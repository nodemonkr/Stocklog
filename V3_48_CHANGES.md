# StockLog v3.48 변경사항

## 카카오 · 네이버 소셜 로그인

- 기존 아이디/비밀번호 로그인과 회원가입은 그대로 유지합니다.
- 관리자에서 연결 테스트까지 성공한 제공자만 로그인/회원가입 화면에 노출됩니다.
- 신규 소셜 사용자는 `소셜 인증 → 투자성향 30문항 → 가입 완료` 순서로 진행합니다.
- 이미 연결된 소셜 사용자는 투자성향 검사를 다시 하지 않고 즉시 로그인합니다.
- 소셜 계정은 `provider + provider_user_id` 조합으로 식별하여 이메일만으로 기존 계정에 자동 연결하지 않습니다.
- 소셜 전용 StockLog 계정은 내부용 username을 자동 생성하고, 화면 표시 이름은 제공자가 전달한 닉네임을 사용합니다.

## 관리자 페이지 OAuth 설정

`.env`에 카카오/네이버 Client ID/Secret을 넣지 않습니다.

관리자 페이지의 **소셜 로그인** 영역에서 제공자별로 다음 값을 저장합니다.

### 카카오

- REST API Key
- Client Secret (카카오 개발자 설정에서 Client Secret 기능을 활성화한 경우 필수)
- Redirect URI
- 로그인 화면 노출 여부

기본 Redirect URI 예시:

`http(s)://StockLog접속주소/api/auth/social/kakao/callback`

### 네이버

- Client ID
- Client Secret
- Redirect URI(Callback URL)
- 로그인 화면 노출 여부

기본 Redirect URI 예시:

`http(s)://StockLog접속주소/api/auth/social/naver/callback`

## 실제 연결 테스트

관리자에서 **실제 연결 테스트**를 누르면 단순 HTTP 핑 테스트가 아니라 다음 OAuth 흐름을 수행합니다.

1. 카카오/네이버 인증 페이지 이동
2. Authorization Code 수신
3. 저장된 Client ID/Secret으로 Access Token 발급
4. Access Token으로 사용자 프로필 조회
5. 모든 단계가 성공해야 `연결 확인` 상태로 저장

연결 테스트를 통과한 제공자만 실제 로그인 화면에 표시됩니다.
Client ID/Secret/Redirect URI가 변경되면 기존 테스트 성공 상태는 자동으로 `테스트 필요`로 바뀝니다.
단순히 활성화/비활성화만 바꾼 경우에는 기존 성공 상태를 유지합니다.

## 보안

- Client ID와 Client Secret은 MySQL/SQLite의 `social_auth_provider_configs`에 암호화하여 저장합니다.
- 암호화에는 기존 StockLog 서버의 `JWT_SECRET` 기반 Fernet 키를 재사용합니다.
- Client Secret은 저장 후 API 응답이나 프론트엔드에 평문으로 다시 반환하지 않습니다.
- OAuth `state`는 고강도 랜덤 값으로 생성하고 `social_auth_sessions`에 10분 동안만 유지합니다.
- OAuth 완료 후 StockLog SPA에는 Access Token이 아니라 일회성 `social_session` 식별자만 전달합니다.
- 실제 StockLog JWT는 SPA가 일회성 세션을 서버와 교환한 뒤 발급합니다.
- 반환 URL은 로그인 요청을 시작한 브라우저 Origin/Referer와 비교하여 오픈 리다이렉트를 방지합니다.
- 관리자 연결 테스트는 테스트를 시작한 관리자 계정과 연결되어 있어 다른 계정이 결과를 조회할 수 없습니다.

## 신규 DB 테이블

- `social_auth_provider_configs`
  - 제공자별 암호화 Client ID/Secret, Redirect URI, 활성화 여부, 테스트 상태
- `social_accounts`
  - StockLog 사용자와 카카오/네이버 사용자 ID 연결
- `social_auth_sessions`
  - 단기 OAuth state, 가입/로그인/관리자 테스트 상태

기존 데이터베이스에 별도 수동 SQL을 실행할 필요 없이 백엔드 시작 시 SQLAlchemy `create_all()`에서 신규 테이블을 생성합니다.

## API

### 공개 인증

- `GET /api/auth/social/providers`
- `GET /api/auth/social/{provider}/start`
- `GET /api/auth/social/{provider}/callback`
- `POST /api/auth/social/exchange`
- `POST /api/auth/social/complete`

### 관리자

- `GET /api/admin/social-auth`
- `PUT /api/admin/social-auth/{provider}`
- `DELETE /api/admin/social-auth/{provider}`
- `GET /api/admin/social-auth/{provider}/test/start`
- `GET /api/admin/social-auth/test-result/{session_id}`

## 기존 정책 유지

- 일반회원 AI 하루 5회
- 테스트계정 AI 무제한
- 관리자 AI 무제한
- 테스트계정과 관리자 권한 분리
- 회원가입 투자성향 검사 30문항 필수
- 사용자별 AI 분석 열람 권한 구조
- 모의투자 v3.47 개선사항
