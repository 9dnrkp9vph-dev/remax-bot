# tests/crm/test_props_records.py — מודול 'נכסים' ב-CRM: שלושת המקורות (פרטי/שת"פ/המשרד) לרשומה אחת, ירידות מחיר, חדש, ירד מפרסום
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_props_records", "_crm_int", "_crm_rooms", "CRM_VIEWS", "CRM_MODULES", "_crm_day", "crm_query", "_crm_norm", "inv_phone9")
rec, q = ns["crm_props_records"], ns["crm_query"]
NOW = 1_800_000_000.0
DAY = 86400
nb = [{"מזהה": "a1", "רחוב1": "שלום עליכם 27", "עיר": "קרית אתא", "שכונה": "אברמסקי", "מחיר": "1,520,000",
       "שם בעל הנכס": "משה", "טלפון בעל הנכס-": "058-4391003", "תיאור נכס": "דירה · 5 חד' · 97 מ\"ר · קומה 2",
       "קישור": "https://yad2.co.il/item/716r58pn", "_ep": NOW - DAY},
      {"מזהה": "a2", "רחוב1": "הרצל 1", "עיר": "קרית ים", "מחיר": "900000", "delisted_at": "2026-10-18", "_ep": NOW - 30 * DAY}]
ex = [{"street": "ורבורג 3, קרית מוצקין", "city": "קרית מוצקין", "rooms": "4", "sqm": "100", "price": "2,100,000",
       "office": "RE/MAX SMART", "phone": "0501231234", "link": "https://yad2.co.il/item/x9", "image": "https://img/x9.jpg", "_ep": NOW - 10 * DAY}]
of = [{"סוכן 1": "רפי", "כתובת": "דובדבן", "מספר בית": "6", "עיר / ישוב": "קרית ביאליק", "חדרים": "3.5", "מחיר": "1,950,000",
       "קישור": "https://yad2.co.il/item/o1", "תמונה": "https://img/o1.jpg", "בלעדיות": "1", "סוג עסקה": "השכרה", "_ep": NOW - 3 * DAY}]
h = {"nb_ep": lambda r: r["_ep"], "nb_pkey": lambda r: "N:" + r["מזהה"],
     "nb_office": lambda r: {"סוג נכס": "דירה", "חדרים": "5", "מ\"ר": "97", "קומה": "2"} if r["מזהה"] == "a1" else {},
     "excl_ep": lambda r: r["_ep"], "excl_pkey": lambda r: "X:x9",
     "prop_ep": lambda r: r["_ep"], "prop_pkey": lambda r: "L:o1", "agent_name": lambda n: n}
pd = {"N:a1": "1,550,000", "X:x9": ""}
R = rec(nb, ex, of, pd, NOW, h)
by = {r["source"] + ":" + r["address"]: r for r in R}
p = by["פרטי:שלום עליכם 27"]
ck(p["price"] == 1520000 and p["price_old"] == 1550000 and p["dropped"] and p["new"] and p["rooms"] == 5.0 and p["type"] == "דירה", p)
ck(p["contact"] == "משה" and p["phone"] == "058-4391003" and p["link"].endswith("716r58pn") and p["status"] == "פעיל", p)
d = by["פרטי:הרצל 1"]
ck(d["delisted"] and d["status"] == "ירד מפרסום" and not d["new"] and d["rooms"] == "", d)
x = by["שת\"פ:ורבורג 3, קרית מוצקין"]
ck(x["contact"] == "RE/MAX SMART" and x["image"].endswith("x9.jpg") and x["price"] == 2100000 and x["dropped"] is False, ("empty old price = no drop", x))
o = by["המשרד:דובדבן 6"]
ck(o["agent"] == "רפי" and o["contact"] == "רפי" and o["deal"] == "השכרה" and o["excl"] == "בלעדי" and o["rooms"] == 3.5, o)
ck(len({r["key"] for r in R}) == len(R), "unique keys")
V = lambda v: q(R, "", {"view": v}, "date", "desc", 1, 50, NOW, module="props")["total"]
ck(V("all") == 3 and V("private") == 1 and V("new") == 1 and V("drops") == 1 and V("delisted") == 1 and V("shtaf") == 1 and V("office") == 1 and V("everything") == 4,
   {v: V(v) for v in ("all", "private", "new", "drops", "delisted", "shtaf", "office", "everything")})
srt = q(R, "", {"view": "everything"}, "price", "desc", 1, 50, NOW, module="props")["rows"]
ck([r["price"] for r in srt] == [2100000, 1950000, 1520000, 900000], "price sorts as a number")
ck(q(R, "0584391003", {"view": "everything"}, "date", "desc", 1, 50, NOW, module="props")["total"] == 1, "search by owner phone")
print("props_records OK", _load.n)
