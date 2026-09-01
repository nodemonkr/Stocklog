#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"

for ENV_FILE in "$ROOT/stocklog.env" "$ROOT/.env"; do
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
done

BASE="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
MODEL="${OLLAMA_MODEL:-qwen3:1.7b}"

echo "=== StockLog AI Diagnose ==="
echo "Ollama URL : $BASE"
echo "Model      : $MODEL"
echo

echo "[1/4] ollama ps"
ollama ps 2>/dev/null || echo "ollama ps 실행 실패"
echo

echo "[2/4] /api/tags"
if ! curl -fsS --max-time 10 "$BASE/api/tags" >/tmp/stocklog-ollama-tags.json; then
  echo "[FAIL] Ollama API 연결 실패"
  exit 1
fi

python3 - <<'PY'
import json
data=json.load(open("/tmp/stocklog-ollama-tags.json"))
for x in data.get("models",[]):
    print("-",x.get("name") or x.get("model"))
PY
echo

echo "[3/4] /api/ps"
curl -fsS --max-time 10 "$BASE/api/ps" || true
echo
echo

echo "[4/4] short JSON chat"
START="$(date +%s)"
CODE="$(
curl -sS   --max-time 300   -o /tmp/stocklog-ai-test.json   -w '%{http_code}'   "$BASE/api/chat"   -H 'Content-Type: application/json'   -d "{
    \"model\":\"$MODEL\",
    \"stream\":false,
    \"think\":false,
    \"format\":\"json\",
    \"keep_alive\":\"10m\",
    \"messages\":[
      {
        \"role\":\"user\",
        \"content\":\"반드시 JSON만 답해. ok=true와 message=StockLog AI 정상 을 반환해.\"
      }
    ],
    \"options\":{
      \"num_ctx\":2048,
      \"num_predict\":80,
      \"temperature\":0
    }
  }"
)"
END="$(date +%s)"

echo "HTTP    : $CODE"
echo "Elapsed : $((END-START)) sec"

python3 - <<'PY'
import json
p="/tmp/stocklog-ai-test.json"
try:
    d=json.load(open(p))
    print("model   :",d.get("model"))
    print("content :",d.get("message",{}).get("content"))
    print("prompt  :",d.get("prompt_eval_count"))
    print("output  :",d.get("eval_count"))
except Exception as e:
    print(open(p).read()[:1500])
    print("parse:",e)
PY

if [ "$CODE" != "200" ]; then
  echo "[FAIL] Ollama chat test failed"
  exit 2
fi

echo "[OK] Ollama basic API works"
