# tests/crm/test_sig_records.py — מודול 'מתעניינים (חתימות)' ב-CRM: שורת חתימה → רשומה, מקור (אפי/פיירברי/חתימה טובה), נחתם/ממתין, תצוגות
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_sig_records", "_crm_int", "CRM_VIEWS", "CRM_MODULES", "_crm_day", "crm_query", "_crm_norm", "inv_phone9")
rec, q = ns["crm_sig_records"], ns["crm_query"]
NOW = 1_800_000_000.0
lab = {"CLIENT_SALE": "קונים", "OWNER_SALE": "מוכר", "OWNER_EXCLUSIVE": "בלעדיות", "CLIENT_RENT": "שכירות"}
h = {"ep": lambda s: float(s) if s else 0, "label": lambda c: lab.get(c, c or "חתימה")}
S = [{"event_id": "app:t1:CLIENT_SALE", "deal_type": "CLIENT_SALE", "client_name": "גדזיי מליקוב", "phone": "0532254463", "agent": "אירנה טנדשוילי",
      "address": "הנשיא 5|הרצל 2", "city": "קרית ביאליק", "budget": "1,285,000", "commission_pct": "https://remax-bot.onrender.com/s/abc", "received_at": str(NOW - 3600)},
     {"event_id": "fb:99:OWNER_EXCLUSIVE", "deal_type": "OWNER_EXCLUSIVE", "client_name": "יוסי גברילוב", "agent": "יאיר חנוכאייב",
      "address": "נעמי שמר 12", "city": "קרית ביאליק", "commission_pct": "https://hatimatova.co.il/doc/77", "received_at": str(NOW - 5 * 86400)},
     {"event_id": "fb:100:OWNER_SALE", "deal_type": "OWNER_SALE", "client_name": "רונן חלד", "agent": "רפי", "address": "דובדבן 6",
      "commission_pct": "", "received_at": str(NOW - 2 * 86400)},
     {"event_id": "fb:101:CLIENT_RENT", "deal_type": "CLIENT_RENT", "client_name": "שוכר", "agent": "רפי", "commission_pct": "2", "received_at": str(NOW - 86400 * 40)}]
R = rec(S, h)
by = {r["client"]: r for r in R}
g = by["גדזיי מליקוב"]
ck(g["type"] == "קונים" and g["source"] == "אפי" and g["status"] == "נחתם" and g["link"].endswith("/s/abc") and g["budget"] == 1285000, g)
ck(g["address"] == "הנשיא 5 · הרצל 2" and g["n_props"] == 2 and g["phone"] == "0532254463" and g["date"] == NOW - 3600, g)
y = by["יוסי גברילוב"]
ck(y["source"] == "חתימה טובה" and y["status"] == "נחתם", y)
r = by["רונן חלד"]
ck(r["source"] == "פיירברי" and r["status"] == "ממתין" and r["link"] == "", r)
ck(by["שוכר"]["status"] == "נחתם" and by["שוכר"]["link"] == "", "commission number (no link) = signed, like the signatures screen")
ck(len({x["key"] for x in R}) == 4, "unique keys")
V = lambda v: q(R, "", {"view": v}, "date", "desc", 1, 50, NOW, module="signatures")["total"]
ck({v: V(v) for v in ("all", "buyers", "owners", "exclusive", "rent", "pending", "hatimatova", "app")} ==
   {"all": 4, "buyers": 1, "owners": 2, "exclusive": 1, "rent": 1, "pending": 1, "hatimatova": 1, "app": 1},
   {v: V(v) for v in ("all", "buyers", "owners", "exclusive", "rent", "pending", "hatimatova", "app")})
ck(q(R, "0532254463", {"view": "all"}, "date", "desc", 1, 50, NOW, module="signatures")["total"] == 1, "search by client phone")
ck(q(R, "", {"view": "all", "agent": "רפי"}, "date", "desc", 1, 50, NOW, module="signatures")["total"] == 2, "agent filter")
print("sig_records OK", _load.n)
