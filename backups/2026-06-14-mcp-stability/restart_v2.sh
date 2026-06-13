#!/bin/bash
set -euo pipefail
cd /opt/xiaozhi-mcp

LOG_KB=/var/log/kb_server.log
LOG_XIAOZHI=/var/log/xiaozhi_client.log
ENV_FILE=/etc/xiaozhi-mcp.env

echo "=== Stop old services ==="
xiaozhi stop 2>/dev/null || true
pkill -f 'kb_server(_v2)?\.py' 2>/dev/null || true
sleep 2

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

if [ -z "${DASHSCOPE_API_KEY:-}" ]; then
  echo "WARN: DASHSCOPE_API_KEY is not set; search_regulation will return an API unavailable message."
fi

export KB_BASE_DIR=/opt/xiaozhi-mcp
export KB_HOST=127.0.0.1
export KB_PORT=8766

echo "=== Start KB Server v2 (RAG, 4 tools) ==="
: > "$LOG_KB"
nohup ./venv/bin/python /opt/xiaozhi-mcp/kb_server_v2.py > "$LOG_KB" 2>&1 &
KB_PID=$!
echo "KB PID: $KB_PID"

for i in $(seq 1 20); do
  if ss -tlnp | grep -q ':8766'; then
    break
  fi
  sleep 1
done

echo "=== KB startup log ==="
tail -120 "$LOG_KB" || true

echo "=== Port check ==="
ss -tlnp | grep ':8766'

echo "=== Start xiaozhi-client ==="
: > "$LOG_XIAOZHI"
nohup xiaozhi start >> "$LOG_XIAOZHI" 2>&1 &
XIAOZHI_PID=$!
echo "xiaozhi PID: $XIAOZHI_PID"
sleep 8

echo "=== xiaozhi status ==="
xiaozhi status || true

echo "=== Registered MCP tools ==="
xiaozhi mcp list --tools || true

echo "=== xiaozhi recent log ==="
tail -160 "$LOG_XIAOZHI" || true