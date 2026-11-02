# tests/social_video/test_run.py — vid_create_one / vid_publish (G, fal, Graph, pick מזויפים)
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
import social_video as V
from _fakes import ROW, make_G, SF
SP.soc_hidden = lambda G: set()
HTTP = SF.ImgHttp()
NOW = time.time()

REVIEWS = []
V.vid_send_review = lambda G, rec, base, env: (REVIEWS.append((rec["id"], base)), ["505709865", "521234567"])[1]
COMPOSED = []
def fake_compose(clip, slides, layers, timeline, music, out, run=None):
    COMPOSED.append({"clip": clip, "n": len(slides), "tl": timeline, "layers": sorted(layers)})
    open(out, "wb").write(b"MP4"); open(out.rsplit(".", 1)[0] + "-cover.jpg", "wb").write(b"JPG")
    return {"ok": True, "duration": 14.0, "cover": out.rsplit(".", 1)[0] + "-cover.jpg"}
V.vid_compose = fake_compose
V.vid_pick = lambda http, key, imgs, desc, feats: {"ai": 0, "room": "living room", "slides": [1, 2, 3], "highlight": "",
                                                    "wm": {i: None for i in range(len(imgs))}, "skip": []}
FAL = {"err": None, "calls": 0}
def fake_ai(fal, jpeg, room):
    FAL["calls"] += 1
    return (None, FAL["err"], 0) if FAL["err"] else (b"CLIPMP4", None, 0.35)
V.vid_ai_clip = fake_ai

def store():
    return V.VidStore(tempfile.mkdtemp())

# ── preview: נוצר, בלי אישורים ובלי Meta ──
G, st, sb = make_G()
env = {"SOCIAL_MODE": "preview", "FAL_KEY": "fk", "CLAUDE_API_KEY": "ck", "APP_BASE_URL": "https://app"}
r = V.vid_create_one(G, "tok1", "manual", "505709865", http=HTTP, now=NOW, env=env, store=store())
ck(r["ok"] and r["status"] == "preview" and r["ai"] is True, r)
rec = sb.videos[-1]
ck(rec["status"] == "preview" and rec["ai"] is True and rec["ai_cost_usd"] == 0.35 and rec["video_token"], rec)
ck(not REVIEWS and COMPOSED[-1]["clip"] and COMPOSED[-1]["n"] == 4, (REVIEWS, COMPOSED[-1]))
ck(COMPOSED[-1]["tl"][0][0] == "ai" and rec["texts"]["end"]["phone"] == "072-555-0101", rec["texts"]["end"])
ck(any("סרטון לרשתות" in a[3] for a in st["acts"]), st["acts"])

# ── publish: ממתין לאישור + שליחה ──
G, st, sb = make_G()
env = dict(env, SOCIAL_MODE="publish", META_TOKEN="mt")
r = V.vid_create_one(G, "tok1", "manual", "505709865", http=HTTP, now=NOW, env=env, store=store())
rec = sb.videos[-1]
ck(r["status"] == "pending" and rec["status"] == "pending" and rec.get("sent_at") and rec.get("review_token"), rec)
ck(REVIEWS[-1][0] == rec["id"] and rec["recipients"] == ["505709865", "521234567"], (REVIEWS, rec.get("recipients")))

# ── בלי FAL_KEY → בלי AI ──
G, st, sb = make_G(); calls = FAL["calls"]
r = V.vid_create_one(G, "tok1", "manual", "", http=HTTP, now=NOW, env=dict(env, FAL_KEY=""), store=store())
ck(r["ai"] is False and FAL["calls"] == calls and COMPOSED[-1]["clip"] is None and COMPOSED[-1]["tl"][0][0] == "kb", r)

# ── fal 402 → בלי AI + פוש פעם ביום ──
G, st, sb = make_G(); FAL["err"] = 402
V.vid_create_one(G, "tok1", "manual", "", http=HTTP, now=NOW, env=env, store=store())
ck(sb.videos[-1]["ai"] is False and len([p for p in st["push"] if "fal" in p[1]]) == 1, st["push"])
sb.videos.clear()
V.vid_create_one(G, "tok1", "manual", "", http=HTTP, now=NOW, env=env, store=store())
ck(len([p for p in st["push"] if "fal" in p[1]]) == 1, "alert once a day")
FAL["err"] = None

# ── חסימות ──
G, st, sb = make_G()
r = V.vid_create_one(G, "nope", "manual", "", http=HTTP, now=NOW, env=env, store=store())
ck(not r["ok"] and r["reason"] == "הנכס לא נמצא", r)
r = V.vid_create_one(G, "tok1", "manual", "", http=HTTP, now=NOW, env=dict(env, SOCIAL_MODE="off"), store=store())
ck(not r["ok"] and r["reason"] == "כבוי", r)
sb.videos.append({"id": "old", "property_key": "tok1", "status": "published", "created_at": SP._dt.datetime.now(SP._dt.timezone.utc).isoformat()})
r = V.vid_create_one(G, "tok1", "manual", "", http=HTTP, now=NOW, env=env, store=store())
ck(not r["ok"] and "כבר נוצר סרטון" in r["reason"], r)

