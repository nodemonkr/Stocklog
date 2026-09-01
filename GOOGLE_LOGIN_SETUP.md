# StockLog v3.59 - Google 로그인 설정

StockLog의 Google 로그인은 일반 API Key가 아니라 **OAuth 2.0 Client ID + Client Secret**을 사용합니다.

## 1. Google Cloud 프로젝트 준비
1. Google Cloud Console에 로그인합니다.
2. 사용할 프로젝트를 선택하거나 새 프로젝트를 만듭니다.
3. 메뉴에서 **Google Auth Platform**으로 이동합니다.

## 2. Branding 구성
1. **Branding**에서 앱 이름을 `StockLog`로 입력합니다.
2. 사용자 지원 이메일을 선택합니다.
3. 운영 도메인은 `stocklog.cloud`를 사용합니다.
4. 실제 서비스 공개 전에는 홈페이지 / 개인정보처리방침 / 이용약관 URL을 준비하는 것을 권장합니다.

## 3. Audience 구성
1. 일반 Google 계정이 로그인할 서비스이므로 Audience는 **External**로 설정합니다.
2. 개발 중에는 Test users에 테스트할 Google 계정을 추가합니다.
3. 실제 공개 시에는 Google Auth Platform의 공개/검증 절차를 확인합니다.

## 4. Data Access / Scope
StockLog 로그인에는 최소 범위만 사용합니다.
- `openid`
- `email`
- `profile`

StockLog는 Google에서 성별 / 나이 / 휴대폰 번호를 요구하지 않습니다. 해당 정보는 StockLog 가입 화면에서 직접 입력받습니다.

## 5. OAuth Client 생성
1. **Google Auth Platform > Clients**로 이동합니다.
2. **Create Client**를 누릅니다.
3. Application type은 **Web application**을 선택합니다.
4. 이름 예시: `StockLog Web Login`
5. Authorized JavaScript origins에 다음 주소를 등록합니다.
   - `https://www.stocklog.cloud`
6. Authorized redirect URIs에 다음 주소를 정확히 등록합니다.
   - `https://www.stocklog.cloud/api/auth/social/google/callback`
7. 생성 후 **Client ID**와 **Client Secret**을 안전하게 보관합니다.

## 6. StockLog 관리자 페이지에 입력
관리자 > 소셜 로그인 > 구글 로그인에서 아래 값을 입력합니다.
- Client ID
- Client Secret
- Redirect URI: `https://www.stocklog.cloud/api/auth/social/google/callback`
- 로그인 화면에 노출: 활성화

저장 후 **실제 연결 테스트**를 실행하고 성공 상태가 된 경우에만 일반 로그인 화면에 Google 버튼이 노출됩니다.

## 7. 보안 주의
- Client Secret은 Git / 프론트엔드 / `.env` 공개 파일에 넣지 않습니다.
- StockLog는 관리자 페이지에서 받은 값을 DB에 암호화하여 저장합니다.
- Google Client Secret은 사용자 브라우저에 내려가지 않습니다.
- Redirect URI는 Google Console과 StockLog 관리자 화면에서 글자 하나까지 동일해야 합니다.

## 8. 가입 정보
신규 사용자는 Kakao / Naver / Google 중 하나로 인증한 후 다음 정보를 입력합니다.
- 이름
- 성별(응답하지 않음 선택 가능)
- 출생연도
- 휴대폰 번호
- 만 14세 이상 확인
- 서비스 이용약관 동의
- 개인정보 수집/이용 동의
- 투자성향 30문항

일반 아이디/비밀번호 회원가입 API는 v3.59부터 차단됩니다.


## v3.60 추가 프로필 권한

StockLog는 신규 회원가입 시 Google 계정에 등록된 프로필 값이 있으면 이를 자동으로 불러와 수정 불가 값으로 사용합니다.

요청 scope:
- `openid`
- `email`
- `profile`
- `https://www.googleapis.com/auth/user.gender.read`
- `https://www.googleapis.com/auth/user.birthday.read`
- `https://www.googleapis.com/auth/user.phonenumbers.read`

Google 계정에 성별, 생년월일, 휴대폰 번호가 등록되어 있지 않거나 사용자가 해당 권한을 제공하지 않은 경우 StockLog 회원가입 화면에서 누락된 항목만 직접 입력합니다. Google에서 수신한 값은 화면에서 잠기며 서버에서도 OAuth 세션 값을 우선 적용합니다.

추가 scope를 운영 환경에서 사용하는 경우 Google OAuth 동의 화면의 데이터 액세스 설정과 앱 검증 요구사항을 Google Cloud Console에서 확인하세요.
