# tests/kit/test_review_view.py — אישור התיק, דף הצפייה של בעל הנכס ומעקב צפיות (בלי רשת)
import os, sys, re, json, subprocess, tempfile, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ["KIT_TICK"] = "0"
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from flask import Flask
import kit_core as KC
import kit as K
from test_routes import SBK
from test_render import sample


class SBT(SBK):
    def kit_by_token(self, col, tok):
        return next((dict(r) for r in self.kits if r.get(col) == tok and tok), None)


def iso(h=0):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=h)).isoformat()


sb = SBT()
st = {"sent": [], "acts": [], "quiet": False, "ok": True}
CFG = {"v2_office": {"name": "רימקס פמילי"}}
G = {"_sbdb": sb, "_load_config": lambda: CFG, "_web_auth": lambda: None,
     "send_text": lambda to, txt: (st["sent"].append((to, txt)), st["ok"])[1],
     "_quiet_hours": lambda: st["quiet"], "_shabbat_quiet_now": lambda: False,
     "DEV_PHONES": {"505709865"}, "_last9": lambda p: "".join(c for c in str(p) if c.isdigit())[-9:],
     "_display_name_for": lambda nm, p: {"505709865": "אייל שמול"}.get(p, nm),
     "_log_activity": lambda *a: st["acts"].append(a)}
app = Flask(__name__); K.register(app, G); c = app.test_client()


def mk(status="pending", h=1, **kw):
    snap = sample()
    snap["claims"] = dict(snap["claims"], **kw.pop("claims", {}))
    r = dict(status=status, agent_name="אוהד לוי", agent_phone="501111111", owner_name="משה כהן",
             owner_phone="544448065", snapshot=snap, sent_review_at=iso(h),
             review_token="rv" + str(len(sb.kits)) + "abcdefghij", view_token="vw" + str(len(sb.kits)) + "abcdefghij")
    r.update(kw)
    return sb.kit_insert(r)


def test_send_review():
    rec = mk()
    st["quiet"] = True
    ck(K.send_review(G, rec, "https://x.test") is False and st["sent"] == [], st["sent"])
    ck(sb.kit_get(rec["id"])["review_due"] is True, sb.kit_get(rec["id"]))
    st["quiet"] = False
    ck(K.send_review(G, rec, "https://x.test") is True, "sent")
    to, txt = st["sent"][-1]
    ck(to == "972505709865", to)
    ck(txt.startswith("תיק פרזנטציה חדש לאישור\nאוהד לוי · משה כהן · הנוטר, קרית ביאליק\n"), txt)
    ck("https://x.test/v2/kit/review/" + rec["review_token"] in txt and "544448065" not in txt, txt)
    r = sb.kit_get(rec["id"])
    ck(r["review_due"] is False and r["sent_review_at"], r)
    # KIT_APPROVER גובר
    os.environ["KIT_APPROVER"] = "052-1234567"
    try:
        K.send_review(G, rec, "https://x.test")
        ck(st["sent"][-1][0] == "972521234567", st["sent"][-1])
    finally:
        del os.environ["KIT_APPROVER"]
    # כשל שליחה → נשאר לסבב הבא
    st["ok"] = False
    ck(K.send_review(G, rec, "https://x.test") is False and sb.kit_get(rec["id"])["review_due"] is True, "fail")
    st["ok"] = True
    # הסבב שולח רק ממתינים שמסומנים review_due ועוד לא פגו
    old = mk(h=50, review_due=True); done = mk("approved", review_due=True); due = mk(review_due=True)
    st["sent"].clear()
    K._kit_tick_once(G)
    got = sorted(t.rsplit("/", 1)[1] for _, t in st["sent"])
    ck(got == sorted([rec["review_token"], due["review_token"]]), got)   # rec נשאר review_due מהכשל
    ck(not any(old["review_token"] in t or done["review_token"] in t for _, t in st["sent"]), "tick filter")


