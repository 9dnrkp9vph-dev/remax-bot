# tests/crm/test_buyer_records.py — מודול 'קונים' ב-CRM: שורת קונה → רשומה (סטטוס, מקור, תקציב), תצוגות
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_buyer_pages", "_crm_bpage_sum", "bpage_expired", "bpage_iso_ep", "crm_buyer_records", "_CRM_BSTAT", "_crm_int", "CRM_VIEWS", "CRM_MODULES", "_crm_day", "crm_query", "_crm_norm", "inv_phone9")
rec, q = ns["crm_buyer_records"], ns["crm_query"]
NOW = 1_800_000_000.0
B = [{"row": 5, "date": str(NOW - 3600), "name": "גדזיי מליקוב", "phone": "053-2254463", "agent": "אירנה טנדשוילי", "budget": "1,285,000",
      "summary": "מהחתמת מתעניין · הנשיא 5", "search": "דירה בביאליק עד 1,300,000"},
     {"row": 6, "date": str(NOW - 86400 * 3), "name": "ליד", "phone": "0501111111", "agent": "אייל שמול", "budget": "",
      "summary": "ליד מהאתר · 5 חדרים במשכנות", "search": "5 חדרים"},
     {"row": 7, "date": "", "name": "בלי טלפון", "phone": "", "agent": "רפי", "summary": "שיחה עם הלקוח", "search": ""}]
st = {"532254463": "hot", "r7": "closed"}
R = rec(B, st, lambda s: float(s) if s else 0)
by = {r["name"]: r for r in R}
g = by["גדזיי מליקוב"]
ck(g["key"] == "b:5" and g["status"] == "חם" and g["source"] == "החתמה" and g["budget"] == 1285000 and g["date"] == NOW - 3600, g)
ck(by["ליד"]["source"] == "אתר" and by["ליד"]["status"] == "פעיל" and by["ליד"]["budget"] == "", by["ליד"])
ck(by["בלי טלפון"]["status"] == "סגר" and by["בלי טלפון"]["source"] == "ידני", ("status by row when no phone", by["בלי טלפון"]))
V = lambda v: q(R, "", {"view": v}, "date", "desc", 1, 50, NOW, module="buyers")["total"]
ck({v: V(v) for v in ("all", "active", "hot", "closed", "site", "signing", "no_phone", "no_budget")} ==
   {"all": 3, "active": 2, "hot": 1, "closed": 1, "site": 1, "signing": 1, "no_phone": 1, "no_budget": 2},
   {v: V(v) for v in ("all", "active", "hot", "closed", "site", "signing", "no_phone", "no_budget")})
ck(q(R, "0532254463", {"view": "all"}, "date", "desc", 1, 50, NOW, module="buyers")["total"] == 1, "search by phone")
ck([e[0] for e in ns["CRM_MODULES"]["buyers"]["editable"]] == ["name", "phone", "agent", "budget", "search", "summary", "status"], "editable fields")
BP = ns["crm_buyer_pages"]
pages = [{"id": "p1", "row": 5, "token": "TOK5abc", "expires_at": "2099-01-01T00:00:00+00:00"},
         {"id": "p2", "row": 6, "token": "TOK6abc", "expires_at": "2020-01-01T00:00:00+00:00"}]
items = [{"page_id": "p1", "mark": "like"}, {"page_id": "p1", "mark": "visit"}, {"page_id": "p1", "mark": "dislike"}, {"page_id": "p1", "mark": ""},
         {"page_id": "p2", "mark": "seen"}]
M = BP(pages, items, NOW)
ck(M["5"] == {"link": "/b/TOK5abc", "n": 4, "like": 2, "dislike": 1, "seen": 0, "expired": False}, ("legacy 'visit' counts as like", M["5"]))
ck(M["6"]["expired"] and M["6"]["seen"] == 1, M["6"])
R2 = rec(B, st, lambda s: float(s) if s else 0, M)
b5 = next(r for r in R2 if r["key"] == "b:5")
ck(b5["bpage"] == "/b/TOK5abc" and b5["bpage_sum"] == "4 נכסים · 2 מתאים · 1 לא מתאים", b5)
ck(next(r for r in R2 if r["key"] == "b:6")["bpage_sum"] == "1 נכסים · 1 ראה · פג תוקף", "expired page")
ck(next(r for r in R2 if r["key"] == "b:7")["bpage"] == "", "no page")
ck(q(R2, "", {"view": "bpage"}, "date", "desc", 1, 50, NOW, module="buyers")["total"] == 2, "view: has a buyer page")
print("buyer_records OK", _load.n)
ns2 = _load.load("crm_csv", "crm_buyer_pages", "_crm_bpage_sum", "bpage_expired", "bpage_iso_ep", "crm_buyer_records", "_CRM_BSTAT", "_crm_int", "CRM_MODULES", "inv_phone9")
csv = ns2["crm_csv"](R2, ns2["CRM_MODULES"]["buyers"]["columns"]).decode("utf-8-sig")
ck("/b/TOK5abc" in csv and "דף קונה" in csv, "CSV export with the 4-field link column")
print("buyer csv OK")
