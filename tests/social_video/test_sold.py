# tests/social_video/test_sold.py — סטורי SOLD (social_sold): טקסטים, רינדור אמיתי, יצירה, פרסום לסטורי בלבד
import os, sys, io, tempfile, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from PIL import Image
import social_publish as SP
import social_video as V
import social_sold as S
from _fakes import ROW, make_G, SF

def jpg(color=(120, 150, 180), size=(1200, 800)):
    b = io.BytesIO(); Image.new("RGB", size, color).save(b, "JPEG"); return b.getvalue()

# ── טקסטים ──
t = S.sold_texts_property(ROW, "seller", ["מעלית", "ממ\"ד", "מרפסת", "חניה"])
ck(t["addr"] == "אהוד מנור 13" and t["tag"] == "נמכר בהצלחה", t)
# [05/11 אייל] כמו בפוסט: חדרים + שכונה + עיר, מ"ר · קומה, מחיר, ועד 3 מאפיינים
ck(t["place"] == "4 חדרים · נאות אפק, קרית ביאליק" and t["price"] == "1,890,000 ₪", t)
ck(t["spec"] == '110 מ"ר · קומה 3' and t["feats"] == 'מעלית · ממ"ד · מרפסת', t)
t0 = S.sold_texts_property(dict(ROW, **{"מחיר": "0", "חדרים": "", 'מ"ר': "", "קומה": ""}), "seller", [])
ck(t0["price"] == "" and t0["place"] == "נאות אפק, קרית ביאליק" and t0["spec"] == "" and t0["feats"] == "", t0)
ck(S.sold_texts_property(dict(ROW, **{"כתובת": "אהוד מנור 13"}), "both")["addr"] == "אהוד מנור 13", "no double number")
ck(S.sold_texts_property(ROW, "both")["tag"] == "ייצגנו את המוכר וגם את הקונה", "both")
ck(S.sold_city("ההגנה 50 ק. מוצקין") == "קרית מוצקין" and S.sold_city("דליה 9, קריית אתא") == "קרית אתא", "city")
ck(S.sold_city("נעמי שמר 10") == "", "no city")
ck(S.sold_texts_deal({"notes": "דליה 9 קרית ים"})["line"] == "דירה בקרית ים", "buyer line")
ck(S.sold_texts_deal({"notes": "דליה 9"})["line"] == "רימקס פמילי · הקריות", "buyer line fallback")
D = {"id": "d1", "deal": True, "agents": ["רויטל", "צדוק"], "side1": "קונה", "side2": "מוכר", "notes": "ציזלינג 36"}
ck(S.sold_agents_for_deal(D) == ["רויטל"], "buyer side only")
ck(S.sold_agents_for_deal(dict(D, side1="", side2="")) == ["רויטל", "צדוק"], "no sides → all")
ck(S.sold_agents_for_deal(dict(D, side1="מוכר וקונה")) == ["רויטל"], "both on one")
ck(S.sold_deal_ok(D) and not S.sold_deal_ok(dict(D, deal=False)), "closed only")
ck(not S.sold_deal_ok(dict(D, side1="מוכר", side2="")), "seller-only deal → no buyer story")

# ── מוזיקה: 3 הקטעים מ-Sound Collection של Meta (אייל בחר 05/11), כל סטורי הקטע הבא ──
ms = [os.path.basename(S.sold_music({}, k)) for k in range(4)]
ck(ms == ["meta-boogie-monster-bash.mp3", "meta-poltergeist-polka.mp3", "meta-wacky-sax.mp3", "meta-boogie-monster-bash.mp3"], ms)
ck(os.path.basename(S.sold_music({"SOLD_MUSIC": "meta-wacky-sax.mp3"}, 0)) == "meta-wacky-sax.mp3", "env pin")
ck(os.path.basename(S.sold_music({"SOLD_MUSIC": "nope.mp3"}, 1)) == "meta-poltergeist-polka.mp3", "bad env → rotation")
ck("/sold/" not in str(V.vid_music("tok1")), "property videos keep their own tracks")

# ── רינדור אמיתי (ffmpeg): מוכר עם צוות, קונה ──
logo = V._logo_path()
for kind, photo, tx, ags in (
        ("seller", jpg(), S.sold_texts_property(ROW, "seller"), [{"name": "דנה כהן", "phone": "072-555-0101"},
                                                               {"name": "יוסי לוי", "phone": "052-123-4567"}]),
        ("buyer", None, S.sold_texts_deal({"notes": "קרית ים"}), [{"name": "דנה כהן", "phone": "072-555-0101"}])):
    out = os.path.join(tempfile.mkdtemp(), "s.mp4")
    r = S.sold_compose(kind, photo, tx, ags, S.sold_music({}), out, logo)
    ck(r["ok"] and os.path.getsize(out) > 20000 and os.path.exists(r["cover"]), r)
    pr = subprocess.run([V.vid_ffmpeg(), "-i", out], capture_output=True, text=True).stderr
    ck("1080x1920" in pr and "Audio" in pr and "00:00:08" in pr, pr[-400:])
ck(not S.sold_compose("seller", None, {}, [], None, "/tmp/x.mp4", logo)["ok"], "seller needs photo")

# ── יצירה + פרסום (Graph מזויף) ──
class FG:
    calls = []; fail = {}
    def __init__(s, http, token, env, sleep=None, version=None): pass
    def page_ig_id(s, pid): return "IG"
    def ig_video(s, ig, kind, url, caption="", cover_url="", ai=True):
        FG.calls.append(("ig_" + kind, url, ai))
        if FG.fail.get("ig"): raise SP.MetaError("bad mt")
        return ("M1", "")
    def fb_video_story(s, pid, url):
        FG.calls.append(("fb_story", url)); return "S1"
    def fb_reel(s, *a): raise AssertionError("no reels")
