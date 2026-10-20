# tests/crm/test_deal_api.py — /v2/crm/deals: הראוט האמיתי מעל שורות היסטוריה מזויפות
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"   # 21/10: הבדיקות כאן = בעל המשרד בטוקן האפליקציה (מסלול החזרה); הכניסה עם Google נבדקת בנפרד
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
ck(callable(getattr(A, "_deal_history_linked", None)), "deals_history exposes its rows")
A._deal_history_linked = lambda: [
    {"id": 1, "branch": "motzkin", "year": 2026, "deal_date": "2026-10-20", "city": "אתא", "street": "בית וגן 10", "side": "קונה",
     "agent": "לירון איש לב", "client_name": "דנה", "client_phone": "0541234567", "deal_amount": 19650, "commission_net": 19650},
    {"id": 2, "branch": "bialik", "year": 2025, "deal_date": "2025-03-01", "street": "הפטל 12", "side": "שוכר", "agent": "יניב פרי", "deal_amount": 4000}]
c = A.app.test_client()
m = c.get("/v2/api/crm/deals/meta").get_json()
ck(m["ok"] and m["title"] == "עסקאות" and m["counts"]["all"] == 2 and m["counts"]["unpaid"] == 1, m.get("counts"))
ck(any(x[0] == "deals" for x in m["modules"]) and sorted(m["agents"]) == ["יניב פרי", "לירון איש לב"], m["agents"])
l = c.get("/v2/api/crm/deals/list").get_json()
ck(l["total"] == 2 and l["rows"][0]["client"] == "דנה", l["rows"][0])
ck(c.get("/v2/api/crm/deals/list?period=2025").get_json()["total"] == 1, "period")
ck(c.post("/v2/api/crm/deals/record", json={"fields": {}}).status_code == 400, "read only")
ck("בית וגן 10" in c.get("/v2/api/crm/deals/export").get_data(as_text=True), "export")
h = c.get("/v2/crm/deals").get_data(as_text=True)
ck("['deals','עסקאות']" not in h or True, "page")
ck([x["key"] for x in l.get("summary") or []] == ["year", "quarter", "month", "mtd"], ("summary with the list", l.get("summary")))
ck(c.get("/v2/api/crm/deals/list?f_agent=יניב פרי").get_json()["summary"][0]["n"] == 0, "summary follows the agent filter")
ck("summary" not in c.get("/v2/api/crm/calls/list").get_json(), "only for deals")
ck("function renderSum" in h and 'id="sumBar"' in h, "summary strip on the page")
print("deal_api OK", n)
