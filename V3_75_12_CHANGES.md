# v3.75.12

- Fixed legacy `themes.rising_count` / related NOT NULL columns causing MySQL 1364 during market-theme sync.
- Startup theme schema repair now assigns safe `DEFAULT 0` to surviving legacy breadth counters.
- Added runtime legacy-safe theme INSERT fallback for DB users without ALTER TABLE permission.
- Existing per-theme isolation remains intact, preventing one bad theme from rolling back already-saved themes.
