# StockLog v3.80.3 Changes

## Stock detail
- Quarterly financial YoY transition labels no longer show qualitative phrases such as `흑자 전환`, `적자 축소`, `적자 확대`, or `적자 전환`.
- Normal comparable periods retain the numeric YoY percentage; sign-transition periods show only `+`, `-`, or `0`.
- The YoY value alone receives the finance color: positive red, negative blue, neutral gray. The `(작년대비)` helper text stays neutral.
- News, broker-report, AI-factor, and chart-analysis copy uses a single neutral dark text color.
- Sentiment colors are reserved for numeric metrics: positive red, neutral gray, negative blue.
- The initial stock-detail loading progress now includes a fourth `차트 분석` stage.

## Portfolio / Gbot auto trading
- Each portfolio holding now exposes `매입가격`, `보유수량`, `수수료`, and `총손익 (수수료반영)` in a dedicated cost strip.
- Auto-trading monitored holdings expose the same four fields.
- Existing Kiwoom net P/L remains the source of truth for fee-reflected total P/L.
- When a stable per-position fee field is unavailable, a display-only cost adjustment is derived from gross market value, purchase principal, and broker net P/L. It does not affect order sizing, risk rules, or trading decisions.

## Investor flow
- Core-flow and institution-detail sections have larger vertical separation.
- The whole stock flow card has no hover lift/shadow transition. Stock detail navigation remains exclusively on the dedicated `종목 상세` button.

## Popular themes
- Gbot theme summaries request sentence-level `summary_lines` with 1–2 model-selected important sentences.
- The UI renders each summary sentence on its own line and visually emphasizes important sentences in bold.
- Older/cached summaries without `summary_lines` fall back to sentence splitting with the first sentence emphasized.

## Version
- Root/project/frontend/mobile version: `3.80.3`.
- `frontend/dist` is intentionally not stamped as `3.80.3` until a successful production build is produced by `restart-all.sh`.
