# tests/deals_history/test_views.py — תצוגות לפי הרשאה, סטטיסטיקה, לא שולם/לא דווח (2026 בלבד), ראוטי קריאה
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from flask import Flask, jsonify, request
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
B = {"collection_status": "", "invoice_no": "", "receipt_no": "", "deposited": "", "remax_approved": "", "notes": "",
     "lawyer_notes": "", "other_broker": "", "lead_source": "", "commission_gross": None}
R = [
 dict(B, id="1", branch="motzkin", year=2025, deal_date="2025-03-02", city="קרית מוצקין", street="הגפן 4", side="מוכר",
      agent="משה כהן", client_name="דנה", client_phone="0501234567", deal_amount=1800000, commission_net=18000,
      paid_amount=18000, reported_date="2025-04-01"),
 dict(B, id="2", branch="bialik", year=2026, deal_date="2026-05-10", city="קרית ביאליק", street="הגפן 9", side="שוכר",
      agent="דנה לוי", client_name="יוסי", client_phone="0529999999", deal_amount=5000, commission_net=5000,
      paid_amount=None, reported_date=None, collection_status="טרם שולם"),
 dict(B, id="3", branch="motzkin", year=2024, deal_date="2024-02-01", city="קרית מוצקין", street="הגפן 4", side="קונה",
      agent="משה כהן + דנה לוי", client_name="רון", client_phone="", deal_amount=1500000, commission_net=15000,
      paid_amount=None, reported_date=None),
 dict(B, id="4", branch="bialik", year=2026, deal_date="2026-06-01", city="קרית ביאליק", street="הרצל 1", side="מוכר",
      agent="משה כהן", client_name="גל", client_phone="", deal_amount=2000000, commission_net=20000,
      paid_amount=20000, reported_date="2026-07-01"),
]
ck(D.is_editor({"drole": "accountant"}) and D.is_editor({"drole": "manager"}) and not D.is_editor({"drole": "agent"}), "editor")
# כרטיס הסוכן: היסטוריה (עד 2025) — תאריך/כתובת/לקוח/סכום בלבד; 2026 — גם עמלה/שולם/דווח
h = D.view_agent(R[0])
ck(h["client"] == "דנה" and h["price"] == 1800000 and h["address"] == "הגפן 4, קרית מוצקין" and h["date"] == "02/03/2025", h)
ck(not any(k in h for k in ("commission_net", "paid", "reported")), ("history has no payment detail", h))
d = D.view_agent(R[3])
ck(d["commission_net"] == 20000 and d["paid"] == 20000 and d["reported"] == "07/2026", d)
ck("client_phone" not in d and "commission_gross" not in d, "agent view minimal")
c = D.view_comps(R[0])
ck(set(c) == {"date", "address", "kind", "side", "price", "agent", "branch"} and c["kind"] == "מכירה", c)
ck(D.view_comps(R[1])["kind"] == "השכרה", "rent")
ck("התחשבנות" not in json.dumps(D.view_full(R[0]), ensure_ascii=False), "no settlement anywhere")
ck_key = lambda x: x.replace(" ", "")
ck([r["id"] for r in D.scope_rows(R, {"keys": {"משהכהן"}}, ck_key)] == ["1", "3", "4"], "agent own incl. joint")
ck([r["id"] for r in D.scope_rows(R, {"keys": {"דנהלוי"}}, ck_key)] == ["2", "3"], "joint deal visible to partner")
ck(D.scope_rows(R, {"keys": set()}, ck_key) == [] and D.scope_rows(R, {"keys": {"מנהל"}}, ck_key) == [], "generic/empty sees nothing")
ck(len(D.scope_rows(R, {"keys": {"משהכהן", "דנהלוי"}}, ck_key)) == 4, "team keys = union")
cs = D.comps_search(R, "הגפן מוצקין")
ck([x["date"] for x in cs["results"]] == ["02/03/2025", "01/02/2024"] and cs["n_sale"] == 2 and cs["avg_sale"] == 1650000, cs)
ck(D.comps_search(R, "דנה")["results"] == [] and D.comps_search(R, "")["results"] == [], "no client-name match, empty q")
st = D.stats(R, 2026)
ck(st["total"]["n"] == 2 and st["total"]["commission"] == 25000 and st["prev"]["n"] == 1, st["total"])
s24 = D.stats(R, 2024)
ag = {x["agent"]: x for x in s24["byAgent"]}
ck(ag["משה כהן"]["n"] == 0.5 and ag["דנה לוי"]["commission"] == 7500 and s24["total"]["n"] == 1, ("joint = half each", s24["byAgent"]))
ck([r["id"] for r in D.unpaid(R)] == ["2"] and [r["id"] for r in D.unreported(R)] == ["2"], "open lists: 2026 only")
# ראוטים
S = {"T": {"role": "agent", "drole": "agent", "name": "משה כהן", "phone": "500000001"},
     "M": {"role": "admin", "drole": "manager", "name": "מנהל", "phone": "500000002"}}
class SB:
    def enabled(self): return True
    def deal_history_all(self): return R
TEAM = {"משה כהן": {"משהכהן"}}
G = {"_web_auth": lambda: S.get(request.headers.get("X-Auth-Token", "")), "_canon_key": ck_key,
     "_scope_keys_phones": lambda role, name, ph, a=None, an=None: (TEAM.get(name, {ck_key(name)}), set(), False),
     "_etag_wrap": lambda d: jsonify(d), "_canon_agent_name": lambda x: x, "_log_activity": lambda *a, **k: None,
     "_sbdb": SB()}
app = Flask("v"); D._HIST_CACHE["ts"] = 0; D.register(app, G, lambda h: h); c = app.test_client()
m = c.get("/v2/api/deals/history/mine", headers={"X-Auth-Token": "T"}).get_json()
ck([x["id"] for x in m["results"]] == ["4", "1", "3"] and m["years"] == [2026, 2025, 2024], m)
cp = c.get("/v2/api/deals/history/comps?q=הגפן", headers={"X-Auth-Token": "T"}).get_data(as_text=True)
ck("0501234567" not in cp and "commission" not in cp and "client" not in cp and "paid" not in cp, "comps json has no private fields")
ck(c.get("/v2/api/deals/history/stats?year=2026", headers={"X-Auth-Token": "T"}).status_code == 403, "agent no stats")
ck(c.get("/v2/api/deals/history/stats?year=2026", headers={"X-Auth-Token": "M"}).get_json()["total"]["n"] == 2, "manager stats")
op = c.get("/v2/api/deals/history/open?kind=unpaid", headers={"X-Auth-Token": "M"}).get_json()
ck([x["id"] for x in op["results"]] == ["2"] and "client_phone" in op["results"][0], op)
ck(c.get("/v2/api/deals/history/search?q=0529999999", headers={"X-Auth-Token": "M"}).get_json()["results"][0]["id"] == "2", "manager search by phone")
ck(c.get("/v2/api/deals/history/search?q=הגפן", headers={"X-Auth-Token": "T"}).status_code == 403, "agent no search")
ck(c.get("/v2/api/deals/history/mine").status_code == 401, "no auth")
print("OK", n, "checks")
