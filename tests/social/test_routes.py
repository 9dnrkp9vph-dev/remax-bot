# tests/social/test_routes.py — register(app, G): הרשאות, publish, preview, status, health, תמונות
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from flask import Flask
import social_publish as SP
from _fakes import ROW, make_G, FakeGraph, ImgHttp
SP.Graph = FakeGraph
SP.soc_hidden = lambda G: set()
SP._HTTP = ImgHttp()
os.environ.pop("META_TOKEN", None); os.environ["SOCIAL_MODE"] = "preview"; os.environ["SOCIAL_AUTO"] = "0"
SESS = {"t": None}
G, st, sb = make_G()
G["_web_auth"] = lambda: SESS["t"]
RUNS = []
real_run = SP.soc_run_one
SP.soc_run_one = lambda G, key, trigger, by_phone, channels=None, **kw: (RUNS.append((key, trigger, by_phone, channels)), {"ok": True})[1]
SP._spawn = lambda fn: fn()          # thread → סינכרוני בבדיקה
app = Flask(__name__); SP.register(app, G); c = app.test_client()
DEV = {"name": "אייל", "role": "admin", "drole": "developer", "phone": "505709865"}
MGR = {"name": "מתן", "role": "admin", "drole": "manager", "phone": "544448065"}
AG = {"name": "דנה", "role": "agent", "drole": "agent", "phone": "501111111"}

for path, meth in (("/v2/api/social/publish", "post"), ("/v2/api/social/preview?key=tok1", "get"),
                   ("/v2/api/social/status?keys=tok1", "get"), ("/v2/api/social/health", "get")):
    SESS["t"] = None; ck(getattr(c, meth)(path, json={"key": "tok1"}).status_code == 401, path)
    for s in (AG, MGR):
        SESS["t"] = s; ck(getattr(c, meth)(path, json={"key": "tok1"}).status_code == 403, (path, s["drole"]))
SESS["t"] = DEV
r = c.post("/v2/api/social/publish", json={"key": "L:tok1", "channels": ["ig"]})
ck(r.status_code == 200 and r.get_json()["queued"] and RUNS[-1] == ("tok1", "manual", "505709865", ["ig"]), (r.get_json(), RUNS))

j = c.get("/v2/api/social/preview?key=tok1").get_json()
ck(j["ok"] and "למכירה" in j["body"] and j["ig_caption"].startswith(j["body"]) and j["images"] == ROW["תמונות"]
   and j["can"]["fb"]["ok"] and j["can"]["ig"]["ok"], j)

sb.rows.append({"id": "r1", "property_key": "tok1", "mode": "publish", "fb_status": "ok", "ig_status": "failed",
                "fb_permalink": "https://fb/p1", "created_at": "2026-10-30T10:00:00+00:00"})
j = c.get("/v2/api/social/status?keys=L:tok1,zz").get_json()
ck(j["items"]["tok1"]["last"]["fb_status"] == "ok" and "can" in j["items"]["tok1"] and j["items"]["zz"]["last"] is None, j)

os.environ["META_TOKEN"] = "SECRET123"
j = c.get("/v2/api/social/health").get_json()
ck(j["ok"] and j["connected"] and "SECRET123" not in str(j) and j["mode"] == "preview", j)
os.environ.pop("META_TOKEN")
j = c.get("/v2/api/social/health").get_json()
ck(j["connected"] is False, j)

SESS["t"] = None
ck(c.get("/v2/social/img/nope.jpg").status_code == 404, "missing token")
tok = SP._IMG.put("https://img/a.jpg", time.time())
r = c.get("/v2/social/img/%s.jpg" % tok)
ck(r.status_code == 200 and r.mimetype == "image/jpeg" and r.data[:2] == b"\xff\xd8" and "no-store" in r.headers.get("Cache-Control", ""), r.status_code)
from PIL import Image; import io
ck(Image.open(io.BytesIO(c.get("/v2/social/img/%s-sq.jpg" % tok).data)).size == (SP.IMG_MAX_PX, SP.IMG_MAX_PX), "square")
print("social_routes OK", n)
