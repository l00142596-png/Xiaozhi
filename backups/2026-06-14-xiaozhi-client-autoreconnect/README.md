# xiaozhi-client 2.3.0 auto reconnect hotfix

Patched on 2026-06-14.

Files patched on Aliyun:
- /usr/lib/node_modules/xiaozhi-client/dist/backend/WebServer.js
- /usr/lib/node_modules/xiaozhi-client/dist/backend/WebServerLauncher.js

Reason:
- The endpoint WebSocket closes with code 1006.
- xiaozhi-client marks the endpoint disconnected but does not reconnect.

Behavior added:
- On abnormal close codes except 1000/1001, schedule one reconnect after reconnectDelay.
- Avoid duplicate reconnect timers with _autoReconnectTimer.
- Keep systemd watchdog as a fallback.

Backups on Aliyun:
- WebServer.js.bak.autoreconnect.*
- WebServerLauncher.js.bak.autoreconnect.*
