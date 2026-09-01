#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

load_stocklog_network_env() {
  for env_file in "$ROOT/stocklog.env" "$ROOT/.env"; do
    if [ -f "$env_file" ]; then
      set -a
      # shellcheck disable=SC1090
      source "$env_file"
      set +a
    fi
  done
}

load_stocklog_network_env

BIND_HOST="${STOCKLOG_BIND_HOST:-0.0.0.0}"
FRONTEND_PORT="${STOCKLOG_FRONTEND_PORT:-5174}"
BACKEND_PORT="${STOCKLOG_BACKEND_PORT:-8100}"
PUBLIC_HOST="${STOCKLOG_PUBLIC_HOST:-}"
ALLOWED_HOSTS="${STOCKLOG_ALLOWED_HOSTS:-}"

normalize_public_host() {
  local value="$1"
  value="${value#http://}"
  value="${value#https://}"
  value="${value%%/*}"
  if [[ "$value" == *:* ]] && [[ "$value" != \[*\] ]]; then
    value="${value%%:*}"
  fi
  printf '%s' "$value"
}

PUBLIC_HOST_ONLY="$(normalize_public_host "$PUBLIC_HOST")"
if [ -n "$PUBLIC_HOST_ONLY" ]; then
  export __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS="$PUBLIC_HOST_ONLY"
  echo "[FRONTEND] 외부 허용 Host: $PUBLIC_HOST_ONLY"
fi
if [ -n "$ALLOWED_HOSTS" ]; then
  echo "[FRONTEND] 추가 허용 Host: $ALLOWED_HOSTS"
fi

echo "[FRONTEND] Same-Origin Proxy: /api,/ws -> 127.0.0.1:${BACKEND_PORT}"
cd "$ROOT/frontend"

command -v node >/dev/null 2>&1 || { echo '[ERROR] Node.js가 없습니다.'; exit 1; }
command -v npm >/dev/null 2>&1 || { echo '[ERROR] npm이 없습니다.'; exit 1; }
echo "[INFO] Node $(node -v) / npm $(npm -v)"

STAMP="node_modules/.package-lock.sha256"
LOCK_HASH="$(sha256sum package-lock.json | awk '{print $1}')"
OLD_HASH="$(cat "$STAMP" 2>/dev/null || true)"

if [ "$LOCK_HASH" != "$OLD_HASH" ] || [ ! -x node_modules/.bin/vite ] || [ ! -d node_modules/react ]; then
  echo '[INFO] 프론트 의존성 설치/복구'
  rm -rf node_modules
  npm ci --no-audit --no-fund
  printf '%s\n' "$LOCK_HASH" > "$STAMP"
else
  echo '[FRONTEND] package-lock 및 Vite 실행 파일 정상'
fi

echo "[FRONTEND] Vite 시작 ${BIND_HOST}:${FRONTEND_PORT}"
exec ./node_modules/.bin/vite --host "$BIND_HOST" --port "$FRONTEND_PORT"
