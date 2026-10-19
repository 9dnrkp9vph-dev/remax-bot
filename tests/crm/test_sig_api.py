# tests/crm/test_sig_api.py — /v2/crm/signatures: הראוט האמיתי מעל get_signings מזויף
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל", "role": "admin"}
A._is_dev = lambda p: True
class SB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
A._sbdb = SB()
A.get_signings = lambda frm="01/01/2020", to="31/12/2099": [
    {"event_id": "app:t1:CLIENT_SALE", "deal_type": "CLIENT_SALE", "client_name": "גדזיי", "phone": "0532254463", "agent": "אירנה",
     "address": "הנשיא 5", "city": "קרית ביאליק", "commission_pct": "https://x/s/abc", "received_at": "19/10/2026 10:00"},
    {"event_id": "fb:9:OWNER_SALE", "deal_type": "OWNER_SALE", "client_name": "רונן", "agent": "רפי", "commission_pct": "", "received_at": "18/10/2026 09:00"}]
c = A.app.test_client()
m = c.get("/v2/api/crm/signatures/meta").get_json()
ck(m["ok"] and m["title"] == "מתעניינים (חתימות)" and m["counts"]["all"] == 2 and m["counts"]["pending"] == 1 and sorted(m["agents"]) == ["אירנה", "רפי"], m)
l = c.get("/v2/api/crm/signatures/list").get_json()
ck(l["total"] == 2 and l["rows"][0]["client"] == "גדזיי", ("newest first", l["rows"][0]))
ck(c.get("/v2/api/crm/signatures/list?f_agent=רפי").get_json()["total"] == 1, "agent filter")
ck(c.post("/v2/api/crm/signatures/record", json={"fields": {}}).status_code == 400, "read only")
ck("גדזיי" in c.get("/v2/api/crm/signatures/export").get_data(as_text=True), "export")
h = c.get("/v2/crm/signatures").get_data(as_text=True)
ck(h.count("<title>") and c.get("/v2/crm/signatures").status_code == 200, "page")
print("sig_api OK", n)
