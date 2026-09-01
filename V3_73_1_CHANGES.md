# StockLog v3.73.1

## Premium AI Obot reliability hotfix

- Reduced the Obot first-pass payload to only pre-calculated investment facts needed for risk review.
- Reduced Obot output schema so a CPU-hosted local model can finish JSON reliably without wasting tokens on a full report.
- Added one automatic ultra-compact retry for timeout, invalid/truncated JSON, HTTP errors, or empty output.
- The retry still uses StockLog Obot; it does not silently replace Obot with deterministic StockLog text.
- Gbot still receives the richer StockLog quantitative context plus the successful Obot review and produces the detailed final premium report.
- Increased the outer Obot stage guard only enough to cover the bounded compact retry, preventing multi-minute retry loops.
- Added internal warning logs for each failed Obot attempt without exposing provider/model details to members.
