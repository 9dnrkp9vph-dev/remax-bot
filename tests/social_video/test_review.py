# tests/social_video/test_review.py — אישור בוואטסאפ: שליחה, כפתורים, webhook, דף אישור, קישור /w/
import os, sys, ast, time, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
import social_video as V
from _fakes import ROW, make_G
NOW = time.time()
def iso(t): return SP._dt.datetime.fromtimestamp(t, SP._dt.timezone.utc).isoformat()
ENV = {"SOCIAL_MODE": "publish", "APP_BASE_URL": "https://app"}

def mkrec(sb, **kw):
    r = dict({"property_key": "tok1", "status": "pending", "sent_at": iso(NOW - 60), "video_token": "TOK",
              "review_token": "RVW", "ai": True,
              "texts": V.vid_texts(ROW, [], "", "דנה כהן", "072-555-0101", "")}, **kw)
    return sb.video_insert(r)

# ── שליחה בתוך החלון: וידאו + כפתורים ──
G, st, sb = make_G(); st["window"].update({"505709865", "521234567"})
rec = mkrec(sb)
to = V.vid_send_review(G, rec, "https://app", ENV)
ck(to == ["505709865", "521234567"], to)
ck("725550101" not in to, "virtual excluded")
kinds = [(p["to"], p["type"]) for p in st["posted"]]
ck(kinds == [("972505709865", "video"), ("972505709865", "interactive"), ("972521234567", "video"), ("972521234567", "interactive")], kinds)
vmsg, imsg = st["posted"][0], st["posted"][1]
ck(vmsg["video"]["link"] == "https://app/v2/social/vid/TOK.mp4", vmsg)
btn = imsg["interactive"]["action"]["buttons"]
ck([b["reply"]["id"] for b in btn] == ["vid:%s:pub" % rec["id"], "vid:%s:skip" % rec["id"]] and [b["reply"]["title"] for b in btn] == ["פרסם", "דלג"], btn)
ck("4 חדרים" in imsg["interactive"]["body"]["text"] and "1,890,000" in imsg["interactive"]["body"]["text"], imsg)
ck(not st["sent"], st["sent"])

# ── מחוץ לחלון, בלי תבנית → טקסט עם קישור לדף אישור ──
G, st, sb = make_G()
rec = mkrec(sb, ai=False)
V.vid_send_review(G, rec, "https://app", ENV)
ck(len(st["sent"]) == 2 and all("https://app/v2/social/review/RVW" in t for _, t in st["sent"]), st["sent"])
ck("ללא AI" in st["sent"][0][1] and not st["posted"], st["sent"][0])

# ── מחוץ לחלון, עם תבנית WA_TPL_VIDEO ──
G, st, sb = make_G()
rec = mkrec(sb)
V.vid_send_review(G, rec, "https://app", dict(ENV, WA_TPL_VIDEO="video_review"))
tp = st["posted"][0]
ck(tp["type"] == "template" and tp["template"]["name"] == "video_review", tp)
comps = {c["type"]: c for c in tp["template"]["components"]}
ck(comps["header"]["parameters"][0]["video"]["link"] == "https://app/v2/social/vid/TOK.mp4", comps["header"])
qr = [c for c in tp["template"]["components"] if c["type"] == "button"]
ck([c["parameters"][0]["payload"] for c in qr] == ["vid:%s:pub" % rec["id"], "vid:%s:skip" % rec["id"]], qr)

# ── שעות שקט → לא נשלח, review_due ──
G, st, sb = make_G(); G["_quiet_hours"] = lambda: True
rec = mkrec(sb)
ck(V.vid_send_review(G, rec, "https://app", ENV) == [] and sb.video_get(rec["id"])["review_due"] is True, sb.video_get(rec["id"]))
ck(not st["posted"] and not st["sent"], "quiet")

