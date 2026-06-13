#!/bin/bash
set -e
cd /opt/xiaozhi-mcp

echo "=== 停止旧服务 ==="
xiaozhi stop 2>/dev/null || true
pkill -f kb_server.py 2>/dev/null || true
sleep 2

echo "=== 启动 KB Server v2 (RAG) ==="
nohup ./venv/bin/python kb_server.py > /var/log/kb_server.log 2>&1 &
echo "KB PID: $!"
sleep 3

echo "=== KB 启动日志 ==="
cat /var/log/kb_server.log

echo "=== 端口检查 ==="
ss -tlnp | grep 8766

echo "=== 启动 xiaozhi-client ==="
nohup xiaozhi start >> /var/log/xiaozhi_client.log 2>&1 &
echo "xiaozhi PID: $!"
sleep 3

echo "=== xiaozhi 工具注册 ==="
grep "工具" /var/log/xiaozhi_client.log | tail -3
