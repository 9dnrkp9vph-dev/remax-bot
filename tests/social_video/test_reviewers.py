# tests/social_video/test_reviewers.py — [18/11 אייל] מי מאשר סרטון, יצירה אוטומטית לסוכן פעיל, ומגבלה ידנית של 2 ביום
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
import social_video as V
from _fakes import ROW, make_G
SP.soc_hidden = lambda G: set()

def G_():
    G, st, sb = make_G()
    G["_shabbat_quiet_now"] = lambda: False
    return G, st, sb

# ── מי מאשר ──
# אוטומטי → הסוכן של הנכס, לנייד האישי (לא אייל, לא המרכזיה)
G, st, sb = G_()
auto = {"id": "v1", "property_key": "tok1", "trigger": "auto", "by_phone": ""}
ck(V.vid_reviewers(G, auto, {}) == ["521234567"], V.vid_reviewers(G, auto, {}))
# לסוכן אין נייד אישי → נופל לאייל (שלא ייתקע בלי מאשר)
G["_phones_for_name"] = lambda nm: ["0725550101"]
ck(V.vid_reviewers(G, auto, {}) == ["505709865"], "fallback to owner")
ck(V.vid_reviewers(G, auto, {"SOCIAL_VIDEO_APPROVER": "0509998877"}) == ["509998877"], "explicit approver")
# ידני → מי שיצר מאשר לעצמו (סוכן, מתאמת או אייל)
G, st, sb = G_()
ck(V.vid_reviewers(G, dict(auto, trigger="manual", by_phone="0503334444"), {}) == ["503334444"], "creator approves")
ck(V.vid_reviewers(G, dict(auto, trigger="manual", by_phone=""), {}) == ["521234567"], "manual without phone → agent")

# בפועל: הודעת האישור של סרטון אוטומטי יוצאת לסוכן בלבד
G, st, sb = G_()
rec = sb.video_insert(dict(auto, video_token="t", review_token="r", texts={"open": {"title": "דירה"}}, recipients=[]))
ck(V.vid_send_review(G, rec, "https://app", {}) == ["521234567"], st)
ck({x[0] for x in st["sent"]} == {"972521234567"} and not st["posted"], st)
# "שלח שוב" של אייל על סרטון של סוכן → גם אייל מקבל
st["sent"].clear()
ck(sorted(V.vid_send_review(G, rec, "https://app", {}, initiator="0505709865")) == ["505709865", "521234567"], st["sent"])

# ── מגבלה ידנית: 2 סרטונים ביום לכל משתמש ──
NOW = time.time()
iso = lambda ago: SP._dt.datetime.fromtimestamp(NOW - ago, SP._dt.timezone.utc).isoformat()
mk = lambda **kw: dict({"trigger": "manual", "by_phone": "0501111111", "status": "pending", "mode": "publish", "created_at": iso(60)}, **kw)
H = [mk(), mk(status="failed"), mk(mode="preview", status="preview"), mk(created_at=iso(2 * 86400)), mk(by_phone="0509999999"),
     mk(trigger="auto"), mk(status="published")]
ck(V.vid_manual_used(H, "501111111", NOW) == 2, V.vid_manual_used(H, "501111111", NOW))
ck(V.vid_manual_used(H, "", NOW) == 0, "no phone")

# ── יצירה אוטומטית: רק לסוכן פעיל, רק עם 2+ תמונות (מחכה בלי הגבלת זמן), ברירת מחדל לפי SOCIAL_AUTO ──
ck(V.vid_auto_on({"SOCIAL_AUTO": "1"}) and not V.vid_auto_on({"SOCIAL_AUTO": "0"}) and not V.vid_auto_on({}), "follows SOCIAL_AUTO")
ck(not V.vid_auto_on({"SOCIAL_AUTO": "1", "SOCIAL_VIDEO_AUTO": "0"}) and V.vid_auto_on({"SOCIAL_VIDEO_AUTO": "1"}), "explicit wins")

ON = {"SOCIAL_AUTO": "1", "SOCIAL_MODE": "publish", "META_TOKEN": "T"}
import datetime as dt
T0 = dt.datetime(2026, 11, 3, 12, 0, tzinfo=SP._IL).timestamp()
rows = lambda *ks, **kw: [dict(ROW, **dict({"מספר מודעה": k, "כתובת": "רחוב " + k}, **kw)) for k in ks]
MADE = []
V.vid_create_one = lambda G_, key, trigger, by_phone, **kw: (MADE.append((key, trigger)), {"ok": True})[1]
stv = V.VidStore(tempfile.mkdtemp())

def world(active):
    G, st, sb = G_()
    G["_usage_rows"] = lambda start: [{"name": ROW["סוכן 1"], "min": 60 if active else 3}]
    SP._ACTIVE_BOX.clear()
    listing = {"rows": rows("a")}
    G["fetch_sheet_rows"] = lambda: list(listing["rows"])
    V.vid_auto_tick(G, T0, ON, store=stv)          # זריעה: הנכסים הקיימים לא מקבלים סרטון
    return G, st, listing

G, st, L = world(active=True); MADE.clear()
L["rows"] = rows("a", "b")
V.vid_auto_tick(G, T0 + 600, ON, store=stv)
ck(MADE == [("b", "auto")], MADE)

G, st, L = world(active=False); MADE.clear()   # הסוכן היה באפי פחות מ-10 דק' ב-30 יום → לא נוצר
L["rows"] = rows("a", "b")
V.vid_auto_tick(G, T0 + 600, ON, store=stv)
ck(MADE == [] and "b" in st["cfg"]["v2_social"]["vid_waiting"], (MADE, st["cfg"]["v2_social"]))

G, st, L = world(active=True); MADE.clear()    # תמונה אחת → מחכה, גם אחרי חודש; כשנוספות תמונות — נוצר
one = rows("b", **{"תמונות": ["https://img/a.jpg"]})
for d in range(1, 36):
    L["rows"] = rows("a") + one
    V.vid_auto_tick(G, T0 + d * 86400 - 3600, ON, store=stv)
ck(MADE == [] and "b" in st["cfg"]["v2_social"]["vid_waiting"], MADE)
L["rows"] = rows("a", "b")
V.vid_auto_tick(G, T0 + 35 * 86400, ON, store=stv)
ck(MADE == [("b", "auto")], MADE)

print("video_reviewers OK", n)
