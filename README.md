# ── 小智语音助手服务器 ──
# 自托管 MQTT+UDP 语音服务器，配合 xiaozhi-esp32 固件使用
# 链路: 设备唤醒 → UDP Opus 录音 → NLS 语音识别 → DashScope Qwen → NLS 语音合成 → 设备播放

## 架构

```
Tab5 设备 ←→ MQTT (控制信令) + UDP (Opus 音频流) ←→ Python 服务器
                                                       ├── 阿里云 NLS (STT + TTS)
                                                       └── 阿里云 DashScope (LLM: Qwen)
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

```bash
cp .env.example .env
# 编辑 .env，填入你的阿里云 AccessKey、NLS AppKey、DashScope API Key
```

### 3. 启动 Mosquitto MQTT Broker

```bash
# Ubuntu/Debian
apt install mosquitto
mosquitto -d
```

### 4. 启动服务器

```bash
python server.py
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `NLS_AK_ID` | 阿里云 AccessKey ID |
| `NLS_AK_SECRET` | 阿里云 AccessKey Secret |
| `NLS_APPKEY` | NLS 项目 AppKey |
| `DASHSCOPE_API_KEY` | DashScope API Key (用于 Qwen LLM) |
| `SERVER_IP` | 服务器公网 IP（默认 47.82.148.97） |

## 协议

基于[小智 AI 开源协议](https://github.com/78/xiaozhi-esp32)：

- **MQTT**: `device/#` 主题，hello/listen/tts/goodbye 消息
- **UDP**: AES-128-CTR 加密 Opus 音频帧，16kHz/16bit/mono/60ms
- **包头**: 16 字节 (type + flags + payload_len + ssrc + timestamp + sequence)

## 文件说明

| 文件 | 说明 |
|------|------|
| `server.py` | 主服务器 |
| `test_nls.py` | NLS Token + STT + TTS 测试 |
| `test_stt.py` | DashScope STT 测试 (已弃用，保留参考) |
| `.env.example` | 环境变量模板 |
| `requirements.txt` | Python 依赖 |

## 许可证

MIT
