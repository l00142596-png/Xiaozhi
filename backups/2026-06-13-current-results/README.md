# 2026-06-13/14 Current Results Backup

This backup preserves the current Xiaozhi work before and after ESP32 UI/audio/battery changes.

## xiaozhi-esp32

- `xiaozhi-esp32-tracked.diff`: tracked file changes from the official `78/xiaozhi-esp32` clone.
- `xiaozhi-esp32-status.txt`: working tree status at backup time.
- `xiaozhi-esp32-untracked/`: relevant untracked source/scripts, excluding build output.

Current major work included in the patch:

- MQTT endpoint restored to config-driven behavior.
- M5Stack Tab5 INA226 battery driver and battery charge/discharge logic work.
- Incoming audio state gate removed earlier.
- Local playback queue is cleared immediately when aborting speech.
- Residual incoming TTS audio is dropped after abort until next TTS start.
- Tab5 short touch tap stops playback while speaking and stops listening while listening.
- Multiline subtitle mode enabled for Tab5 and current sdkconfig; bottom subtitle card wraps text, caps height, and uses tighter line spacing.
- Display clears stale battery icon when the board reports no valid battery, avoiding the no-battery 70% ghost icon.

Build and flash status:

- Build succeeded with ESP-IDF 5.5.2 for ESP32-P4.
- `build/xiaozhi.bin` generated successfully.
- Flash to COM7 succeeded on 2026-06-14.

Note: `build/` and `build_tab5/` are intentionally not backed up because they are generated build output.

## xiaozhi-mcp-bridge / KB MCP

- `kb_server_v2.py`: FastMCP knowledge-base server using `DASHSCOPE_API_KEY` from environment.
- `restart_v2*.sh`, `remote_prepare_kb.sh`, `test_rag.sh`, watchdog scripts: deployment/helper scripts.
- `xiaozhi.config.sanitized.json`: token/key-redacted config snapshot.

Remote VPS deployment status at backup time:

- KB MCP runs on `/opt/xiaozhi-mcp`.
- systemd services enabled: `xiaozhi-kb.service`, `xiaozhi-client.service`.
- KB SSE URL: `http://127.0.0.1:8766/sse`.
- Exposed tools only: `save_knowledge`, `search_knowledge`, `list_all_knowledge`, `search_regulation`.
- RAG files exist remotely under `/opt/xiaozhi-mcp/rag/`.

Secrets intentionally excluded or redacted:

- DashScope API key.
- Xiaozhi cloud MCP endpoint token.
- Runtime cache and tool call logs.