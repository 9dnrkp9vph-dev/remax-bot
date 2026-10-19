# tests/crm/test_wa_count.py — וואטסאפ: כל הודעה מהמספר הרשמי נרשמת; פתיחת וואטסאפ מאפי (טלפון הסוכן) נרשמת לפי מסך
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
LOG = []
A._log_activity = lambda *a: LOG.append(a)
class R:
    def __init__(s, ok): s.ok = ok; s.status_code = 200 if ok else 400; s.text = ""
    def json(s): return {"messages": [{"id": "x"}]} if s.ok else {"error": 1}
A.requests.post = lambda *a, **k: R(True)
ok, _ = A._d360_post_message({"to": "972501234567", "type": "text"})
ck(ok and LOG and LOG[-1][3] == "וואטסאפ רשמי — נשלח" and LOG[-1][1] == "system", LOG)
ck("4567" in LOG[-1][4] and "972501234567" not in LOG[-1][4], "only last 4 digits")
A.requests.post = lambda *a, **k: R(False)
A._d360_post_message({"to": "972501234567", "type": "template"})
ck(LOG[-1][3] == "וואטסאפ רשמי — נכשל", LOG[-1])
# פתיחת וואטסאפ מאפי
import effie_v2  # noqa
A._web_auth = lambda: {"phone": "505709865", "name": "אלי שמול", "role": "agent"}
c = A.app.test_client()
LOG.clear()
j = c.post("/v2/api/wa/click", json={"page": "/v2/newborn"}).get_json()
ck(j["ok"] and LOG[-1][0] == "אלי שמול" and LOG[-1][3] == "וואטסאפ מהטלפון — נכס נולד", LOG)
c.post("/v2/api/wa/click", json={"page": "/v2/buyers"}); ck(LOG[-1][3] == "וואטסאפ מהטלפון — קונים", LOG[-1])
c.post("/v2/api/wa/click", json={"page": "/v2/weird"}); ck(LOG[-1][3] == "וואטסאפ מהטלפון — אחר", LOG[-1])
A._web_auth = lambda: None
ck(c.post("/v2/api/wa/click", json={"page": "/v2/buyers"}).status_code == 403, "auth")
print("wa_count OK", n)
