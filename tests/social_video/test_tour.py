# tests/social_video/test_tour.py — סגנון "סיור בדירה" (social_video_tour) + אישור לאייל בלבד
import os, sys, io, json, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from PIL import Image
import social_publish as SP
import social_video as V
import social_video_tour as T
from _fakes import ROW, make_G, SF

def jpg(color=(90, 90, 90), size=(1440, 960)):
    b = io.BytesIO(); Image.new("RGB", size, color).save(b, "JPEG"); return b.getvalue()

# ── עיצוב מתחלף: שני סרטונים רצופים לא באותו עיצוב ──
ck([T.tour_theme(k) for k in range(4)] == ["dark", "cream", "split", "dark"], "rotation")
ck(T.tour_theme(None) == "dark", "none")

# ── חיתוך סימן מים החוצה ──
ck(T.tour_photo_box(1440, 960, None) == (86, 0, 1354, 845), T.tour_photo_box(1440, 960, None))   # רצועה תחתונה 12% תמיד נחתכת
ck(T.tour_photo_box(720, 480, (0.0, 0.92, 0.12, 0.99)) == T.tour_photo_box(720, 480, None), "yad2 bottom-left (קובי 04/11) — in band")
b = T.tour_photo_box(720, 480, None); ck(b[3] <= 480 * 0.88 and b[0] > 0 and b[2] < 720, b)   # גם RE/MAX בפינה הימנית-תחתונה בחוץ
b = T.tour_photo_box(1440, 960, (0.02, 0.02, 0.18, 0.14))      # פינה שמאלית-עליונה
ck(b and (b[0] >= 0.18 * 1440 or b[1] >= 0.14 * 960), b)
ck(abs((b[2] - b[0]) / (b[3] - b[1]) - 1.5) < 0.02, b)
b = T.tour_photo_box(1440, 960, (0.75, 0.80, 0.97, 0.95))      # פינה ימנית-תחתונה (כמו בסרטון של 03/11)
ck(b and (b[2] <= 0.75 * 1440 or b[3] <= 0.80 * 960), b)
ck(T.tour_photo_box(1440, 960, (0.3, 0.3, 0.7, 0.7)) is None, "centre wm → skip photo")

# ── תוכנית שקפים ──
TX = V.vid_texts(ROW, ["מעלית"], "", "דנה כהן", "072-555-0101", "")
sh = T.tour_plan(TX, [4, 1, 2, 0], {4: "נוף פתוח לים", 2: "המטבח"}, ["מעלית", "ממ\"ד"])
ck(sh[0] == {"i": 4, "title": "נוף פתוח לים", "sub": TX["open"]["place"]}, sh[0])
ck(sh[1]["title"] == "מעלית · ממ\"ד" and sh[1]["sub"] == TX["s2"]["main"], sh[1])   # בלי כיתוב → רשימת מאפיינים
ck(sh[2]["title"] == "המטבח" and sh[3]["title"] == "", sh)
ck(len(T.tour_plan(TX, list(range(12)), {}, [])) == T.MAX_SHOTS, "max shots")
ck(T.tour_plan(TX, [0, 1], {}, [])[0]["title"] == TX["open"]["title"], "fallback title")
ck(T.tour_duration(7) == 15.25, "duration")
ck(T.tour_phone("0529125049") == "052-912-5049" and T.tour_phone("+972-52-9125049") == "052-912-5049", "phone fmt")
ck(T.tour_phone("046000800") == "04-600-0800" and T.tour_phone("072-555-0101") == "072-555-0101", "phone fmt 2")

# ── Claude: סדר, כיתובים, סימנים ──
class R:
    def __init__(s, j): s.status_code, s._j = 200, j
    def json(s): return s._j
class Http:
    def __init__(s, ans): s.ans, s.log = ans, []
    def post(s, url, headers=None, json=None, timeout=None):
        s.log.append(json); return R({"content": [{"type": "text", "text": s.ans}]})
IMGS = [jpg() for _ in range(6)]
ans = json.dumps({"order": [3, 0, 5, 1, 9], "captions": {"3": "נוף פתוח לים", "0": "050-1234567", "5": "x"},
                  "wm": {"1": [0.3, 0.3, 0.7, 0.7], "2": None}, "skip": [5]})
