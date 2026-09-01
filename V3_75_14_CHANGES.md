# StockLog v3.75.14

- Kiwoom account/P&L source mapping corrected for current REST API semantics.
- Removed ka10085 from holding/P&L sources; ka10077 is the account-return candidate.
- Per-holding broker purchase/evaluation/P&L values are kept separately and reconciled.
- Impossible total P/L states are recalculated from the same broker row (evaluation - purchase).
- Total assets are reconciled against Kiwoom cash + securities evaluation when a returned total is securities-only or inconsistent.
- Fresh snapshots are reconciled before DB persistence so manual/auto/portfolio/admin use one account basis.
- Portfolio exposes whether total assets/P&L use direct Kiwoom values or a Kiwoom-ledger reconciliation.
