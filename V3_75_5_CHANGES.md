# StockLog v3.75.6

## Global trade fill notifications
- Replaced page-local fill detection with one account-wide notifier mounted at the app root.
- Added lightweight `/api/trading/fill-events` polling that queries only Kiwoom execution TR `ka10076`.
- Default broker execution refresh floor is 5 seconds and has a short server-side per-user cache.
- Notifications appear regardless of the current StockLog page.
- A browser refresh seeds existing executions without replaying them as new notifications.
- Automatic and manual executions are labeled separately.
- Automatic order cards are reconciled from the global execution poll even when the auto-trading page is closed.
- Pending automatic orders are also reconciled by the backend watcher, so completed fills remain recorded even when no browser is open.

## Auto trading history UX
- Increased history page size from 8 to 12 items.
- Replaced tall inline audit cards with compact, aligned rows showing only stock, status, amount, quantity/price, confidence and latest time.
- Removed inline expanded details from the list.
- Added a dedicated large audit detail sheet with execution summary, decision/order/fill timeline, Gbot reason, evidence, risks, exit plan, order identifiers and timestamps.
- A fill event refreshes the same automatic order record instead of creating a separate history item.
