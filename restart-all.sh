#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"


VERSION_FILE="$ROOT/VERSION"
if [ ! -s "$VERSION_FILE" ]; then
  echo "[ERROR] VERSION 파일이 없거나 비어 있습니다: $VERSION_FILE"
  exit 1
fi
STOCKLOG_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

case "${1:-}" in
  --version|-V|version) echo "StockLog v${STOCKLOG_VERSION}"; exit 0 ;;
esac

load_stocklog_network_env() {
  if [ -f "$ROOT/stocklog.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/stocklog.env"
    set +a
  fi

  if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
  fi
}

build_frontend() {
  local frontend="$ROOT/frontend"
  local stamp="$frontend/node_modules/.package-lock.sha256"
  local lock_hash

  dist_matches_version() {
    [ -f "$frontend/dist/index.html" ] \
      && [ -f "$frontend/dist/VERSION" ] \
      && [ "$(tr -d '[:space:]' < "$frontend/dist/VERSION" 2>/dev/null || true)" = "$STOCKLOG_VERSION" ]
  }

  use_verified_existing_dist() {
    local reason="$1"
    if dist_matches_version; then
      echo "[WARN] ${reason} - v${STOCKLOG_VERSION} 검증 dist를 유지합니다."
      cd "$ROOT"
      return 0
    fi
    echo "[ERROR] ${reason}"
    echo "[ERROR] 현재 frontend/dist는 v${STOCKLOG_VERSION}로 빌드되었다는 표식이 없어 구버전 dist를 대신 사용하지 않습니다."
    echo "[HINT] Node/npm 의존성을 준비한 뒤 ./restart-all.sh 를 다시 실행하세요."
    cd "$ROOT"
    return 1
  }

  echo "=== frontend production build ==="
  [ -d "$frontend" ] || { echo "[ERROR] frontend 폴더가 없습니다: $frontend"; return 1; }

  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    use_verified_existing_dist "Node/npm이 없어 frontend source를 빌드할 수 없습니다."
    return $?
  fi

  cd "$frontend"
  echo "[INFO] Node $(node -v) / npm $(npm -v)"

  if [ ! -f package-lock.json ]; then
    use_verified_existing_dist "package-lock.json이 없어 재현 가능한 frontend build를 할 수 없습니다."
    return $?
  fi

  lock_hash="$(sha256sum package-lock.json | awk '{print $1}')"

  # Existing node_modules is kept whenever the required runtime is usable.
  # This avoids deleting a healthy offline installation just because app metadata/version changed.
  if [ ! -x node_modules/.bin/vite ] || [ ! -d node_modules/react ]; then
    echo '[INFO] 프론트 의존성 설치/복구 시도'
    rm -rf node_modules
    if ! npm ci --no-audit --no-fund; then
      rm -rf node_modules
      use_verified_existing_dist "npm 의존성 설치에 실패했습니다."
      return $?
    fi
  else
    echo '[INFO] 기존 프론트 의존성 사용'
  fi

  mkdir -p node_modules
  printf '%s\n' "$lock_hash" > "$stamp"

  echo '[BUILD] React production dist 생성 중...'
  rm -rf "$frontend/dist.next"
  if ! npm run build -- --outDir dist.next; then
    rm -rf "$frontend/dist.next"
    use_verified_existing_dist "production frontend build에 실패했습니다."
    return $?
  fi

  if [ ! -f "$frontend/dist.next/index.html" ]; then
    rm -rf "$frontend/dist.next"
    use_verified_existing_dist "dist.next/index.html이 생성되지 않았습니다."
    return $?
  fi

  printf '%s\n' "$STOCKLOG_VERSION" > "$frontend/dist.next/VERSION"

  rm -rf "$frontend/dist.previous"
  if [ -d "$frontend/dist" ]; then
    mv "$frontend/dist" "$frontend/dist.previous"
  fi
  mv "$frontend/dist.next" "$frontend/dist"
  rm -rf "$frontend/dist.previous"

  echo "[OK] production build 완료: $frontend/dist (v${STOCKLOG_VERSION})"
  cd "$ROOT"
}

load_stocklog_network_env
BACKEND_PORT="${STOCKLOG_BACKEND_PORT:-8100}"
FRONTEND_PORT="${STOCKLOG_FRONTEND_PORT:-5174}"

echo "=== StockLog v${STOCKLOG_VERSION} CLEAN RESTART ==="

# Build first. If the build fails, the currently running service and previous
# dist stay untouched instead of taking the site down before a failed deploy.
build_frontend

if ! ./stop-all.sh; then
  echo
  echo "[ERROR] 기존 StockLog 프로세스를 완전히 종료하지 못했습니다."
  echo "${BACKEND_PORT}/${FRONTEND_PORT} 포트 사용 상태를 확인해주세요."
  ss -ltnp 2>/dev/null | grep -E ":${BACKEND_PORT}|:${FRONTEND_PORT}" || true
  exit 1
fi

rm -rf "$ROOT/.pids"
mkdir -p "$ROOT/.pids" "$ROOT/logs"

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.](${BACKEND_PORT}|${FRONTEND_PORT})$"; then
  echo "[ERROR] 재시작 직전에도 StockLog 포트가 사용 중입니다."
  ss -ltnp 2>/dev/null | grep -E ":${BACKEND_PORT}|:${FRONTEND_PORT}" || true
  exit 1
fi

./start-all.sh

echo
echo "=== backend health ==="
curl -fsS --max-time 3 "http://127.0.0.1:${BACKEND_PORT}/health"
echo

echo "=== production dist ==="
ls -lh "$ROOT/frontend/dist/index.html"

echo "=== listening ports ==="
ss -ltnp 2>/dev/null | grep -E ":${FRONTEND_PORT}|:${BACKEND_PORT}" || true

echo
"$ROOT/network-info.sh" || true

echo
echo "StockLog v${STOCKLOG_VERSION} 재시작 완료"
echo "- 내부 개발 서버: ${FRONTEND_PORT}"
echo "- 외부 Caddy 서비스: frontend/dist"
echo "브라우저 캐시가 남아 있으면 Ctrl+Shift+R로 새로고침하세요."
