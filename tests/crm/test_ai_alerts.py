# tests/crm/test_ai_alerts.py — [21/10 אייל] טאב 'AI' ב-CRM (רק לבעל המשרד): לקוח עבר (טלפון מעסקאות / מקבלי מסמכים)
# שמפרסם דירה או נוסף כקונה + 'קונים שמפרסמים נכס' (עבר מהניהול באפי), עם קישורים לכל המידע.
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_ai_records", "bs_p9", "CRM_MODULES", "CRM_VIEWS", "CRM_ACCESS_MODULES", "crm_query", "_crm_norm",
                "inv_phone9", "_crm_day", "crm_access_for", "_crm_on_or_after", "_crm_td")
AI, Q = ns["crm_ai_records"], ns["crm_query"]
NOW = 1_800_000_000.0
DAY = 86400
deals = [{"key": "d:1", "date": NOW - 400 * DAY, "client": "משה כהן", "phone": "054-1111111", "address": "הנוטר 18, קרית ביאליק", "agent": "רפי", "side": "מוכר"},
         {"key": "d:2", "date": NOW - 30 * DAY, "client": "משה כהן", "phone": "0541111111", "address": "הרצל 2, קרית ים", "agent": "קובי חמו", "side": "קונה"},
         {"key": "d:3", "date": NOW - 50 * DAY, "client": "בלי טלפון", "phone": "", "address": "x"}]
invs = [{"key": "iv:1", "date": NOW - 90 * DAY, "client": "רונית לוי", "phone": "0522222222", "type": "חשבונית מס", "agent": "אלי שמול"}]
idx = {"541111111": [{"key": "L1", "addr": "שבזי 4 קרית ביאליק", "price": "2,100,000", "rent": False, "link": "https://yad2.co.il/item/L1", "raw": {"_ep": NOW - 2 * DAY}}],
       "533333333": [{"key": "L2", "addr": "זר", "price": "1", "rent": False, "link": "https://x", "raw": {"_ep": NOW}}]}
buyers = [{"row": 7, "name": "רונית לוי", "phone": "052-2222222", "agent": "נדב רייזר", "date": "x", "search": "4 חדרים באפק", "_ep": NOW - DAY},
          {"row": 8, "name": "זר", "phone": "0534444444", "agent": "a", "date": "y", "_ep": NOW}]
bs = [{"key": "541111111|L1|רפי", "status": "pending", "buyer": "משה כהן", "agent": "רפי", "addr": "שבזי 4 קרית ביאליק", "price": "2,100,000",
       "link": "https://yad2.co.il/item/L1", "listed": __import__("datetime").datetime.fromtimestamp(NOW - 3 * DAY).strftime("%d/%m/%Y"), "sent_ts": 0, "gone": False}]
R = AI(deals, invs, idx, buyers, bs, NOW, lambda b: b.get("_ep"), lambda raw: raw.get("_ep"))
by = {r["type"]: r for r in R}
ps = by["לקוח עבר מפרסם נכס"]
ck(ps["name"] == "משה כהן" and ps["phone"] == "0541111111" and ps["date"] == NOW - 2 * DAY and ps["link"].endswith("L1")
   and "הרצל 2" in ps["past"] and "2 עסקאות" in ps["past"] and ps["deals_link"] == "/v2/crm/deals?q=0541111111", ps)
pb = by["לקוח עבר נוסף כקונה"]
ck(pb["name"] == "רונית לוי" and pb["agent"] == "נדב רייזר" and "חשבונית מס" in pb["past"] and pb["buyer_link"] == "/v2/crm/buyers?q=0522222222"
   and pb["inv_link"] == "/v2/crm/invoices?q=0522222222" and pb["what"] == "4 חדרים באפק", pb)
b1 = by["קונה שמפרסם נכס"]
ck(b1["status"] == "ממתין לשליחה לסוכן" and b1["bs_key"] == "541111111|L1|רפי" and b1["agent"] == "רפי" and b1["buyer_link"].endswith("0541111111"), b1)
ck(len(R) == 3 and len({r["key"] for r in R}) == 3, [r["type"] for r in R])
# תצוגות
V = lambda v: Q(R, "", {"view": v}, "date", "desc", 1, 50, NOW, module="ai")["total"]
ck(V("all") == 3 and V("past_seller") == 1 and V("past_buyer") == 1 and V("buyer_seller") == 1 and V("recent") == 3, {v: V(v) for v in ("all", "recent")})
# רק לבעל המשרד: לא ניתן לתת אותו בהרשאות; בעל המשרד רואה
ck("ai" not in ns["CRM_ACCESS_MODULES"], "not assignable")
own = ns["crm_access_for"]("eyalshmul@gmail.com", "", {}, ["eyalshmul@gmail.com"], False)
other = ns["crm_access_for"]("x@y.com", "", {"v2_crm_access": {"x@y.com": {"modules": ["ai", "deals"], "scope": "all"}}}, ["eyalshmul@gmail.com"], False)
ck("ai" in own["modules"] and "ai" not in (other or {}).get("modules", []), (own, other))
print("ai_alerts OK", _load.n)
