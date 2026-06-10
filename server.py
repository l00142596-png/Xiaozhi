import json,os,threading,uuid,struct,time,logging,socket,select,base64,io,urllib.request
import paho.mqtt.client as mqtt
import opuslib
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(levelname)s] %(message)s")
log=logging.getLogger("xiaozhi")

# ── 环境变量 / .env 加载 ──
def _load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1)
                os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
_load_env()

IP=os.environ.get("SERVER_IP","47.82.148.97")
UDP_BASE=19000

try:
 from Crypto.Cipher import AES
 def aes(k,n,d):
  c=AES.new(k,AES.MODE_ECB);r=bytearray();t=bytearray(n[:16])
  for i in range(0,len(d),16):
   ks=c.encrypt(bytes(t))
   for j,b in enumerate(d[i:i+16]):r.append(b^ks[j])
   for j in range(15,-1,-1):
    t[j]=(t[j]+1)&0xFF
    if t[j]!=0:break
  return bytes(r)
except:
 def aes(k,n,d):return d

S=16000;F=60;Z=int(S*F/1000)

# ── DashScope (LLM) ──
API_KEY=os.environ.get("DASHSCOPE_API_KEY","")
LLM_URL="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# ── NLS (STT + TTS) ──
NLS_AK_ID=os.environ.get("NLS_AK_ID","")
NLS_AK_SECRET=os.environ.get("NLS_AK_SECRET","")
NLS_APPKEY=os.environ.get("NLS_APPKEY","")
NLS_TOKEN=None;NLS_TOKEN_EXPIRY=0

def get_nls_token():
 import hmac,hashlib,base64 as b64
 from email.utils import formatdate
 global NLS_TOKEN,NLS_TOKEN_EXPIRY
 if NLS_TOKEN and time.time()+60<NLS_TOKEN_EXPIRY:
  return NLS_TOKEN
 nonce=str(uuid.uuid4());date_str=formatdate(timeval=time.time(),localtime=False,usegmt=True)
 ch=f"x-acs-signature-method:HMAC-SHA1\nx-acs-signature-nonce:{nonce}\nx-acs-signature-version:1.0\n"
 sign_str=f"POST\n\n\napplication/json\n{date_str}\n{ch}/pop/2018-05-18/tokens"
 sig=b64.b64encode(hmac.new(NLS_AK_SECRET.encode(),sign_str.encode(),hashlib.sha1).digest()).decode()
 h={"Authorization":f"acs {NLS_AK_ID}:{sig}","Date":date_str,"Content-Type":"application/json",
    "x-acs-signature-method":"HMAC-SHA1","x-acs-signature-version":"1.0","x-acs-signature-nonce":nonce}
 try:
  import xml.etree.ElementTree as ET
  r=urllib.request.urlopen(urllib.request.Request("https://nls-meta.cn-shanghai.aliyuncs.com/pop/2018-05-18/tokens",data=b"",headers=h,method="POST"),timeout=10)
  root=ET.fromstring(r.read())
  node=root.find('.//Token/Id')
  if node is not None:
   NLS_TOKEN=node.text
   exp=root.find('.//Token/ExpireTime')
   NLS_TOKEN_EXPIRY=int(exp.text) if exp is not None else 0
   log.info(f"NLS token: {NLS_TOKEN[:8]}... expires in {NLS_TOKEN_EXPIRY-time.time():.0f}s")
  return NLS_TOKEN
 except Exception as e:
  log.error(f"NLS token error: {e}")
  return None

