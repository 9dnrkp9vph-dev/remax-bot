# tests/social_video/test_fixes.py — תיקוני הביקורת הסופית (התאוששות, fal, מחיר 0, ניסיון חוזר כפול, תווית AI)
import os, sys, time, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
import social_video as V
from _fakes import ROW, make_G, SF
SP.soc_hidden = lambda G: set()
NOW = time.time()
def iso(t): return SP._dt.datetime.fromtimestamp(t, SP._dt.timezone.utc).isoformat()
ENV = {"SOCIAL_MODE": "publish", "META_TOKEN": "mt", "APP_BASE_URL": "https://app", "SOCIAL_VIDEO_STYLE": "classic"}
V._blocked_now = lambda G_, t: False
V._spawn = lambda fn: fn()
STORE = V.VidStore(tempfile.mkdtemp()); V._STORE = STORE

# ── 1: קובץ חסר בלחיצה → "לא זמין", failed, ואפשר ליצור מחדש ──
G, st, sb = make_G()
rec = sb.video_insert({"property_key": "tok1", "status": "pending", "sent_at": iso(NOW - 60), "video_token": "Gone1",
                       "recipients": ["505709865"], "created_at": iso(NOW - 60)})
PUB = []; real_pub = V.vid_publish
V.vid_publish = lambda G_, vid, **kw: PUB.append(vid)
msg = V.vid_on_button(G, "972505709865", "vid:%s:pub" % rec["id"], now=NOW, env=ENV)
ck(msg == "הסרטון לא זמין — צור מחדש" and sb.video_get(rec["id"])["status"] == "failed" and PUB == [], (msg, sb.video_get(rec["id"])))
ck(V.vid_can_create(ROW, sb.video_recent(31), NOW, set(), "manual")[0], "re-create allowed after missing file")
V.vid_publish = real_pub
# vid_publish: הנכס נעלם / אין טוקן → failed; השהיית קצב → publish_at
open(STORE.path("Ok1"), "wb").write(b"x")
r1 = sb.video_insert({"property_key": "gone", "status": "approved", "video_token": "Ok1", "created_at": iso(NOW)})
V.vid_publish(G, r1["id"], now=NOW, env=ENV, store=STORE)
ck(sb.video_get(r1["id"])["status"] == "failed", sb.video_get(r1["id"]))
r2 = sb.video_insert({"property_key": "tok1", "status": "approved", "video_token": "Ok1", "created_at": iso(NOW)})
V.vid_publish(G, r2["id"], now=NOW, env=dict(ENV, META_TOKEN=""), store=STORE)
ck(sb.video_get(r2["id"])["status"] == "failed", sb.video_get(r2["id"]))
r3 = sb.video_insert({"property_key": "tok1", "status": "approved", "video_token": "Ok1", "created_at": iso(NOW)})
G["_load_config"]()["v2_social"] = {"paused_until": NOW + 3600}
V.vid_publish(G, r3["id"], now=NOW, env=ENV, store=STORE)
ck(sb.video_get(r3["id"]).get("publish_at") and sb.video_get(r3["id"])["status"] == "approved", sb.video_get(r3["id"]))
G["_load_config"]()["v2_social"] = {}

# ── 2: שאריות אחרי אתחול ──
G, st, sb = make_G()
sb.videos.append({"id": "s1", "property_key": "tok1", "status": "rendering", "created_at": iso(NOW - 3600), "updated_at": iso(NOW - 3600)})
ck(V.vid_can_create(ROW, sb.video_recent(31), NOW, set(), "manual")[0], "stale rendering does not block")
sb.videos.append({"id": "s2", "property_key": "x", "status": "approved", "decided_at": iso(NOW - 3600), "created_at": iso(NOW - 4000), "updated_at": iso(NOW - 3600)})
sb.videos.append({"id": "s3", "property_key": "y", "status": "publishing", "created_at": iso(NOW - 4000), "updated_at": iso(NOW - 3600)})
sb.videos.append({"id": "s4", "property_key": "z", "status": "approved", "decided_at": iso(NOW - 60), "created_at": iso(NOW - 600), "updated_at": iso(NOW - 60)})
V._recover_stale(G, sb.video_recent(31), NOW)
ck(sb.video_get("s1")["status"] == "failed" and sb.video_get("s2")["status"] == "partial" and sb.video_get("s3")["status"] == "partial", [sb.video_get(x)["status"] for x in ("s1", "s2", "s3")])
ck(sb.video_get("s4")["status"] == "approved", "fresh approved untouched")

# ── 3: שגיאת רשת אחרי ההגשה ל-fal → unknown (בלי ניסיון חוזר) ──
class R:
    def __init__(s, code=200, j=None, content=b""): s.status_code, s._j, s.content = code, j, content; s.text = ""
    def json(s):
        if s._j is None: raise ValueError("bad json")
        return s._j
class Http:
    def __init__(s, steps): s.steps, s.posts = steps, 0
    def post(s, url, **kw): s.posts += 1; return s.steps["submit"]()
    def get(s, url, **kw):
        if url.endswith("/status"): return R(200, {"status": "COMPLETED"})
        if "/requests/" in url: return s.steps["result"]()
        return s.steps["dl"]()
