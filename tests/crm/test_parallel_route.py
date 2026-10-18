# tests/crm/test_parallel_route.py — הראוט האמיתי /v2/api/crm/parallel עם מקורות מזויפים
import os, sys, warnings, datetime; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from zoneinfo import ZoneInfo
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
today = datetime.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
dmy = today.strftime("%d/%m/%Y")
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
A.web_fetch_raw = lambda t, f, to: [dict(caller_phone="0546631493", agent_phone="0505235330", agent="אלי",
                                        received_at=dmy + " 17:08")]
A.get_signings = lambda *a, **k: [dict(agent="דידי לוי", commission_pct="https://sign.hatimatova.co.il/x", received_at=dmy + " 10:00")]
class FakeSB:
    def enabled(s): return True
    def fetch_shadow(s, st, since):
        return [dict(caller_phone="546631493", agent_phone="505235330", received_at=dmy + " 17:09")] if st == "calls" else []
    def fetch_invoices_rows(s, q, limit=400): return [dict(doc_num="7", created_at=today.isoformat() + "T10:00:00+03:00")]
A._sbdb = FakeSB()
c = A.app.test_client()
j = c.get("/v2/api/crm/parallel?days=2").get_json()
ck(j["ok"] and len(j["days"]) == 2 and j["days"][-1]["day"] == today.isoformat(), j)
ck(j["days"][-1]["calls"]["matched"] == 1 and j["days"][-1]["invoices"]["only_legacy"], j["days"][-1])
ck(j["sig_nonapp"] == [["דידי לוי", 1]], j["sig_nonapp"])
A._is_dev = lambda p: False
ck(c.get("/v2/api/crm/parallel").status_code == 403, "dev only")
print("parallel_route OK", n)
