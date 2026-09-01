#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT/.pids"

mkdir -p "$PID_DIR"

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

pid_alive() {
  local pid="$1"

  [ -n "$pid" ] \
    && kill -0 "$pid" 2>/dev/null
}

wait_dead() {
  local pid="$1"
  local max_checks="${2:-15}"

  for ((i=1; i<=max_checks; i++)); do
    if ! pid_alive "$pid"; then
      return 0
    fi

    sleep 0.2
  done

  return 1
}

stop_pidfile() {
  # IMPORTANT:
  # Do not reference $name in the same `local` declaration under `set -u`.
  local name="$1"
  local pidfile="$PID_DIR/${name}.pid"
  local pid=""

  if [ ! -f "$pidfile" ]; then
    return 0
  fi

  pid="$(cat "$pidfile" 2>/dev/null || true)"

  if pid_alive "$pid"; then
    echo "[STOP] $name PID=$pid"

    kill "$pid" 2>/dev/null || true

    if ! wait_dead "$pid" 15; then
      echo "[STOP] $name PID=$pid 강제 종료"
      kill -9 "$pid" 2>/dev/null || true
      wait_dead "$pid" 5 || true
    fi
  fi

  rm -f "$pidfile"
}

port_busy() {
  local port="$1"

  ss -ltn 2>/dev/null \
    | awk '{print $4}' \
    | grep -Eq "[:.]${port}$"
}

kill_port_process() {
  local port="$1"

  if ! port_busy "$port"; then
    return 0
  fi

  echo "[STOP] 잔존 ${port} 포트 프로세스 정리"

  # Preferred on Ubuntu.
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi

  sleep 0.4

  if ! port_busy "$port"; then
    return 0
  fi

  # Fallback when fuser did not catch it.
  if command -v lsof >/dev/null 2>&1; then
    mapfile -t pids < <(
      lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null \
        | sort -u \
        || true
    )

    for pid in "${pids[@]:-}"; do
      [ -n "$pid" ] || continue

      echo "[STOP] port=$port PID=$pid"

      kill "$pid" 2>/dev/null || true

      if ! wait_dead "$pid" 10; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    done
  fi

  sleep 0.4

  if port_busy "$port"; then
    echo "[WARN] ${port} 포트가 아직 사용 중입니다."
    echo "       현재 LISTEN 프로세스:"
    ss -ltnp 2>/dev/null \
      | grep -E "[:.]${port}[[:space:]]" \
      || true

    return 1
  fi

  return 0
}

echo "=== StockLog process stop ==="

stop_pidfile backend
stop_pidfile frontend

backend_stop_ok=0
frontend_stop_ok=0

kill_port_process "$BACKEND_PORT" || backend_stop_ok=$?
kill_port_process "$FRONTEND_PORT" || frontend_stop_ok=$?

rm -f \
  "$PID_DIR/backend.pid" \
  "$PID_DIR/frontend.pid"

if [ "$backend_stop_ok" -ne 0 ] \
  || [ "$frontend_stop_ok" -ne 0 ]; then
  echo
  echo "[ERROR] 일부 StockLog 포트를 정리하지 못했습니다."
  exit 1
fi

echo "[OK] StockLog 프로세스 종료 완료"
