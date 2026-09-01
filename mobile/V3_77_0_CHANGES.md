> **SUPERSEDED BY `V3_78_0_CHANGES.md` (2026-08-27).** 3.77.0은 네이티브 전환의 실제 설치 확인 기준선이며, 현재 기능 완성도/검증 기준은 3.78.0 문서를 우선합니다.

# StockLog Mobile V3.77.0 — Native App Working Baseline

> **상태: 실제 Android Preview APK에서 앱 구동 확인된 기준선**
>
> 이 문서는 StockLog 모바일 앱을 수정하거나 다시 빌드할 때 **가장 먼저 읽어야 하는 기준 문서**입니다.
> 2026-08-26~27에 WebView 기반 앱을 폐기하고 React Native 네이티브 앱으로 다시 구성하면서 발생했던 빌드/타입/연결 오류와 최종 안정화 방법을 기록합니다.
>
> 앞으로 작업할 때는 이 문서의 구조와 제약을 유지한 상태에서 변경하세요. 특별한 이유 없이 Expo SDK, React Native, EAS project 연결, API 포트, 앱 scheme/package, 네이티브 스타일 규칙을 임의 변경하지 않습니다.

---

## 1. 현재 정상 동작 구조

StockLog 모바일은 **WebView 앱이 아닙니다.**

```text
StockLog Android App
  └─ React Native / Expo Router 네이티브 UI
       ├─ SecureStore 인증 토큰
       ├─ HTTP API
       └─ WebSocket
              ↓
      FastAPI Backend :8100
              ↓
        MySQL / Kiwoom / AI
```

웹 프론트(Vite)는 모바일 UI 렌더링에 사용하지 않습니다.

- 모바일 UI: `mobile/src/`
- 백엔드: `backend/`
- 웹 프론트: `frontend/`
- 모바일이 웹 HTML/CSS/JS를 내장해서 실행하는 구조는 **폐기됨**

### 절대 되돌리지 말 것

아래 구조는 화면 잘림/반응형 문제 때문에 폐기했습니다.

- `react-native-webview`
- `stocklog-bundle.ts`
- `STOCKLOG_WEB_HTML`
- `sync:web`
- Vite production bundle을 앱 HTML로 내장하는 방식

웹 기능을 모바일에 추가할 때는 **같은 FastAPI API를 사용하되 React Native 화면을 별도로 구현**합니다.

---

## 2. 서버 포트 역할 — 중요

실제 FastAPI/Uvicorn 백엔드 포트는 **8100**입니다.

```text
8100 = FastAPI 실제 백엔드
5174 = Vite 웹 프론트
3000 = 외부 웹 진입 포트 → 5174 → /api,/ws 프록시 → 8100
```

모바일 기본 연결:

```text
http://somensomes.iptime.org:8100
```

모바일 fallback:

```text
http://somensomes.iptime.org:3000
```

### 규칙

1. 앱은 **8100 직접 연결을 우선**합니다.
2. 3000은 백엔드가 아닙니다. 기존 웹 프록시 경로입니다.
3. 외부 LTE/5G에서 8100 직접 연결을 쓰려면 공유기/방화벽에 TCP 8100 포트포워딩이 필요합니다.
4. 8100 직접 접근이 막힐 때만 3000 fallback을 사용합니다.
5. 장기적으로 HTTPS를 적용하면 HTTP cleartext 예외를 제거할 수 있습니다.

---

## 3. 현재 고정된 Expo / React Native 조합

`mobile/package.json` 기준 정상 동작 확인 조합:

- Mobile app version: **3.77.0**
- Expo SDK: **57.0.16**
- React: **19.2.3**
- React Native: **0.86.2**
- Expo Router: **57.0.16**
- react-native-gesture-handler: **2.32.0**
- TypeScript: **6.0.3**
- expo-secure-store: **57.0.1**
- expo-build-properties: **57.0.13**

### 의존성 변경 규칙

Expo 네이티브 패키지는 임의로 `npm install package@latest` 하지 않습니다.

가능하면:

```bash
npx expo install <package>
```

을 사용해 현재 Expo SDK와 호환되는 버전을 설치합니다.

의존성 변경 후에는 반드시:

```bash
npm install --package-lock=true --no-audit --no-fund
npm run check:styles
npm run typecheck
npx expo-doctor@latest
```

를 통과시킵니다.

`npm audit fix --force`는 Expo/React Native 버전 조합을 깨뜨릴 수 있으므로 빌드 오류 해결 목적으로 사용하지 않습니다.

---

