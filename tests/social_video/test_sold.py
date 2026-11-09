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
# [05/11 אייל] עסקת קונה: כתובת מלאה ונתונים בהקלדה ידנית
dt = S.sold_texts_deal({"notes": "ציזלינג 36"}, {"addr": " ציזלינג 36 ", "city": "קרית ים", "rooms": "4", "size": "105",
                                              "floor": "3", "price": "1,250,000", "feats": "מעלית, חניה ,מרפסת, מחסן"})
ck(dt["addr"] == "ציזלינג 36" and dt["place"] == "4 חדרים · קרית ים" and dt["spec"] == '105 מ"ר · קומה 3', dt)
ck(dt["feats"] == "מעלית · חניה · מרפסת" and dt["price"] == "1,250,000 ₪", dt)
dt = S.sold_texts_deal({"notes": "דליה 9 קרית ים", "sale_price": "990000"}, {})
ck(dt["addr"] == "דליה 9 קרית ים" and dt["place"] == "קרית ים" and dt["price"] == "990,000 ₪" and dt["spec"] == "", dt)
ck(S.sold_texts_deal({"notes": "x" * 200}, {"addr": "y" * 200})["addr"] == "y" * 60, "clipped")
ck(S.sold_texts_deal({"notes": ""}, {"price": "abc"})["price"] == "", "bad price")
D = {"id": "d1", "deal": True, "agents": ["רויטל", "צדוק"], "side1": "קונה", "side2": "מוכר", "notes": "ציזלינג 36"}
ck(S.sold_agents_for_deal(D) == ["רויטל"], "buyer side only")
ck(S.sold_agents_for_deal(dict(D, side1="", side2="")) == ["רויטל", "צדוק"], "no sides → all")
ck(S.sold_agents_for_deal(dict(D, side1="מוכר וקונה")) == ["רויטל"], "both on one")
ck(S.sold_deal_ok(D) and not S.sold_deal_ok(dict(D, deal=False)), "closed only")
ck(S.sold_agents_for_deal(D, ["צדוק", "רויטל", "זר"]) == ["צדוק", "רויטל"], "picked team, strangers dropped")
ck(S.sold_agents_for_deal(D, ["זר"]) == ["רויטל"], "nothing valid → default")
ck(not S.sold_deal_ok(dict(D, side1="מוכר", side2="")), "seller-only deal → no buyer story")

# [05/11 אייל] שני הצדדים שלנו — סרטון אחד משולב: מוכר → קונה → שיתוף פעולה
ck(S.sold_names([" רויטל ", "צדוק", "רויטל", "", "זר", None]) == ["רויטל", "צדוק"], "team names")
ck(S.sold_names("junk") == [], "bad names")
bt = S.sold_texts_both(S.sold_texts_property(ROW, "both"))
ck(bt["seller"]["tag"] == "נמכר בהצלחה" and bt["buyer"]["kind"] == "buyer" and "addr" not in bt["buyer"], bt)
ck(bt["addr"] == "אהוד מנור 13" and bt["title"] == "שיתוף פעולה" and bt["title2"] == "בפמילי", bt)
ck(S.sold_duration("both") == 14.0 and S.sold_duration("seller") == 8.0 and S.sold_duration("buyer") == 8.0, "durations")
GR = make_G(rows=[ROW])[0]
ck(S.sold_row_by_addr(GR, "אהוד מנור 13") is not None and S.sold_row_by_addr(GR, " אהוד  מנור 13, קרית ביאליק") is not None, "addr match")
ck(S.sold_row_by_addr(GR, "אהוד מנור 15") is None and S.sold_row_by_addr(GR, "") is None, "no addr match")

# [06/11 אייל] "אלי שמול מוגדר צוות ולא רואים גם את יהודית" — צוות של שניים בהגדרות → שניהם בסטורי
TG = make_G(cfg={"teams": [["אלי שמול", "יהודית שמול"], ["א", "ב", "ג"]]})[0]
ck(S.sold_with_team(TG, ["אלי שמול"]) == ["אלי שמול", "יהודית שמול"], "team of two added")
ck(S.sold_with_team(TG, ["יהודית  שמול"]) == ["יהודית  שמול", "אלי שמול"], "canon match")
ck(S.sold_with_team(TG, ["א"]) == ["א"], "big sharing team → not added")
ck(S.sold_with_team(TG, ["אלי שמול", "רויטל"]) == ["אלי שמול", "רויטל"], "already two")
ck(S.sold_with_team(TG, ["זר"]) == ["זר"] and S.sold_with_team({}, ["אלי שמול"]) == ["אלי שמול"], "no team / no cfg")

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
TEAMS = {"seller": [{"name": "בן כהן", "phone": "072-555-0101"}, {"name": "בנימין לוי", "phone": "052-123-4567"}],
         "buyer": [{"name": "אלי שמול", "phone": "072-555-0202"}, {"name": "יהודית שמול", "phone": "052-765-4321"}]}
