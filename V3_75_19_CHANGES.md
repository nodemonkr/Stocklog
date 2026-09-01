# StockLog v3.75.19

- Fixed AI 체결사유 detail layout inheriting the global sidebar `aside` styles.
- Replaced the detail metadata semantic `aside` with a dedicated neutral column.
- Changed the modal overlay from dark navy to a light frosted background and softened the shell shadow.
- Added defensive CSS so any nested aside inside the AI detail can never become a 100vh dark sidebar.