## 4. EAS 프로젝트 연결 — 임의 변경 금지

`mobile/app.json`의 연결 정보:

```text
expo.name       = StockLog
expo.slug       = mobile
expo.owner      = nodemonkr
android.package = com.nodemonkr.mobile
ios.bundleId    = com.nodemonkr.mobile
scheme          = stocklog
EAS projectId   = afd959bb-dee8-42bd-89f1-026104166cad
```

### 과거 오류

`projectId`가 가리키는 Expo 프로젝트 slug는 `mobile`인데 로컬 slug를 `stocklog-mobile`로 바꾸면 다음 오류가 납니다.

```text
Slug for project identified by extra.eas.projectId (mobile)
does not match the slug field (stocklog-mobile)
```

따라서 **slug는 `mobile` 유지**가 기준입니다.

---

## 5. EAS 빌드 프로필

`mobile/eas.json`:

### development

- `developmentClient: true`
- Metro/Development Build 테스트용
- 앱 실행 시 Development Client 화면이 나올 수 있음
- 실제 설치용 최종 테스트 앱으로 사용하지 않음

### preview

- `distribution: internal`
- Android `buildType: apk`
- **실제 휴대폰 설치 확인용 기본 프로필**
- 설치 후 Expo Go/Metro/QR 필요 없음

### production

- 스토어 배포 지향
- `autoIncrement: true`

일반적인 APK 테스트 빌드는:

```bash
./restart-mobile.sh preview
```

을 사용합니다.

---

## 6. `restart-mobile.sh`가 정상 기준

프로젝트 루트에서:

```bash
./restart-mobile.sh preview
```

를 실행하는 것을 기본 빌드 절차로 사용합니다.

현재 스크립트 흐름:

```text
1. 모바일 API/EAS 환경 동기화
2. 백엔드 + 웹 서비스 재시작
3. FastAPI :8100 /health 확인
4. 모바일 npm 의존성 + package-lock 동기화
5. React Native 스타일 사전검사
6. TypeScript tsc --noEmit
7. expo-doctor
8. expo config 검사
9. 모바일 필수 FastAPI route 감사
10. EAS Cloud preview APK build
```

### 옵션

```bash
./restart-mobile.sh preview --skip-servers
./restart-mobile.sh preview --skip-build
```

- `--skip-servers`: 서버 재시작 생략
- `--skip-build`: EAS 빌드 없이 로컬 검증까지만 수행

### ADB / Android Studio

현재 빌드는 EAS Cloud에서 수행하므로 서버 PC에 Android Studio나 adb가 없어도 됩니다.

과거 `spawn adb ENOENT`는 빌드 자체가 아니라 로컬 설치/실행 단계에서 adb가 없어서 발생했습니다.
Preview APK는 EAS 빌드 페이지에서 휴대폰에 직접 다운로드해 설치합니다.

---

## 7. Git 없이 EAS 빌드하는 현재 방식

현재 루트 `restart-mobile.sh`는:

```bash
export EAS_NO_VCS=1
```

을 사용합니다.

따라서 `/home/conda/Stocklog/mobile`을 별도 Git repository로 `git init`할 필요가 없습니다.

특별히 VCS 기반 EAS workflow로 변경할 이유가 없다면 이 방식을 유지합니다.

---

## 8. 인증 저장 방식

WebView 시절의 `localStorage`를 사용하지 않습니다.

현재 모바일 인증 토큰은 **Expo SecureStore**에 저장합니다.

소셜 로그인 앱 복귀 scheme:

```text
stocklog://auth
```

백엔드 환경에는:

```text
STOCKLOG_MOBILE_RETURN_URL=stocklog://auth
```

가 유지되어야 합니다.

Google/Kakao/Naver 인증은 시스템 브라우저를 사용한 뒤 앱 딥링크로 복귀하는 구조입니다.

---

## 9. HTTP 연결 관련 네이티브 설정

현재 API가 HTTP이므로 Android/iOS에 제한적인 예외 설정이 존재합니다.

Android:

```text
expo-build-properties
android.usesCleartextTraffic = true
```

iOS:

```text
NSAppTransportSecurity
somensomes.iptime.org HTTP exception
```

서버가 HTTPS로 이전되기 전까지 임의 제거하지 않습니다.

---

## 10. React Native 스타일 규칙 — 매우 중요

### 지원하지 않는 fontWeight를 사용하지 말 것

과거 다음 값을 사용해 TypeScript 오류가 **257개까지 연쇄 발생**했습니다.

```text
650
750
850
950
```

