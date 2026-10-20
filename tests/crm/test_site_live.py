# tests/crm/test_site_live.py — 'באתר עכשיו' בלוח הבקרה (אייל 21/10): אפי קוראת /site/live מהאתר במפתח
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
import effie_v2 as E
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
os.environ["SITE_KEY"] = "kk"; os.environ["SITE_PUBLIC_URL"] = "https://site.test/"
CALLS = []
class R:
    status_code = 200
    def json(self): return {"ok": True, "now": 3, "by_src": {"facebook": 2, "direct": 1}}
def fake_get(url, headers=None, timeout=None):
    CALLS.append((url, headers)); return R()
E._requests.get = fake_get
c = A.app.test_client()
j = c.get("/v2/api/crm/site_live").get_json()
ck(j == {"ok": True, "now": 3, "by_src": {"facebook": 2, "direct": 1}}, j)
ck(CALLS[0][0] == "https://site.test/site/live" and CALLS[0][1] == {"X-Site-Key": "kk"}, CALLS)
c.get("/v2/api/crm/site_live")
ck(len(CALLS) == 1, "10s cache")
A._is_dev = lambda p: False
ck(c.get("/v2/api/crm/site_live").status_code == 403, "owner only")
html = E._CRM_DASH_HTML if hasattr(E, "_CRM_DASH_HTML") else ""
src = open(E.__file__, encoding="utf-8").read()
ck("באתר עכשיו" in src and "siteLive()" in src and "/v2/api/crm/site_live" in src, "dashboard card")
print("site_live OK", n)
