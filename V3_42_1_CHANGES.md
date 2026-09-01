# StockLog v3.43.0

## OpenDART / external API DB compatibility fix

- Fixed HTTP 500 from `POST /api/admin/external-apis/dart/test` on databases created by early v3.40 builds.
- Older databases could contain a legacy `external_api_credentials.enabled` column defined as `NOT NULL` without a default, while current code writes `is_enabled`. MySQL therefore rejected new provider rows with error 1364 (`Field 'enabled' doesn't have a default value`).
- Startup schema repair now detects the legacy column, backfills it safely, and changes it to `BOOLEAN NOT NULL DEFAULT 1` so old and new StockLog builds can coexist.
- No API key, credential, or existing data is deleted.
- OpenDART test success/failure continues to be stored in the current `is_enabled`/test-status fields.
