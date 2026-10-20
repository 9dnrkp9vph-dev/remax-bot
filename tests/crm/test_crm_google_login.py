# tests/crm/test_crm_google_login.py — /auth/google/callback עם next=crm: טוקן CRM רק לבעל המשרד או למי שברשימה
import os, sys, warnings, time, re; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_OWNER_EMAILS"] = "eyalshmul@gmail.com"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
A.GOOGLE_CLIENT_ID = A.GOOGLE_CLIENT_ID or "cid"; A.GOOGLE_CLIENT_SECRET = A.GOOGLE_CLIENT_SECRET or "sec"
A._gauth_enabled = lambda: True
A._g_token_exchange = lambda code: {"access_token": "at"}
WHO = {}
A._g_userinfo = lambda at: {"email": WHO["email"], "name": "x"}
A._gauth_all = lambda: {"eyalshmul@gmail.com": {"phone": "505709865"}}
CFG = {"v2_crm_access": {"hodaya@gmail.com": {"name": "הודיה", "phone": "0541111111", "modules": ["dashboard", "meetings"], "scope": "team"}}}
A._load_config = lambda: CFG
LOG = []; A._log_activity = lambda *a: LOG.append(a)
c = A.app.test_client()
def login(email, nxt="crm"):
    WHO["email"] = email
    r = c.get("/auth/google/login?next=" + nxt)
    st = re.search(r"state=([^&]+)", r.headers["Location"]).group(1)
    return c.get("/auth/google/callback?code=x&state=" + st).get_data(as_text=True)
h = login("eyalshmul@gmail.com")
tok = re.search(r"crmTok', \"([^\"]+)\"", h)
ck(tok and A._verify_crm_token(tok.group(1)) == ("505709865", "eyalshmul@gmail.com") and "/v2/crm/dashboard" in h, h[:400])
h = login("Hodaya@gmail.com")
tok = re.search(r"crmTok', \"([^\"]+)\"", h)
ck(tok and A._verify_crm_token(tok.group(1)) == ("541111111", "hodaya@gmail.com") and "/v2/crm/meetings" in h, ("first allowed module", h[:400]))
h = login("stranger@gmail.com")
ck("crmTok" not in h and "אין לך הרשאה" in h, h[:300])
ck(any("כניסה ל-CRM" in str(x) for x in LOG), "logged")
ck(c.get("/crm/login").status_code == 200 and "/auth/google/login?next=crm" in c.get("/crm/login").get_data(as_text=True), "login page")
A._g_userinfo = lambda at: {"email": WHO["email"], "name": "x", "email_verified": False}
ck("crmTok" not in login("eyalshmul@gmail.com"), "unverified Google email refused")
print("crm_google_login OK", n)