class P:
 def stt(self,pcm):
  if not pcm or len(pcm)<1600:
   log.warning("STT: audio too short (%d bytes)",len(pcm))
   return ""
  t=get_nls_token()
  if not t:
   log.error("STT: no NLS token")
   return ""
  params=f"appkey={NLS_APPKEY}&format=pcm&sample_rate=16000&enable_punctuation_prediction=true&enable_inverse_text_normalization=true"
  try:
   r=urllib.request.urlopen(urllib.request.Request(
    f"https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr?{params}",
    data=pcm,headers={"X-NLS-Token":t,"Content-Type":"application/octet-stream"}),timeout=30)
   resp=json.loads(r.read())
   text=resp.get("result","")
   if text:
    log.info(f"STT: {text}")
    return text
   log.warning(f"STT empty: {json.dumps(resp,ensure_ascii=False)[:200]}")
   return ""
  except Exception as e:
   log.error(f"STT error: {e}")
   return ""

 def llm(self,text):
  if not text:
   return "请再说一遍。"
  req=json.dumps({"model":"qwen-plus","messages":[
   {"role":"system","content":"你是小五，一名铁路施工安全AI助手。精通铁路工程施工安全技术规程。用中文简洁回答，专业准确，控制在100字以内。不要自我介绍，直接回答。记住：你就是小五。"},
   {"role":"user","content":text}
  ]}).encode()
  h={"Authorization":f"Bearer {API_KEY}","Content-Type":"application/json"}
  try:
   r=urllib.request.urlopen(urllib.request.Request(LLM_URL,data=req,headers=h),timeout=20)
   resp=json.loads(r.read())
   reply=resp.get("choices",[{}])[0].get("message",{}).get("content","")
   if reply:
    log.info(f"LLM: {reply}")
    return reply
   log.warning(f"LLM empty: {json.dumps(resp,ensure_ascii=False)[:200]}")
   return "抱歉，我暂时无法回答。"
  except Exception as e:
   log.error(f"LLM error: {e}")
   return "网络好像不太好，请稍后再试。"

 def tts(self,text):
  if not text:
   log.warning("TTS: empty text")
   return b""
  t=get_nls_token()
  if not t:
   log.error("TTS: no NLS token")
   return b""
  from urllib.parse import quote
  url=f"https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts?appkey={NLS_APPKEY}&text={quote(text)}&token={t}&format=pcm&sample_rate=16000&voice=ruoxi"
  try:
   r=urllib.request.urlopen(urllib.request.Request(url),timeout=30)
   data=r.read()
   # NLS TTS returns raw PCM (not WAV) when format=pcm
   if data[:4]==b'RIFF':
    # Strip WAV header: find "data" chunk
    idx=data.find(b'data')
    if idx>=0:
     data=data[idx+8:]
   log.info(f"TTS: {len(data)} bytes PCM")
   return data
  except Exception as e:
   log.error(f"TTS error: {e}")
   return b""

p=P()
sessions={}
MAX_SESSIONS=50

class Session:
 def __init__(self,sid,topic,k,n,port):
  self.session_id=sid;self.topic=topic;self.aes_key=bytes.fromhex(k)
  self.aes_nonce=bytes.fromhex(n);self.udp_port=port
  self.audio_frames=[];self.sequence=0;self.device_addr=None;self.sock=None
  self.audio_event=threading.Event()  # signaled when device sends listen/stop

c=None
def on_connect(m,ud,f,rc):log.info(f"Connected {rc}");m.subscribe("device/#")

def udp_handler():
    while True:
        socks = {}
        for sid, s in list(sessions.items()):
            if s.sock:
                socks[sid] = s.sock
        if not socks:
            time.sleep(0.1); continue
        try:
            r,_,_ = select.select(list(socks.values()),[],[],0.5)
            for sock in r:
                for sid,s in list(sessions.items()):
                    if s.sock==sock:
                        try:
                            data,addr = sock.recvfrom(2048)
                            s.device_addr=addr
                            if data and len(data)>=16:
                                dec=aes(s.aes_key,data[:16],data[16:])
                                s.audio_frames.append(bytes(dec))
                        except Exception as e:
                            log.warning("UDP error: %s", e)
                        break
        except: pass

def send_tts_audio(sess,reply,tts_pcm,stt_text=""):
 # Send STT text → device displays it
 if stt_text:
  c.publish(sess.topic,json.dumps({"type":"tts","state":"sentence_start","text":stt_text}))
 # Send TTS start via MQTT
 c.publish(sess.topic,json.dumps({"type":"tts","state":"start"}))
 c.publish(sess.topic,json.dumps({"type":"tts","state":"sentence_start","text":reply}))
 time.sleep(0.3)  # Wait for device main loop to transition to Speaking state

 # Pre-encode all Opus frames (much faster than per-frame encode+send)
 encoder=opuslib.Encoder(S,1,'voip')
 frames=[];seq=0;ts=0
 for off in range(0,len(tts_pcm),Z*2):
  f=tts_pcm[off:off+Z*2]
  if len(f)<Z*2:f+=b'\x00'*(Z*2-len(f))
  od=encoder.encode(f,Z)
  hdr=bytearray(16);hdr[0]=0x01
  struct.pack_into('>H',hdr,2,len(od))
  struct.pack_into('>I',hdr,8,ts)
  struct.pack_into('>I',hdr,12,seq)
  enc=aes(sess.aes_key,bytes(hdr),bytes(od))
  frames.append(bytes(hdr)+enc)
  seq+=1;ts+=Z

 log.info("Sending %d TTS frames (%d bytes PCM)",len(frames),len(tts_pcm))
 # Send frames with near-real-time pacing (~50ms/frame for 60ms Opus frames)
 for i,pkt in enumerate(frames):
  if sess.device_addr and sess.sock:
   try:sess.sock.sendto(pkt,sess.device_addr)
   except:pass
  if i<len(frames)-1:time.sleep(0.048)  # ~50ms/frame (near real-time)

 c.publish(sess.topic,json.dumps({"type":"tts","state":"stop"}))
 log.info("TTS done")

