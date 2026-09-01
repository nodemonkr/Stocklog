# StockLog v3.59

## Google 로그인
- Google OAuth 2.0 / OpenID Connect 추가
- 관리자 소셜 로그인 카드에서 Client ID / Secret / Redirect URI 암호화 저장
- 실제 OAuth 왕복 연결 테스트 후에만 로그인 버튼 노출
- scopes: `openid email profile`

## Social-only signup
- 신규 일반 회원의 아이디/비밀번호 직접 회원가입 제거
- Kakao / Naver / Google 인증 후에만 신규 가입 가능
- 이름 / 성별 / 출생연도 / 휴대폰 번호 수집
- 만 14세 이상 확인
- 서비스 이용약관 / 개인정보 수집·이용 필수 동의
- 동의 버전과 동의 시각을 `user_consents`에 보관
- 기존 투자성향 30문항 가입 절차 유지

## 관리자 계정
- 일반 로그인 화면은 간편 로그인만 표시
- 기존 로컬 관리자 비상 로그인은 `/?admin=1`에서만 노출
- 공개 UI에서는 로컬 로그인 폼을 노출하지 않으며, 기존 로컬 계정 호환용 `/api/auth/login`은 유지합니다.
- 비상 관리자 로그인은 별도 `/api/auth/admin-login`을 사용합니다.
- OAuth 공급자 장애/설정 오류 시 관리자 접근 수단을 유지
