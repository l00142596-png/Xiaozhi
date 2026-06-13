#!/bin/bash
set -e
cd /opt/xiaozhi-mcp

# 杀旧 watchdog
pkill -f "bash watchdog.sh" 2>/dev/null || true
sleep 1

# 重启 xiaozhi-client（当前已断连）
xiaozhi stop 2>/dev/null || true
sleep 2
nohup xiaozhi start >> /var/log/xiaozhi_client.log 2>&1 &
echo "xiaozhi-client restarted, PID: $!"

# 等连接建立
sleep 3

# 验证
echo "=== 最新连接状态 ==="
grep -E "端点连接成功|连接已关闭" /var/log/xiaozhi_client.log | tail -3

# 启新 watchdog
nohup bash watchdog.sh > /var/log/watchdog.log 2>&1 &
echo "watchdog started, PID: $!"
