# StockLog v3.75.9

## Portfolio
- Fix per-holding evaluation amount when Kiwoom omits the item-level amount.
- Add daily P/L and total P/L per holding and at portfolio summary level.
- Derive prior close from synchronized price bars with StockLog market data fallback.
- Add `AI 체결사유` on holdings attributable to Gbot automatic fills.
- Repair portfolio theme/category mix by using normalized holding evaluation values.

## Manual paper trading
- Embed the full stock order workspace directly into `모의투자(수동)` instead of leaving the page mostly empty and opening it as a modal.
- Keep stock search, quote/orderbook, normal order, pending/fills and reservation tools in the page.

## Automatic paper trading
- Add safety-block cooldown so the same persistent blocked BUY/SELL is not re-added every watcher cycle.
- Updating auto-trading settings resets that cooldown; manual one-shot decisions bypass it.
- Add individual history delete and terminal-history cleanup APIs/UI. Active/pending orders cannot be deleted.
- Rename the detailed Gbot reason action to `AI 체결사유` and keep the existing detailed execution/audit view.

## Validation
- Backend Python compileall passed.
- App.jsx TypeScript parser/no-emit check passed.
- CSS brace structure checked.
