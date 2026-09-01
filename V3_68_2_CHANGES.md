# StockLog v3.68.3

## Smart Analysis stock search coverage fix

- Fixed NORMAL-member Smart search being executed only inside the daily random 20-stock discovery list.
- Explicit stock name/code search now searches the complete active KOSPI/KOSDAQ stock master regardless of membership tier.
- Premium AI/profile score values remain server-side locked for NORMAL users.
- Explicit search can surface a listed security even when StockLog analysis is not ready; the UI shows `분석 데이터 준비 중` instead of silently hiding it or showing a misleading 0 score.
- Search results are labeled as search results rather than `랜덤` discovery ranking for NORMAL members.

## Universe omission protection

- Added `universe_last_seen_at` and `universe_missing_count` metadata to the stock master.
- A stock missing from one Kiwoom ka10099 snapshot is no longer immediately deactivated.
- A previously active stock is deactivated only after 3 consecutive universe misses.
- Sync provider status records how many missing rows were retained and how many were actually deactivated.

This specifically prevents valid listings such as 한글과컴퓨터 (030520) from appearing absent because they were outside a NORMAL member's random discovery set or because of a one-off provider omission.
