# tests/social_video/test_routes.py — register(): הרשאות, יצירה, קבצים ציבוריים, דף אישור, /w/, ולולאה אוטומטית
import os, sys, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from flask import Flask
import social_publish as SP
import social_video as V
REAL_BLOCKED = V._blocked_now
from _fakes import ROW, make_G
SP.soc_hidden = lambda G: set()
os.environ["SOCIAL_MODE"] = "preview"; os.environ.pop("META_TOKEN", None); os.environ["SOCIAL_VIDEO_AUTO"] = "0"
STORE = V.VidStore(tempfile.mkdtemp())
V._STORE = STORE
open(STORE.path("AbC123"), "wb").write(b"\x00\x00\x00\x18ftypmp42" + b"x" * 5000)
open(STORE.cover("AbC123"), "wb").write(b"\xff\xd8jpg")
SESS = {"t": None}
G, st, sb = make_G(); G["_web_auth"] = lambda: SESS["t"]
RUNS = []
V.vid_create_one = lambda G_, key, trigger, by_phone, **kw: (RUNS.append((key, trigger, by_phone)), {"ok": True})[1]
PUBS = []
V.vid_publish = lambda G_, vid, **kw: (PUBS.append((vid, kw.get("channels"))), {"ok": True})[1]
V._spawn = lambda fn: fn()
app = Flask(__name__); V.register(app, G); c = app.test_client()
DEV = {"name": "אייל", "drole": "developer", "phone": "505709865"}
AG = {"name": "דנה", "drole": "agent", "phone": "501111111"}

for path, meth in (("/v2/api/social/video", "post"), ("/v2/api/social/videos?keys=tok1", "get"),
                   ("/v2/api/social/video/retry", "post"), ("/v2/api/social/video/health", "get")):
    SESS["t"] = None; ck(getattr(c, meth)(path, json={"key": "tok1"}).status_code == 401, path)
    SESS["t"] = AG; ck(getattr(c, meth)(path, json={"key": "tok1"}).status_code == 403, path)
SESS["t"] = DEV
r = c.post("/v2/api/social/video", json={"key": "L:tok1"})
ck(r.status_code == 200 and r.json["ok"] and RUNS == [("tok1", "manual", "505709865")], (r.json, RUNS))
ck(c.post("/v2/api/social/video", json={}).status_code == 400, "no key")

sb.videos.append({"id": "v9", "property_key": "tok1", "status": "partial", "video_token": "AbC123",
                  "created_at": SP._dt.datetime.now(SP._dt.timezone.utc).isoformat(), "ig_reel_status": "failed"})
j = c.get("/v2/api/social/videos?keys=tok1,tok2").json
ck(j["ok"] and j["items"]["tok1"]["last"]["id"] == "v9" and j["items"]["tok1"]["can"]["ok"] is False and "tok2" not in j["items"], j)
r = c.post("/v2/api/social/video/retry", json={"id": "v9", "channels": ["ig_reel", "bogus"]})
ck(r.json["ok"] and PUBS == [("v9", ["ig_reel"])], (r.json, PUBS))
sb.videos[-1]["status"] = "published"
ck(c.post("/v2/api/social/video/retry", json={"id": "v9"}).json["ok"] is False, "retry only partial")
# [02/11] שלח שוב לאישור — רק לסרטון שממתין
RS = []
_orig_send = V.vid_send_review
V.vid_send_review = lambda G_, rec, base, env, initiator="": (RS.append((rec["id"], initiator)), ["505709865"])[1]
sb.videos.append({"id": "v8", "property_key": "tok1", "status": "pending", "video_token": "AbC123", "review_token": "R8",
                  "created_at": SP._dt.datetime.now(SP._dt.timezone.utc).isoformat()})
SESS["t"] = AG; ck(c.post("/v2/api/social/video/resend", json={"id": "v8"}).status_code == 403, "resend dev only")
SESS["t"] = DEV
r = c.post("/v2/api/social/video/resend", json={"id": "v8"})
ck(r.json["ok"] and RS == [("v8", "505709865")] and sb.video_get("v8")["recipients"] == ["505709865"], (r.json, RS))
V.vid_send_review = lambda G_, rec, base, env, initiator="": []
r = c.post("/v2/api/social/video/resend", json={"id": "v8"})
ck(r.json["ok"] is False and "לא נשלח" in r.json["error"], r.json)
ck(c.post("/v2/api/social/video/resend", json={"id": "v9"}).json["ok"] is False, "resend only pending")
V.vid_send_review = _orig_send
sb.videos.remove(sb.video_get("v8"))
h = c.get("/v2/api/social/video/health").json
ck(h["ok"] and "fal" in h and "month_cost" in h and h["month_cap"] == V.MONTH_AI_CAP, h)

SESS["t"] = None
r = c.get("/v2/social/vid/AbC123.mp4")
ck(r.status_code == 200 and r.mimetype == "video/mp4" and "no-store" in r.headers.get("Cache-Control", ""), r.status_code)
r = c.get("/v2/social/vid/AbC123.mp4", headers={"Range": "bytes=0-99"})
ck(r.status_code == 206 and len(r.data) == 100, (r.status_code, len(r.data)))
ck(c.get("/v2/social/vid/AbC123-cover.jpg").mimetype == "image/jpeg", "cover")
ck(c.get("/v2/social/vid/nope.mp4").status_code == 404 and c.get("/v2/social/vid/..%2Fx.mp4").status_code == 404, "404")

