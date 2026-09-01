# StockLog Gemini 무료 연동 방법

1. Google AI Studio에서 Gemini API Key를 생성합니다.
2. 유료 서비스 없이 운영하려면 사용 중인 Google 프로젝트의 결제 설정을 직접 확인합니다.
3. StockLog 로그인 → 관리자 → 외부 API · AI → Gemini AI로 이동합니다.
4. API Key 입력 → 저장 → 연결 확인 순으로 누릅니다.
5. 스마트 종목 상세의 심층 분석은 Gemini와 로컬 Ollama를 동시에 실행한 뒤 하나의 최종 합의 의견으로 통합합니다.
6. 프리미엄 이상 모의투자 보유종목 자동 모멘텀은 대량 자동분석이므로 Gemini Flash-Lite 우선 + Ollama fallback의 빠른 방식을 유지합니다.
7. Gemini 무료 안전 한도/429/연결 오류가 발생해도 로컬 Ollama로 자동 전환합니다.

기본 StockLog 자체 안전 한도:
- 전체 Gemini 실제 요청 200회/일
- 백그라운드 자동 분석 120회/일

심층 듀얼 분석 1회가 정상적으로 끝나면 Gemini는 보통 2회 호출됩니다.
- 독립 분석 1회
- Gemini + Ollama 최종 합의 1회

따라서 기본 200회 안전 한도라면 캐시 미적중 심층 분석은 이론상 최대 약 100회 수준에서 먼저 StockLog 자체 보호 한도에 도달할 수 있습니다. 실제 무료 quota와는 별개의 StockLog 내부 보호값입니다.

환경변수 예시:

```bash
GEMINI_APP_DAILY_GUARD=200
GEMINI_BACKGROUND_GUARD=120
GEMINI_MANUAL_MODEL=gemini-3.6-flash
GEMINI_BACKGROUND_MODEL=gemini-2.5-flash-lite

AI_ENSEMBLE_GEMINI_TIMEOUT_SECONDS=50
AI_ENSEMBLE_OLLAMA_TIMEOUT_SECONDS=85
AI_ENSEMBLE_SYNTHESIS_TIMEOUT_SECONDS=50

OLLAMA_NUM_CTX=4096
OLLAMA_NUM_PREDICT=520
OLLAMA_TIMEOUT_SECONDS=60
```

API Key 자체는 `.env`에 넣을 필요가 없으며 관리자 페이지에서 암호화 저장하는 방식을 권장합니다.

Gemini에는 공개 종목 컨텍스트만 전달하며 계좌번호, 회원 ID, 보유수량, 평균매입가 등 개인 포지션 정보는 보내지 않습니다.
