# tests/deals_history/test_branch_sort.py — אייל 12/10: בורר סניף למנהלים, החדש תמיד למעלה, חיפוש שכונה ב'העסקאות שלי'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from flask import Flask, jsonify, request
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
B = {"collection_status": "", "invoice_no": "", "receipt_no": "", "deposited": "", "remax_approved": "", "notes": "",
     "lawyer_notes": "", "other_broker": "", "lead_source": "", "commission_gross": None, "client_phone": "", "client_name": ""}
def row(i, br, date, street, city, agent, **k):
    return dict(B, id=i, branch=br, year=int(date[:4]), deal_date=date, street=street, city=city, side="מוכר", agent=agent,
                deal_amount=1000000, commission_net=10000, paid_amount=None, reported_date=None, **k)
R = [row("1", "bialik", "2026-02-01", "נעמי שמר 2", "ביאליק", "משה כהן"),
     row("2", "bialik", "2026-09-01", "אהוד מנור 5", "ביאליק", "דנה לוי"),
     row("3", "motzkin", "2026-05-01", "הגפן 4", "מוצקין", "משה כהן"),
     row("4", "kiryat_yam", "2026-07-01", "הרצל 1", "ים", "קובי חמו"),
     row("5", "motzkin", "2025-03-01", "נעמי שמר 8", "ביאליק", "משה כהן"),
     row("6", "bialik", "2026-08-01", "הגפן 9", "ביאליק", "משה כהן", missing_since="2026-10-12T00:00:00Z"),
     row("7", "motzkin", "2026-10-01", "הגפן 7", "מוצקין", "רון", missing_since="2026-10-11T00:00:00Z")]
# 1. החדש למעלה — גם ב'לא שולם'/'לא דווח'
ck([r["id"] for r in D.unpaid(D.active_rows(R))] == ["2", "4", "3", "1"], [r["id"] for r in D.unpaid(D.active_rows(R))])
ck([r["id"] for r in D.unreported(D.active_rows(R))] == ["2", "4", "3", "1"], "unreported newest first")
ck([r["id"] for r in D._sort_desc([dict(id="a", deal_date=""), dict(id="b", deal_date="2020-01-01")])] == ["b", "a"], "no date last")
# 2. בורר סניף
ck([r["id"] for r in D.by_branch(R, "bialik")] == ["1", "2", "6"] and D.by_branch(R, "") == R and D.by_branch(R, "xx") == R, "by_branch")
IDX = {"city": {"קרית ביאליק": ["ביאליק", "קרית ביאליק"], "קרית מוצקין": ["מוצקין", "קרית מוצקין"]},
       "nb": {"אפק": {"city": "קרית ביאליק", "aliases": ["אפק", "אפקה", "נאות אפק"]}}, "ambiguous": set()}
ST = [("נעמי שמר 1", "נאות אפק, אפקה", "קרית ביאליק"), ("נעמי שמר 3", "נאות אפק, אפקה", "קרית ביאליק"),
      ("אהוד מנור 1", "אפק", "קרית ביאליק"), ("אהוד מנור 2", "אפק", "קרית ביאליק")]
S = {"T": {"role": "agent", "drole": "agent", "name": "משה כהן", "phone": "500000001"},
     "M": {"role": "admin", "drole": "manager", "name": "מנהל", "phone": "500000002"}}
class SB:
    def enabled(self): return True
    def deal_history_all(self): return R
kk = lambda x: x.replace(" ", "")
G = {"_web_auth": lambda: S.get(request.headers.get("X-Auth-Token", "")), "_canon_key": kk,
     "_scope_keys_phones": lambda role, name, ph, a=None, an=None: ({kk(name)}, set(), False),
     "_etag_wrap": lambda d: jsonify(d), "_canon_agent_name": lambda x: x, "_log_activity": lambda *a, **k: None,
     "_sbdb": SB(), "_nb_alias_idx": lambda: IDX, "_street_nb_rows": lambda: ST}
app = Flask("b"); D._HIST_CACHE["ts"] = 0; D.register(app, G, lambda h: h); c = app.test_client()
M, T = {"X-Auth-Token": "M"}, {"X-Auth-Token": "T"}
st = c.get("/v2/api/deals/history/stats?year=2026&branch=bialik", headers=M).get_json()
ck(st["total"]["n"] == 2 and [b["branch"] for b in st["byBranch"]] == ["bialik"] and st["branch"] == "bialik", st)
ck(c.get("/v2/api/deals/history/stats?year=2026", headers=M).get_json()["total"]["n"] == 4, "all branches")
op = c.get("/v2/api/deals/history/open?kind=unpaid&branch=motzkin", headers=M).get_json()
ck([x["id"] for x in op["results"]] == ["3"], op)
se = c.get("/v2/api/deals/history/search?q=הגפן&branch=bialik", headers=M).get_json()
ck([x["id"] for x in se["results"]] == ["6"], se)
rv = c.get("/v2/api/deals/history/review?branch=motzkin", headers=M).get_json()
ck([x["id"] for x in rv["missing"]] == ["7"], rv)
rv2 = c.get("/v2/api/deals/history/review", headers=M).get_json()
ck([x["id"] for x in rv2["missing"]] == ["7", "6"], ("review newest first", [x["id"] for x in rv2["missing"]]))
cm = c.get("/v2/api/deals/history/comps?q=הגפן&branch=motzkin", headers=M).get_json()
ck([x["address"] for x in cm["results"]] == ["הגפן 4, מוצקין"], cm["results"])
ck(len(c.get("/v2/api/deals/history/comps?q=נעמי שמר&branch=motzkin", headers=T).get_json()["results"]) == 2, "agent: branch ignored")
# 3. סוכן: חיפוש שכונה/רחוב רק בעסקאות שלו
m = c.get("/v2/api/deals/history/mine?q=באפקה", headers=T).get_json()
ck([x["id"] for x in m["results"]] == ["1", "5"] and m["area"] == "אפק · קרית ביאליק" and m["n"] == 2, m)
m2 = c.get("/v2/api/deals/history/mine?q=הגפן", headers=T).get_json()
ck([x["id"] for x in m2["results"]] == ["3"], ("own street only, missing excluded", m2["results"]))
m3 = c.get("/v2/api/deals/history/mine?q=באפקה&year=2025", headers=T).get_json()
ck([x["id"] for x in m3["results"]] == ["5"] and m3["years"] == [2026, 2025], m3)
ck([x["id"] for x in c.get("/v2/api/deals/history/mine", headers=T).get_json()["results"]] == ["3", "1", "5"], "mine unchanged")
R.append(dict(row("8", "kiryat_yam", "2026-01-01", "", "", "קובי חמו"), deal_date="", missing_since="2026-10-12T00:00:00Z"))
D._HIST_CACHE["ts"] = 0
ck("8" not in [x["id"] for x in c.get("/v2/api/deals/history/review", headers=M).get_json()["missing"]], "sum row not in review")
print("OK", n, "checks")
