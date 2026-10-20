# tests/crm/test_props_api.py — /v2/crm/props: הראוט האמיתי עם מקורות מזויפים (נכס נולד, שת"פ, נכסי המשרד בשלושת סוגי העסקה)
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
A.fetch_newborn = lambda: [{"מזהה": "a1", "רחוב1": "שלום עליכם 27", "עיר": "קרית אתא", "מחיר": "1,520,000", "שם בעל הנכס": "משה",
                            "טלפון בעל הנכס-": "0584391003", "תיאור נכס": "דירה · 5 חד'", "נוצר בתאריך": "19/10/2026 10:00"}]
A.fetch_external_exclusives = lambda: [{"street": "ורבורג 3", "city": "קרית מוצקין", "price": "2100000", "office": "SMART", "link": "https://yad2.co.il/item/x9"}]
A._office_rows_for = lambda dc: ([{"סוכן 1": "רפי", "כתובת": "דובדבן", "מספר בית": "6", "מחיר": "5000", "מספר מודעה": "o" + (dc or "s")}] if dc != "commercial" else [], {"rent": "השכרה", "commercial": "מסחרי"}.get(dc))
A._price_dropped_map = lambda: {}
c = A.app.test_client()
m = c.get("/v2/api/crm/props/meta").get_json()
ck(m["ok"] and m["title"] == "נכסים" and m["counts"]["all"] == 4 and m["counts"]["private"] == 1 and m["counts"]["office"] == 2, m.get("counts"))
ck(m["agents"] == ["רפי"], m["agents"])
l = c.get("/v2/api/crm/props/list?view=office&sort=deal&dir=asc").get_json()
ck(l["total"] == 2 and {r["deal"] for r in l["rows"]} == {"מכירה", "השכרה"}, l)
r = c.get("/v2/api/crm/props/record?key=" + c.get("/v2/api/crm/props/list?view=private").get_json()["rows"][0]["key"]).get_json()
ck(r["ok"] and r["record"]["contact"] == "משה", r)
ck(c.post("/v2/api/crm/props/record", json={"fields": {}}).status_code == 400, "read only")
ex = c.get("/v2/api/crm/props/export?view=all")
ck(ex.status_code == 200 and "שלום עליכם" in ex.get_data(as_text=True), "export")
h = c.get("/v2/crm/props").get_data(as_text=True)
ck("t === 'price'" in h and "t === 'link'" in h, "price/link cells")
ck('class="hero"' in h and "['status', 'price', 'phone', 'link'].indexOf(c[2])" in h, "drawer: picture, formatted price and clickable link (not raw URLs)")
print("props_api OK", n)
