# tests/social_video/test_pick.py — בחירת תמונות (Claude vision) עם נפילה בטוחה
import os, sys, io, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from PIL import Image
import social_video as V
KEY = "sk-ant-secret"
def jpg():
    b = io.BytesIO(); Image.new("RGB", (1440, 960), (90, 90, 90)).save(b, "JPEG"); return b.getvalue()
IMGS = [jpg() for _ in range(5)]
DESC = "דירה משופצת מהיסוד עם נוף פתוח ומרפסת שמש"

class R:
    def __init__(s, code, j): s.status_code, s._j = code, j; s.text = json.dumps(j)
    def json(s): return s._j
class Http:
    def __init__(s, answer=None, code=200, boom=False): s.answer, s.code, s.boom, s.log = answer, code, boom, []
    def post(s, url, headers=None, json=None, timeout=None):
        s.log.append((url, headers, json))
        if s.boom: raise RuntimeError("down " + KEY)
        return R(s.code, {"content": [{"type": "text", "text": s.answer}]})

good = json.dumps({"ai": 2, "room": "living room", "slides": [0, 3, 4], "highlight": "משופצת מהיסוד",
                   "wm": {"0": [0.03, 0.03, 0.17, 0.13], "2": None}, "skip": [1]})
h = Http("```json\n" + good + "\n```")
p = V.vid_pick(h, KEY, IMGS, DESC, ["מעלית"])
ck(p["ai"] == 2 and p["room"] == "living room" and p["slides"] == [0, 3, 4] and p["highlight"] == "משופצת מהיסוד", p)
ck(p["wm"][0] == (0.03, 0.03, 0.17, 0.13) and p["wm"][2] is None and p["skip"] == [1], p)
url, hd, body = h.log[0]
ck(url == "https://api.anthropic.com/v1/messages" and hd["x-api-key"] == KEY and body["model"] == "claude-sonnet-4-5", (url, body.get("model")))
imgs = [c for c in body["messages"][0]["content"] if c["type"] == "image"]
ck(len(imgs) == 5 and imgs[0]["source"]["media_type"] == "image/jpeg", len(imgs))

bad_hl = json.dumps(dict(json.loads(good), highlight="נוף לים"))
ck(V.vid_pick(Http(bad_hl), KEY, IMGS, DESC, [])["highlight"] == "", "invented highlight dropped")
long_hl = json.dumps(dict(json.loads(good), highlight="דירה משופצת מהיסוד עם נוף פתוח"))
ck(V.vid_pick(Http(long_hl), KEY, IMGS, DESC, [])["highlight"] == "", ">4 words dropped")
ph = json.dumps(dict(json.loads(good), highlight="משופצת 0541234567"))
ck("054" not in V.vid_pick(Http(ph), KEY, IMGS, DESC + " 0541234567", [])["highlight"], "phone scrubbed")
dup = json.dumps(dict(json.loads(good), slides=[2, 3]))
ck(2 not in V.vid_pick(Http(dup), KEY, IMGS, DESC, [])["slides"], "ai not in slides")

def is_fallback(p):
    return p["ai"] == 0 and p["slides"] == [1, 2, 3] and p["highlight"] == "" and p["wm"][0] == V.WM_DEFAULT
ck(is_fallback(V.vid_pick(Http("not json"), KEY, IMGS, DESC, [])), "broken json")
ck(is_fallback(V.vid_pick(Http(json.dumps(dict(json.loads(good), ai=9))), KEY, IMGS, DESC, [])), "ai out of range")
ck(is_fallback(V.vid_pick(Http(boom=True), KEY, IMGS, DESC, [])), "http raises")
ck(is_fallback(V.vid_pick(Http(good, code=500), KEY, IMGS, DESC, [])), "500")
ck(is_fallback(V.vid_pick(None, "", IMGS, DESC, [])), "no key")
two = V.vid_pick(None, "", IMGS[:2], DESC, [])
ck(two["ai"] == 0 and two["slides"] == [1], two)
print("video_pick OK", n)
