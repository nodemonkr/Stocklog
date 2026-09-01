# StockLog v3.58.3

- Public terminology: `우위` -> `추천`, `명확도` -> `점수`, `중립` -> `관망`.
- Public separators standardized to `/` instead of middle-dot separators.
- User-facing AI prompts explicitly require formal Korean honorific style.
- Percent and multiple figures such as `65%`, `2.0배` are emphasized in business/financial analysis narratives.
- Financial change calculation corrected: interim income metrics use cumulative filing amounts and compare only with the prior-year same reporting basis; capital/balance values compare with the prior fiscal-year-end value supplied by the same filing. Adjacent quarters are no longer compared as if they were equivalent periods.
- Added persisted filing-native comparison fields to `financial_quarters` with automatic startup migration. Existing legacy rows are refreshed on first detail view when comparison metadata is absent.