p = T.tour_pick(Http("```json\n" + ans + "\n```"), "k", IMGS, "נוף פתוח לים", "m")
ck(p["order"] == [3, 0, 1], p)                         # 5 בדילוג, 9 מחוץ לטווח
ck(p["captions"] == {3: "נוף פתוח לים"}, p)            # טלפון ולא-עברית נזרקים
ck(p["wm"][1] == (0.3, 0.3, 0.7, 0.7) and p["wm"][0] is None and p["wm"][2] is None, p["wm"])
# [04/11] פורמט חדש: כיתוב צמוד לתמונה
p3 = T.tour_pick(Http(json.dumps({"shots": [{"i": 2, "caption": "המטבח"}, {"i": 0, "caption": "הסלון"}, {"i": 4}, {"i": 5, "caption": "x"}],
                                  "wm": {}, "skip": [5]})), "k", IMGS, "", "m")
ck(p3["order"] == [2, 0, 4] and p3["captions"] == {2: "המטבח", 0: "הסלון"}, p3)
p2 = T.tour_pick(Http(json.dumps({"order": [1, 0]})), "k", IMGS, "", "m")
ck(p2["wm"][0] == (0.02, 0.02, 0.18, 0.14), "no wm answer → default corner")
ck(T.tour_pick(Http("not json"), "k", IMGS, "", "m")["order"] == list(range(6)), "fallback")
ck(T.tour_pick(None, "", IMGS, "", "m")["captions"] == {}, "no key")

# ── ניקוי: תמונה עם סימן במרכז מדלגים עליה ומשלימים מהשאר ──
cl = T.tour_slides(IMGS, p)
ck([i for _, i in cl] == [3, 0, 2, 4], [i for _, i in cl])   # 1 נפסלה (סימן במרכז), 5 בדילוג
ck(Image.open(io.BytesIO(cl[0][0])).size == (1268, 845), "clean photo: only the bottom band + 3:2")

# ── יצירה: סגנון סיור כברירת מחדל, בלי fal, עיצוב לפי ההיסטוריה ──
ck(V.vid_style({}) == "tour" and V.vid_style({"SOCIAL_VIDEO_STYLE": "classic"}) == "classic", "style")
SP.soc_hidden = lambda G: set()
CALLS = []
def fake_tour(photos, shots, texts, theme, music, out, logo, agent_photo=None, popen=None):
    CALLS.append({"n": len(shots), "theme": theme, "titles": [s["title"] for s in shots]})
    open(out, "wb").write(b"MP4"); open(out.rsplit(".", 1)[0] + "-cover.jpg", "wb").write(b"J")
    return {"ok": True, "duration": T.tour_duration(len(shots)), "cover": out.rsplit(".", 1)[0] + "-cover.jpg"}
T.vid_compose_tour = fake_tour
FAL = []
V.vid_ai_clip = lambda *a, **k: (FAL.append(1), (b"x", None, 0.35))[1]
G, st, sb = make_G()
env = {"SOCIAL_MODE": "preview", "FAL_KEY": "fk", "APP_BASE_URL": "https://app"}
r = V.vid_create_one(G, "tok1", "manual", "505709865", http=SF.ImgHttp(), now=time.time(), env=env,
                     store=V.VidStore(tempfile.mkdtemp()))
rec = sb.videos[-1]
ck(r["ok"] and rec["status"] == "preview" and not FAL and rec["ai"] is False and rec["ai_cost_usd"] == 0, (r, rec))
ck(rec["texts"]["tour"]["theme"] == "dark" and CALLS[-1]["n"] >= 2, (rec["texts"].get("tour"), CALLS))
ck(rec["texts"]["end"]["phone"] == "072-555-0101", rec["texts"]["end"])   # [04/11] אייל: בסוף — הטלפון הווירטואלי של הסוכן
ck(V._summary(rec).endswith(rec["texts"]["open"]["price"]) and "AI" not in V._summary(rec), V._summary(rec))
sb.videos[-1]["property_key"] = "other"
sb.videos[-1]["created_at"] = "2020-01-01T00:00:00+00:00"
V.vid_create_one(G, "tok1", "manual", "", http=SF.ImgHttp(), now=time.time(), env=env, store=V.VidStore(tempfile.mkdtemp()))
ck(CALLS[-1]["theme"] in ("cream", "dark"), CALLS[-1])

