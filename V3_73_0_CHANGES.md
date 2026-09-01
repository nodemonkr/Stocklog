# StockLog v3.73.0

## Premium AI pipeline
- Premium analysis now runs `StockLog Obot -> StockLog Gbot -> StockLog verification` sequentially.
- Obot receives a deliberately compressed factual packet and performs a short risk/opposing-view review.
- Gbot receives the full StockLog quantitative context plus Obot's review and writes the detailed final report.
- Final verdict is still normalized to 매수 추천 / 관망 / 매도 추천 and receives deterministic fact consistency checks.
- Full-context double generation was removed from the premium path to reduce local CPU latency.
- Premium local Obot time is bounded and a full-timeout retry is not performed, preventing 5+ minute waits.

## Progress UX
- The backend cache row exposes real stages: `obot_running`, `obot_completed`, `gbot_running`, `gbot_completed`, `verifying`.
- Detail loading UI separately shows StockLog Obot and StockLog Gbot stages, followed by final verification.

## Service protection
- Customer-facing naming remains StockLog Gbot / StockLog Obot. Provider/model implementation details remain internal.
