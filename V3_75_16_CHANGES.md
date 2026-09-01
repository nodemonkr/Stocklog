# StockLog v3.75.16

- Same-day positions no longer count the move from yesterday close before the user owned the shares as investor P/L.
- For positions fully acquired today, the portfolio `금일 투자손익` uses Kiwoom net position P/L/cost basis.
- Full-day stock move is preserved separately as `주가 일간변동` for context.
- Portfolio headline `금일 투자손익` is reconciled from holding-level P/L instead of trusting a zero-valued mock-account daily field.
- Existing holdings continue to use previous-close day movement when no reliable broker daily P/L exists.