sb.videos.append({"id": "v10", "property_key": "tok1", "status": "pending", "video_token": "AbC123", "review_token": "RT10",
                  "sent_at": SP._dt.datetime.now(SP._dt.timezone.utc).isoformat(), "texts": V.vid_texts(ROW, [], "", "", "", ""),
                  "created_at": SP._dt.datetime.now(SP._dt.timezone.utc).isoformat()})
r = c.get("/v2/social/review/RT10")
ck(r.status_code == 200 and "AbC123.mp4" in r.get_data(as_text=True), r.status_code)
V._blocked_now = lambda G_, t: False
r = c.post("/v2/social/review/RT10", json={"action": "pub"})
ck(r.status_code == 200 and sb.video_get("v10")["status"] == "approved" and ("v10", None) in PUBS, (r.get_data(as_text=True), PUBS))
ck(c.get("/v2/social/review/zzzz").status_code == 404, "review 404")
sb.link_insert({"code": "Qw12", "property_key": "tok1", "channel": "fb_reel"})
r = c.get("/w/Qw12")
ck(r.status_code == 302 and r.headers["Location"].startswith("https://wa.me/972521234567"), r.headers.get("Location"))
ck(c.get("/w/none").status_code == 404, "w 404")

# ── לולאה ──
V._blocked_now = REAL_BLOCKED
import datetime as dt
IL = SP._IL
DAY = dt.datetime(2026, 11, 2, 12, 0, tzinfo=IL).timestamp()
NIGHT = dt.datetime(2026, 11, 2, 23, 0, tzinfo=IL).timestamp()
rows = [dict(ROW, **{"מספר מודעה": "k%d" % i, "מספר בית": str(i)}) for i in range(3)]
G2, st2, sb2 = make_G(rows=rows); RUNS.clear()
pub = {"SOCIAL_MODE": "publish", "META_TOKEN": "t", "SOCIAL_VIDEO_AUTO": "1"}
ck(V.vid_auto_tick(G2, DAY, env=dict(pub, SOCIAL_MODE="preview"))["ran"] is False, "not in preview")
ck(V.vid_auto_tick(G2, DAY, env=dict(pub, SOCIAL_VIDEO_AUTO="0"))["ran"] is False, "flag off")
r = V.vid_auto_tick(G2, DAY, env=pub)
ck(r.get("seeded") == 3 and RUNS == [], r)
new = [dict(ROW, **{"מספר מודעה": "n%d" % i, "מספר בית": str(10 + i)}) for i in range(5)]
G2["fetch_sheet_rows"] = lambda: rows + new
r = V.vid_auto_tick(G2, DAY + 600, env=pub)
ck(len(RUNS) == 3 and all(t == "auto" for _, t, _ in RUNS), RUNS)
ck(len(G2["_load_config"]()["v2_social"]["vid_waiting"]) == 2, G2["_load_config"]()["v2_social"])
RUNS.clear()
G3, st3, sb3 = make_G(rows=rows)
V.vid_auto_tick(G3, DAY, env=pub); G3["fetch_sheet_rows"] = lambda: rows + new
V.vid_auto_tick(G3, NIGHT, env=pub)
ck(RUNS == [], "night")
# הודעות אישור שממתינות, פג, ופרסום מתוזמן
G4, st4, sb4 = make_G(rows=rows); PUBS.clear()
iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()
sb4.videos += [{"id": "a", "property_key": "k0", "status": "pending", "sent_at": iso(DAY - 49 * 3600), "created_at": iso(DAY - 49 * 3600)},
               {"id": "b", "property_key": "k1", "status": "approved", "publish_at": iso(DAY - 60), "created_at": iso(DAY - 3600)},
               {"id": "c", "property_key": "k2", "status": "pending", "review_due": True, "sent_at": iso(DAY - 600),
                "created_at": iso(DAY - 600), "video_token": "AbC123", "texts": V.vid_texts(ROW, [], "", "", "", "")}]
SENT = []
V.vid_send_review = lambda G_, rec, base, env, initiator="": (SENT.append(rec["id"]), ["505709865"])[1]
V.vid_auto_tick(G4, DAY, env=pub)
ck(sb4.video_get("a")["status"] == "expired", sb4.video_get("a"))
ck(("b", None) in PUBS, PUBS)
ck(SENT == ["c"] and sb4.video_get("c")["review_due"] is False and sb4.video_get("c")["recipients"] == ["505709865"], sb4.video_get("c"))
# [02/11] הודעת אישור שנדחתה לבוקר נשלחת גם כשיצירה אוטומטית כבויה (SOCIAL_VIDEO_AUTO), ובלי ליצור סרטונים
G5, st5, sb5 = make_G(rows=rows); SENT.clear(); RUNS.clear()
sb5.videos.append({"id": "d", "property_key": "k3", "status": "pending", "review_due": True, "sent_at": iso(DAY - 600),
                   "created_at": iso(DAY - 600), "video_token": "AbC124", "recipients": ["505709865"],
                   "texts": V.vid_texts(ROW, [], "", "", "", "")})
V.vid_send_review = lambda G_, rec, base, env, initiator="": (SENT.append(rec["id"]), ["521234567"])[1]
r = V.vid_auto_tick(G5, DAY, env=dict(pub, SOCIAL_VIDEO_AUTO="0"))
ck(SENT == ["d"] and RUNS == [] and r.get("ran") is False, (SENT, RUNS, r))
ck(sb5.video_get("d")["recipients"] == ["505709865", "521234567"] and sb5.video_get("d")["review_due"] is False, sb5.video_get("d"))
print("video_routes OK", n)