for photo in (jpg(), None):   # בלי תמונה (עסקה בלי נכס של המשרד) → אייקון בית
    out = os.path.join(tempfile.mkdtemp(), "b.mp4")
    r = S.sold_compose("both", photo, bt, TEAMS, S.sold_music({}, 2), out, logo)   # wacky-sax 12ש' → חוזר בלופ
    ck(r["ok"] and r["duration"] == 14.0, r)
    pr = subprocess.run([V.vid_ffmpeg(), "-i", out], capture_output=True, text=True).stderr
    ck("1080x1920" in pr and "Audio" in pr and "00:00:14" in pr, pr[-400:])

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
r = S.sold_create(G, "deal", "d1", "buyer", "", http=HTTP, env=env, store=store, db=db,
                  details={"addr": "ציזלינג 36", "price": "1250000", "agents": ["רויטל", "צדוק"]})
ck(r["ok"] and COMP[-1][2]["addr"] == "ציזלינג 36" and [a["name"] for a in COMP[-1][3]] == ["רויטל", "צדוק"], COMP[-1])
# צוות מההגדרות נכנס אוטומטית לסטורי של נכס עם סוכן אחד
GT, _, _ = make_G(rows=[dict(ROW, **{"סוכן 1": "אלי שמול", "סוכן 2": ""})], cfg={"teams": [["אלי שמול", "יהודית שמול"]]})
r = S.sold_create(GT, "prop", "tok1", "seller", "", http=HTTP, env=env, store=store, db=db)
ck(r["ok"] and [a["name"] for a in COMP[-1][3]] == ["אלי שמול", "יהודית שמול"], COMP[-1][3])
GT["_deals_load"] = lambda: [dict(D, agents=["אלי שמול"], side1="קונה", side2="")]
r = S.sold_create(GT, "deal", "d1", "buyer", "", http=HTTP, env=env, store=store, db=db, details={"agents": ["אלי שמול"]})
ck(r["ok"] and [a["name"] for a in COMP[-1][3]] == ["אלי שמול", "יהודית שמול"], COMP[-1][3])
# משולב מ"הנכסים שלי": צד המוכר מהנכס, צד הקונה נבחר
r = S.sold_create(G, "prop", "tok1", "both", "", http=HTTP, env=env, store=store, db=db,
                  details={"buyer_agents": ["אלי שמול", "יהודית שמול"]})
kind, has_photo, tx, ags = COMP[-1]
ck(r["ok"] and kind == "both" and has_photo and tx["seller"]["tag"] == "נמכר בהצלחה", COMP[-1])
ck([a["name"] for a in ags["seller"]] == ["דנה כהן", "יוסי לוי"] and [a["name"] for a in ags["buyer"]] == ["אלי שמול", "יהודית שמול"], ags)
ck(db.get(r["id"])["kind"] == "both" and db.get(r["id"])["agents"] == ["דנה כהן", "יוסי לוי", "אלי שמול", "יהודית שמול"], db.get(r["id"]))
r = S.sold_create(G, "prop", "tok1", "both", "", http=HTTP, env=env, store=store, db=db, details={"buyer_agents": []})
ck(r["ok"] and COMP[-1][0] == "seller" and COMP[-1][2]["tag"].startswith("ייצגנו"), "no buyer team → regular 8s story")
# [09/11 אייל] מחיר העסקה שונה מהמחיר במודעה → מוקלד בטופס וגובר (גם במשולב); ריק = המחיר מהמודעה
r = S.sold_create(G, "prop", "tok1", "seller", "", http=HTTP, env=env, store=store, db=db, details={"price": "1,090,000"})
ck(r["ok"] and COMP[-1][2]["price"] == SP._price("1090000") + " ₪", COMP[-1][2])
listed = S.sold_texts_property(ROW, "seller")["price"]
r = S.sold_create(G, "prop", "tok1", "seller", "", http=HTTP, env=env, store=store, db=db, details={"price": ""})
ck(r["ok"] and COMP[-1][2]["price"] == listed, (COMP[-1][2], listed))
r = S.sold_create(G, "prop", "tok1", "both", "", http=HTTP, env=env, store=store, db=db,
                  details={"price": "1090000", "buyer_agents": ["אלי שמול"]})
ck(r["ok"] and COMP[-1][0] == "both" and COMP[-1][2]["price"] == SP._price("1090000") + " ₪", COMP[-1][2])
# משולב מעסקה: צד הקונה מהעסקה, צד המוכר נבחר; כתובת של נכס המשרד → התמונה שלו
r = S.sold_create(G, "deal", "d1", "buyer", "", http=HTTP, env=env, store=store, db=db,
                  details={"addr": "אהוד מנור 13", "agents": ["רויטל"], "seller_agents": ["בן כהן", "בנימין לוי"]})
kind, has_photo, tx, ags = COMP[-1]
ck(r["ok"] and kind == "both" and has_photo and tx["addr"] == "אהוד מנור 13", COMP[-1])
ck([a["name"] for a in ags["buyer"]] == ["רויטל"] and [a["name"] for a in ags["seller"]] == ["בן כהן", "בנימין לוי"], ags)
ck(db.get(r["id"])["ref"] == "d:d1" and db.get(r["id"])["side"] == "both", db.get(r["id"]))
r = S.sold_create(G, "deal", "d1", "buyer", "", http=HTTP, env=env, store=store, db=db,
                  details={"addr": "ציזלינג 36", "seller_agents": ["בן כהן"]})
ck(r["ok"] and COMP[-1][0] == "both" and not COMP[-1][1] and COMP[-1][2]["addr"] == "ציזלינג 36", "no office prop → no photo")
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