SP.Graph = FG
COMP = []
def fake_compose(kind, photo, texts, agents, music, out, logo_path, popen=None):
    COMP.append((kind, bool(photo), texts, agents)); open(out, "wb").write(b"MP4")
    return {"ok": True, "duration": 8.0, "cover": out}
real_compose, S.sold_compose = S.sold_compose, fake_compose
HTTP = SF.ImgHttp()
env = {"SOCIAL_MODE": "publish", "META_TOKEN": "mt", "APP_BASE_URL": "https://app"}
G, st, sb = make_G(rows=[dict(ROW, **{"סוכן 2": "יוסי לוי"})])
G["_deals_load"] = lambda: [D, dict(D, id="d2", deal=False)]
store, db = V.VidStore(tempfile.mkdtemp()), S.SoldDB(os.path.join(tempfile.mkdtemp(), "s.json"))

r = S.sold_create(G, "prop", "tok1", "both", "505709865", http=HTTP, env=env, store=store, db=db)
ck(r["ok"] and r["status"] == "ready", r)
kind, has_photo, tx, ags = COMP[-1]
ck(kind == "seller" and has_photo and tx["tag"].startswith("ייצגנו") and [a["name"] for a in ags] == ["דנה כהן", "יוסי לוי"], COMP[-1])
ck(ags[0]["phone"] == "072-555-0101", ags[0])            # הווירטואלי, כמו בסרטוני הנכסים
rec = db.get(r["id"])
ck(rec["status"] == "ready" and store.exists(rec["video_token"]) and rec["ref"] == "p:tok1", rec)

p = S.sold_publish(G, r["id"], http=HTTP, env=env, store=store, db=db)
ck(p["ok"] and p["status"] == "published", p)
ck([c[0] for c in FG.calls] == ["ig_STORIES", "fb_story"] and FG.calls[0][2] is False, FG.calls)   # סטורי בלבד, בלי סימון AI
ck(FG.calls[0][1] == "https://app/v2/social/vid/%s.mp4" % rec["video_token"], FG.calls[0])
ck(not S.sold_publish(G, r["id"], http=HTTP, env=env, store=store, db=db)["ok"], "no double publish")

# כשל באינסטגרם → חלקי, ניסיון חוזר רק לאינסטגרם
r = S.sold_create(G, "prop", "tok1", "seller", "", http=HTTP, env=env, store=store, db=db)
FG.calls, FG.fail = [], {"ig": True}
p = S.sold_publish(G, r["id"], http=HTTP, env=env, store=store, db=db)
ck(p["status"] == "partial" and "bad ***" in p["reason"] and "mt" not in p["reason"].replace("bad ***", ""), p)
FG.calls, FG.fail = [], {}
p = S.sold_publish(G, r["id"], http=HTTP, env=env, store=store, db=db)
ck(p["status"] == "published" and [c[0] for c in FG.calls] == ["ig_STORIES"], FG.calls)

# עסקת קונה: בלי תמונה, רק סוכן הקונה
r = S.sold_create(G, "deal", "d1", "buyer", "", http=HTTP, env=env, store=store, db=db)
ck(r["ok"] and COMP[-1][0] == "buyer" and not COMP[-1][1] and [a["name"] for a in COMP[-1][3]] == ["רויטל"], COMP[-1])
ck(not S.sold_create(G, "deal", "d2", "buyer", "", http=HTTP, env=env, store=store, db=db)["ok"], "open deal blocked")
ck(not S.sold_create(G, "prop", "nope", "seller", "", http=HTTP, env=env, store=store, db=db)["ok"], "no prop")
ck(S.sold_create(G, "prop", "tok1", "buyer", "", http=HTTP, env=env, store=store, db=db)["reason"] == "צד לא תקין", "bad side")

# מצב בדיקה: נוצר אבל לא מתפרסם
r = S.sold_create(G, "prop", "tok1", "seller", "", http=HTTP, env=dict(env, SOCIAL_MODE="preview"), store=store, db=db)
ck(r["ok"], r)
ck(S.sold_publish(G, r["id"], http=HTTP, env=dict(env, SOCIAL_MODE="preview"), store=store, db=db)["reason"].startswith("מצב בדיקה"), "preview")

# כשל רינדור → failed, הקובץ נמחק
S.sold_compose = lambda *a, **k: {"ok": False, "error": "boom mt"}
r = S.sold_create(G, "prop", "tok1", "seller", "", http=HTTP, env=env, store=store, db=db)
rec = db.get(r["id"])
ck(rec["status"] == "failed" and "mt" not in rec["error"] and not store.exists(rec["video_token"]), rec)

# רינדור שנתקע (אתחול באמצע) → מוצג כנכשל, ואפשר ליצור שוב
db.update(r["id"], {"status": "rendering", "ts": time.time() - 2000})
ck(S.sold_view(db.get(r["id"]), time.time())["status"] == "failed", "stale")
S.sold_compose = fake_compose
ck(S.sold_create(G, "prop", "tok1", "seller", "", http=HTTP, env=env, store=store, db=db)["ok"], "after stale")
db.update(db.last("p:tok1")["id"], {"status": "rendering", "ts": time.time()})
ck(S.sold_create(G, "prop", "tok1", "seller", "", http=HTTP, env=env, store=store, db=db)["reason"] == "כבר בהכנה", "inflight")

print("sold OK", n)
