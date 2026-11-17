# tests/social_video/test_agent_send.py — [17/11 אייל] אחרי האישור והפרסום: הסרטון נשלח לסוכן בוואטסאפ, לנייד האישי (לא לווירטואלי)
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_video as V
from _fakes import ROW, make_G

ENV = {"SOCIAL_MODE": "publish", "APP_BASE_URL": "https://app", "META_TOKEN": "t"}
NOW = time.time()

def setup(**over):
    G, st, sb = make_G()
    G["_shabbat_quiet_now"] = lambda: False
    stv = V.VidStore(tempfile.mkdtemp())
    tok = stv.new_token()
    open(stv.path(tok), "wb").write(b"x" * 10)
    rec = sb.video_insert(dict({"property_key": "tok1", "video_token": tok, "status": "published", "ig_reel_status": "ok",
                                "ig_reel_permalink": "https://ig/r", "fb_reel_permalink": "https://fb/r",
                                "recipients": ["505709865"],
                                "texts": {"open": {"title": "דירת 4 חדרים", "place": "נאות אפק, קרית ביאליק"}}}, **over))
    return G, st, sb, stv, rec

# בתוך חלון 24ש': הודעת וידאו אחת עם כיתוב — לנייד האישי, לא למספר המרכזיה
G, st, sb, stv, rec = setup()
st["window"].add("521234567")
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "521234567", st)
p = st["posted"][-1]
ck(len(st["posted"]) == 1 and p["to"] == "972521234567" and p["type"] == "video", st["posted"])
ck(p["video"]["link"] == "https://app/v2/social/vid/%s.mp4" % rec["video_token"], p)
cap = p["video"]["caption"]
ck("דנה" in cap and "דירת 4 חדרים" in cap and "https://ig/r" in cap and "https://fb/r" in cap, cap)
ck(not st["sent"] and "725550101" not in str(st["posted"]), "never the virtual line")
ck(sb.videos[-1]["texts"]["agent_sent"] and sb.videos[-1]["texts"]["open"]["title"] == "דירת 4 חדרים", sb.videos[-1]["texts"])
# פעם אחת בלבד
ck(V.vid_send_agent(G, sb.video_get(rec["id"]), ENV, store=stv) == "" and len(st["posted"]) == 1, "once")

# מחוץ לחלון: הודעת טקסט עם קישור לסרטון (send_text — תבנית family_update)
G, st, sb, stv, rec = setup()
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "521234567" and not st["posted"], st)
to, txt = st["sent"][-1]
ck(to == "972521234567" and "/v2/social/vid/%s.mp4" % rec["video_token"] in txt and "דירת 4 חדרים" in txt, st["sent"])
ck(sb.videos[-1]["texts"].get("agent_sent"), "marked")

# וואטסאפ דחה את הווידאו → נפילה לטקסט עם קישור
G, st, sb, stv, rec = setup()
st["window"].add("521234567")
G["_d360_post_message"] = lambda payload: (st["posted"].append(payload), (False, "rejected"))[1]
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "521234567" and len(st["sent"]) == 1, st)

# שום דבר לא יצא → לא מסומן (התחזוקה תנסה שוב)
G, st, sb, stv, rec = setup()
G["send_text"] = lambda to, txt: False
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "" and not sb.videos[-1]["texts"].get("agent_sent"), "retry later")

# שעות שקט / שבת → לא שולחים עכשיו ולא מסמנים
for key in ("_quiet_hours", "_shabbat_quiet_now"):
    G, st, sb, stv, rec = setup()
    G[key] = lambda: True
    ck(V.vid_send_agent(G, rec, ENV, store=stv) == "" and not st["sent"] and not st["posted"], key)
    ck(not sb.videos[-1]["texts"].get("agent_sent"), key + " not marked")

# לסוכן יש רק מספר מרכזיה → לא נשלח לשום מקום
G, st, sb, stv, rec = setup()
G["_phones_for_name"] = lambda nm: ["0725550101"]
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "" and not st["sent"] and not st["posted"], "virtual only")

# הסוכן הוא מי שאישר (כבר קיבל את הסרטון) → לא שולחים שוב, מסומן
G, st, sb, stv, rec = setup(recipients=["521234567"])
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "" and not st["sent"] and sb.videos[-1]["texts"].get("agent_sent"), "approver = agent")

# כבוי ב-Render / מצב בדיקה / הקובץ כבר נמחק / שום ערוץ לא עלה
G, st, sb, stv, rec = setup()
ck(V.vid_send_agent(G, rec, dict(ENV, SOCIAL_VIDEO_SEND_AGENT="0"), store=stv) == "" and not st["sent"], "off")
ck(V.vid_send_agent(G, rec, dict(ENV, SOCIAL_MODE="preview"), store=stv) == "" and not st["sent"], "preview")
os.remove(stv.path(rec["video_token"]))
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "" and not st["sent"], "file gone")
G, st, sb, stv, rec = setup(ig_reel_status="failed", status="partial")
ck(V.vid_send_agent(G, rec, ENV, store=stv) == "" and not st["sent"], "nothing published")

# התחזוקה משלימה: סרטון שעלה בזמן שקט (או שהשליחה נכשלה) נשלח בסבב הבא; סרטון ממתין — לא
G, st, sb, stv, rec = setup()
sb.video_insert({"property_key": "tok1", "video_token": "zz", "status": "pending", "texts": {}, "recipients": []})
V._housekeeping(G, NOW, ENV, stv)
ck(len(st["sent"]) == 1 and st["sent"][0][0] == "972521234567", st["sent"])
V._housekeeping(G, NOW, ENV, stv)
ck(len(st["sent"]) == 1, "housekeeping sends once")

print("video_agent_send OK", n)
