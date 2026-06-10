import json, hmac, hashlib, base64, time, uuid, urllib.request, os
from email.utils import formatdate

# Load .env if present
def _load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1)
                os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
_load_env()

AK_ID = os.environ.get("NLS_AK_ID", "")
AK_SECRET = os.environ.get("NLS_AK_SECRET", "")
APPKEY = os.environ.get("NLS_APPKEY", "")

def get_token():
    url = "https://nls-meta.cn-shanghai.aliyuncs.com/pop/2018-05-18/tokens"
    nonce = str(uuid.uuid4())
    date_str = formatdate(timeval=time.time(), localtime=False, usegmt=True)

    canonical_headers = f"x-acs-signature-method:HMAC-SHA1\nx-acs-signature-nonce:{nonce}\nx-acs-signature-version:1.0\n"
    sign_str = f"POST\n\n\napplication/json\n{date_str}\n{canonical_headers}/pop/2018-05-18/tokens"
    signature = base64.b64encode(hmac.new(AK_SECRET.encode(), sign_str.encode(), hashlib.sha1).digest()).decode()

    headers = {
        "Authorization": f"acs {AK_ID}:{signature}",
        "Date": date_str,
        "Content-Type": "application/json",
        "x-acs-signature-method": "HMAC-SHA1",
        "x-acs-signature-version": "1.0",
        "x-acs-signature-nonce": nonce,
    }

    print(f"Sign string:\n{sign_str}")
    print(f"\nSignature: {signature[:40]}...")

    try:
        req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
        r = urllib.request.urlopen(req, timeout=10)
        raw = r.read()
        print(f"Status: {r.status}")
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        token_node = root.find('.//Token/Id')
        if token_node is not None:
            token = token_node.text
            expire = root.find('.//Token/ExpireTime')
            exp_str = expire.text if expire is not None else "unknown"
            print(f"\nToken: {token}")
            print(f"Expires: {exp_str} ({int(exp_str) - int(time.time())}s remaining)" if exp_str != "unknown" else "")
            return token
        print("Token Id not found in XML")
        return None
    except urllib.error.HTTPError as e:
        print(f"\nHTTP {e.code}: {e.read().decode()[:500]}")
        return None
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        return None

print("=== Getting NLS Token ===")
token = get_token()

if token:
    print(f"\nSUCCESS - Token: {token[:30]}...")

    # Test STT
    print(f"\n=== Testing STT ===")
    params = f"appkey={APPKEY}&format=pcm&sample_rate=16000&enable_punctuation_prediction=true"
    stt_url = f"https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr?{params}"
    pcm = b'\x00' * 16000 * 2
    try:
        req = urllib.request.Request(stt_url, data=pcm, headers={"X-NLS-Token": token, "Content-Type": "application/octet-stream"})
        r = urllib.request.urlopen(req, timeout=10)
        print(f"STT: {r.read().decode()[:500]}")
    except urllib.error.HTTPError as e:
        print(f"STT HTTP {e.code}: {e.read().decode()[:500]}")
    except Exception as e:
        print(f"STT error: {e}")

    # Test TTS
    print(f"\n=== Testing TTS ===")
    from urllib.parse import quote
    text = "你好世界"
    tts_url = f"https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts?appkey={APPKEY}&text={quote(text)}&token={token}&format=pcm&sample_rate=16000&voice=ruoxi"
    try:
        req = urllib.request.Request(tts_url)
        r = urllib.request.urlopen(req, timeout=10)
        data = r.read()
        print(f"TTS: {len(data)} bytes received")
        if data[:4] == b"RIFF":
            print("WAV format detected")
    except urllib.error.HTTPError as e:
        print(f"TTS HTTP {e.code}: {e.read().decode()[:500]}")
    except Exception as e:
        print(f"TTS error: {e}")
