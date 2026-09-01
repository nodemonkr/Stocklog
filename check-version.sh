#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VERSION_FILE="$ROOT/VERSION"
[ -s "$VERSION_FILE" ] || { echo "[ERROR] VERSION 파일이 없습니다."; exit 1; }
VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

read_json_version(){
  python3 - "$1" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    data=json.load(f)
if sys.argv[1].endswith('app.json'):
    print(data.get('expo',{}).get('version',''))
else:
    print(data.get('version',''))
PY
}

FRONTEND_VERSION="$(read_json_version frontend/package.json)"
MOBILE_VERSION="$(read_json_version mobile/package.json)"
MOBILE_APP_VERSION="$(read_json_version mobile/app.json)"
DIST_VERSION="$([ -f frontend/dist/VERSION ] && tr -d '[:space:]' < frontend/dist/VERSION || true)"

echo "=== StockLog version check ==="
echo "project : v${VERSION}"
echo "frontend: v${FRONTEND_VERSION}"
echo "mobile  : v${MOBILE_VERSION}"
echo "app.json: v${MOBILE_APP_VERSION}"
echo "dist    : ${DIST_VERSION:+v${DIST_VERSION}}${DIST_VERSION:-(not built for current version)}"

status=0
for item in "frontend:${FRONTEND_VERSION}" "mobile:${MOBILE_VERSION}" "app.json:${MOBILE_APP_VERSION}"; do
  name="${item%%:*}"; value="${item#*:}"
  if [ "$value" != "$VERSION" ]; then
    echo "[MISMATCH] ${name}=${value}, project=${VERSION}"
    status=1
  fi
done

if [ "$DIST_VERSION" != "$VERSION" ]; then
  echo "[STALE] frontend/dist는 v${VERSION} 빌드가 아닙니다. ./restart-all.sh 성공 시 자동 갱신됩니다."
  status=1
fi

if grep -q 'v3\.76\.14' frontend/src/App.jsx restart-all.sh start-all.sh backend/app/main.py 2>/dev/null; then
  echo "[WARN] 실행 코드에 이전 하드코딩 버전 문자열이 남아 있습니다."
  status=1
fi

BACKEND_PORT="${STOCKLOG_BACKEND_PORT:-8100}"
if curl -fsS --max-time 2 "http://127.0.0.1:${BACKEND_PORT}/health" >/tmp/stocklog-health-version.json 2>/dev/null; then
  python3 - "$VERSION" /tmp/stocklog-health-version.json <<'PY'
import json,sys,re
expected=sys.argv[1]
data=json.load(open(sys.argv[2],encoding='utf-8'))
service=str(data.get('service',''))
print(f"runtime : {service or '-'}")
m=re.search(r'v([^ ]+)',service)
if m and m.group(1)!=expected:
    print(f"[MISMATCH] running backend={m.group(1)}, project={expected}")
    raise SystemExit(1)
PY
  runtime_status=$?
  [ "$runtime_status" -eq 0 ] || status=1
else
  echo "runtime : backend not running (skip)"
fi

if [ "$status" -eq 0 ]; then
  echo "[OK] StockLog v${VERSION} 버전이 일치합니다."
else
  echo "[ERROR] 버전 불일치가 있습니다."
fi
exit "$status"
