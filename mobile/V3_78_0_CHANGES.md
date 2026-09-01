> **SUPERSEDED BY `V3_78_1_CHANGES.md` (2026-08-28).** Expo SDK 57 doctor 실검증에서 React Native 0.86.3 요구가 확인되어 3.78.1에서 수정했습니다. 새 작업은 3.78.1 문서를 우선합니다.

# StockLog Mobile V3.78.0 — Web Feature Parity Native Baseline

> **현재 모바일 작업 기준 문서 — 2026-08-27**
>
> V3.77.0의 실제 Android Preview APK 구동 확인 기준선을 그대로 유지하면서, `frontend/`에서 실제 사용하는 기능/API를 `backend/`와 대조해 React Native `mobile/`에 보강한 버전입니다.
> 앞으로 모바일 기능 수정 또는 재빌드 전에는 이 문서와 `V3_77_0_CHANGES.md`의 Expo/EAS/HTTP/네이티브 제약을 함께 읽습니다.

## 1. 절대 유지할 구조

- WebView 사용 금지. 모바일은 `mobile/src/` React Native 네이티브 UI입니다.
- 웹 HTML/CSS/Vite bundle을 앱에 내장하지 않습니다.
- FastAPI 실제 백엔드 우선 주소: `http://somensomes.iptime.org:8100`
- fallback: `http://somensomes.iptime.org:3000`
- Expo owner/slug: `nodemonkr` / `mobile`
- Android/iOS id: `com.nodemonkr.mobile`
- scheme: `stocklog`
- EAS projectId: `afd959bb-dee8-42bd-89f1-026104166cad`
- `EAS_NO_VCS=1` 클라우드 빌드 흐름 유지
- Android HTTP cleartext / iOS `somensomes.iptime.org` ATS 예외는 HTTPS 전환 전까지 유지

## 2. 고정 패키지 조합

- App: **3.78.0**
- Expo: `~57.0.16`
- React: `19.2.3`
- React Native: `0.86.2` *(3.78.0 패키징 당시 값; Expo Doctor 실검증 결과 SDK 57 요구값은 0.86.3이며 3.78.1에서 수정)*
- Expo Router: `~57.0.16`
- TypeScript: `~6.0.3`
- `expo-secure-store`: `~57.0.1`
- `expo-file-system`: `~57.0.5`
- `expo-sharing`: `~57.0.15`

진단 로그 ZIP의 기기 저장/공유를 위해 FileSystem legacy API와 Sharing을 사용합니다. 임의 최신 버전으로 올리지 말고 SDK 57 권장 버전을 유지합니다.

## 3. V3.78.0에서 웹 기준으로 보강된 사용자 기능

### 인증/계정
- 일반 로그인 / 관리자 전용 로그인
- 회원가입 아이디 중복 확인, 비밀번호 확인, 만 14세 확인, 필수동의
- Google/Kakao/Naver 시스템 브라우저 OAuth + `stocklog://auth` 복귀 구조 유지
- 회원 기본정보(이름/성별/출생연도/마스킹 휴대폰), 등급, AI 일 사용량 표시
- 멤버십 기능 권한에 따른 잠금 UI

### 투자성향
- 웹과 같은 30문항 데이터 사용
- SecureStore 임시저장 및 검사 이어하기
- 5축 코드/점수 비율/강점/주의점 상세
- 48가지 조합 브라우저
- 결과 서버 저장 및 재검사

### 종목 분석
- 스마트 분석: 검색, 전략, 대표/세부테마, 전체시장 권한, 시총/PER/PBR/ROE/배당/커버리지/점수/수급/심리 고급필터, 페이지 크기
- 스마트 점수 상세: 항목별 StockLog 평가, 투자성향 적합, 근거
- 인기테마 분석 및 GBOT 요약
- 수급 분석: 기간/시장/투자자/정렬/신호, 기관 세부주체, 최근 주간 데이터
- 종목 상세: 실제 차트, 재무, 테마/사업분류, 저장 수급, 뉴스/리포트/공시 필터·페이지, 공개정보 강제갱신
- AI 종목 분석: 일 사용량 확인, 신규/재분석 동의, 진행상태, 결과·근거·위험요인

### 모의투자/포트폴리오
- 키움 연결 조회/저장/테스트
- 주문가능금액, 현재가, 5단계 호가, 매수가능수량
- 시장가/지정가 매수·매도, 25/50/75/100% 수량
- 주문 종목 실제 일봉 차트
- 보유종목 상세: `/chart/cached` 실제 저장 차트 + `/investor-flow` 오늘 투자자별 매수/매도
- 보유수량/평균단가/매입·평가금액/포트폴리오 비중
- 카테고리별 투자 비중
- 직접매수/GBOT 귀속 및 AI 체결사유 상세
- 미체결 / 체결 / 예약관리 구분
- 프리미엄 보유종목 AI 모멘텀 및 비권한 잠금 UI

