# tests/crm/test_parallel_page.py — עמוד /v2/crm/parallel: נפתח בדפדפן עם טוקן הכניסה של אפי (fbTok) ומציג את הדוח
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
c = A.app.test_client()
r = c.get("/v2/crm/parallel")
assert r.status_code == 200 and "text/html" in r.content_type, r.status_code
h = r.get_data(as_text=True)
assert "crmTok" in h and "/crm/login" in h and "X-Auth-Token" in h and "/v2/api/crm/parallel" in h, "uses app login token"
assert 'dir="rtl"' in h and "Heebo" in h, "RTL + font"
print("parallel_page OK")