React Native에서 현재 사용하는 안전한 값:

```text
100, 200, 300, 400, 500, 600, 700, 800, 900
normal, bold
```

기존 수정 매핑:

```text
650 → 600
750 → 700
850 → 800
950 → 900
```

왜 큰 오류로 번졌는가:

비정상 `fontWeight` 하나가 `StyleSheet.create()`의 `NamedStyles` 타입을 깨뜨리면 해당 스타일 객체가 `ViewStyle | TextStyle | ImageStyle`로 넓게 추론되어 정상 `<View>`, `<Text>`, `<Pressable>`, `<TextInput>`까지 수십~수백 개의 가짜 오류를 발생시킵니다.

현재 예방 검사:

```bash
npm run check:styles
```

파일:

```text
mobile/scripts/check-native-styles.mjs
```

이 검사는 잘못된 fontWeight와 WebView-era runtime reference를 사전에 차단합니다.

---

## 11. TypeScript `noImplicitAny` 주의

`data: any`에서 파생된 배열의 `.map()`은 콜백 인덱스를 자동으로 `number`로 추론하지 못할 수 있습니다.

잘못된 예:

```tsx
items.map((x: any, i) => ...)
```

현재 안전한 형태:

```tsx
items.map((x: any, i: number) => ...)
```

특히 `mobile/src/app/stock/[code].tsx`에서 이 문제로 마지막 3개의 TS7006 오류가 발생했고 수정했습니다.

새 화면을 추가할 때도 `any` 기반 데이터의 `map/filter/reduce` 콜백 타입을 명시적으로 확인합니다.

---

## 12. package-lock 동기화 규칙

과거 `package.json`에 패키지를 추가하고 `package-lock.json`을 갱신하지 않아 다음 오류가 났습니다.

```text
npm ci can only install packages when package.json and package-lock.json are in sync
```

현재 `restart-mobile.sh`는 의도적으로:

```bash
npm install --package-lock=true --no-audit --no-fund
```

을 사용하여 모바일 dependency 변경 시 lockfile을 같이 복구합니다.

안정된 lockfile을 CI에서 고정하고 싶을 때만 `npm ci`로 전환합니다. 그 경우 먼저 package/lock 일치 여부를 확인해야 합니다.

---

## 13. 현재 네이티브 구현 기능

### 일반 사용자

- 로그인 / 로그아웃 / 로그인 유지
- 회원가입 + 30문항 투자성향 검사
- Google / Kakao / Naver 로그인
- 홈 / 시장 현황 / 자산 요약
- 종목 검색
- 종목 상세
  - 가격
  - 추세 차트
  - 핵심 지표
  - 테마
  - 최근 재무
  - 수급
  - 뉴스/리포트/공시
  - AI 분석 실행/상태/결과
- 스마트 분석
- 인기 테마 / GBOT 테마 요약
- 수급 분석
- 키움 모의투자 연결
- 포트폴리오 / 보유종목 / 최근 주문
- 시장가·지정가 매수/매도
- 가격감시 예약주문 등록/목록/취소
- GBOT 자동매매 상태/시작/중지/1회 실행
- 자동매매 안전한도/운영 설정
- 자동매매 보유종목/주문 이력
- 투자성향 조회/재검사

### 관리자

- 운영 현황
- 회원 검색/등급 변경/삭제
- Naver/OpenDART/Gemini 설정 및 테스트
- Google/Kakao/Naver OAuth 설정/테스트
- 회원등급별 기능 권한
- 자동 새로고침 정책
- 전체 동기화 일정
- 통합 동기화 실행/중지

---

## 14. 아직 별도 모바일 UI가 없는 저빈도 기능

백엔드는 유지하지만 전용 네이티브 UI는 아직 없는 항목:

1. 관리자 진단 로그 ZIP/개별 파일 다운로드
2. 회원 한 명의 전체 감사/진단 상세 패널
3. 테마 DB repair / normalize / 개별 theme diagnostic
4. 종류별 모든 개별 동기화 시작/중지 세부 패널
5. 종목 호가창 전용 화면
6. 기존 예약주문 편집 — 현재 취소 후 재등록
7. GBOT 판단 감사 로그 전체 evidence / guard context

일반 사용자 핵심 흐름과 분리된 운영/진단 기능이므로 후순위입니다.

---

## 15. 새 기능 추가 시 권장 절차

### 백엔드 API가 이미 있는 경우

