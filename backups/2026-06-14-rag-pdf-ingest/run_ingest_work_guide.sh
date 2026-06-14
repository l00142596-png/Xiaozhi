#!/usr/bin/env bash
set -euo pipefail
cd /opt/xiaozhi-mcp
LOG=/var/log/rag_ingest_work_guide.log
PDF=$(find source_pdfs -maxdepth 1 -type f -name '《工务系统普速铁路作业指导书》*.pdf' | head -1)
if [ -z "${PDF:-}" ]; then
  echo "PDF not found" >&2
  exit 1
fi
if [ -f /etc/xiaozhi-mcp.env ]; then
  set -a
  . /etc/xiaozhi-mcp.env
  set +a
fi
{
  echo "=== RAG ingest start $(date '+%F %T') ==="
  echo "PDF=$PDF"
  ./venv/bin/python scripts/ingest_pdf_to_rag.py "$PDF" \
    --title '工务系统普速铁路作业指导书' \
    --source-name '工务系统普速铁路作业指导书（2015）.pdf' \
    --ocr --ocr-dpi 180 --ocr-psm 6 \
    --chunk-chars 650 --overlap-chars 80 --batch-size 10 \
    --replace-source
  echo "=== RAG ingest done $(date '+%F %T') ==="
  ./venv/bin/python - <<'PY'
import json, numpy as np
from pathlib import Path
chunks=json.loads(Path('rag/chunks.json').read_text(encoding='utf-8'))
emb=np.load('rag/embeddings.npz')['embeddings']
count=sum(1 for c in chunks if c.get('filename')=='工务系统普速铁路作业指导书（2015）.pdf')
print({'total_chunks': len(chunks), 'embeddings_shape': emb.shape, 'work_guide_chunks': count})
PY
  echo "=== restarting kb/client $(date '+%F %T') ==="
  systemctl restart xiaozhi-kb.service
  sleep 5
  systemctl restart xiaozhi-client.service
  sleep 8
  systemctl status xiaozhi-kb.service --no-pager -l | sed -n '1,20p'
  systemctl status xiaozhi-client.service --no-pager -l | sed -n '1,20p'
  grep -Ei 'MCP WebSocket|工具列表|knowledge 服务加载|error|ERROR' /var/log/xiaozhi_client.log | tail -40 || true
  echo "=== all done $(date '+%F %T') ==="
} >> "$LOG" 2>&1
