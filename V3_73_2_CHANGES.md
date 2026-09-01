# StockLog v3.73.2

## Premium AI reliability / live progress

- StockLog Obot interactive analysis now uses Ollama NDJSON streaming (`stream=true`).
- Removed the old 30~60 second per-read timeout from the premium Obot fast-risk pass.
- CPU model loading and prompt evaluation can therefore continue without being mistaken for a dead request.
- A 600-second configurable hard safety guard remains only for truly wedged Obot jobs (`AI_OBOT_HARD_LIMIT_SECONDS`).
- Obot streaming activity is propagated to the stock-detail status API: connecting, input processing, first response, generating, retry, completed.
- The detail page shows overall elapsed time, received Obot response characters, current generation state, and compact retry state.
- Backend stage persistence is throttled while live progress remains updated in memory, avoiding a database commit per token.
- Gbot and final verification remain separate visible phases.
- Frontend polling window was extended so it no longer abandons a healthy server-side analysis at six minutes.
- Obot/Gbot underlying provider names remain hidden from public analysis payloads.
