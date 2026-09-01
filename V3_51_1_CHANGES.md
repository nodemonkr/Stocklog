# StockLog v3.51.1

## Smart recommendation freshness
- Confirmed that the Smart page itself refreshed every 15 seconds, but the recommendation rank was deterministic and dominated by slow-moving financial/valuation metrics. This made the same top candidates likely to remain visible for several days even when the page was refreshing normally.
- Rebalanced the StockLog recommendation score without turning it into a short-term momentum screener:
  - fundamentals/valuation remain the majority of the score;
  - 20-day momentum has a modestly larger influence;
  - today's positive price change contributes a small capped score.
- Added `recommendation_updated_at` to each Smart recommendation row using the newest available Kiwoom metrics / DART financials / valuation / stock update timestamp.
- The Smart list now shows a small `업데이트 MM/DD HH:MM` line directly below the stock code/market.

## Compatibility
- Existing AI access policy, social login, mobile responsive UI, Kiwoom API stability queue and deployment scripts are unchanged.
- Archive root remains `Stocklog/`.