SUBOK = lambda: R(200, {"status_url": "https://q/requests/r/status", "response_url": "https://q/requests/r"})
def boom(): raise ConnectionError("reset")
for steps in ({"submit": lambda: R(200, None)}, {"submit": SUBOK, "result": boom},
              {"submit": SUBOK, "result": lambda: R(200, {"video": {"url": "https://v/x.mp4"}}), "dl": boom}):
    h = Http(steps)
    d, err, cost = V.vid_ai_clip(V.Fal(h, "k", sleep=lambda s: None, clock=lambda: 0), b"j", "room")
    ck(d is None and err == "timeout" and h.posts == 1 and cost == 0.35, (err, h.posts, cost))
# סטטוס בלי שדה status → ממשיכים לחכות (לא כשל ודאי)
clock = {"t": 0}
class Http2(Http):
    def get(s, url, **kw):
        if url.endswith("/status"): return R(400, {"detail": "x"})
        return R(200, {})
h = Http2({"submit": SUBOK})
d, err, cost = V.vid_ai_clip(V.Fal(h, "k", sleep=lambda s: clock.__setitem__("t", clock["t"] + s), clock=lambda: clock["t"]), b"j", "room")
ck(err == "timeout" and h.posts == 1, (err, h.posts))
# עלות נרשמת גם כשה-AI נכשל
G, st, sb = make_G()
V.vid_pick = lambda *a: {"ai": 0, "room": "room", "slides": [1, 2], "highlight": "", "wm": {0: None, 1: None, 2: None, 3: None}, "skip": []}
V.vid_ai_clip = lambda fal, j, room: (None, "timeout", 0.35)
V.vid_compose = lambda clip, slides, layers, tl, music, out, run=None: (open(out, "wb").write(b"m"), {"ok": True, "duration": 14, "cover": out})[1]
V.vid_send_review = lambda *a, **k: []
V.vid_create_one(G, "tok1", "manual", "", http=SF.ImgHttp(), now=NOW, env=dict(ENV, SOCIAL_MODE="preview", FAL_KEY="fk"), store=STORE)
ck(sb.videos[-1]["ai"] is False and sb.videos[-1]["ai_cost_usd"] == 0.35, sb.videos[-1])

# ── 4: מחיר 0 / שטח לא מספרי ──
t = V.vid_texts(dict(ROW, **{"מחיר": "0", 'מ"ר': "—", "חדרים": "abc"}), [], "", "", "", "")
ck(t["open"]["price"] == "" and "0 ₪" not in t["end"]["recap"] and t["s2"]["main"] == "קומה 3" and t["open"]["title"] == "דירה למכירה", t)

# ── 5: ניסיון חוזר — תפיסה אטומית, לחיצה שנייה לא מפרסמת פעמיים ──
from flask import Flask
G, st, sb = make_G(); G["_web_auth"] = lambda: {"drole": "developer", "phone": "505709865"}
CALLS = []
V.vid_publish = lambda G_, vid, **kw: CALLS.append((vid, kw.get("channels")))
app = Flask("x"); V.register(app, G); c = app.test_client()
sb.videos.append({"id": "p1", "property_key": "tok1", "status": "partial", "created_at": iso(NOW - 60), "video_token": "Ok1"})
ck(c.post("/v2/api/social/video/retry", json={"id": "p1"}).json["ok"] and sb.video_get("p1")["status"] == "publishing", sb.video_get("p1"))
ck(c.post("/v2/api/social/video/retry", json={"id": "p1"}).json["ok"] is False and len(CALLS) == 1, CALLS)
V.vid_publish = real_pub
ck("publishing" in V._PUBLISHABLE, V._PUBLISHABLE)
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "effie_v2.py"), encoding="utf-8").read()
i = src.index("function vidRetry(")
ck("VID.busy" in src[i:i + 400], "retry busy guard in UI")

# ── 6: תווית AI רק כשיש AI ──
class H6:
    def __init__(s): s.posts = []
    def post(s, url, data=None, **kw):
        s.posts.append((url, dict(data or {})))
        class RR:
            status_code = 200
            def json(self): return {"id": "C1"}
        return RR()
    def get(s, url, params=None, **kw):
        class RR:
            status_code = 200
            def json(self): return {"status_code": "FINISHED", "permalink": ""}
        return RR()
h = H6(); g = SP.Graph(h, "t", {"SOCIAL_MODE": "publish"}, sleep=lambda s: None)
g.ig_video("IG", "STORIES", "u", ai=False)
ck("is_ai_generated" not in h.posts[0][1], h.posts[0])
h = H6(); g = SP.Graph(h, "t", {"SOCIAL_MODE": "publish"}, sleep=lambda s: None)
g.ig_video("IG", "REELS", "u", ai=True)
ck(h.posts[0][1].get("is_ai_generated") == "true", h.posts[0])
print("video_fixes OK", n)
