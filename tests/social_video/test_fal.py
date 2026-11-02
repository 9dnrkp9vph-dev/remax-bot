# tests/social_video/test_fal.py — לקוח fal: queue → polling → הורדה; ניסיון חוזר זהיר; המפתח לא דולף
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_video as V
KEY = "secret-fal-key-123"

class R:
    def __init__(s, code=200, j=None, content=b""): s.status_code, s._j, s.content = code, j, content; s.text = json.dumps(j) if j is not None else ""
    def json(s): return s._j
class Http:
    def __init__(s, script): s.script, s.log = script, []
    def post(s, url, headers=None, json=None, timeout=None):
        s.log.append(("POST", url, headers, json)); return s.script["submit"].pop(0)
    def get(s, url, headers=None, timeout=None):
        s.log.append(("GET", url, headers, None))
        if url.endswith("/status"): return s.script["status"].pop(0)
        if "/requests/" in url: return R(200, {"video": {"url": "https://v3b.fal.media/x.mp4"}})
        return R(200, None, b"MP4DATA")
SUB = lambda: R(200, {"status_url": "https://queue.fal.run/fal-ai/kling-video/requests/r1/status",
                      "response_url": "https://queue.fal.run/fal-ai/kling-video/requests/r1"})
clock = {"t": 0}
def sleep(s): clock["t"] += s
def now(): return clock["t"]

h = Http({"submit": [SUB()], "status": [R(200, {"status": "IN_QUEUE"}), R(200, {"status": "IN_PROGRESS"}), R(200, {"status": "COMPLETED"})]})
f = V.Fal(h, KEY, sleep=sleep, clock=now)
ck(f.clip(b"\xff\xd8jpg", "prompt") == b"MP4DATA", "ok")
m, url, hd, body = h.log[0]
ck(url == "https://queue.fal.run/" + V.FAL_DEFAULT_MODEL and hd["Authorization"] == "Key " + KEY, (url, hd))
ck(body["image_url"].startswith("data:image/jpeg;base64,") and body["duration"] == "5" and "people" in body["negative_prompt"], body)
ck(all(KEY not in str(x[1]) and KEY not in json.dumps(x[3] or {}) for x in h.log), "key only in header")
hl = V.Fal(Http({"submit": []}), KEY, model="fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video")
ck(hl.args()["duration"] == "6" and hl.args()["prompt_optimizer"] is False, hl.args())
ck(V.Fal(None, KEY).cost() == 0.35 and hl.cost() == 0.19, "cost")

# כשל ודאי ואז הצלחה → submit פעמיים
clock["t"] = 0
h2 = Http({"submit": [SUB(), SUB()], "status": [R(200, {"status": "FAILED"}), R(200, {"status": "COMPLETED"})]})
data, err, cost = V.vid_ai_clip(V.Fal(h2, KEY, sleep=sleep, clock=now), b"jpg", "living room")
ck(data == b"MP4DATA" and err is None and abs(cost - 0.70) < 1e-9, (data, err, cost))
ck(sum(1 for x in h2.log if x[0] == "POST") == 2, "two submits")

# timeout → unknown, בלי ניסיון חוזר
clock["t"] = 0
h3 = Http({"submit": [SUB(), SUB()], "status": [R(200, {"status": "IN_PROGRESS"})] * 200})
data, err, cost = V.vid_ai_clip(V.Fal(h3, KEY, sleep=sleep, clock=now), b"jpg", "living room")
ck(data is None and err == "timeout" and sum(1 for x in h3.log if x[0] == "POST") == 1, (err, h3.log[:1]))
ck(cost == 0.35, cost)   # נשלח ועלול להיות מחויב

# 402 → בלי ניסיון שני
h4 = Http({"submit": [R(402, {"detail": "Insufficient balance " + KEY})]})
data, err, cost = V.vid_ai_clip(V.Fal(h4, KEY, sleep=sleep, clock=now), b"jpg", "living room")
ck(data is None and err == 402 and cost == 0 and len(h4.log) == 1, (err, cost))
try:
    V.Fal(Http({"submit": [R(402, {"detail": "x " + KEY})]}), KEY, sleep=sleep, clock=now).clip(b"j", "p")
    ck(False, "should raise")
except V.FalError as e:
    ck(KEY not in str(e) and e.code == 402, str(e))

ck("living room" in V.vid_prompt("living room") and "keep the room exactly as in the photo" in V.vid_prompt("living room"), "prompt")
ck("facade" in V.vid_prompt("building facade") and "keep the building exactly" in V.vid_prompt("building facade"), "facade prompt")
ck(V.vid_prompt("") == V.vid_prompt("room"), "default room")
print("video_fal OK", n)
