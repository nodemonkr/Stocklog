#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
STAMP="$VENV/.requirements.sha256"

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
BACKEND_PORT="${STOCKLOG_BACKEND_PORT:-8100}"
cd "$BACKEND"

venv_is_usable() {
  [ -x "$VENV/bin/python" ] || return 1
  "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' >/dev/null 2>&1
}

if ! venv_is_usable; then
  echo "[BACKEND] Python venv가 없거나 손상됨 → 재생성"
  rm -rf "$VENV"
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

if [ ! -f .env ]; then
  echo "[BACKEND] .env 없음 → .env.example 복사"
  cp .env.example .env
fi
chmod 600 .env 2>/dev/null || true

JWT_VALUE="$(grep -E '^(JWT_SECRET|SECRET_KEY)=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"
if [ -z "$JWT_VALUE" ] || [ "$JWT_VALUE" = "CHANGE_THIS_TO_A_LONG_RANDOM_STRING" ] || [ "$JWT_VALUE" = "CHANGE_ME" ] || [ "$JWT_VALUE" = "changeme" ]; then
  echo "[SECURITY WARNING] backend/.env 의 JWT_SECRET(또는 SECRET_KEY)가 비어 있거나 기본값입니다."
  echo "외부 공개 전 긴 랜덤 값으로 변경하세요. 기존 암호화 키를 바꾸면 저장된 키움 Key/Secret은 다시 저장해야 합니다."
fi

REQ_HASH="$(sha256sum requirements.txt | awk '{print $1}')"
OLD_HASH="$(cat "$STAMP" 2>/dev/null || true)"
DEPS_OK=0
python - <<'PY' >/dev/null 2>&1 && DEPS_OK=1 || true
import fastapi, httpx, sqlalchemy, pymysql, bs4, websockets, cryptography, jose
PY

if [ "$REQ_HASH" != "$OLD_HASH" ] || [ "$DEPS_OK" -ne 1 ]; then
  echo "[BACKEND] Python 의존성 설치/복구"
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  printf '%s\n' "$REQ_HASH" > "$STAMP"
else
  echo "[BACKEND] requirements 및 핵심 import 정상"
fi

echo "[BACKEND] Uvicorn 시작 ${BIND_HOST}:${BACKEND_PORT}"
exec python -m uvicorn app.main:app --host "$BIND_HOST" --port "$BACKEND_PORT"
