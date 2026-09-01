#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROFILE="preview"
SKIP_SERVERS=0
SKIP_BUILD=0

for arg in "$@"; do
  case "$arg" in
    development|preview|production) PROFILE="$arg" ;;
    --skip-servers) SKIP_SERVERS=1 ;;
    --skip-build|--no-build) SKIP_BUILD=1 ;;
    -h|--help)
      cat <<USAGE
Usage: ./restart-mobile.sh [preview|production|development] [--skip-servers] [--skip-build]

Default: preview cloud APK build.
- preview: installable standalone APK (no Expo Go / no Metro required after install)
- production: store-oriented Android build
- development: Expo development client
USAGE
      exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

for env_file in "$ROOT/stocklog.env" "$ROOT/.env"; do
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
done

BACKEND_PORT="${STOCKLOG_BACKEND_PORT:-8100}"
PUBLIC_HOST="${STOCKLOG_PUBLIC_HOST:-somensomes.iptime.org}"
FALLBACK_PORT="${STOCKLOG_PUBLIC_PORT:-3000}"
DIRECT_ORIGIN="${STOCKLOG_MOBILE_API_URL:-http://${PUBLIC_HOST}:${BACKEND_PORT}}"
FALLBACK_ORIGIN="${STOCKLOG_MOBILE_FALLBACK_URL:-http://${PUBLIC_HOST}:${FALLBACK_PORT}}"

echo '=================================================='
echo ' StockLog native mobile restart + EAS build'
echo '=================================================='
echo "Backend process    : 127.0.0.1:${BACKEND_PORT}"
echo "App primary API    : ${DIRECT_ORIGIN}"
echo "App fallback API   : ${FALLBACK_ORIGIN}"
echo "EAS profile        : ${PROFILE}"
echo

# Keep EAS build-time endpoints and backend mobile redirect/CORS in sync.
echo '[1/6] Synchronizing mobile environment...'
python3 - "$ROOT/mobile/eas.json" "$ROOT/backend/.env" "$DIRECT_ORIGIN" "$FALLBACK_ORIGIN" <<'PY'
import json,sys
from pathlib import Path

eas_path=Path(sys.argv[1]); backend_env=Path(sys.argv[2]); direct=sys.argv[3].rstrip('/'); fallback=sys.argv[4].rstrip('/')
with eas_path.open(encoding='utf-8') as f:data=json.load(f)
for cfg in data.get('build',{}).values():
    env=cfg.setdefault('env',{})
    env['EXPO_PUBLIC_API_URL']=direct
    env['EXPO_PUBLIC_API_FALLBACK_URL']=fallback
    env['EXPO_PUBLIC_ALLOW_HTTP']='true'
with eas_path.open('w',encoding='utf-8') as f:
    json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')

lines=backend_env.read_text().splitlines() if backend_env.exists() else []
existing=[]
for line in lines:
    if line.startswith('CORS_ORIGINS='):
        existing=[x.strip() for x in line.split('=',1)[1].split(',') if x.strip()]
vals=[]
for x in existing+['http://localhost:5174','http://127.0.0.1:5174',direct,fallback]:
    if x and x not in vals: vals.append(x)
out=[]; cors_done=False; return_done=False
for line in lines:
    if line.startswith('CORS_ORIGINS='):
        if not cors_done: out.append('CORS_ORIGINS='+','.join(vals)); cors_done=True
    elif line.startswith('STOCKLOG_MOBILE_RETURN_URL='):
        if not return_done: out.append('STOCKLOG_MOBILE_RETURN_URL=stocklog://auth'); return_done=True
    else:
        out.append(line)
if not cors_done: out.append('CORS_ORIGINS='+','.join(vals))
if not return_done: out.append('STOCKLOG_MOBILE_RETURN_URL=stocklog://auth')
backend_env.parent.mkdir(parents=True,exist_ok=True)
backend_env.write_text('\n'.join(out).rstrip()+'\n')
PY

if [ "$SKIP_SERVERS" -eq 0 ]; then
  echo '[2/6] Restarting StockLog backend/web services...'
  "$ROOT/restart-all.sh"
