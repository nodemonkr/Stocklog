#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
for env_file in "$ROOT/stocklog.env" "$ROOT/.env"; do
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
done
BACKEND_PORT="${STOCKLOG_BACKEND_PORT:-8100}"
FRONTEND_PORT="${STOCKLOG_FRONTEND_PORT:-5174}"
PUBLIC_HOST="${STOCKLOG_PUBLIC_HOST:-}"
PUBLIC_PORT="${STOCKLOG_PUBLIC_PORT:-3000}"
MOBILE_BACKEND_PORT="${STOCKLOG_MOBILE_BACKEND_PORT:-$BACKEND_PORT}"
MOBILE_FALLBACK_PORT="${STOCKLOG_MOBILE_FALLBACK_PORT:-$PUBLIC_PORT}"

echo "=== StockLog 접속 주소 ==="
echo "Backend local : http://127.0.0.1:${BACKEND_PORT}"
echo "Web local     : http://127.0.0.1:${FRONTEND_PORT}"
for ip in $(hostname -I 2>/dev/null || true); do
  [[ "$ip" =~ ^127\. ]] && continue
  [[ "$ip" == *:* ]] && continue
  echo "Backend LAN   : http://${ip}:${BACKEND_PORT}"
  echo "Web LAN       : http://${ip}:${FRONTEND_PORT}"
done
if [ -n "$PUBLIC_HOST" ]; then
  echo "Web external  : http://${PUBLIC_HOST}:${PUBLIC_PORT}"
  echo "Mobile API    : http://${PUBLIC_HOST}:${MOBILE_BACKEND_PORT}  (direct backend)"
  echo "Mobile fallback: http://${PUBLIC_HOST}:${MOBILE_FALLBACK_PORT}  (/api,/ws proxy -> ${BACKEND_PORT})"
fi

echo
echo "=== 포트 역할 ==="
echo "${BACKEND_PORT}: FastAPI/Uvicorn 실제 백엔드 포트"
echo "${FRONTEND_PORT}: Vite 웹 프론트 포트"
echo "${PUBLIC_PORT}: 기존 외부 웹 포트(공유기에서 ${FRONTEND_PORT}로 전달)"
echo
echo "모바일 앱은 ${MOBILE_BACKEND_PORT} 백엔드 직접 연결을 먼저 시도합니다."
echo "직접 연결이 실패하면 ${MOBILE_FALLBACK_PORT}의 /api,/ws 프록시를 자동 fallback으로 사용합니다."
echo "외부 모바일에서 ${MOBILE_BACKEND_PORT} 직접 연결을 쓰려면 공유기 TCP ${MOBILE_BACKEND_PORT} -> 서버:${BACKEND_PORT} 포트포워딩이 필요합니다."
