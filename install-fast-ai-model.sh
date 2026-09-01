#!/usr/bin/env bash
set -euo pipefail
MODEL="${1:-qwen3:1.7b}"
echo "[StockLog] CPU용 빠른 AI 모델 설치: $MODEL"
command -v ollama >/dev/null 2>&1 || { echo "[ERROR] ollama 명령을 찾을 수 없습니다."; exit 1; }
ollama pull "$MODEL"
echo
echo "[OK] 설치 완료: $MODEL"
echo "stocklog.env 또는 .env에 다음 값을 사용하세요:"
echo "OLLAMA_MODEL=$MODEL"
echo "OLLAMA_NUM_CTX=1024"
echo "OLLAMA_NUM_PREDICT=120"
echo "OLLAMA_TIMEOUT_SECONDS=45"
