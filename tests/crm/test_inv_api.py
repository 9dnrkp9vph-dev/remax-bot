# tests/crm/test_inv_api.py — /v2/crm/invoices: הראוט האמיתי מעל invoices מזויף + הצלבת סוכן
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
import supabase_db as SD
A._web_auth = lambda: {"phone": "505709865", "name": "אייל", "role": "admin"}
A._is_dev = lambda p: True
class SB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
    def invoices_all(s): return INV
A._sbdb = SB()
INV = [
    {"client_name": "דנה כהן", "phone": "0541234567", "phone9": "541234567", "doc_type": "חשבונית מס", "doc_num": "1052",
     "charge_line": "דמי תיווך", "created_at": "2026-10-19T10:00:00+03:00", "source": "fireberry", "link": "https://x/1", "amount": "11700", "row_hash": "h1"},
    {"client_name": "יוסי", "phone": "", "phone9": "", "doc_type": "קבלה", "doc_num": "", "charge_line": "",
     "created_at": "2025-03-01T09:00:00+02:00", "source": "", "link": "", "amount": "", "row_hash": "h2"}]
A._fetch_manual_buyers = lambda: [{"name": "דנה כהן", "phone": "0541234567", "agent": "רפי"}]
A.get_signings = lambda frm="01/01/2020", to="31/12/2099": []
c = A.app.test_client()
m = c.get("/v2/api/crm/invoices/meta").get_json()
ck(m["ok"] and m["title"] == "מקבלי מסמכים" and m["counts"]["all"] == 2 and m["counts"]["tax"] == 1, m)
ck(any(x[0] == "invoices" for x in m["modules"]), ("in the module bar", m["modules"]))
l = c.get("/v2/api/crm/invoices/list").get_json()
ck(l["total"] == 2 and l["rows"][0]["client"] == "דנה כהן" and l["rows"][0]["agent"] == "רפי", l["rows"][0])
ck(c.get("/v2/api/crm/invoices/list?period=2025").get_json()["total"] == 1, "period")
ck(c.post("/v2/api/crm/invoices/record", json={"fields": {}}).status_code == 400, "read only")
ck("1052" in c.get("/v2/api/crm/invoices/export").get_data(as_text=True), "export")
ck(c.get("/v2/crm/invoices").status_code == 200, "page")
A._is_dev = lambda p: False
ck(c.get("/v2/api/crm/invoices/list").status_code == 403, "owner only")
print("inv_api OK", n)
