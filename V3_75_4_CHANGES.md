# StockLog v3.75.4

## Navigation
- Main workspace page is persisted in the browser URL (`?page=`), so refresh restores the current page.
- Sidebar navigation uses browser history; Back/Forward restores the previous/next StockLog page.
- Stock detail state is also represented in the URL and participates in browser history.

## Trade fill notifications
- Manual paper trading: detects newly increased broker fill quantities and shows a top toast for 5.5 seconds.
- Automatic paper trading: detects new partial/full fills and shows the same top toast.
- Toast includes buy/sell, stock, newly filled quantity, fill price, amount, and time.

## Automatic trading history
- Added `GET /api/trading/auto/history` with server-side pagination.
- Default order history is 8 cards per page with first/previous/page/next/last controls.
- `orders` and `all` audit modes are paginated independently.
- A Gbot decision/order remains one database row/card. The same card is updated from decision to order acceptance, partial fill, and full fill.
- Order card now shows decision time, order time, fill time, quantities, prices, amount, Gbot reason, evidence, risks, exit plan, and Kiwoom order number.

## Fill reconciliation
- Auto status refreshes the Kiwoom account using the existing guarded account-sync cadence (default broker refresh floor: 20 seconds).
- Fill reconciliation updates the existing AutoTradingDecision row instead of generating a second history record.
- Kiwoom HHMMSS execution time is used as the best-effort fill timestamp when available.