# ── לחיצה: ראשון קובע ──
G, st, sb = make_G()
rec = mkrec(sb, recipients=["505709865", "521234567"])
PUB = []
V._spawn = lambda fn: fn()
V._blocked_now = lambda G_, t: False   # הבדיקה לא תלויה בשעה שבה היא רצה
V.vid_publish = lambda G_, vid, **kw: (PUB.append(vid), {"ok": True, "status": "published"})[1]
msg = V.vid_on_button(G, "972505709865", "vid:%s:pub" % rec["id"], now=NOW, env=ENV)
ck(PUB == [rec["id"]] and sb.video_get(rec["id"])["status"] == "approved" and sb.video_get(rec["id"])["decided_by"] == "אייל שמול", sb.video_get(rec["id"]))
ck("יעלה" in msg, msg)
msg2 = V.vid_on_button(G, "972521234567", "vid:%s:pub" % rec["id"], now=NOW, env=ENV)
ck(PUB == [rec["id"]] and msg2 == "כבר פורסם ע\"י אייל שמול", msg2)
ck(any(t == "972521234567" and "כבר פורסם" in x for t, x in st["sent"]), st["sent"])
ck(V.vid_on_button(G, "972599999999", "vid:%s:skip" % rec["id"], now=NOW, env=ENV) is None, "stranger")
ck(V.vid_on_button(G, "972505709865", "evil:1:pub", now=NOW, env=ENV) is None, "foreign payload")
ck(V.vid_on_button(G, "972505709865", "vid:nope:pub", now=NOW, env=ENV) is None, "unknown id")
rec2 = mkrec(sb, recipients=["505709865"])
ck(V.vid_on_button(G, "972505709865", "vid:%s:skip" % rec2["id"], now=NOW, env=ENV) == "דולג — לא יעלה" and sb.video_get(rec2["id"])["status"] == "skipped", "skip")
rec3 = mkrec(sb, recipients=["505709865"], sent_at=iso(NOW - 49 * 3600))
ck(V.vid_on_button(G, "972505709865", "vid:%s:pub" % rec3["id"], now=NOW, env=ENV) == "הסרטון כבר לא בתוקף" and sb.video_get(rec3["id"])["status"] == "expired", "expired")
night = SP._dt.datetime(2026, 11, 2, 23, 30, tzinfo=SP._IL).timestamp()
rec4 = mkrec(sb, recipients=["505709865"], sent_at=iso(night - 60)); PUB.clear()
V._blocked_now = lambda G_, t: True
m4 = V.vid_on_button(G, "972505709865", "vid:%s:pub" % rec4["id"], now=night, env=ENV)
ck(PUB == [] and sb.video_get(rec4["id"]).get("publish_at") and "08:00" in m4, (m4, sb.video_get(rec4["id"])))
V._blocked_now = lambda G_, t: False

# ── דף אישור ──
rec5 = mkrec(sb, review_token="R5", recipients=["505709865"])
code, html = V.vid_review_page(G, "R5", NOW)
ck(code == 200 and "/v2/social/vid/TOK.mp4" in html and "פרסם" in html and "דלג" in html and 'dir="rtl"' in html, code)
ck(V.vid_review_page(G, "nope", NOW)[0] == 404, "404")
code, txt = V.vid_review_action(G, "R5", "pub", NOW, ENV)
ck(code == 200 and sb.video_get(rec5["id"])["status"] == "approved", (code, txt))
ck(V.vid_review_action(G, "R5", "pub", NOW, ENV)[1].startswith("כבר פורסם"), "page double")
ck(V.vid_review_action(G, "nope", "pub", NOW, ENV)[0] == 404, "page 404")
rec6 = mkrec(sb, review_token="R6", sent_at=iso(NOW - 49 * 3600))
ck("לא בתוקף" in V.vid_review_page(G, "R6", NOW)[1], "expired page")

# ── קישור /w/ ──
sb.link_insert({"code": "abc1234", "video_id": rec["id"], "property_key": "tok1", "channel": "fb_reel"})
code, loc = V.vid_wa_redirect(G, "abc1234", ENV)
ck(code == 302 and loc.startswith("https://wa.me/972521234567?text=") and sb.links["abc1234"]["clicks"] == 1, (code, loc))
from urllib.parse import unquote
t = unquote(loc.split("text=", 1)[1])
ck("בפייסבוק" in t and "4 חדרים" in t and "tok1" in t and "13" not in t, t)
ck(V.vid_wa_redirect(G, "zzz", ENV)[0] == 404, "unknown code")
G2, _, sb2 = make_G(cfg={"v2_office": {"name": "רימקס פמילי", "phone": "04-6000800"}})
G2["_phones_for_name"] = lambda n: ["0725550101"]
sb2.link_insert({"code": "c2", "property_key": "tok1", "channel": "fb_reel"})
ck(V.vid_wa_redirect(G2, "c2", ENV)[1].startswith("https://wa.me/97246000800"), V.vid_wa_redirect(G2, "c2", ENV))

# ── webhook ב-app.py מנתב כפתורים ──
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "app.py"), encoding="utf-8").read()
fn = next(nd for nd in ast.parse(src).body if isinstance(nd, ast.FunctionDef) and nd.name == "_d360_webhook")
CALLS = []
class FakeSV:
    @staticmethod
    def vid_on_button(g, frm, payload): CALLS.append((frm, payload)); return None
ns = {"_wa_window_mark": lambda x: None, "log": type("L", (), {"warning": staticmethod(lambda *a: None)})(),
      "_WA_STATUS_LOG": [], "_wa_diag_save": lambda: None, "_il_now_hm": lambda: "", "_social_video": FakeSV}
ns["globals"] = lambda: ns
exec(compile(ast.Module(body=[fn], type_ignores=[]), "app.py", "exec"), ns)
ns["_d360_webhook"]({"entry": [{"changes": [{"value": {"messages": [
    {"from": "972505709865", "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "vid:v1:pub", "title": "פרסם"}}},
    {"from": "972521234567", "type": "button", "button": {"payload": "vid:v1:skip", "text": "דלג"}},
    {"from": "972521234567", "type": "text", "text": {"body": "hi"}}]}}]}]})
ck(CALLS == [("972505709865", "vid:v1:pub"), ("972521234567", "vid:v1:skip")], CALLS)
print("video_review OK", n)
