# StockLog v3.51 - Kiwoom API Stability

## Kiwoom request safety
- Added a per-client priority request gate so one mock token does not fire overlapping REST requests.
- Priority: order > executions/balance > orderbook > buying power > normal queries > themes.
- Keeps a conservative global interval and a >1 second same-TR interval for mock trading.
- HTTP 429 / flow-control responses trigger exponential cooldown instead of immediate repeated retries.
- Added runtime status diagnostics (normal / cooldown / auth error / warning, queue size, last success/error).

## Buying power
- Removed `kt00010` from account buying-power summary logic.
- Uses `kt00001` and its broker-reported cash-backed stock orderable amount fields.
- Added 10-second single-flight cache and last-good short fallback to prevent duplicate account requests.

## Orderbook and themes
- Orderbook calls are merged/cached for 2.5 seconds, with a short stale fallback.
- Theme list and theme-membership requests are cached for 10 minutes.
- If live theme refresh is temporarily limited, the last in-memory response or synchronized DB themes are shown with a stale-data notice instead of blanking the page.

## Post-order refresh
- Removed the simultaneous refresh burst after a buy/sell order.
- Portfolio -> buying power -> orderbook refreshes now run sequentially with spacing.
- Frontend suppresses overlapping buying-power and same-symbol orderbook requests.

## Admin
- Added Kiwoom API runtime status card to the admin page.

## Deployment
- Version bumped to v3.51.
- `restart-all.sh` still builds `frontend/dist` safely before restarting services.
- Project root remains `Stocklog/`.

## Verification
- Python compileall passed.
- Bash syntax checks passed for restart/start/stop scripts.
- Buying-power single-flight test passed (6 concurrent callers -> 1 broker loader call).
- Orderbook single-flight/cache test passed (5 concurrent callers -> 1 loader call).
- Priority gate test passed (order -> orderbook -> theme).
- Full Vite build could not be executed in the artifact environment because frontend dependencies are not installed there; `restart-all.sh` performs the real production build on the Stocklog server.
