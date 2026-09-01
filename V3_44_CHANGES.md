# StockLog v3.44.0

## Unified sync resilience
- Unified sync now treats a `partial` stage as completed-with-warning and continues to later stages.
- Final unified status is `completed`, `success_with_warnings`, or `failed`.
- Kiwoom theme partial failures no longer populate the red `last_error` field.
- Existing valid theme relationships are preserved when a theme returns no members or fails to refresh.
- Transient theme errors receive delayed retry and do not block Market Theme / Classification stages after retries are exhausted.

## Repeated ignorable theme handling
- Empty/deprecated theme-like failures are tracked in the persisted theme sync provider state.
- After 3 consecutive deterministic failures, the theme is temporarily skipped for 30 days and then automatically eligible for recheck.
- Successful refresh clears its prior failure record.
- Transient/unknown failures are never permanently suppressed.

## Admin UX
- Minor partial failures are shown as `완료(주의)` rather than a red error.
- Unified completion can show `최근 전체 동기화 완료 · 참고사항 있음`.
- Warning details are collapsed by default and shown only when the administrator selects `상세 보기`.
- Red error banner is reserved for an actual unified-sync `failed` state.
