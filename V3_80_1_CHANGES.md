# StockLog v3.80.1

## UI / UX
- 수급 분석 핵심 수급/기관 세부 제목을 한 줄로 정리하고 카드 상단의 불필요한 거래일 누적 설명 문구도 제거했습니다.
- 수급 수량과 전 페이지 등락/PnL 색상 규칙을 한국 증시 관례에 맞춰 `+ = 빨강`, `- = 파랑`으로 통일했습니다.
- 스마트 분석 종목 검색은 입력 중 자동 조회하지 않고 Enter(또는 검색 아이콘)로만 실행합니다. 검색 중에는 전체 화면 로딩창 대신 검색창 내부 상태만 표시합니다.
- 스마트 분석 검색창의 중첩 배경색 문제를 수정해 밝은 테마에서 하나의 흰색 검색 필드로 보이도록 했습니다.
- 포트폴리오 투자 평가액 옆 KPI 카드들을 밝은 배경/진한 글자로 재정리했습니다.
- 계정 프로필의 화면 테마 선택을 제거하고 StockLog 웹 UI를 밝은 테마로 고정했습니다.
- 종목 상세의 감성/판단 색상은 `긍정 = 빨강`, `부정·주의 = 파랑`, `관망·중립 = 회색`으로 통일했습니다.

## Version management
- 루트 `VERSION` 파일을 단일 프로젝트 버전 소스로 추가했습니다.
- frontend Vite 빌드가 `VERSION`을 읽어 메뉴/로그인/모바일 헤더의 버전 문구에 자동 반영합니다.
- backend FastAPI title/version 및 `/health`, `/health/ready`가 같은 `VERSION`을 사용합니다.
- `start-all.sh`, `restart-all.sh` CLI 출력이 루트 버전을 동적으로 표시합니다.
- `check-version.sh`가 project/frontend/mobile/app.json 및 실행 중 backend 버전 일치 여부를 검사합니다.

## Deployment / verification hardening
- `./restart-all.sh --version`, `./start-all.sh --version`으로 서비스를 재시작하지 않고 루트 프로젝트 버전을 확인할 수 있습니다.
- `restart-all.sh`는 실행 중인 서비스를 내리기 전에 프론트엔드를 먼저 빌드하고, 다른 버전의 오래된 `frontend/dist`를 새 버전처럼 자동 재사용하지 않습니다.
- production 빌드 성공 시 `frontend/dist/VERSION`을 기록하고 `check-version.sh`가 해당 표식을 검증합니다.
- `STOCKLOG_PROJECT_MAP.md`를 추가해 frontend/backend/mobile 경계와 배포 규칙을 문서화했습니다.