### 예약주문
- 신규 등록 / 수정 / 취소
- 가격 이하/이상 조건
- 시장가/지정가
- 만료시각
- 현재가/최우선 매도/최우선 매수 가격 바로 적용
- 호가 5단계 및 수량 +/-

### GBOT 자동매매
- 종목선정, 시장/가격/시총/거래량/스마트점수/테마 범위
- 거래시간/판단주기/예산/종목당 한도/현금비율/최대종목/일 주문 제한
- 손절/익절, 직접매수 보유분 매도 허용
- 시작/중지/1회 판단
- 전체 판단/실제 주문 이력, 페이지, 개별삭제/정리
- AI 판단, 근거, 리스크, Guard, 주문 결과 상세

## 4. V3.78.0에서 보강된 관리자 기능

- 운영 현황 및 동기화 상태
- 회원 목록 + 회원 1명 상세 감사정보 + 멤버십 변경
- 외부 API 저장/테스트/활성·비활성/삭제/사용량
- Google/Kakao/Naver 소셜 OAuth 설정/테스트
- 회원등급별 기능 및 새로고침 정책
- 키움/DART/키움테마/시장테마/사업분류/수급 개별 동기화 시작·중지
- 8개 scope 선택 통합 동기화
  - `kiwoom`, `dart`, `kiwoom_themes`, `market_themes`, `classification`, `theme_engine`, `flow`, `smart_scores`
- 자동 동기화 시간 여러 개 + 동일 8개 scope 선택 + 수급 대상/기간 저장
- 테마 DB 상태/복구, 표준화, 커버리지, 종목 진단
- 동기화 오류 TXT 조회/공유 + 전체 ZIP 공유
- 모바일 관리자 동기화 API 실패도 `/api/admin/sync-error-logs/client-event`로 진단 기록(60초 중복 억제)

## 5. 검증 결과

이 패키징 시점에 수행한 검사:

- `backend/app` Python `compileall`: **PASS**
- `restart-mobile.sh`, `build-mobile.sh`, `restart-all.sh` bash syntax: **PASS**
- `mobile/package.json`, `app.json`, `eas.json` JSON parse: **PASS**
- `mobile/scripts/check-native-styles.mjs`: **PASS**
- WebView-era runtime 문자열/의존성 금지 검사: **PASS**
- 전체 TS/TSX TypeScript parser 문법 오류: **0**
- frontend/mobile API 문자열 대조: 앱이 직접 호출할 필요가 없는 OAuth provider callback 및 동적 템플릿 표기 차이를 제외하고 대응 확인
- 백엔드 route 존재 감사는 `restart-mobile.sh`에 확대 유지

### 현재 실행환경에서 직접 못 한 검사

패키징 환경에서 npm registry 의존성 설치가 타임아웃되어 `node_modules`를 만들 수 없었습니다. 따라서 아래 네트워크/의존성 기반 검사는 이 환경에서 성공 여부를 거짓으로 기록하지 않습니다.

- `npm run typecheck`의 **완전한 SDK 타입검사**
- `npx expo-doctor@latest`
- `npx expo config --type public`
- EAS Cloud 실제 APK 컴파일

대신 TSX 파서 검사로 문법 오류가 없음을 확인했고, SDK 57 문서 기준 `expo-file-system ~57.0.5`, `expo-sharing ~57.0.15`가 권장 조합임을 확인했습니다.

실제 StockLog 서버에서는 루트에서 아래 한 명령이 의존성 동기화 → 전체 타입검사 → expo-doctor → config → 필수 backend route 감사 → EAS preview APK 빌드까지 수행합니다.

```bash
./restart-mobile.sh preview
```

EAS 빌드만 생략하고 로컬 검증까지:

```bash
./restart-mobile.sh preview --skip-build
```

## 6. 다음 작업자가 반드시 지킬 것

1. 웹 기능을 모바일에 옮길 때 화면 이름만 흉내내지 말고 `frontend/src`의 실제 API 요청과 `backend/app/main.py` 응답 구조를 함께 대조합니다.
2. 응답의 `items`, `series`, `categories` 구조를 추측하지 않습니다.
3. 웹 화면을 WebView로 되돌리지 않습니다.
4. Expo/RN/EAS 식별값과 API 포트를 임의 변경하지 않습니다.
5. `fontWeight`는 100 단위 또는 `normal`/`bold`만 사용합니다.
6. 패키지 변경 후 `restart-mobile.sh preview --skip-build`를 최소 기준으로 통과시킵니다.
7. 설치 확인용 Android 결과물은 development client가 아니라 **preview APK**를 기본으로 사용합니다.
