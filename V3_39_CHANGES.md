# StockLog v3.39.0

## Market Intelligence overhaul
- News ordering now uses article publication time, not fetch time.
- Multi-query collection from Google News RSS.
- Optional Naver Search News API integration (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`) with date sorting.
- Near-duplicate headline removal, stock relevance score, importance score and source-quality prior.
- News cache TTL reduced to 15 minutes by default; old cache rows without publication timestamps are refreshed.
- OpenDART recent disclosure collection/caching with importance ranking and original filing links.
- Broker research is cached in MySQL and ordered by actual report date.
- Stock detail refresh now refreshes news, disclosures and broker reports together.
- Stock detail adds paged official disclosures (2 items/page) and news importance badges.
- StockLog AI Bot consumes newest + most important cached news, disclosures and broker reports, and focuses on recent changes instead of recalculating quantitative scores.

## Optional configuration
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `NEWS_CACHE_SECONDS=900`
- `BROKER_REPORT_CACHE_SECONDS=21600`
- `DISCLOSURE_CACHE_SECONDS=900`
- `DISCLOSURE_LOOKBACK_DAYS=120`
