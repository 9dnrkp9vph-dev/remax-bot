# tests/social_video/test_remind.py — [25/11 אייל] תזכורת לאישור סרטון: 3 שעות אחרי שנשלח ולא אושר — פעם אחת
import os, sys, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
import social_video as V
from _fakes import ROW, make_G
NOW = time.time()
iso = lambda t: SP._dt.datetime.fromtimestamp(t, SP._dt.timezone.utc).isoformat()
ENV = {"SOCIAL_MODE": "publish", "APP_BASE_URL": "https://app", "META_TOKEN": "t"}
AGENT = "521234567"

def setup(ago_h, **kw):
    G, st, sb = make_G()
    G["_shabbat_quiet_now"] = lambda: False
    stv = V.VidStore(tempfile.mkdtemp())
    rec = sb.video_insert(dict({"property_key": "tok1", "status": "pending", "trigger": "auto", "video_token": "TOK",
                                "review_token": "RVW", "sent_at": iso(NOW - ago_h * 3600), "recipients": [AGENT],
                                "texts": V.vid_texts(ROW, [], "", "דנה כהן", "", "")}, **kw))
    return G, st, sb, stv, rec

ck(V.REMIND_H == 3, V.REMIND_H)

# פחות מ-3 שעות → כלום
G, st, sb, stv, rec = setup(2.5)
V._housekeeping(G, NOW, ENV, stv)
ck(not st["sent"] and not st["posted"], ("too early", st["sent"], st["posted"]))

# 3 שעות ולא אושר → תזכורת לסוכן (מחוץ לחלון: טקסט עם קישור לדף האישור), מסומן
G, st, sb, stv, rec = setup(3.1)
V._housekeeping(G, NOW, ENV, stv)
ck(len(st["sent"]) == 1 and st["sent"][0][0] == "972" + AGENT, st["sent"])
txt = st["sent"][0][1]
ck("תזכורת" in txt and "/v2/social/review/RVW" in txt, txt)
ck(sb.video_get(rec["id"])["texts"].get("reminded"), sb.video_get(rec["id"])["texts"])
ck(sb.video_get(rec["id"])["status"] == "pending", "still waiting")
# פעם אחת בלבד
V._housekeeping(G, NOW + 3600, ENV, stv)
ck(len(st["sent"]) == 1, ("once", st["sent"]))

# בתוך החלון: הסרטון + כפתורים, עם "תזכורת" בטקסט
G, st, sb, stv, rec = setup(4)
st["window"].add(AGENT)
V._housekeeping(G, NOW, ENV, stv)
btn = [p for p in st["posted"] if p.get("type") == "interactive"]
ck(len(btn) == 1 and "תזכורת" in btn[0]["interactive"]["body"]["text"], st["posted"])

# כבר נשלח לכמה נמענים (אייל לחץ "שלח שוב") → התזכורת לכולם
G, st, sb, stv, rec = setup(4, recipients=[AGENT, "505709865"])
V._housekeeping(G, NOW, ENV, stv)
ck(sorted(x[0] for x in st["sent"]) == ["972505709865", "972" + AGENT], st["sent"])

# שעות שקט / שבת → מחכה (לא נשלח, לא מסומן, בלי review_due); כשהשקט נגמר — נשלח
for key in ("_quiet_hours", "_shabbat_quiet_now"):
    G, st, sb, stv, rec = setup(5)
    G[key] = lambda: True
    V._housekeeping(G, NOW, ENV, stv)
    r2 = sb.video_get(rec["id"])
    ck(not st["sent"] and not st["posted"] and not r2["texts"].get("reminded") and not r2.get("review_due"), key)
    G[key] = lambda: False
    V._housekeeping(G, NOW, ENV, stv)
    ck(len(st["sent"]) == 1, key + " after quiet")

# עדיין לא נשלח בכלל (review_due — חיכה לבוקר) → אין תזכורת; אושר/פג → אין תזכורת
for kw in ({"review_due": True, "recipients": []}, {"status": "approved"}, {"status": "expired"}):
    G, st, sb, stv, rec = setup(5, **kw)
    G["_quiet_hours"] = lambda: True if kw.get("review_due") else False
    V._housekeeping(G, NOW, ENV, stv)
    ck(not st["sent"] and not st["posted"], kw)

# השליחה נכשלה → לא מסומן (ננסה בסבב הבא)
G, st, sb, stv, rec = setup(4)
G["send_text"] = lambda to, txt: False
V._housekeeping(G, NOW, ENV, stv)
ck(not sb.video_get(rec["id"])["texts"].get("reminded"), "retry")

# כיבוי: SOCIAL_VIDEO_REMIND_H=0
G, st, sb, stv, rec = setup(10)
V._housekeeping(G, NOW, dict(ENV, SOCIAL_VIDEO_REMIND_H="0"), stv)
ck(not st["sent"], "off")

print("video_remind OK", n)
