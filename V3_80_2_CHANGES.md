# StockLog v3.80.2 Changes

## Web UI

- Flow analysis result cards
  - Core flow and institution-detail metric cells now share the same 4-column dimensions and typography.
  - Added more spacing between the core-flow and institution-detail sections.
  - Removed stock-detail navigation from the whole result card.
  - Added a dedicated `종목 상세` button in each stock header.
- Login
  - Re-isolated the member/admin login layout from legacy global CSS rules.
  - Rebuilt desktop spacing, input alignment, form width, button styling, and responsive single-column behavior for the light theme.
- Smart analysis
  - Search input styling is normalized so the inner input no longer inherits generic page input surfaces.
  - Search still executes only on Enter/search submit.
  - The existing Smart Analysis loading overlay is shown again while an Enter search is running.
  - Total score and profile score colors now use: `80+ = red`, `<70 = blue`, `70-79 = gray`.

## Version

- Root/project/frontend/mobile version: `3.80.2`.
- `frontend/dist` is intentionally not stamped as `3.80.2` until a successful production build is produced by `restart-all.sh`.