def test_review_page_and_decide():
    rec = mk()
    tok = rec["review_token"]
    ck(c.get("/v2/kit/review/bad!tok").status_code == 404, "bad")
    ck(c.get("/v2/kit/review/zzzzzzzz").status_code == 404, "unknown")
    r = c.get("/v2/kit/review/" + tok)
    h = r.get_data(as_text=True)
    ck(r.status_code == 200 and h.count("<img") == 6, h.count("<img"))
    ck("אשר ושלח לסוכן" in h and "דחה" in h and 'maxlength="300"' in h and "544448065" not in h, "buttons")
    ck(r.headers["Cache-Control"] == "no-store" and "noindex" in r.headers["X-Robots-Tag"], r.headers)
    im = c.get("/v2/kit/review/%s/p1.jpg" % tok)
    ck(im.status_code == 200 and im.mimetype == "image/jpeg" and im.data[:2] == b"\xff\xd8", im.status_code)
    ck(c.get("/v2/kit/review/%s/p7.jpg" % tok).status_code == 404 and c.get("/v2/kit/review/%s/p0.jpg" % tok).status_code == 404, "range")
    # אישור
    r = c.post("/v2/kit/review/" + tok, json={"action": "approve"})
    ck(r.get_data(as_text=True) == "אושר" and r.mimetype == "text/plain", r.get_data(as_text=True))
    k = sb.kit_get(rec["id"])
    ck(k["status"] == "approved" and k["decided_at"] and k["decided_by"] == "אייל שמול", k)
    ck(st["acts"][-1][3] == "תיק פרזנטציה — אושר", st["acts"][-1])
    ck(c.post("/v2/kit/review/" + tok, json={"action": "approve"}).get_data(as_text=True) == "כבר אושר", "2nd")
    ck(c.post("/v2/kit/review/" + tok, json={"action": "reject"}).get_data(as_text=True) == "כבר אושר", "rej after")
    h = c.get("/v2/kit/review/" + tok).get_data(as_text=True)
    ck("אושר" in h and 'id="act"' not in h, "status line")
    # דחייה עם סיבה
    r2 = mk()
    t = c.post("/v2/kit/review/" + r2["review_token"], json={"action": "reject", "reason": "  חסר מחיר " + "x" * 400})
    ck(t.get_data(as_text=True) == "נדחה", t.get_data(as_text=True))
    k2 = sb.kit_get(r2["id"])
    ck(k2["status"] == "rejected" and k2["reject_reason"].startswith("חסר מחיר") and len(k2["reject_reason"]) == 300, k2)
    ck(st["acts"][-1][3] == "תיק פרזנטציה — נדחה", st["acts"][-1])
    ck(c.post("/v2/kit/review/" + r2["review_token"], json={"action": "approve"}).get_data(as_text=True) == "כבר נדחה", "after reject")
    # פג תוקף
    r3 = mk(h=49)
    ck(c.post("/v2/kit/review/" + r3["review_token"], json={"action": "approve"}).get_data(as_text=True) == "פג תוקף", "expired")
    ck(sb.kit_get(r3["id"])["status"] == "pending", "not flipped")
    # הפסיד במרוץ: מישהו אחר החליט בין הקריאה ל-PATCH
    r4 = mk()
    real = sb.kit_claim
    def lose(kid, frm, to, f):
        sb.kit_update(kid, {"status": "rejected"}); return False
    sb.kit_claim = lose
    try:
        ck(c.post("/v2/kit/review/" + r4["review_token"], json={"action": "approve"}).get_data(as_text=True) == "כבר נדחה", "race")
    finally:
        sb.kit_claim = real
    # טוקן ישן אחרי שליחה חוזרת
    sb.kit_update(r4["id"], {"review_token": "rotatedtokenxyz"})
    ck(c.post("/v2/kit/review/" + r4["review_token"], json={"action": "approve"}).status_code == 404, "old token")


def _closed(path):
    r = c.get(path)
    h = r.get_data(as_text=True)
    ck(r.status_code == 410 and "<img" not in h and "התיק אינו זמין" in h and "רימקס פמילי" in h, (path, r.status_code))
    ck(r.headers["Cache-Control"] == "no-store" and "noindex" in r.headers["X-Robots-Tag"], r.headers)
    ck("{" not in h.split("<style>")[0] and "משה" not in h, "no snapshot data")


def test_view_closed():
    for kit in (mk("pending"), mk("rejected"), mk(h=49)):
        v = kit["view_token"]
        _closed("/k/" + v)
        ck(c.get("/k/%s/p1.jpg" % v).status_code == 410 and c.get("/k/%s.pdf" % v).status_code == 410, "assets closed")
        ck(c.post("/k/%s/ping" % v).status_code == 410, "ping closed")
    _closed("/k/unknowntoken123")
    _closed("/k/bad!token")