# ── תמונת הסוכן לסוף הסרטון: דיסק → Supabase → אין (אות) ──
import base64
AVD = tempfile.mkdtemp(); os.environ["MAP_CACHE_DIR"] = AVD
G, st, sb = make_G()
G["_agent_vphones9"] = lambda: {"725550101"}
G["_phones_for_name"] = lambda n: ["072-555-0101", "0521234567"]
ck(V._agent_photo(G, {"סוכן 1": ""}) is None, "no agent")
class SB:
    def __init__(s, has): s.has, s.asked = has, []
    def avatar_get(s, p): s.asked.append(p); return base64.b64encode(jpg((10, 200, 10), (256, 256))).decode() if p in s.has else ""
G["_sbdb"] = SB(set())
ck(V._agent_photo(G, ROW) is None and G["_sbdb"].asked[0] == "521234567", G["_sbdb"].asked)   # הנייד האישי קודם
G["_sbdb"] = SB({"725550101"})          # התמונה שמורה דווקא על מספר אחר של הסוכן
fp = V._agent_photo(G, ROW)
ck(fp and fp.endswith("v2_avatars/725550101.jpg") and Image.open(fp).size == (256, 256), fp)
G["_sbdb"] = SB(set())
ck(V._agent_photo(G, ROW) == fp, "cached on disk after first fetch")
os.makedirs(os.path.join(AVD, "v2_avatars"), exist_ok=True)
Image.new("RGB", (256, 256), (1, 2, 3)).save(os.path.join(AVD, "v2_avatars", "521234567.jpg"))
ck(V._agent_photo(G, ROW).endswith("521234567.jpg"), "disk: personal phone first")
del os.environ["MAP_CACHE_DIR"]

# ── אישור: אייל בלבד כברירת מחדל ──
G, st, sb = make_G()
G["_quiet_hours"] = lambda: False; G["_shabbat_quiet_now"] = lambda: False
G["DEV_PHONES"] = {"505709865"}
G["_wa_window_open"] = lambda to: False
SENT = []
G["send_text"] = lambda to, t: SENT.append(to) or True
G["_agent_vphones9"] = lambda: set()
G["_phones_for_name"] = lambda n: ["0521234567"]
rec = {"id": "v9", "property_key": "tok1", "video_token": "t", "review_token": "r", "texts": TX, "recipients": []}
sb.videos.append(dict(rec))
ck(V.vid_send_review(G, rec, "https://app", {}) == ["505709865"], SENT)
SENT.clear()
ck(V.vid_send_review(G, rec, "https://app", {"SOCIAL_VIDEO_REVIEW_AGENT": "1"}) == ["505709865", "521234567"], SENT)

# ── רינדור אמיתי קצר (אם יש ffmpeg) ──
import importlib
importlib.reload(T)
if V.vid_ffmpeg():
    d = tempfile.mkdtemp()
    ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    photos = {0: jpg((200, 120, 60)), 1: jpg((60, 160, 90)), 2: jpg((40, 60, 160))}
    shots = T.tour_plan(TX, [0, 1, 2], {0: "נוף פתוח"}, ["מעלית"])
    for theme in T.THEMES:
        out = os.path.join(d, theme + ".mp4")
        rr = T.vid_compose_tour(photos, shots, TX, theme, None, out, os.path.join(ROOT, "family-logo.png"), fp)
        ck(rr["ok"] and os.path.getsize(out) > 10000, rr)
        ck(Image.open(rr["cover"]).size == (1080, 1920), rr)
    ck(not T.vid_compose_tour({0: photos[0]}, shots[:1], TX, "dark", None, os.path.join(d, "x.mp4"), None)["ok"], "1 shot")
print("video_tour OK", n)
