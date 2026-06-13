#!/bin/bash
# xiaozhi-client 断连自动重启看门狗
# xiaozhi.me 会空闲超时关闭 WebSocket (1006)，且 xiaozhi-client 不会自动重连

LOG_FILE="/var/log/xiaozhi_client.log"
RESTART_COOLDOWN=60  # 两次重启之间最少间隔秒数，避免死循环

last_restart=0

while true; do
  if [ -f "$LOG_FILE" ]; then
    # 取最后一条连接/断连状态行
    last_status=$(grep -E "端点连接成功|连接已关闭" "$LOG_FILE" | tail -1)

    if echo "$last_status" | grep -q "连接已关闭"; then
      now=$(date +%s)
      if [ $((now - last_restart)) -ge $RESTART_COOLDOWN ]; then
        echo "[$(date)] WebSocket 已断开，重启 xiaozhi-client..."
        cd /opt/xiaozhi-mcp
        xiaozhi stop 2>/dev/null
        sleep 2
        nohup xiaozhi start >> "$LOG_FILE" 2>&1 &
        last_restart=$now
        echo "[$(date)] 重启完成"
      fi
    elif echo "$last_status" | grep -q "端点连接成功"; then
      :  # 连接正常，无需操作
    fi
  fi
  sleep 15
done