def test_view_open():
    kit = mk("approved")
    v = kit["view_token"]
    r = c.get("/k/" + v)
    h = r.get_data(as_text=True)
    ck(r.status_code == 200 and h.count("<img") == 6 and ("/k/%s.pdf" % v) in h, h.count("<img"))
    ck(r.headers["Cache-Control"] == "no-store" and "noindex" in r.headers["X-Robots-Tag"], r.headers)
    ck("העסק שלנו בגוגל" in h and "https://g.page/r/bialik" in h, "google")
    ck("wa.me/972501111111" in h and "wa.me/972544448065" not in h and "544448065" not in h, "wa agent")
    ck("לעמוד של אוהד לוי באתר" in h and "לאתר הנכסים שלנו" in h and "הורד כ-PDF" in h, "links")
    ck("snapshot" not in h and "1,850,000" not in h and "משה" not in h, "no snapshot data")
    imgs = re.findall(r'<img[^>]*src="([^"]+)"', h)
    ck(imgs == ["/k/%s/p%d.jpg" % (v, i) for i in range(1, 7)] and "<a" not in "".join(re.findall(r"<a[^>]*><img", h)), imgs)
    ck(c.get("/k/%s/p6.jpg" % v).data[:2] == b"\xff\xd8" and c.get("/k/%s/p7.jpg" % v).status_code == 404, "p6/p7")
    # בלי קישור לגוגל
    k2 = mk("sent", claims={"g_url": ""})
    h2 = c.get("/k/" + k2["view_token"]).get_data(as_text=True)
    ck("העסק שלנו בגוגל" not in h2, "no google")
    ck(">אינסטגרם<" not in h2 and ">פייסבוק<" not in h2, "no social by default")
    k3 = mk("approved", claims={"instagram": "https://instagram.com/remaxfamily", "facebook": "http://bad"})
    h3 = c.get("/k/" + k3["view_token"]).get_data(as_text=True)
    ck("https://instagram.com/remaxfamily" in h3 and ">אינסטגרם<" in h3 and ">פייסבוק<" not in h3, "social links")
    # PDF
    p = c.get("/k/%s.pdf" % v)
    ck(p.status_code == 200 and p.data[:4] == b"%PDF" and p.mimetype == "application/pdf", p.status_code)
    cd = p.headers["Content-Disposition"]
    ck(cd.startswith("attachment; filename*=UTF-8''") and "%D7" in cd, cd)
    ck(p.headers["Cache-Control"] == "no-store", p.headers)
    # ping
    ck(c.post("/k/%s/ping" % v).status_code == 204, "ping")
    ck(c.post("/k/%s/ping" % v).status_code == 204, "ping 2")
    vv = sb.kit_get(kit["id"])["views"]
    ck(vv["opens"] == 1 and vv["secs"] == 15, vv)
    # סקריפט הפעימה
    js = re.findall(r"<script>(.*?)</script>", h, re.S)
    ck(len(js) == 1 and "setInterval(p,15000)" in js[0] and "visibilityState==='hidden'" in js[0]
       and "/k/%s/ping" % v in js[0], js)
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write(js[0]); f.close()
    ck(subprocess.run(["node", "--check", f.name]).returncode == 0, "node --check")
    rv = re.findall(r"<script>(.*?)</script>", c.get("/v2/kit/review/" + kit["review_token"]).get_data(as_text=True), re.S)
    f2 = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f2.write("\n".join(rv)); f2.close()
    ck(subprocess.run(["node", "--check", f2.name]).returncode == 0, "node --check review")


def test_binding():
    RULES = {(r.rule, m): r.endpoint for r in app.url_map.iter_rules() for m in (r.methods or ()) if m in ("GET", "POST")}
    want = {("/v2/kit/review/<tok>", "GET"): "kit_review_page", ("/v2/kit/review/<tok>", "POST"): "kit_review_decide",
            ("/v2/kit/review/<tok>/p<int:n>.jpg", "GET"): "kit_review_img",
            ("/k/<vtok>", "GET"): "kit_view_page", ("/k/<vtok>/p<int:n>.jpg", "GET"): "kit_view_img",
            ("/k/<vtok>.pdf", "GET"): "kit_view_pdf", ("/k/<vtok>/ping", "POST"): "kit_view_ping"}
    for rule, ep in want.items():
        ck(RULES.get(rule) == ep and app.view_functions[ep].__name__ == ep, (rule, RULES.get(rule)))


if __name__ == "__main__":
    for _f in (test_send_review, test_review_page_and_decide, test_view_closed, test_view_open, test_binding):
        _f()
    print("OK", n)