# ── כשל רינדור → failed ──
G, st, sb = make_G()
V.vid_compose = lambda *a, **k: {"ok": False, "error": "ffmpeg: boom fk"}
r = V.vid_create_one(G, "tok1", "manual", "", http=HTTP, now=NOW, env=env, store=store())
ck(not r["ok"] and sb.videos[-1]["status"] == "failed" and "fk" not in sb.videos[-1]["error"], sb.videos[-1])
# קליפ Kling כבר שולם — גם כשהרינדור נכשל הרשומה מסומנת AI ונספרת בעלות/במכסה החודשית
ck(sb.videos[-1]["ai"] is True and sb.videos[-1]["ai_cost_usd"] == 0.35, sb.videos[-1])
V.vid_compose = fake_compose

# ── vid_publish ──
class FG:
    calls = []; fail = {}
    def __init__(s, http, token, env, sleep=None, version=None): s.env = env
    def page_ig_id(s, pid): return "IG"
    def ig_quota(s, ig): return 25
    def ig_video(s, ig, kind, url, caption="", cover_url="", ai=True):
        SF._GUARD(s); FG.calls.append(("ig_" + kind, url, caption, cover_url))
        e = FG.fail.get("ig_" + kind)
        if e: raise e
        return ("M_" + kind, "https://ig/r" if kind == "REELS" else "")
    def fb_video_story(s, pid, url):
        SF._GUARD(s); FG.calls.append(("fb_story", url)); return "S1"
    def fb_reel(s, pid, url, desc):
        SF._GUARD(s); FG.calls.append(("fb_reel", url, desc)); return ("R1", "https://fb/r")
SP.Graph = FG

def approved_video(G, sb, st_):
    stv = store()
    V.vid_create_one(G, "tok1", "manual", "", http=HTTP, now=NOW, env=env, store=stv)
    v = sb.videos[-1]; v["status"] = "approved"; v["decided_by"] = "אייל"
    return v, stv

G, st, sb = make_G(); FG.calls = []
v, stv = approved_video(G, sb, st)
r = V.vid_publish(G, v["id"], http=HTTP, now=NOW, env=env, store=stv)
ck([c[0] for c in FG.calls] == ["ig_STORIES", "ig_REELS", "fb_story", "fb_reel"], FG.calls)
ck(r["ok"] and sb.videos[-1]["status"] == "published", (r, sb.videos[-1]["status"]))
vurl = "https://app/v2/social/vid/%s.mp4" % v["video_token"]
ck(FG.calls[0][1] == vurl and FG.calls[1][3] == vurl.replace(".mp4", "-cover.jpg"), FG.calls[:2])
cap, desc = FG.calls[1][2], FG.calls[3][2]
ck("/w/" not in cap and "13" not in cap and "#נדלן" in cap, cap)
ck("לוואטסאפ ישיר: https://app/w/" in desc, desc)
code = desc.rsplit("/w/", 1)[1].strip()
ck(sb.links[code]["channel"] == "fb_reel" and sb.links[code]["property_key"] == "tok1", sb.links)
ck(sb.videos[-1]["ig_reel_permalink"] == "https://ig/r" and sb.videos[-1]["fb_reel_permalink"] == "https://fb/r", sb.videos[-1])

G, st, sb = make_G(); FG.calls = []; FG.fail = {"ig_REELS": SP.MetaError("bad mt")}
v, stv = approved_video(G, sb, st)
r = V.vid_publish(G, v["id"], http=HTTP, now=NOW, env=env, store=stv)
ck(sb.videos[-1]["status"] == "partial" and sb.videos[-1]["ig_reel_status"] == "failed" and sb.videos[-1]["ig_story_status"] == "ok", sb.videos[-1])
ck("bad ***" in sb.videos[-1]["error"], sb.videos[-1]["error"])
FG.fail = {}; FG.calls = []
r = V.vid_publish(G, v["id"], http=HTTP, now=NOW, env=env, store=stv)
ck([c[0] for c in FG.calls] == ["ig_REELS"] and sb.videos[-1]["status"] == "published", (FG.calls, sb.videos[-1]["status"]))

G, st, sb = make_G(); FG.calls = []
v, stv = approved_video(G, sb, st)
os.remove(stv.path(v["video_token"]))
r = V.vid_publish(G, v["id"], http=HTTP, now=NOW, env=env, store=stv)
ck(r["reason"] == "הסרטון לא זמין — צור מחדש" and FG.calls == [], r)

G, st, sb = make_G(); FG.calls = []
v, stv = approved_video(G, sb, st)
r = V.vid_publish(G, v["id"], http=HTTP, now=NOW, env=dict(env, SOCIAL_MODE="preview"), store=stv)
ck(r["reason"] == "מצב בדיקה" and FG.calls == [], r)
v["status"] = "pending"
r = V.vid_publish(G, v["id"], http=HTTP, now=NOW, env=env, store=stv)
ck(not r["ok"] and FG.calls == [], r)
print("video_run OK", n)
