# tests/social_video/test_sold_routes.py — social_sold.register(): הרשאות, יצירה (נכס/עסקה), פרסום ברקע, רשימה
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from flask import Flask
import social_video as V
import social_sold as S
from _fakes import make_G
os.environ["SOCIAL_MODE"] = "publish"
S._DB = S.SoldDB(os.path.join(tempfile.mkdtemp(), "s.json"))
SESS = {"t": None}
G, st, sb = make_G(); G["_web_auth"] = lambda: SESS["t"]
RUNS, PUBS = [], []
S.sold_create = lambda G_, kind, ref, side, by, details=None: RUNS.append((kind, ref, side, by, details))
S.sold_publish = lambda G_, sid: PUBS.append(sid)
V._spawn = lambda fn: fn()
app = Flask(__name__); S.register(app, G); c = app.test_client()
DEV = {"name": "אייל", "drole": "developer", "phone": "505709865"}
AG = {"name": "דנה", "drole": "agent", "phone": "501111111"}

for path, meth in (("/v2/api/social/sold", "post"), ("/v2/api/social/sold/publish", "post"), ("/v2/api/social/sold/list?keys=tok1", "get")):
    SESS["t"] = None; ck(getattr(c, meth)(path, json={"key": "tok1"}).status_code == 401, path)
    SESS["t"] = AG; ck(getattr(c, meth)(path, json={"key": "tok1"}).status_code == 403, path)
SESS["t"] = DEV
ck(c.post("/v2/api/social/sold", json={"key": "L:tok1", "side": "both"}).json["ok"] and RUNS[-1] == ("prop", "tok1", "both", "505709865", None), RUNS)
ck(c.post("/v2/api/social/sold", json={"deal": "d1"}).json["ok"] and RUNS[-1] == ("deal", "d1", "buyer", "505709865", None), RUNS)
DET = {"addr": "ציזלינג 36", "agents": ["רויטל"]}
ck(c.post("/v2/api/social/sold", json={"deal": "d1", "details": DET}).json["ok"] and RUNS[-1][4] == DET, RUNS)
ck(c.post("/v2/api/social/sold", json={"deal": "d1", "details": "junk"}).json["ok"] and RUNS[-1][4] is None, RUNS)
ck(c.post("/v2/api/social/sold", json={}).status_code == 400, "nothing")

r1 = S._DB.insert({"ref": "p:tok1", "status": "ready", "video_token": "T1", "ts": time.time()})
r2 = S._DB.insert({"ref": "d:d1", "status": "rendering", "video_token": "T2", "ts": time.time()})
j = c.get("/v2/api/social/sold/list?keys=tok1,tok2&deals=d1").json
ck(j["ok"] and j["mode"] == "publish" and j["items"]["p:tok1"]["status"] == "ready" and j["items"]["d:d1"]["token"] == "T2", j)
ck("p:tok2" not in j["items"], j)
ck(c.post("/v2/api/social/sold/publish", json={"id": r1["id"]}).json["ok"] and PUBS == [r1["id"]], PUBS)
ck(not c.post("/v2/api/social/sold/publish", json={"id": r2["id"]}).json["ok"] and len(PUBS) == 1, "not ready")
os.environ["SOCIAL_MODE"] = "preview"
ck("מצב בדיקה" in c.post("/v2/api/social/sold/publish", json={"id": r1["id"]}).json["error"] and len(PUBS) == 1, "preview")
print("sold routes OK", n)
