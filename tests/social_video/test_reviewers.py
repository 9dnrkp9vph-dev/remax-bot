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

# [18/11 אייל] הסרטון האוטומטי הולך אחרי הפוסט האוטומטי (הפוסט כבר עבר: סוכן פעיל, 2+ תמונות) — ונשלח לאישור הסוכן
ON = {"SOCIAL_AUTO": "1", "SOCIAL_MODE": "publish", "META_TOKEN": "T"}
import datetime as dt
T0 = dt.datetime(2026, 11, 3, 12, 0, tzinfo=SP._IL).timestamp()
MADE = []
real_create = V.vid_create_one
V.vid_create_one = lambda G_, key, trigger, by_phone, **kw: (MADE.append((key, trigger)), {"ok": True})[1]
stv = V.VidStore(tempfile.mkdtemp())
G, st, sb = G_()
V.vid_auto_tick(G, T0, ON, store=stv)
ck(MADE == [], "listing without an automatic post → no video")
sb.rows.append({"id": "p1", "property_key": "tok1", "trigger": "auto", "mode": "publish", "ig_status": "ok",
                "created_at": dt.datetime.fromtimestamp(T0 - 300, dt.timezone.utc).isoformat()})
V.vid_auto_tick(G, T0, ON, store=stv)
ck(MADE == [("tok1", "auto")], MADE)
V.vid_create_one = real_create
print("video_reviewers OK", n)
