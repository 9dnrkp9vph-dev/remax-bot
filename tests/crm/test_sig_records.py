# tests/crm/test_sig_records.py — מודול 'מתעניינים (חתימות)' ב-CRM: שורת חתימה → רשומה, מקור (אפי/פיירברי/חתימה טובה), נחתם/ממתין, תצוגות
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_sig_fill_budget", "_crm_sig_token", "crm_unify_agents", "crm_sig_records", "_crm_dmy", "_crm_int", "CRM_VIEWS", "CRM_MODULES", "_crm_day", "crm_query", "_crm_norm", "inv_phone9")
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
P = rec([{"event_id": "KE90D8L4YOf1guDF", "doc_token": "KE90D8L4YOf1guDF", "status": "pending", "deal_type": "CLIENT_SALE",
            "client_name": "אגומאס ג'מבר", "agent": "נדב רייזר", "address": "אלי כהן 5", "commission_pct": "", "received_at": str(NOW)}], h)[0]
ck(P["source"] == "אפי" and P["status"] == "ממתין" and P["link"] == "/s/KE90D8L4YOf1guDF", ("pending Effie doc = Effie, link to the doc", P))
Q = rec([{"event_id": "KE90D8L4YOf1guDF", "deal_type": "CLIENT_SALE", "client_name": "עותק מהגיליון", "commission_pct": "", "received_at": str(NOW)},
         {"event_id": "3f2a1b4c-1111-2222-3333-444455556666", "deal_type": "OWNER_SALE", "client_name": "פיירברי", "commission_pct": "", "received_at": str(NOW)},
         {"event_id": "314970617", "deal_type": "OWNER_SALE", "client_name": "תז", "commission_pct": "", "received_at": str(NOW)}], h)
ck([x["source"] for x in Q] == ["אפי", "פיירברי", "פיירברי"] and Q[0]["link"] == "/s/KE90D8L4YOf1guDF", ("16-char Effie token id = Effie", Q))
U = ns["crm_unify_agents"]
recs = [{"agent": "אירנה טנדשוילי"}, {"agent": "אירנה טנדשווילי"}, {"agent": "אירנה טנדשוילי"}, {"agent": "אוהד\u200f פלד"}, {"agent": "אוהד  פלד"}, {"agent": ""}]
U(recs, lambda n: n.replace(" ", "").replace("וו", "ו"))
ck([r["agent"] for r in recs] == ["אירנה טנדשוילי"] * 3 + ["אוהד פלד", "אוהד פלד", ""], ("one name per agent, most common spelling", recs))
F = ns["crm_sig_fill_budget"]
sg = [{"event_id": "307600478", "commission_pct": "https://remax-bot.onrender.com/s/DpBmo_M09njPnuoF", "budget": ""},
      {"event_id": "Tq2hP6JNy8nP67Ju", "doc_token": "Tq2hP6JNy8nP67Ju", "commission_pct": ""},
      {"event_id": "fb:1", "commission_pct": "", "budget": "900000"},
      {"event_id": "12345", "commission_pct": "2"}]
asked = []
def fh(toks):
    asked.extend(toks); return {"DpBmo_M09njPnuoF": "HDR-3280000", "Tq2hP6JNy8nP67Ju": "HDR-2000000|HDR-2400000"}
hp = lambda hdr: [int(x.split("-")[1]) for x in hdr.split("|")]
out = F(sg, fh, hp)
ck([g.get("budget") for g in out] == ["3280000", "2200000", "900000", None], ("price from the signed document", out))
ck(sorted(asked) == ["DpBmo_M09njPnuoF", "Tq2hP6JNy8nP67Ju"] and "budget" not in sg[1], ("only rows without budget, input not mutated", asked))
ck(F(sg, lambda t: (_ for _ in ()).throw(RuntimeError("down")), hp)[0].get("budget") == "", "lookup failure = unchanged")
print("sig_records OK", _load.n)