else
  echo '[2/6] Server restart skipped.'
fi

if ! curl -fsS --max-time 5 "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null; then
  echo "[ERROR] FastAPI health check failed on 127.0.0.1:${BACKEND_PORT}" >&2
  tail -120 "$ROOT/logs/backend.log" 2>/dev/null || true
  exit 1
fi
echo "[OK] Backend health: ${BACKEND_PORT}"

echo '[3/6] Installing/synchronizing native mobile dependencies...'
cd "$ROOT/mobile"
command -v node >/dev/null || { echo '[ERROR] Node.js is missing.' >&2; exit 1; }
command -v npm >/dev/null || { echo '[ERROR] npm is missing.' >&2; exit 1; }
# npm install is intentional: it repairs package-lock.json when the mobile dependency list changes.
npm install --package-lock=true --no-audit --no-fund

echo '[4/6] TypeScript + Expo validation...'
npm run check:styles
npm run typecheck
npx --yes expo-doctor@latest
npx expo config --type public >/dev/null
echo '[OK] Native mobile validation passed.'

echo '[5/6] Checking API routes expected by native app...'
npm run audit:api
python3 - "$ROOT/backend/app/main.py" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
required=[
'/api/auth/login','/api/auth/admin-login','/api/auth/register','/api/auth/check-username','/api/auth/me','/api/investment-profile','/api/ai-usage',
'/api/stocks/search','/api/market-overview','/api/stocks/{code}/detail','/api/stocks/{code}/chart','/api/stocks/{code}/chart/cached','/api/stocks/{code}/investor-flow','/api/stocks/{code}/quote','/api/stocks/{code}/orderbook','/api/stocks/{code}/ai-analysis/status','/api/stocks/{code}/ai-analysis/start',
'/api/smart/filter-options','/api/smart/recommend/{mode}','/api/smart/stocks/{code}/score-detail','/api/themes','/api/themes/gbot-summary','/api/flow-analysis/rankings',
'/api/trading/connection','/api/trading/connection/test','/api/trading/portfolio','/api/trading/buying-power','/api/trading/order','/api/trading/reservations','/api/trading/fill-events','/api/trading/portfolio/outlook','/api/trading/portfolio/outlook/start','/api/trading/auto/status','/api/trading/auto/options','/api/trading/auto/settings','/api/trading/auto/history','/api/trading/auto/cycles','/api/trading/auto/learning','/api/trading/auto/learning/review-ready','/api/trading/auto/start','/api/trading/auto/stop','/api/trading/auto/run-once',
'/api/admin/status','/api/admin/users','/api/admin/external-apis','/api/admin/social-auth','/api/admin/membership/features','/api/admin/membership/refresh-policy','/api/admin/unified-sync/status','/api/admin/unified-sync/start','/api/admin/unified-sync/stop','/api/admin/unified-sync/schedule','/api/admin/sync-error-logs','/api/admin/sync-error-logs/client-event','/api/admin/sync-error-logs/download-all','/api/admin/theme-db/status','/api/admin/theme-db/repair','/api/admin/theme-normalize','/api/admin/theme-normalize/status','/api/admin/market-data/status','/api/admin/market-data/stop','/api/admin/theme-sync/status','/api/admin/market-theme-sync/status','/api/admin/classification-sync/status','/api/admin/flow-sync/status'
]
missing=[x for x in required if x not in s]
if missing:
    raise SystemExit('Missing backend routes: '+', '.join(missing))
print('[OK] Native mobile backend route audit passed.')
PY

if [ "$SKIP_BUILD" -eq 1 ]; then
  echo '[6/6] EAS build skipped (--skip-build).'
  exit 0
fi

echo '[6/6] Starting EAS cloud Android build...'
# Cloud build only. No Android Studio, adb, emulator, or USB connection is required here.
export EAS_NO_VCS=1
export EAS_PROJECT_ROOT="$ROOT/mobile"
exec npx --yes eas-cli@latest build --platform android --profile "$PROFILE" --clear-cache --non-interactive
