#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${1:-preview}"
case "$PROFILE" in development|preview|production) ;; *) echo "Usage: $0 [development|preview|production]" >&2; exit 2;; esac
cd "$ROOT/mobile"
npm install --package-lock=true --no-audit --no-fund
npm run check:styles
npm run typecheck
npx expo-doctor@latest
npx expo config --type public >/dev/null
export EAS_NO_VCS=1
export EAS_PROJECT_ROOT="$ROOT/mobile"
exec npx --yes eas-cli@latest build --platform android --profile "$PROFILE" --clear-cache --non-interactive
