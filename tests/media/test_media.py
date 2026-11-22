# tests/media/test_media.py — [22/11] שרת המדיה: אפי שולחת חומרים, מקבלת סרטון + שער; בלי מפתח אין כניסה;
# בלי MEDIA_URL הכל מקומי כמו קודם; כשל בשרת המדיה = הסרטון נכשל עם הודעה, אפי לא נופלת.
import io, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m=""):
    global n; assert c, m; n += 1
os.environ["MEDIA_KEY"] = "k-test"
import media_remote as MR
import media_app as MA
import social_video as V

# ── קידוד הלוך-חזור ──
d = tempfile.mkdtemp()
fp = os.path.join(d, "a.mp3"); open(fp, "wb").write(b"MUSIC")
src = {"photos": {0: b"\xff\xd8A", 3: b"\xff\xd8B"}, "slides": [(b"x", (0.1, 0.2, 0.3, 0.4)), (b"y", None)],
       "music": MR.File(fp), "none": MR.File(None), "gone": MR.File("/no/such"), "t": "שלום", "n": 3,
       "agents": {"seller": [{"name": "דנה", "photo": MR.File(fp)}]}}
enc = MR.encode(src)
import json; enc = json.loads(json.dumps(enc))   # עובר JSON אמיתי
out = MR.decode(enc, tempfile.mkdtemp())
ck(out["photos"] == {0: b"\xff\xd8A", 3: b"\xff\xd8B"}, out["photos"])
ck(out["slides"][0][0] == b"x" and out["slides"][0][1] == [0.1, 0.2, 0.3, 0.4] and out["slides"][1][1] is None)
ck(open(out["music"], "rb").read() == b"MUSIC" and out["music"].endswith(".mp3"))
ck(out["none"] is None and out["gone"] is None and out["t"] == "שלום" and out["n"] == 3)
ck(open(out["agents"]["seller"][0]["photo"], "rb").read() == b"MUSIC")

ck(not MR.enabled({}) and not MR.enabled({"MEDIA_URL": "http://m"}) and MR.enabled({"MEDIA_URL": "http://m/", "MEDIA_KEY": "k"}))
ck(MR.url({"MEDIA_URL": "http://m/"}) == "http://m")

# ── http מדומה מעל שרת המדיה האמיתי (Flask test client) ──
class Resp:
    def __init__(self, r): self.r, self.status_code = r, r.status_code
    def json(self): return self.r.get_json()
    def iter_content(self, n): yield self.r.data
class Http:
    def __init__(self): self.c, self.calls = MA.app.test_client(), []
    def _p(self, u): return u.split("http://m", 1)[1]
    def post(self, u, json=None, headers=None, timeout=None):
        self.calls.append(("POST", self._p(u))); return Resp(self.c.post(self._p(u), json=json, headers=headers or {}))
    def get(self, u, headers=None, timeout=None, stream=False):
        self.calls.append(("GET", self._p(u))); return Resp(self.c.get(self._p(u), headers=headers or {}))
ENV = {"MEDIA_URL": "http://m", "MEDIA_KEY": "k-test"}
seen = {}
def fake_compose(kind, a, out_path):
    seen.update(kind=kind, a=a, music=open(a["music"], "rb").read() if a.get("music") else None)
    open(out_path, "wb").write(b"V" * 5000)
    cover = out_path.rsplit(".", 1)[0] + "-cover.jpg"; open(cover, "wb").write(b"C" * 10)
    return {"ok": True, "duration": 12.5, "cover": cover}
MA.compose = fake_compose
outp = os.path.join(tempfile.mkdtemp(), "tok.mp4")
h = Http()
r = MR.render("tour", {"photos": {1: b"img"}, "music": MR.File(fp), "theme": "full"}, outp, ENV, http=h, sleep=lambda s: time.sleep(0.05))
ck(r["ok"] and r["duration"] == 12.5 and r["cover"] == outp[:-4] + "-cover.jpg", r)
ck(open(outp, "rb").read() == b"V" * 5000 and open(r["cover"], "rb").read() == b"C" * 10)
ck(seen["kind"] == "tour" and seen["a"]["photos"] == {1: b"img"} and seen["music"] == b"MUSIC")
ck(not MA.JOBS, "job cleaned after download")

# כשל ברינדור → הודעה, בלי קובץ
MA.compose = lambda kind, a, out_path: {"ok": False, "error": "ffmpeg: boom"}
r = MR.render("classic", {}, os.path.join(tempfile.mkdtemp(), "x.mp4"), ENV, http=Http(), sleep=lambda s: time.sleep(0.05))
ck(r == {"ok": False, "error": "ffmpeg: boom"}, r)
def crash(kind, a, out_path): raise ValueError("x")
MA.compose = crash
r = MR.render("sold", {}, os.path.join(tempfile.mkdtemp(), "x.mp4"), ENV, http=Http(), sleep=lambda s: time.sleep(0.05))
ck(not r["ok"] and "ValueError" in r["error"], r)

# מפתח שגוי / חסר; סוג לא מוכר; שרת לא עונה
r = MR.render("tour", {}, outp, {"MEDIA_URL": "http://m", "MEDIA_KEY": "wrong"}, http=Http())
ck(not r["ok"] and "403" in r["error"] and MR.BUSY in r["error"], r)
c = MA.app.test_client()
ck(c.post("/render", json={"kind": "tour"}).status_code == 403 and c.get("/job/x").status_code == 403)
ck(c.post("/render", json={"kind": "zzz"}, headers={"X-Media-Key": "k-test"}).status_code == 400)
ck(c.get("/job/nope", headers={"X-Media-Key": "k-test"}).status_code == 404)
hj = c.get("/health").get_json(); ck(hj["ok"] and hj["key"] is True, hj)
class Dead:
    def post(self, *a, **k): raise ConnectionError("down")
r = MR.render("tour", {}, outp, ENV, http=Dead())
ck(not r["ok"] and MR.BUSY in r["error"], r)
os.environ["MEDIA_KEY"] = ""
ck(c.post("/render", json={"kind": "tour"}, headers={"X-Media-Key": ""}).status_code == 503, "no key configured = closed")
os.environ["MEDIA_KEY"] = "k-test"

# תור מלא → 429; ניקוי עבודות ישנות
MA.JOBS.clear()
for i in range(MA.MAX_QUEUE):
    MA.JOBS["q%d" % i] = {"status": "queued", "dir": tempfile.mkdtemp(), "ts": time.time()}
ck(c.post("/render", json={"kind": "tour"}, headers={"X-Media-Key": "k-test"}).status_code == 429)
MA.JOBS.clear()
dd = tempfile.mkdtemp(); MA.JOBS["old"] = {"status": "done", "dir": dd, "ts": time.time() - MA.KEEP_S - 5}
MA._sweep(); ck("old" not in MA.JOBS and not os.path.exists(dd))

# הגנת הזיכרון באפי לא חוסמת כשהרינדור מרוחק
MB = 1 << 20
ck(V.vid_mem_ok(ENV, (2000 * MB, 2048 * MB)) == (True, None))
ck(V.vid_mem_ok({}, (2000 * MB, 2048 * MB))[0] is False)

# שרת המדיה לא טוען את אפי ולא מריץ לולאות
ck("app" not in sys.modules and "effie_v2" not in sys.modules, "media server must not import the main app")
print("ok", n)
