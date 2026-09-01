# StockLog v3.68.1

## Smart Analysis membership hardening

- PREMIUM / EVENT / ADMIN (or accounts with `smart_full_market`) keep the full-market StockLog AI ranking.
- NORMAL accounts no longer receive AI-ranked top stocks. They receive a stable daily 20-stock random sample based on user/date/stock code.
- NORMAL API payloads no longer serialize AI score, profile-fit score, score labels, score preview components, or recommendation score/type.
- `/api/smart/stocks/{code}/score-detail` now requires premium full-market access, preventing score leakage through direct API calls.
- NORMAL Smart Analysis score cells render as locked premium-only panels.

## Smart list layout

- Ranking is now a dedicated column separate from the stock-name cell.
- PREMIUM shows the actual AI ranking number; NORMAL labels the list as random rather than implying an AI rank.
- Desktop/tablet/mobile grid rules were rebuilt to avoid rank/name overlap.
- Score-detail is disabled for NORMAL while stock detail remains available.

## Score information tooltip

- Header information tooltips are rendered through a React portal using fixed positioning.
- Tooltips are no longer clipped by the table/scroll container's overflow.
- Hover, keyboard focus, and tap/click are supported.

## Validation

- Backend pytest suite: 36 passed.
- Backend Python compile audit: passed.
- Frontend modified JSX delimiter/static checks: passed.
- CSS brace audit: passed.
- A full Vite build was attempted, but dependency installation exceeded the execution time limit in the validation environment.
