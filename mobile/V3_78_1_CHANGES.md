# StockLog Mobile V3.78.1 — Expo SDK 57 Dependency Validation Fix

> **현재 모바일 최우선 기준 문서 — 2026-08-28**
>
> 기능 기준선은 `V3_78_0_CHANGES.md`의 웹 기능 parity 내용을 그대로 계승합니다.
> 실제 StockLog 서버에서 `./restart-mobile.sh preview`를 실행한 결과 Expo Doctor가 React Native 패치 버전 불일치를 정확히 검출했고, V3.78.1에서 이를 수정했습니다.

## 1. 이번 수정의 원인

실제 서버 검증 결과:

```text
expo-doctor: 20/21 checks passed
react-native expected 0.86.3 / found 0.86.2
```

따라서 이 문제는 서버/포트/백엔드 연결 문제가 아니라 `mobile/package.json`의 React Native 패치 버전이 Expo SDK 57 요구 버전보다 1단계 낮았던 문제입니다.

`uuid@7.0.3` deprecated 메시지는 npm 경고이며 이번 Expo Doctor 실패 원인이 아닙니다.

## 2. 고정 패키지 기준

- App: **3.78.1**
- Expo: `~57.0.16`
- React: `19.2.3`
- React Native: **`0.86.3`**
- Expo Router: `~57.0.16`
- TypeScript: `~6.0.3`
- `expo-secure-store`: `~57.0.1`
- `expo-file-system`: `~57.0.5`
- `expo-sharing`: `~57.0.15`

Expo SDK 버전 정합성은 임의 추측보다 실제 `expo-doctor` 결과를 우선합니다.

## 3. restart-mobile.sh 개선

검증 단계의 Expo Doctor 호출을 다음처럼 무인 실행 가능하게 변경했습니다.

```bash
npx --yes expo-doctor@latest
```

따라서 새 서버/클린 환경에서 expo-doctor 패키지가 아직 없어도 `Ok to proceed? (y)` 입력을 요구하지 않습니다.

의존성 동기화는 기존처럼:

```bash
npm install --package-lock=true --no-audit --no-fund
```

을 사용합니다. 패키지 압축에는 `node_modules`와 생성된 `package-lock.json`을 기준 산출물로 강제 포함하지 않으며, 실제 서버에서 package.json 기준으로 동기화합니다.

## 4. 네트워크/포트 기준 — 변경 없음

- FastAPI/Uvicorn: `8100`
- Vite 내부 웹: `5174`
- 기존 외부 웹: `3000` → 공유기에서 `5174` 전달
- 모바일 1차 API: `http://somensomes.iptime.org:8100`
- 모바일 fallback: `http://somensomes.iptime.org:3000`의 `/api`, `/ws` 프록시
- 외부 모바일에서 8100 직접 연결 사용 시 TCP `8100 -> 서버:8100` 포트포워딩 필요

이 포트 역할은 임의 변경하지 않습니다.

## 5. 기능 기준선

V3.78.0에서 반영한 아래 네이티브 기능은 그대로 유지됩니다.

- WebView 금지 / React Native 네이티브 UI
- 인증·회원가입·소셜 OAuth
- 투자성향 검사/이어하기/상세 결과
- 스마트 분석/점수 상세/인기테마/수급 분석
- 종목 상세/차트/뉴스/리포트/공시/AI 분석
- 포트폴리오/호가/주문/미체결/체결/예약주문
- GBOT 자동매매 전체 설정·판단/주문 감사정보
- 관리자 회원/API/OAuth/동기화/테마/진단로그
- 8100 직접 연결 + 3000 fallback

기능 세부 목록은 `V3_78_0_CHANGES.md`를 함께 참고합니다.

## 6. 다음 빌드의 통과 기준

루트에서:

```bash
./restart-mobile.sh preview
```

정상 기준:

1. Backend health 8100 PASS
2. npm dependency install/sync PASS
3. `check:styles` PASS
4. `tsc --noEmit` PASS
5. Expo Doctor **21/21 PASS**
6. Expo public config PASS
7. Native backend route audit PASS
8. EAS preview Android build 시작 및 완료

빌드만 생략해 검증하려면:

```bash
./restart-mobile.sh preview --skip-build
```

## 7. 다음 작업자가 지킬 것

1. 모바일 패키지 변경 시 Expo Doctor가 제시하는 SDK 호환 버전을 우선합니다.
2. React Native를 다시 `0.86.2`로 내리지 않습니다.
3. `V3_78_1_CHANGES.md`를 모바일 작업의 첫 번째 기준 문서로 읽습니다.
4. WebView로 회귀하지 않습니다.
5. Expo owner/slug/projectId/package/scheme 및 8100/3000 연결 구조를 임의 변경하지 않습니다.
6. 최종본이라 부르기 전에 실제 서버의 `restart-mobile.sh preview --skip-build` 또는 전체 preview 빌드 로그를 확인합니다.
