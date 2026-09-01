# StockLog v3.58.1

## 거래 연동 화면 긴급 수정
- 서비스 표면 보호 작업에서 사용자용 설정 컴포넌트 이름을 `TradingConnectionSettings`로 변경했지만 메인 라우팅에 남아 있던 이전 `KiwoomSettings` 참조를 수정했습니다.
- 거래 연동 페이지 진입 시 `ReferenceError: KiwoomSettings is not defined`로 빈 화면이 되던 문제를 해결했습니다.
- 동일한 이전 컴포넌트 참조가 사용자 렌더링 경로에 남아 있지 않은지 재검사했습니다.
