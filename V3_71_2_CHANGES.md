# StockLog v3.71.2

## Premium AI decision consistency
- Fixed a contradictory UI where the deterministic final verdict could be `매수 추천` while the cached LLM headline/summary still said `관망`.
- A single final verdict now regenerates headline, executive summary, strategy, entry timing, buy plan and verdict reason.
- Existing cached premium analyses are re-normalized on read, so users do not need to consume another AI analysis credit to receive the corrected copy.
- Added a decision-balance summary showing positive / caution / neutral quantitative dimensions.
- Quantitative summary now explicitly includes performance, valuation, foreign/institution flow, 20/60-day trend and news/report/disclosure evidence when available.
- `analysis_schema_version` bumped to 3.71.2.

## Reliability
- Added a regression test covering a stale `관망` LLM narrative corrected to `매수 추천` by StockLog's quantitative consistency layer.
- Existing positive/risk/watch evidence minimums remain enforced.
