# StockLog Web ↔ Mobile Parity Audit — V3.80.0

## 일반 사용자 핵심 흐름

| 영역 | Web | Mobile V3.80.0 |
|---|---|---|
| 로그인/회원가입/소셜 로그인 | O | O |
| 홈 시장지표 | O | O |
| 총자산/구매가능/금일손익/금일수익률/총손익/총수익률/보유수 | O | O |
| 종목검색 | O | O |
| 종목 상세 현재가/차트/재무/수급/뉴스/리포트/공시/AI | O | O |
| 스마트분석 필터/점수 상세 | O | O |
| 스마트분석 시장요약 | O | O |
| 테마 목록/설명/Gbot/관련종목 | O | O (native modal) |
| 수급 1/3/5/7/20일 | O | O (등급 정책 동일) |
| 수급 기관 세부 주체/신호 | O | O |
| 포트폴리오/보유 상세/일봉/당일 수급 | O | O |
| 호가/매수가능수량/시장가·지정가 주문 | O | O |
| 미체결/체결/예약 관리 | O | O |
| 예약주문 등록/수정/취소 | O | O |
| 보유종목 AI 전망 | O | O (등급 정책 적용) |
| 자동매매 설정/시작/중지/1회판단 | O | O |
| 자동매매 전체 판단/주문 감사 | O | O |
| 오늘 자동매매 진단 | O | O |
| Gbot 실패 학습 메모리 | O | O |
| 투자성향 | O | O |

## 관리자

회원/정책/외부 API/OAuth/스케줄/개별 동기화/선택 통합동기화/테마 유지보수/진단로그를 native screen으로 제공한다. Desktop의 넓은 표는 모바일 카드/세로 레이아웃으로 재설계한다.

## V3.80.0 안정성 감사

- hidden tab polling 제거 또는 focus guard 적용
- 포트폴리오/자동매매 silent refresh
- 종목 상세 conditional hook 제거
- 일반회원 locked flow period 실제 disabled
- 8100 → 3000 fallback에도 timeout 적용
- mobile API route 자동대조 missing 0

모바일 UI는 웹 픽셀 복제가 아니라 동일 기능·동일 정책·동일 backend를 모바일에 적합한 native UX로 제공하는 것을 parity 기준으로 한다.

## 실제 API 호출 재대조

2026-08-30 패키징 직전 `frontend/src/App.jsx`와 `mobile/src`를 정규화하여 재대조했다.

- Web API shapes: **81**
- Mobile API shapes: **95**
- Web에서 호출하지만 Mobile에 대응 호출이 없는 API shapes: **0**

모바일 전용/추가 호출은 native UX, 진단, 직접 quote/chart 선로딩 등에 사용된다.
