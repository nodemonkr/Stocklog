# StockLog v3.67.1

## Smart Analysis 500 hotfix

- Fixed `/api/smart/recommend/{mode}` HTTP 500 caused by a missing `_smart_strategy_match` function after the v3.67.0 theme/filter refactor.
- Moved strategy matching into `smart_scoring.strategy_match` so future API layout changes cannot silently remove the implementation.
- Avoid loading the full provider-theme relation map when no theme/subtheme filter is selected.
- Hardened malformed legacy investment-profile JSON and smart-score component cache handling.
- Restored premium filter preset metadata accidentally omitted in v3.67.0.
- Added regression tests for all strategy presets and malformed inputs.