1. 기존 웹 UI를 복사하지 않는다.
2. 백엔드 route/request/response를 확인한다.
3. 모바일 React Native 화면을 별도로 설계한다.
4. 공통 API client를 통해 FastAPI에 연결한다.
5. 작은 화면에서 표 대신 카드/리스트/상세 화면을 사용한다.
6. TypeScript 타입을 가능하면 `any` 대신 interface/type으로 정의한다.
7. 아래 검사를 모두 통과시킨다.

```bash
cd mobile
npm run check:styles
npm run typecheck
npx expo-doctor@latest
npx expo config --type public >/dev/null
```

8. 최종적으로:

```bash
cd ..
./restart-mobile.sh preview
```

### 백엔드 API가 없는 경우

웹 프론트 로직을 모바일에서 복제하지 말고 먼저 FastAPI에 공통 API를 만든 뒤 웹/모바일이 공유하도록 합니다.

---

## 16. 문제 발생 시 진단 순서

빌드 오류가 나오면 무작정 패키지를 업그레이드하지 말고 아래 순서로 확인합니다.

```text
1. npm run check:styles
2. npm run typecheck
3. npx expo-doctor@latest
4. npx expo config --type public
5. app.json slug/projectId/package 확인
6. eas.json profile/env 확인
7. http://127.0.0.1:8100/health 확인
8. 모바일 API URL 8100 / fallback 3000 확인
9. package.json ↔ package-lock.json 동기화 확인
10. 네이티브 package 변경 여부 확인 → 변경했다면 APK 재빌드
```

### 네이티브 dependency가 바뀌었을 때

JS/TS 코드만 바뀐 경우와 달리 Expo native module을 추가/변경했다면 기존 APK의 네이티브 바이너리와 JS가 달라질 수 있습니다.
반드시 새 preview APK를 다시 빌드합니다.

---

## 17. 이 기준선에서 확인된 과거 주요 오류와 원인

### `Unable to load script / index.android.bundle`

- Development Build에서 Metro 연결이 없거나 dev-client/native binary가 맞지 않을 때 발생
- standalone preview APK 용도와 development client 용도를 구분해야 함

### `react-native-gesture-handler ... undefined is not a function`

- JS dependency와 설치된 APK의 native module 버전 mismatch 가능성
- SDK 호환 버전 사용 + APK 재빌드 필요

### `npm ci ... package-lock ... not in sync`

- package.json만 변경하고 lockfile 미갱신
- 현재는 `npm install --package-lock=true`로 처리

### `Failed to resolve plugin for module expo-router`

- `node_modules`가 없거나 의존성 설치가 불완전
- npm install 후 Expo config/doctor 확인

### EAS slug mismatch

- `slug=stocklog-mobile`로 잘못 변경해서 발생
- 현재 `slug=mobile`이 정상

### `spawn adb ENOENT`

- 로컬 Android SDK/adb가 없는 환경에서 자동 설치/실행 시도
- EAS Cloud APK 빌드 자체에는 adb 필요 없음

### WebView 화면 잘림

- 웹 데스크톱 UI를 모바일 WebView에 그대로 내장한 구조적 문제
- 현재는 WebView 제거 후 React Native 네이티브 UI로 재구축 완료

### TypeScript 257 errors

- 비표준 fontWeight (`650`,`750`,`850`,`950`)가 StyleSheet 타입 전체를 오염시킴
- 현재 100단위 지원값으로 정규화 + 사전검사 추가

### TS7006 implicit any 3 errors

- `stock/[code].tsx`의 `map((x:any,i)=>...)`
- `i:number` 명시로 해결

---

## 18. 앞으로의 유지 원칙

**이 앱은 현재 실제 구동 확인된 상태입니다.**

따라서 새 작업을 시작할 때는 먼저 다음을 보존합니다.

- WebView로 되돌리지 않기
- FastAPI 8100 직접 연결 우선 유지
- 3000은 fallback 프록시로만 취급
- Expo SDK 57 / RN 0.86 계열 호환성 유지
- EAS slug `mobile`, 기존 projectId 유지
- Android package / iOS bundleId `com.nodemonkr.mobile` 유지
- `stocklog://auth` 딥링크 유지
- SecureStore 인증 유지
- 지원되는 fontWeight만 사용
- strict TypeScript 오류를 우회하지 말고 수정
- `restart-mobile.sh` 검증을 통과한 뒤 빌드
- `npm audit fix --force`로 빌드 문제를 해결하려 하지 않기
- native dependency 변경 시 preview APK 재빌드

이 문서를 현재 모바일 앱의 **known-good baseline**으로 취급합니다.
