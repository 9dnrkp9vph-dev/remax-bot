# tests/crm/test_switches.py — מתגי כיבוי מהדשבורד: כל הוואטסאפ הרשמי / כל הפושים
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
CFG = {}
A._load_config = lambda: CFG
A._config_mutate = lambda fn: (True, fn(CFG))
A._cache_clear = lambda *a: None
LOG = []; A._log_activity = lambda *a: LOG.append(a)
POSTS = []
class R:
    ok = True; status_code = 200; text = ""
    def json(s): return {"messages": [{}]}
A.requests.post = lambda *a, **k: (POSTS.append(a[0] if a else k.get("url")), R())[1]
A._quiet_mode = lambda: False; A._quiet_hours = lambda: False
A.ONESIGNAL_REST_KEY = "k"
# דלוק (ברירת מחדל)
ok, _ = A._d360_post_message({"to": "972501234567", "type": "text"})
ck(ok and POSTS, "wa sends by default")
POSTS.clear()
ck(A._send_push_raw("t", "b", ["1"]) and POSTS, "push sends by default")
# כיבוי
CFG["v2_switches"] = {"wa_official_off": True, "push_off": True}
POSTS.clear()
ok, r = A._d360_post_message({"to": "972501234567", "type": "text"})
ck(not ok and not POSTS, "wa blocked, nothing posted")
ck(LOG[-1][3] == "וואטסאפ רשמי — מושבת", LOG[-1])
ck(A._send_push_raw("t", "b", ["1"]) is False and not POSTS and A._PUSH_LAST.get("reason") == "PUSH_OFF", A._PUSH_LAST)
# ה-API
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
c = A.app.test_client()
CFG["v2_switches"] = {}
j = c.get("/v2/api/crm/switches").get_json()
ck(j["ok"] and j["wa_official"] is True and j["push"] is True, j)
j = c.post("/v2/api/crm/switches", json={"push": False}).get_json()
ck(j["ok"] and CFG["v2_switches"]["push_off"] is True and "wa_official_off" not in CFG["v2_switches"], CFG)
ck(any("פוש" in str(x[3]) and "כובה" in str(x[3]) for x in LOG), "logged who switched")
A._is_dev = lambda p: False
ck(c.post("/v2/api/crm/switches", json={"push": True}).status_code == 403, "dev only")
print("switches OK", n)
