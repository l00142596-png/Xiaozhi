#!/bin/bash
set -euo pipefail
cd /opt/xiaozhi-mcp

cp -n kb_server.py "kb_server.py.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
chmod +x restart_v2.sh

if [ ! -f /etc/xiaozhi-mcp.env ]; then
  key=$(python3 - <<'PY'
import re
from pathlib import Path
text = Path('/opt/xiaozhi-mcp/kb_server.py').read_text(encoding='utf-8')
m = re.search(r'DASHSCOPE_API_KEY\s*=\s*["\']([^"\']+)', text)
print(m.group(1) if m else '')
PY
)
  if [ -n "$key" ]; then
    umask 077
    printf 'DASHSCOPE_API_KEY=%s\n' "$key" > /etc/xiaozhi-mcp.env
  fi
fi
chmod 600 /etc/xiaozhi-mcp.env 2>/dev/null || true

./venv/bin/python -m py_compile kb_server_v2.py
echo 'py_compile ok'

echo '--- non-secret config check ---'
grep -n 'DASHSCOPE_API_KEY' kb_server_v2.py restart_v2.sh /etc/xiaozhi-mcp.env 2>/dev/null | sed 's/=.*/=<redacted>/' || true