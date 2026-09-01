> [!IMPORTANT]
> StockLog 모바일의 현재 **실제 동작 확인 기준선과 빌드/타입/API/EAS 규칙**은 [`V3_80_0_CHANGES.md`](./V3_80_0_CHANGES.md)를 먼저 확인하세요. WebView 폐기, FastAPI 8100 직접 연결, EAS preview APK, TypeScript 스타일 제약 등 과거 오류 재발 방지 기준이 정리되어 있습니다.

# StockLog Mobile Native

StockLog 모바일은 Expo SDK 57 / React Native / Expo Router 기반의 별도 네이티브 UI입니다.
웹 프론트엔드를 WebView로 렌더링하지 않습니다.

## Architecture

- Native UI: `mobile/src/app`, `mobile/src/components`
- Auth token: Expo SecureStore
- Primary backend: `EXPO_PUBLIC_API_URL` (default `http://somensomes.iptime.org:8100`)
- Network fallback: `EXPO_PUBLIC_API_FALLBACK_URL` (default `http://somensomes.iptime.org:3000`)
- Backend business logic / DB / Kiwoom integration are shared with StockLog web.

## Build

From repository root:

```bash
./restart-mobile.sh
```

This installs mobile dependencies, validates TypeScript/Expo, checks backend routes, and starts an EAS `preview` cloud APK build.

To validate without EAS build:

```bash
./restart-mobile.sh --skip-build
```

After a preview APK is installed, Expo Go, Metro, adb, Android Studio, and a PC are not required to launch the app.
