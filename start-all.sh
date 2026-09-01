#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION_FILE="$ROOT/VERSION"
if [ -s "$VERSION_FILE" ]; then
  STOCKLOG_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
else
  STOCKLOG_VERSION="0.0.0-dev"
fi
case "${1:-}" in
  --version|-V|version) echo "StockLog v${STOCKLOG_VERSION}"; exit 0 ;;
esac
mkdir -p "$ROOT/logs" "$ROOT/.pids"
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

load_stocklog_network_env
BACKEND_PORT="${STOCKLOG_BACKEND_PORT:-8100}"
FRONTEND_PORT="${STOCKLOG_FRONTEND_PORT:-5174}"
port_busy(){ ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]$1$"; }
pid_alive(){ local pid="$1"; [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; }
start_process(){
  local name="$1" script="$2" port="$3"
  if port_busy "$port"; then echo "[ERROR] $name: $port 포트가 이미 사용 중입니다."; return 1; fi
  : > "$ROOT/logs/$name.log"
  nohup "$script" > "$ROOT/logs/$name.log" 2>&1 &
  local pid=$!; echo "$pid" > "$ROOT/.pids/$name.pid"; echo "[START] $name PID=$pid"
}
wait_http(){
  local name="$1" pid="$2" url="$3" max_wait="$4"
  echo "[WAIT] $name 준비 상태 확인 중..."
  for ((i=1;i<=max_wait;i++)); do
    if ! pid_alive "$pid"; then echo "[ERROR] $name 프로세스 종료"; tail -100 "$ROOT/logs/$name.log" || true; return 1; fi
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then echo "[OK] $name READY (${i}s)"; return 0; fi
    sleep 1
  done
  echo "[ERROR] $name 준비 timeout"; tail -120 "$ROOT/logs/$name.log" || true; return 1
}
start_process backend "$ROOT/run-backend.sh" "$BACKEND_PORT"
wait_http backend "$(cat "$ROOT/.pids/backend.pid")" "http://127.0.0.1:${BACKEND_PORT}/health" "${BACKEND_START_TIMEOUT:-90}"
start_process frontend "$ROOT/run-frontend.sh" "$FRONTEND_PORT"
wait_http frontend "$(cat "$ROOT/.pids/frontend.pid")" "http://127.0.0.1:${FRONTEND_PORT}/" "${FRONTEND_START_TIMEOUT:-60}"
echo; echo "StockLog v${STOCKLOG_VERSION} READY"; "$ROOT/network-info.sh" || true
