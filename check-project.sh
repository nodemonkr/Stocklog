#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "[1/4] Python syntax"
python3 -m compileall -q backend/app

echo "[2/4] Shell syntax"
for f in ./*.sh; do bash -n "$f"; done

echo "[3/4] Frontend dependency state"
if [ -x frontend/node_modules/.bin/vite ]; then
  echo "  Vite installed"
else
  echo "  Vite missing: run ./run-frontend.sh to restore dependencies"
fi

echo "[4/4] Project size hotspots"
wc -l backend/app/main.py backend/app/kiwoom.py backend/app/providers.py frontend/src/App.jsx frontend/src/style.css

echo "Static checks completed."
