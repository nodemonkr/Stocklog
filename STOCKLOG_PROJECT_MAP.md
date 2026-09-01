# StockLog Project Map

## Current release

- Project version source: `VERSION`
- Current version: `3.80.8`
- Web runtime ports: backend `8100`, frontend `5174`
- Deployment/restart entrypoint: `./restart-all.sh`

## Repository layout

### `frontend/`

React 19 + Vite 7 single-page web application.

Key files:
- `src/App.jsx`: main application shell and most page/component flows (auth, dashboard, smart analysis, stock detail, flow analysis, portfolio/trading, account/admin, Gbot/auto trading).
- `src/api.js`: frontend API client layer.
- `src/style.css`: shared web styling and finance color conventions.
- `vite.config.js`: Vite configuration; reads the root `VERSION` and injects `__STOCKLOG_VERSION__` into the web build.
- `dist/`: production build output. A successful current build contains `dist/VERSION`.

### `backend/`

FastAPI + SQLAlchemy backend with a large API surface (about 145 HTTP route declarations in `app/main.py`).

Major modules:
- `app/main.py`: API composition, health endpoints, account/admin, stock, portfolio, smart/AI, sync and trading endpoints.
- `app/kiwoom.py`: Kiwoom REST/realtime integration.
- `app/smart_scoring.py`: smart-stock scoring.
- `app/analysis.py`, `app/ai_analyst.py`: stock/Gbot analysis logic.
- `app/theme_classification.py`, `app/theme_taxonomy.py`: theme classification/taxonomy.
- `app/auto_trading_safety.py`, `app/auto_learning.py`: automated trading safety and learning memory.
- `app/database.py`, `app/models.py`, `app/schemas.py`: persistence/model/schema layer.
- `app/external_api.py`, `app/providers.py`: external provider integration.

The FastAPI app reads the root `VERSION`, so `/health` identifies the running StockLog release.

### `mobile/`

Expo 57 + React Native 0.86 + Expo Router application.

Key areas:
- `src/app/(tabs)/`: primary app tabs (home, analysis, portfolio, auto trading, more).
- `src/app/stock/[code].tsx`: stock detail.
- `src/app/admin/`: mobile admin tools.
- `src/components/ui.tsx`: shared native UI primitives.
- `src/constants/theme.ts`: light palette and Korean-market finance colors (`positive` red, `negative` blue).
- `app.json`, `package.json`: mobile release version metadata, kept aligned with root `VERSION`.

## Runtime / deployment flow

1. `restart-all.sh` reads root `VERSION`.
2. It builds `frontend` first.
3. Only a successful build is promoted from `dist.next` to `dist`, and `dist/VERSION` is stamped.
4. A failed build may reuse an existing `dist` only when its `dist/VERSION` exactly matches the root version; stale UI is never silently served as the new release.
5. Existing processes are stopped only after the frontend build succeeds.
6. `start-all.sh` starts backend and frontend and waits for readiness.
7. `check-version.sh` compares root, frontend package, mobile package/app, production `dist`, and the running backend (when available).

## UI conventions from v3.80.5

- Gain / positive numeric movement (`+`, `.up`): red.
- Loss / negative numeric movement (`-`, `.down`): blue.
- Stock-detail semantic sentiment: positive red, negative blue, neutral/watch gray.
- Web UI is light-theme only; theme selection is not exposed in account settings.
- Smart-analysis stock search executes on Enter/search submit instead of every keystroke, and Enter search shows the existing full loading overlay.
- Smart-analysis total/profile score color thresholds: 80+ red, below 70 blue, 70–79 gray.
- Flow-analysis cards do not open stock detail when the card body is clicked; a dedicated stock-detail button is used.

- Stock-detail financial YoY transitions use only +/- (no qualitative transition labels); only the change value is red/blue/gray.
- Stock-detail news/report/analysis copy remains neutral dark text; sentiment colors are reserved for numeric values.
- Portfolio and Gbot auto-holding surfaces expose acquisition price, quantity, fee/cost adjustment, and fee-reflected total P/L.
- Flow core/institution blocks are visually separated and static; navigation remains on the dedicated detail button.
- Popular-theme Gbot summaries render sentence-by-sentence with selected key sentences emphasized.
- Stock-detail loading explicitly includes chart/technical analysis as a loading stage.
