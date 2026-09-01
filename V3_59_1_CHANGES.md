# StockLog v3.59.1 - Social Login Visibility / Google OAuth Fix

- 관리자 `로그인 화면에 노출` 체크를 소셜 로그인 노출의 실제 기준으로 사용하도록 수정했습니다.
- 기존에는 `configured + enabled + last_test_status=success`가 모두 참이어야 로그인 버튼이 보여 테스트 상태가 어긋나면 체크를 켜도 숨겨질 수 있었습니다.
- OAuth 연결 테스트 결과는 진단 정보로 유지하되 실제 로그인 노출/시작을 가로막는 숨은 스위치로 사용하지 않습니다.
- `/api/auth/social/providers` 응답에 `Cache-Control: no-store`를 적용해 관리자 변경 직후 오래된 노출 상태가 남지 않도록 했습니다.
- 로그인 페이지가 다시 활성화되거나 포커스를 받을 때 소셜 로그인 제공자 상태를 다시 조회합니다.
- `/?admin=1` 관리자 진입 후 로그아웃하면 `admin=1`을 URL에서 제거하여 공개 간편 로그인 화면으로 정상 복귀합니다.
- 로그인 화면의 `별도 아이디/비밀번호가 필요하지 않습니다.` 안내 블록을 제거했습니다.
- Google OAuth의 기존 신규가입/기존회원 로그인 흐름(scope openid/email/profile, token exchange, userinfo, SocialAccount 매핑)은 유지했습니다.
- 신규 소셜 회원가입은 OAuth 인증 완료 후 세션을 60분으로 연장해 기본정보 입력 + 30문항 투자성향 검사 도중 10분 만료가 발생하지 않도록 했습니다.
