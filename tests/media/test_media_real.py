# tests/media/test_media_real.py — רינדור אמיתי מקצה לקצה דרך שרת המדיה (מדלג כשאין ffmpeg במחשב)
import io, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ["MEDIA_KEY"] = "k"
import media_remote as MR, media_app as MA, social_video as V, social_video_tour as T
if not V.vid_ffmpeg():
    print("skip (no ffmpeg)"); sys.exit(0)
from PIL import Image
def jpg(c):
    b = io.BytesIO(); Image.new("RGB", (1600, 1200), c).save(b, "JPEG"); return b.getvalue()
class Resp:
    def __init__(self, r): self.r, self.status_code = r, r.status_code
    def json(self): return self.r.get_json()
    def iter_content(self, n): yield self.r.data
class Http:
    c = MA.app.test_client()
    def post(self, u, json=None, headers=None, timeout=None): return Resp(self.c.post(u.split("http://m", 1)[1], json=json, headers=headers or {}))
    def get(self, u, headers=None, timeout=None, stream=False): return Resp(self.c.get(u.split("http://m", 1)[1], headers=headers or {}))
ENV = {"MEDIA_URL": "http://m", "MEDIA_KEY": "k"}
texts = {"open": {"title": "דירת 4 חדרים", "place": "נאות אפק, קרית ביאליק"}, "s2": {"main": "4 חד' · 100 מ\"ר"},
         "end": {"agent": "דנה לוי", "phone": "052-1234567", "price": "2,050,000 ₪", "office": "רימקס פמילי"}}
photos = {0: jpg((200, 180, 150)), 1: jpg((120, 150, 190))}
shots = T.tour_plan(texts, [0, 1], {}, ["מעלית", "ממ\"ד"])
out = os.path.join(tempfile.mkdtemp(), "t.mp4")
t0 = time.time()
r = MR.render("tour", {"photos": photos, "shots": shots, "texts": texts, "theme": "full", "music": MR.File(V.vid_music("k1")),
                       "agent_photo": MR.File(None)}, out, ENV, http=Http(), sleep=lambda s: time.sleep(0.5))
assert r["ok"], r
assert os.path.getsize(out) > 50000 and os.path.getsize(r["cover"]) > 2000, (os.path.getsize(out), r)
print("ok tour %.1fs %dKB dur=%s" % (time.time() - t0, os.path.getsize(out) // 1024, r["duration"]))

# הסגנון הרגיל (בלי קליפ AI): שכבות הטקסט נבנות בשרת המדיה
row = {"מספר מודעה": "k1", "עיר": "קרית ביאליק", "רחוב": "עוזי חיטמן", "מחיר": "2050000", "חדרים": "5", "מ\"ר": "142"}
tx = V.vid_texts(row, ["מעלית"], "", "דנה לוי", "0521234567", "046000800")
tl = V.vid_timeline(1, False)
out2 = os.path.join(tempfile.mkdtemp(), "c.mp4")
r = MR.render("classic", {"clip": MR.File(None), "slides": [(photos[0], None), (photos[1], (0.7, 0.8, 1.0, 1.0))], "texts": tx,
                          "timeline": tl, "ai": False, "music": MR.File(V.vid_music("k1"))}, out2, ENV, http=Http(),
              sleep=lambda s: time.sleep(0.5))
assert r["ok"] and os.path.getsize(out2) > 50000 and os.path.exists(r["cover"]), r
print("ok classic %dKB dur=%s" % (os.path.getsize(out2) // 1024, r["duration"]))

# "נמכר"
import social_sold as S
st = S.sold_texts_property(row, "seller")
if st is not None:
    out3 = os.path.join(tempfile.mkdtemp(), "s.mp4")
    r = MR.render("sold", {"kind": "seller", "photo": photos[0], "texts": st, "agents": [{"name": "דנה לוי", "phone": "052-1234567", "photo": MR.File(None)}],
                           "music": MR.File(S.sold_music({}, 0))}, out3, ENV, http=Http(), sleep=lambda s: time.sleep(0.5))
    assert r["ok"] and os.path.getsize(out3) > 30000, r
    print("ok sold %dKB" % (os.path.getsize(out3) // 1024))
else:
    print("sold: texts builder not found — skipped")