def process_audio(sess):
 log.info("Waiting for audio (max 8s)...")
 sess.audio_event.wait(timeout=8)  # wakes early on listen/stop
 if sess.session_id not in sessions:
  return
 log.info("Processing audio: %d opus frames",len(sess.audio_frames))
 if not sess.audio_frames:
  log.warning("No audio data")
  return
 # Decode Opus frames → PCM for STT
 decoder=opuslib.Decoder(S,1)
 pcm=bytearray()
 for frame in sess.audio_frames:
  try:pcm.extend(decoder.decode(frame,Z))
  except:pass
 pcm=bytes(pcm)
 # Debug: save decoded PCM for diagnostics
 try:
  with open("/tmp/debug_pcm.raw","wb") as f:f.write(pcm)
  log.info("Debug PCM saved: %d bytes to /tmp/debug_pcm.raw",len(pcm))
 except:pass

 text=p.stt(pcm)
 if not text:
  log.warning("STT returned empty")
  # Send fallback message instead of just returning
  fallback="没听清，请再说一遍。"
  fallback_pcm=p.tts(fallback)
  send_tts_audio(sess,fallback,fallback_pcm,"")
  sess.audio_frames=[]
  return

 log.info(f"STT: {text}")
 reply=p.llm(text)
 if not reply:
  log.warning("LLM returned empty")
  fallback="抱歉，我暂时无法回答。"
  fallback_pcm=p.tts(fallback)
  send_tts_audio(sess,fallback,fallback_pcm,"")
  sess.audio_frames=[]
  return

 log.info(f"LLM: {reply}")
 tts_pcm=p.tts(reply)
 send_tts_audio(sess,reply,tts_pcm,text)

 # Reset audio buffer for continuous conversation (auto mode)
 sess.audio_frames=[]
 log.info("Session %s ready for next round",sess.session_id[:8])

def on_message(m,ud,msg):
 try:
  d=json.loads(msg.payload)
  if not isinstance(d,dict):return
 except:return
 mt=d.get("type");log.info(f"<< {mt}")
 # Skip hello responses (loop prevention)
 if mt=="hello" and "session_id" in d:
  log.info("Skipping hello response (loop prevention)")
  return
 if mt=="hello":
  # Clean session for this topic only
  for sid, s in list(sessions.items()):
   if s.topic == msg.topic:
    if s.sock: s.sock.close()
    del sessions[sid]
  sid=str(uuid.uuid4())
  port=UDP_BASE
  k=os.urandom(16).hex();n=os.urandom(16).hex()
  us=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  us.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  try:
   us.bind(("0.0.0.0",port))
  except OSError:
   for offset in range(1,100):
    try:
     us.bind(("0.0.0.0",UDP_BASE+offset))
     port=UDP_BASE+offset
     break
    except: pass
  us.setblocking(False)
  sess=Session(sid,msg.topic,k,n,port);sess.sock=us
  sessions[sid]=sess
  resp=json.dumps({"type":"hello","session_id":sid,"transport":"udp",
   "audio_params":{"sample_rate":16000,"frame_duration":60},
   "udp":{"server":IP,"port":port,"encryption":"aes-128-ctr","key":k,"nonce":n}})
  m.publish(msg.topic,resp);log.info(f"Session {sid}: UDP {port}")
 elif mt=="listen":
  state=d.get("state","")
  if state=="start":
   sid=d.get("session_id","")
   log.info(f"Listen start for session {sid[:8]}")
   if sid in sessions:
    sess=sessions[sid];sess.audio_event.clear()
    threading.Thread(target=process_audio,args=(sess,),daemon=True).start()
   else:
    log.warning(f"Session {sid[:8]} not found (may have been cleaned up)")
  elif state=="stop":
   sid=d.get("session_id","")
   if sid in sessions:
    sessions[sid].audio_event.set()
    log.info("Listen stop → waking audio processing")
 elif mt=="goodbye":
  sid=d.get("session_id","")
  if sid in sessions:
   sessions[sid].audio_event.set()
   log.info("Goodbye → waking audio processing")

def main():
 global c
 # Validate credentials
 missing=[]
 if not NLS_AK_ID: missing.append("NLS_AK_ID")
 if not NLS_AK_SECRET: missing.append("NLS_AK_SECRET")
 if not NLS_APPKEY: missing.append("NLS_APPKEY")
 if not API_KEY: missing.append("DASHSCOPE_API_KEY")
 if missing:
  log.error("Missing env vars: %s — set them in .env or environment",", ".join(missing))
  log.error("Copy .env.example to .env and fill in your credentials")
  return

 log.info("=== XiaoZhi Cloud Server v7 ===")
 log.info("Server IP: %s",IP)
 c=mqtt.Client();c.on_connect=on_connect;c.on_message=on_message
 c.connect("127.0.0.1",1883,60)
 threading.Thread(target=udp_handler,daemon=True).start()
 log.info("UDP handler started, Waiting...")
 c.loop_forever()
main()
