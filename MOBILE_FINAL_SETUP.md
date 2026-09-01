> SUPERSEDED BY mobile/V3_80_0_CHANGES.md
> 이 문서는 WebView/초기 standalone 전환 과정의 과거 기록입니다. 현재 실제 동작 확인된 모바일 기준은 `mobile/V3_80_0_CHANGES.md`이며, 새 작업/빌드 판단은 그 문서를 우선합니다.

# StockLog Mobile standalone integration (2026-08-26)

## Final port behavior

- FastAPI/Uvicorn backend: **8100**
- Web Vite frontend: **5174**
- Existing external web port: **3000** -> frontend/Vite -> `/api`,`/ws` proxy -> 8100
- Installed mobile app primary API: **http://somensomes.iptime.org:8100**
- Mobile automatic fallback: **http://somensomes.iptime.org:3000**

The previous mobile build used port 3000 because the checked-in network configuration explicitly exposed only the web gateway and proxied API/WebSocket traffic to 8100. This revision changes the installed app to try the actual backend port 8100 first, so it operates independently from the web frontend whenever router/firewall access to 8100 is available.

## One-command operation

Run from the project root:

```bash
./restart-mobile.sh
```

It restarts/health-checks the StockLog servers, synchronizes EAS endpoint values, installs mobile dependencies and refreshes package-lock.json, embeds the current production web bundle, runs Expo Doctor/config validation, and starts an EAS **preview APK** cloud build. It uses `EAS_NO_VCS=1`, so a Git repository is not required, and `--non-interactive`, so it will not try to install the finished APK through local adb.

For server-only validation without an EAS build:

```bash
./restart-mobile.sh --skip-eas
```

## Router requirement

For the phone to use the direct 8100 path outside the LAN, configure TCP **8100 -> StockLog server:8100** on the router/firewall. If that is not available, the app automatically falls back to the existing port 3000 gateway.

## Known browser-to-WebView limitation

Admin diagnostic log ZIP/file download still originates from browser Blob/download code. Core admin APIs and log viewing work, but OS-level file saving from that specific web flow can vary by Android WebView version.
